"""Isolated local LG emulator control. No downloads, system installs or TV targets."""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time

from .build import member


def find_root():
    common = subprocess.check_output(['git', '-C', str(Path(__file__).resolve().parent),
                                      'rev-parse', '--path-format=absolute', '--git-common-dir'], text=True)
    return Path(common.strip()).resolve().parent


APP_ID = 'com.omarchytv.home'


class EmulatorError(RuntimeError):
    pass


class Emulator:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.base = member(self.root, '.local/emulator')
        source = self.base/'config.json'
        if not source.is_file():
            raise EmulatorError('Local emulator is not configured; see fork/EMULATOR.md')
        self.config = json.loads(source.read_text())
        self.validate_config(self.config)
        self.run = member(self.base, 'run');self.run.mkdir(exist_ok=True)
        self.disk = member(self.base, self.config['disk'])
        self.sock = self.run/'qmp.sock'
        self.pidfile = self.run/'vm.pid'

    @staticmethod
    def validate_config(c):
        if c.get('schema') != 1 or c.get('bind') != '127.0.0.1':
            raise EmulatorError('Only a configured localhost VM is supported')
        for name in ('name', 'machine', 'cpu'):
            if not re.fullmatch(r'[a-zA-Z0-9_.-]+', c.get(name, '')):
                raise EmulatorError('Invalid VM '+name)
        ports = [c['ports'][k] for k in ('ssh', 'inspector', 'vnc')]
        if any(type(n) is not int or not 1024 <= n <= 65535 for n in ports) or len(set(ports)) != 3 or c['ports']['vnc'] < 5900:
            raise EmulatorError('Use three distinct unprivileged localhost ports (VNC at least 5900)')
        if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', c.get('guestMac', '')):
            raise EmulatorError('Invalid emulator NIC address')
        if not 512 <= c.get('memoryMiB', 0) <= 4096 or not 1 <= c.get('cpus', 0) <= 4:
            raise EmulatorError('Use 512–4096 MiB RAM and 1–4 vCPUs')
        if c.get('guestUser', 'developer') != 'developer':
            raise EmulatorError('Only the SDK developer account is supported')

    def owned_pid(self):
        if not self.pidfile.exists():
            return None
        pid = int(self.pidfile.read_text())
        proc = Path('/proc')/str(pid)
        if pid <= 1:
            raise EmulatorError('Invalid owned PID record')
        if not proc.exists():
            return None
        if proc.stat().st_uid != os.getuid():
            raise EmulatorError('PID belongs to another user; refusing control')
        raw = (proc/'cmdline').read_bytes()
        if not raw:
            return None
        argv = raw.decode().split('\0')
        if (Path(argv[0]).name != 'qemu-system-x86_64' or '-name' not in argv or
                argv[argv.index('-name')+1].split(',')[0] != self.config['name'] or
                not any(a.startswith('file='+str(self.disk)+',') for a in argv)):
            raise EmulatorError('PID does not match this VM and disk; refusing control')
        net = argv[argv.index('-netdev')+1] if '-netdev' in argv else ''
        vnc = argv[argv.index('-vnc')+1] if '-vnc' in argv else ''
        if 'restrict=on' not in net or any(not x.startswith('hostfwd=tcp:127.0.0.1:') for x in net.split(',') if x.startswith('hostfwd=')) or not vnc.startswith('127.0.0.1:'):
            raise EmulatorError('VM networking is not restricted to localhost; refusing control')
        return pid

    def qmp(self, method, arguments=None):
        if not self.owned_pid():
            raise EmulatorError('Emulator is stopped; run ./fork/emulator start')
        with socket.socket(socket.AF_UNIX) as sock:
            sock.settimeout(20);sock.connect(str(self.sock))
            stream = sock.makefile('rwb');json.loads(stream.readline())
            def call(name, args):
                stream.write((json.dumps({'execute':name, 'arguments':args or {}})+'\n').encode());stream.flush()
                while True:
                    line = stream.readline()
                    if not line:
                        raise EmulatorError('VM control connection closed')
                    message = json.loads(line)
                    if 'error' in message:
                        raise EmulatorError(str(message['error']))
                    if 'return' in message:
                        return message['return']
            call('qmp_capabilities', {})
            if call('query-name', {}).get('name') != self.config['name']:
                raise EmulatorError('Wrong VM control target')
            return call(method, arguments)

    def command(self):
        c = self.config;p = c['ports']
        if ',' in str(self.base):
            raise EmulatorError('QEMU drive paths cannot contain commas')
        return ['qemu-system-x86_64', '-name', c['name']+',process=otv-webos3', '-no-user-config', '-nodefaults',
                '-machine', c['machine']+',accel=kvm', '-cpu', c['cpu'], '-smp', str(c['cpus']), '-m', str(c['memoryMiB']),
                '-drive', 'file='+str(self.disk)+',if=ide,index=0,format=qcow2,cache=writeback',
                '-device', 'VGA,vgamem_mb=32', '-device', 'pcnet,netdev=vmnet,mac='+c['guestMac'],
                '-netdev', 'user,id=vmnet,restrict=on,hostfwd=tcp:127.0.0.1:'+str(p['ssh'])+'-:22,hostfwd=tcp:127.0.0.1:'+str(p['inspector'])+'-:9998',
                '-device', 'piix3-usb-uhci,id=usb', '-device', 'usb-tablet,bus=usb.0',
                '-audiodev', 'none,id=silent', '-device', 'AC97,audiodev=silent',
                '-serial', 'file:'+str(self.run/'serial.log'), '-display', 'none',
                '-vnc', '127.0.0.1:'+str(p['vnc']-5900), '-qmp', 'unix:'+str(self.sock)+',server=on,wait=off',
                '-monitor', 'none', '-sandbox', 'on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny',
                '-rtc', 'base=utc', '-boot', 'order=c,menu=off', '-no-reboot', '-pidfile', str(self.pidfile),
                '-D', str(self.run/'qemu.log')]

    def start(self):
        if self.owned_pid():
            return 'Already running'
        if self.config.get('licenseAccepted') is not True:
            raise EmulatorError('LG SDK license acceptance is required before starting')
        if not os.access('/dev/kvm', os.R_OK | os.W_OK):
            raise EmulatorError('KVM is unavailable; no drivers or system packages will be installed automatically')
        base = member(self.base, self.config['baseDisk'])
        if base.stat().st_mode & 0o222:
            raise EmulatorError('Vendor backing image must be read-only')
        if hashlib.file_digest(base.open('rb'), 'sha256').hexdigest() != self.config['baseSha256']:
            raise EmulatorError('Vendor image hash changed; refusing to boot')
        if not self.disk.is_file():
            raise EmulatorError('Writable overlay missing; restore/create it explicitly, never overwrite a disk')
        for port in [self.config['ports'][k] for k in ('ssh', 'inspector', 'vnc')]:
            with socket.socket() as probe:
                try:probe.bind(('127.0.0.1', port))
                except OSError:raise EmulatorError('Local port already in use: '+str(port))
        if self.pidfile.exists():self.pidfile.unlink()
        if self.sock.exists():
            if not self.sock.is_socket():raise EmulatorError('Unexpected file at the VM socket path')
            self.sock.unlink()
        with (self.run/'stderr.log').open('ab') as log:
            subprocess.run(['setsid', '-f', *self.command()], stdin=subprocess.DEVNULL, stdout=log, stderr=log, check=True)
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            if self.pidfile.exists() and self.sock.exists() and self.owned_pid():
                self.qmp('query-status');return 'Started (headless, local only)'
            time.sleep(.25)
        raise EmulatorError('VM did not start; inspect .local/emulator/run/stderr.log')

    def stop(self, force=False):
        if not self.owned_pid():return 'Already stopped'
        self.qmp('quit' if force else 'system_powerdown')
        deadline = time.monotonic()+20
        while time.monotonic() < deadline:
            if not self.owned_pid():return 'Stopped'
            time.sleep(.25)
        raise EmulatorError('Guest has not shut down; use stop --force to quit only this owned VM')

    def ssh_command(self, args):
        key = member(self.base, self.config['sshKey'])
        known = member(self.base, 'keys/known_hosts')
        if not key.is_file() or not known.is_file():raise EmulatorError('Emulator SSH key/pinned host is missing')
        return ['ssh', '-F', '/dev/null', '-p', str(self.config['ports']['ssh']), '-i', str(key),
                '-o', 'IdentityAgent=none', '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
                '-o', 'PreferredAuthentications=publickey', '-o', 'PasswordAuthentication=no', '-o', 'KbdInteractiveAuthentication=no',
                '-o', 'HostKeyAlgorithms=+ssh-rsa', '-o', 'PubkeyAcceptedAlgorithms=ssh-rsa',
                '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile='+str(known),
                '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'ConnectTimeout=5', '-o', 'LogLevel=ERROR',
                'developer@127.0.0.1', *args]

    def verify_sdk_target(self):
        self.qmp('query-status')
        home = member(self.base, 'home')
        items = json.loads(member(home, '.webos/tv/novacom-devices.json').read_text())
        device = [d for d in items if d.get('name') == 'otv-webos3' and d.get('profile') == 'tv']
        if len(device) != 1 or device[0].get('host') != '127.0.0.1' or int(device[0].get('port', 0)) != self.config['ports']['ssh'] or device[0].get('username') != 'developer' or device[0].get('privateKey', {}).get('openSsh') != Path(self.config['sshKey']).name:
            raise EmulatorError('SDK target is not this localhost VM; refusing any SDK operation')
        subprocess.run(self.ssh_command(['true']), stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=12)
        return home

    def wait_ready(self):
        deadline = time.monotonic()+60
        while time.monotonic() < deadline:
            try:return self.verify_sdk_target()
            except (subprocess.SubprocessError, ConnectionError, TimeoutError):time.sleep(1)
        raise EmulatorError('VM is running but its pinned developer SSH did not become ready')

    def sdk(self, script, args):
        home = self.wait_ready()
        node = Path(self.config['sdkNode'])
        if not node.is_file():raise EmulatorError('Configured SDK Node runtime is missing; use an existing Node 22 runtime')
        version = subprocess.check_output([str(node), '--version'], text=True).strip()
        if not version.startswith('v22.'):
            raise EmulatorError('Use Node 22 for this legacy SDK CLI; the system Node version is not changed')
        cli = self.root/'fork/node_modules/@webos-tools/cli/bin'/script
        env = {**os.environ, 'HOME':str(home), 'APPDATA':str(home), 'USERPROFILE':str(home)}
        result = subprocess.run([str(node), str(cli), '--device', 'otv-webos3', *args], env=env,
                                text=True, capture_output=True, timeout=120)
        log = member(self.base, 'evidence/'+script+'.log');log.write_text(result.stdout+result.stderr)
        if result.returncode:raise EmulatorError('SDK operation failed; see '+str(log.relative_to(self.root)))
        return result.stdout

    def install(self, build=None):
        if build is None:
            build = json.loads(member(self.base, 'evidence/build-result.json').read_text())['build']
        out = member(self.root, build)
        if not out.is_relative_to(self.root/'.local/builds'):
            raise EmulatorError('Use a validated ignored source-build directory')
        manifest = json.loads((out/'manifest.json').read_text())
        if manifest.get('profile') != 'emulator':raise EmulatorError('Use the dedicated emulator profile, not the livingroom profile')
        package = member(out, manifest['package']['file'])
        if hashlib.file_digest(package.open('rb'), 'sha256').hexdigest() != manifest['package']['sha256']:
            raise EmulatorError('Package hash does not match the validated manifest')
        info = json.loads((out/'app/appinfo.json').read_text())
        if info.get('id') != APP_ID or info.get('inspectable') is not True:
            raise EmulatorError('Expected the debuggable emulator-only launcher build')
        if any(t.get('url', '').endswith('/'+APP_ID+'/index.html') for t in self.targets()):
            self.sdk('ares-launch.js', ['--close', APP_ID])
            deadline = time.monotonic()+10
            while time.monotonic() < deadline:
                if not any(t.get('url', '').endswith('/'+APP_ID+'/index.html') for t in self.targets()):break
                time.sleep(.25)
            else:raise EmulatorError('Old VM launcher did not close; package was not installed')
        self.sdk('ares-install.js', [str(package)])
        record = {'target':'isolated localhost VM only', 'appId':APP_ID, 'profile':'emulator', 'build':build,
                  'sourceCommit':manifest['sourceCommit'], 'sha256':manifest['package']['sha256'], 'realTVTouched':False}
        (self.base/'installed.json').write_text(json.dumps(record, indent=2)+'\n')
        return 'Installed in the isolated VM only'

    def launch(self):
        self.sdk('ares-launch.js', [APP_ID])
        deadline = time.monotonic()+20
        while time.monotonic() < deadline:
            try:
                if any(t.get('url', '').endswith('/'+APP_ID+'/index.html') for t in self.targets()):
                    return 'OmarchyTV launched in the VM'
            except (OSError, ValueError, http.client.HTTPException):pass
            time.sleep(.5)
        raise EmulatorError('Launch returned, but the app inspector target was not ready')

    def targets(self):
        if not self.owned_pid():return []
        connection = http.client.HTTPConnection('127.0.0.1', self.config['ports']['inspector'], timeout=3)
        try:
            connection.request('GET', '/json/list');response = connection.getresponse()
            if response.status != 200:raise EmulatorError('VM inspector is not ready; redirects are refused')
            return json.loads(response.read(1024*1024))
        finally:connection.close()

    def screenshot(self, filename=None):
        name = filename or 'vm-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.png'
        if not re.fullmatch(r'[A-Za-z0-9_.-]+\.png', name):raise EmulatorError('Use a simple PNG filename; captures stay in ignored evidence')
        target = member(self.base, 'evidence/'+name);ppm = target.with_suffix('.ppm')
        self.qmp('screendump', {'filename':str(ppm)})
        try:from PIL import Image
        except ImportError:raise EmulatorError('Full PPM saved; Pillow is needed to convert it to PNG')
        with Image.open(ppm) as image:image.save(target)
        return str(target.relative_to(self.root))

    def view(self, fullscreen=False):
        self.qmp('query-status')
        if not shutil.which('remote-viewer'):raise EmulatorError('remote-viewer is not installed; use an existing VNC client on localhost')
        home = member(self.base, 'home')
        env = {**os.environ, 'HOME':str(home), 'XDG_CONFIG_HOME':str(home/'.config'), 'XDG_CACHE_HOME':str(home/'.cache'),
               'XDG_STATE_HOME':str(home/'.state'), 'GSETTINGS_BACKEND':'memory'}
        cmd = ['remote-viewer', '--auto-resize=never', '--zoom=75', '--title=OmarchyTV · webOS 3 emulator']
        if fullscreen:cmd.append('--full-screen')
        cmd.append('vnc://127.0.0.1:'+str(self.config['ports']['vnc']))
        with (self.run/'viewer.log').open('ab') as log:
            subprocess.run(['setsid', '-f', *cmd], env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, check=True)
        return 'Viewer opened (1920×1080 guest; no automatic resize)'


