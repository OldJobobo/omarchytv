import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fork.emulator import Emulator, EmulatorError

CONFIG = {'schema':1, 'name':'test-webos3', 'machine':'pc-i440fx-9.2', 'cpu':'qemu32', 'cpus':2,
          'memoryMiB':1024, 'disk':'disks/test.qcow2', 'baseDisk':'vendor/original.vmdk',
          'baseSha256':'0'*64, 'licenseAccepted':True, 'bind':'127.0.0.1',
          'ports':{'ssh':16622, 'inspector':19998, 'vnc':15901},
          'guestMac':'52:54:00:12:34:56', 'guestUser':'developer', 'sshKey':'keys/emulator-key'}


class EmulatorTests(unittest.TestCase):
    def setUp(self):
        parent = Path(os.environ.get('OTV_TEST_TMP', Path(__file__).resolve().parents[2]/'.local/test-tmp'))
        parent.mkdir(parents=True, exist_ok=True);self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name);self.base = self.root/'.local/emulator';self.base.mkdir(parents=True)
        (self.base/'config.json').write_text(json.dumps(CONFIG));self.emu = Emulator(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_view_uses_visible_local_cursor_without_resizing_guest(self):
        with patch.object(self.emu, 'qmp'), patch('fork.emulator.shutil.which', return_value='/usr/bin/remote-viewer'), patch('fork.emulator.subprocess.run') as run:
            self.emu.view()
        command = run.call_args.args[0]
        self.assertIn('--cursor=local', command)
        self.assertIn('--auto-resize=never', command)
        self.assertEqual(command[-1], 'vnc://127.0.0.1:15901')

    def test_command_has_no_bridge_shares_host_audio_or_writable_vendor_disk(self):
        command = self.emu.command();net = command[command.index('-netdev')+1]
        self.assertIn('restrict=on', net);self.assertIn('hostfwd=tcp:127.0.0.1:', net)
        self.assertNotIn('bridge', net);self.assertNotIn('-fsdev', command);self.assertNotIn('-virtfs', command)
        self.assertIn('none,id=silent', command)
        self.assertIn('format=qcow2', command[command.index('-drive')+1])
        self.assertNotIn('original.vmdk', command[command.index('-drive')+1])
        self.assertNotIn('-daemonize', command,'use setsid before the seccomp spawn-deny filter')

    def test_nonlocal_privileged_duplicate_and_invalid_vnc_config_refused(self):
        for value in ('0.0.0.0', 'tv.example.invalid'):
            c = copy.deepcopy(CONFIG);c['bind'] = value
            with self.assertRaises(EmulatorError):Emulator.validate_config(c)
        for ports in ({'ssh':22,'inspector':19998,'vnc':15901}, {'ssh':16622,'inspector':16622,'vnc':15901}, {'ssh':16622,'inspector':19998,'vnc':2000}):
            c = copy.deepcopy(CONFIG);c['ports'] = ports
            with self.assertRaises(EmulatorError):Emulator.validate_config(c)

    def test_unrelated_pid_is_never_controlled(self):
        self.emu.pidfile.write_text(str(os.getpid()))
        with patch.object(self.emu, 'qmp') as qmp:
            with self.assertRaisesRegex(EmulatorError, 'does not match'):self.emu.stop(force=True)
            qmp.assert_not_called()

    def test_license_required_without_attempting_download_or_start(self):
        self.emu.config['licenseAccepted'] = False
        with patch.object(self.emu, 'owned_pid', return_value=None), patch('fork.emulator.subprocess.run') as run:
            with self.assertRaisesRegex(EmulatorError, 'license acceptance'):self.emu.start()
            run.assert_not_called()

    def test_sdk_retarget_to_another_device_is_blocked_before_ssh(self):
        home = self.base/'home';config = home/'.webos/tv/novacom-devices.json';config.parent.mkdir(parents=True)
        config.write_text(json.dumps([{'name':'otv-webos3','profile':'tv','host':'tv.example.invalid','port':16622,'username':'developer'}]))
        with patch.object(self.emu, 'qmp'), patch('fork.emulator.subprocess.run') as run:
            with self.assertRaisesRegex(EmulatorError, 'not this localhost VM'):self.emu.verify_sdk_target()
            run.assert_not_called()

    def test_livingroom_profile_never_installed_by_emulator_helper(self):
        build = self.root/'.local/builds/test';build.mkdir(parents=True)
        (build/'manifest.json').write_text(json.dumps({'profile':'livingroom'}))
        with patch.object(self.emu, 'sdk') as sdk:
            with self.assertRaisesRegex(EmulatorError, 'dedicated emulator profile'):self.emu.install('.local/builds/test')
            sdk.assert_not_called()

    def test_unsupported_node_stops_before_running_sdk(self):
        node = self.base/'node';node.write_text('fixture');self.emu.config['sdkNode'] = str(node)
        with patch.object(self.emu, 'wait_ready', return_value=self.base/'home'), patch('fork.emulator.subprocess.check_output',return_value='v26.0.0'), patch('fork.emulator.subprocess.run') as run:
            with self.assertRaisesRegex(EmulatorError, 'Node 22'):self.emu.sdk('ares-launch.js', [])
            run.assert_not_called()

    def test_screenshot_cannot_write_outside_ignored_evidence(self):
        with patch.object(self.emu, 'qmp') as qmp:
            with self.assertRaises(EmulatorError):self.emu.screenshot('../outside.png')
            qmp.assert_not_called()

    def test_launch_waits_through_cold_boot_inspector_reset(self):
        with patch.object(self.emu, 'wait_ready'), patch.object(self.emu, 'wait_boot'), patch.object(self.emu, 'app_visible', return_value=True), patch.object(self.emu, 'sdk') as sdk, patch.object(self.emu, 'targets', side_effect=[ConnectionResetError('not ready'), [{'url':'file:///apps/com.omarchytv.home/index.html'}]]), patch('fork.emulator.time.sleep'):
            self.assertIn('launched', self.emu.launch())
            sdk.assert_called_once_with('ares-launch.js', ['com.omarchytv.home'])

    def test_inspector_target_is_not_enough_for_launch_success(self):
        app = [{'url':'file:///apps/com.omarchytv.home/index.html'}]
        with patch.object(self.emu, 'wait_ready'), patch.object(self.emu, 'wait_boot'), patch.object(self.emu, 'sdk'), patch.object(self.emu, 'targets', return_value=app), patch.object(self.emu, 'app_visible', side_effect=[False, True]) as visible, patch('fork.emulator.time.sleep'):
            self.assertIn('visible', self.emu.launch())
            self.assertEqual(visible.call_count, 2)

    def test_sdk_welcome_boot_is_observed_once_per_owned_pid(self):
        welcome = [{'url':'file:///usr/palm/applications/com.webos.app.emulwelcome/index.html'}]
        with patch.object(self.emu, 'owned_pid', return_value=42), patch.object(self.emu, 'targets', side_effect=[[], welcome]) as targets, patch('fork.emulator.time.sleep'):
            self.emu.wait_boot();self.emu.wait_boot()
            self.assertEqual(targets.call_count, 2)
            self.assertEqual(json.loads((self.emu.run/'boot-ready.json').read_text())['pid'], 42)

    def test_inspector_redirects_never_follow_a_nonlocal_target(self):
        with patch.object(self.emu, 'owned_pid', return_value=99), patch('fork.emulator.http.client.HTTPConnection') as client:
            client.return_value.getresponse.return_value.status = 302
            with self.assertRaisesRegex(EmulatorError, 'redirects are refused'):self.emu.targets()
            client.assert_called_once_with('127.0.0.1', CONFIG['ports']['inspector'], timeout=3)
            client.return_value.close.assert_called_once()

    def test_missing_setup_fails_with_actionable_message(self):
        (self.base/'config.json').unlink()
        with self.assertRaisesRegex(EmulatorError, 'not configured'):Emulator(self.root)


if __name__ == '__main__':unittest.main()