def main():
    parser = argparse.ArgumentParser(description='Local LG webOS 3 VM only. Never contacts the physical TV or installs system software.')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status', help='owned VM, resources and app target').add_argument('--json', action='store_true')
    sub.add_parser('start', help='start isolated headless VM without changing its disk contents outside the overlay')
    sub.add_parser('run', help='start, launch installed OmarchyTV, and open the viewer')
    sub.add_parser('view', help='open existing VM viewer').add_argument('--fullscreen', action='store_true')
    sub.add_parser('stop', help='request guest shutdown; --force quits only the verified owned VM').add_argument('--force', action='store_true')
    sub.add_parser('launch', help='launch OmarchyTV only in the local VM')
    sub.add_parser('install', help='install validated emulator-profile IPK only in the local VM').add_argument('--build')
    sub.add_parser('screenshot', help='save original full guest frame in ignored evidence').add_argument('filename', nargs='?')
    sub.add_parser('key', help='send a key to the VM, never the desktop or TV').add_argument('key', choices=['left','right','up','down','enter','back','escape','home'])
    sub.add_parser('shell', help='pinned SDK developer shell inside the local VM')
    sub.add_parser('smoke', help='real-engine theme/keyboard smoke; refuses an attached viewer')
    args = parser.parse_args()
    try:
        emu = Emulator(find_root())
        if args.command == 'status':
            pid = emu.owned_pid();data = {'running':bool(pid), 'pid':pid, 'memoryMiB':emu.config['memoryMiB'],
                    'cpus':emu.config['cpus'], 'bind':'127.0.0.1', 'restrictedNetwork':True, 'realTVTouched':False}
            if pid:
                data['vmState'] = emu.qmp('query-status')['status']
                data['viewerClients'] = len(emu.qmp('query-vnc').get('clients', []))
                try:data['appTargets'] = [t.get('title') for t in emu.targets()]
                except (OSError, ValueError, http.client.HTTPException):data['appTargets'] = ['inspector not ready']
            if args.json:print(json.dumps(data, indent=2))
            else:
                print('webOS 3 VM: '+('running' if pid else 'stopped'))
                print(str(data['memoryMiB'])+' MiB RAM · '+str(data['cpus'])+' vCPUs · localhost only · no TV contact')
                if pid:print('Apps: '+(', '.join(data['appTargets']) or 'none ready'))
            return
        if args.command == 'start':message = emu.start()
        elif args.command == 'run':
            print(emu.start())
            if (emu.base/'installed.json').exists():print(emu.launch())
            message = emu.view()
        elif args.command == 'view':message = emu.view(args.fullscreen)
        elif args.command == 'stop':message = emu.stop(args.force)
        elif args.command == 'launch':message = emu.launch()
        elif args.command == 'install':
            print('Replacing OmarchyTV in the isolated VM only; its current VM instance will close')
            message = emu.install(args.build)
        elif args.command == 'screenshot':message = 'Captured full VM frame: '+emu.screenshot(args.filename)
        elif args.command == 'key':
            key = {'enter':'ret','back':'backspace','escape':'esc','home':'meta_r'}.get(args.key,args.key)
            emu.qmp('send-key', {'keys':[{'type':'qcode','data':key}], 'hold-time':60});message = 'Sent '+args.key+' to the VM'
        elif args.command == 'shell':
            emu.verify_sdk_target();raise SystemExit(subprocess.call(emu.ssh_command([])))
        elif args.command == 'smoke':
            emu.qmp('query-status')
            if emu.qmp('query-vnc').get('clients'):
                raise EmulatorError('Close the VM viewer before automated input/theme testing')
            raise SystemExit(subprocess.call(['node', str(emu.root/'fork/emulator-smoke.cjs')]))
        else:raise EmulatorError('Unknown emulator command')
        print(message)
    except (EmulatorError, OSError, ValueError, KeyError, subprocess.SubprocessError, RuntimeError) as error:
        print('Stopped: '+str(error), file=sys.stderr);raise SystemExit(1)
