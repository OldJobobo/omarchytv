"""Small, guarded Git workflow for this fork. Never pushes or contacts a TV."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from build import BuildError, create_build, member
from guard import audit


class WorkflowError(RuntimeError):
    pass


def find_root():
    common = subprocess.check_output(['git', '-C', str(Path(__file__).resolve().parent),
                                      'rev-parse', '--path-format=absolute', '--git-common-dir'], text=True)
    return Path(common.strip()).resolve().parent


class Workflow:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.local = member(self.root, '.local')
        self.local.mkdir(exist_ok=True)
        self.series = json.loads((self.root/'fork/series.json').read_text())
        if self.series.get('schema') != 1:
            raise WorkflowError('Unsupported series schema')

    def git(self, *args, cwd=None, check=True):
        p = subprocess.run(['git', '-C', str(cwd or self.root), *args], text=True, capture_output=True)
        if check and p.returncode:
            raise WorkflowError(p.stderr.strip() or p.stdout.strip() or 'Git failed')
        return p.stdout.strip() if check else p

    def ref(self, name):
        return self.git('rev-parse', '--verify', name+'^{commit}')

    def worktrees(self):
        items = []
        for block in self.git('worktree', 'list', '--porcelain').split('\n\n'):
            data = dict(line.split(' ', 1) for line in block.splitlines() if ' ' in line)
            if 'worktree' in data:
                items.append((data.get('branch', '').removeprefix('refs/heads/'), Path(data['worktree'])))
        return items

    def features(self):
        return self.git('for-each-ref', '--format=%(refname:short)', 'refs/heads/fix/', 'refs/heads/feat/',
                        'refs/heads/test/', 'refs/heads/docs/', 'refs/heads/refactor/').splitlines()

    def clean(self, path):
        if not path.resolve().is_relative_to(self.root):
            raise WorkflowError('A managed branch is checked out outside this checkout; handle it explicitly: '+str(path))
        if self.git('status', '--porcelain', '--untracked-files=all', cwd=path):
            raise WorkflowError('Uncommitted work; nothing will be stashed or reset: '+str(path.relative_to(self.root) or '.'))
        for name in ('MERGE_HEAD', 'REBASE_HEAD', 'CHERRY_PICK_HEAD'):
            if self.git('rev-parse', '--verify', name, cwd=path, check=False).returncode == 0:
                raise WorkflowError('Finish the existing Git operation in '+str(path))

    def preflight(self):
        if self.git('branch', '--show-current') != self.series['workflowBranch']:
            raise WorkflowError('Run from the primary '+self.series['workflowBranch']+' checkout')
        for branch, path in self.worktrees():
            if branch in self.features()+[self.series['workflowBranch'], 'main', self.series['integrationBranch']]:
                self.clean(path)
        if any(branch == 'main' for branch, _ in self.worktrees()):
            raise WorkflowError('Leave main unchecked out; it is an upstream mirror ref')

    def status(self):
        return {'branch':self.git('branch', '--show-current'), 'upstream':self.ref('upstream/main'),
                'main':self.ref('main'), 'features':{b:self.ref(b) for b in self.features()},
                'integration':self.git('rev-parse', '--verify', self.series['integrationBranch'], check=False).stdout.strip() or None,
                'profiles':sorted(p.name for p in (self.local/'profiles').glob('*') if p.is_dir()),
                'dirty':bool(self.git('status', '--porcelain')), 'network':'not contacted'}

    def feature(self, name):
        if not re.fullmatch(r'(?:fix|feat|test|docs|refactor)/[a-z0-9][a-z0-9._-]*', name):
            raise WorkflowError('Use a feature name such as fix/short-description')
        self.ref('upstream/main')
        path = member(self.root, '.local/worktrees/'+name.replace('/', '-'))
        if path.exists() or self.git('show-ref', '--verify', '--quiet', 'refs/heads/'+name, check=False).returncode == 0:
            raise WorkflowError('Feature/worktree already exists; refusing to replace it')
        path.parent.mkdir(parents=True, exist_ok=True)
        self.git('worktree', 'add', '--no-track', '-b', name, str(path), 'upstream/main')
        return path

    def test(self, path, label):
        logs = self.local/'evidence';logs.mkdir(exist_ok=True)
        commands = []
        files = sorted((path/'webos/tests').glob('*.test.js'))
        if files:
            commands.append(['node', '--test', *[str(f.relative_to(path)) for f in files]])
        if (path/'fork/tests').is_dir():
            commands.append([sys.executable, '-m', 'unittest', 'discover', '-s', 'fork/tests', '-v'])
        output = ''
        for cmd in commands:
            p = subprocess.run(cmd, cwd=path, text=True, capture_output=True,
                               env={**os.environ, 'OTV_TEST_TMP':str(self.local/'test-tmp')})
            output += p.stdout+p.stderr
            log = logs/(label.replace('/', '-')+'.log');log.write_text(output)
            if p.returncode:
                raise WorkflowError('Tests failed; see '+str(log.relative_to(self.root)))

    def update(self, apply=False):
        self.preflight()
        refs = [self.series['workflowBranch'], *self.features()]
        if not apply:
            return {'action':'preview', 'branches':refs, 'note':'No network or ref changes. Add --apply to fetch upstream, rebase and test.'}
        for branch, _ in self.worktrees():
            if branch == self.series['integrationBranch']:
                raise WorkflowError('The disposable integration ref is checked out; leave it detached before rebuilding')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        record = {'before':{b:self.ref(b) for b in ['main', *refs]}, 'completed':[]}
        records = self.local/'updates';records.mkdir(exist_ok=True)
        log = records/(stamp+'.json')
        log.write_text(json.dumps(record, indent=2)+'\n')
        self.git('fetch', 'upstream', 'main')
        target = self.ref('upstream/main');record['target'] = target
        if self.git('merge-base', '--is-ancestor', 'main', target, check=False).returncode:
            raise WorkflowError('main contains non-upstream history; refusing to reset it')
        self.git('update-ref', 'refs/heads/main', target, record['before']['main'])
        for branch in refs:
            path = next((p for b, p in self.worktrees() if b == branch), None)
            temporary = path is None
            if temporary:
                path = member(self.root, '.local/rebase/'+branch.replace('/', '-'))
                path.parent.mkdir(parents=True, exist_ok=True)
                self.git('worktree', 'add', str(path), branch)
            result = self.git('rebase', '--no-autostash', '--no-update-refs', 'upstream/main', cwd=path, check=False)
            if result.returncode:
                record['blocked'] = {'branch':branch, 'path':str(path.relative_to(self.root))}
                log.write_text(json.dumps(record, indent=2)+'\n')
                raise WorkflowError('Rebase stopped in '+str(path.relative_to(self.root))+'. Resolve/continue or abort there; no automatic reset. See '+str(log.relative_to(self.root)))
            self.test(path, 'rebase-'+branch)
            record['completed'].append(branch)
            log.write_text(json.dumps(record, indent=2)+'\n')
            if temporary:
                self.git('worktree', 'remove', str(path))
        return {'action':'rebased-and-tested', 'upstream':target, 'record':str(log.relative_to(self.root)),
                'note':'No push. Rebuild livingroom with integrate; review private overlay guards with build.'}

    def integrate(self):
        self.preflight()
        name = self.series['integrationBranch']
        if any(branch == name for branch, _ in self.worktrees()):
            raise WorkflowError('Integration ref is checked out; refusing to move it')
        state_file = self.local/'integration-state.json'
        old = self.git('rev-parse', '--verify', name, check=False).stdout.strip()
        owned = json.loads(state_file.read_text()).get('commit') if state_file.exists() else None
        if old and old != owned:
            raise WorkflowError('Integration ref has unrecorded/user commits; refusing to overwrite it')
        for branch in self.series['features']:
            if self.git('merge-base', '--is-ancestor', 'upstream/main', branch, check=False).returncode:
                raise WorkflowError(branch+' is stale; run update --apply first')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        path = member(self.root, '.local/integrations/'+stamp)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.git('worktree', 'add', '--detach', str(path), self.series['workflowBranch'])
        for branch in self.series['features']:
            result = self.git('merge', '--no-ff', '--no-commit', branch, cwd=path, check=False)
            if result.returncode:
                raise WorkflowError('Integration conflict retained in '+str(path.relative_to(self.root))+'; fix the independent feature, then rebuild')
            if self.git('diff', '--cached', '--quiet', cwd=path, check=False).returncode:
                args = ['commit', '-m', 'Integrate '+branch]
                model = os.environ.get('PI_MODEL')
                if model:
                    owner = self.git('config', '--get', 'fork.owner', check=False).stdout.strip() or 'OldJobobo'
                    args += ['-m', '--[ Pi :: '+model+' ]--\n   --- on behalf of: @'+owner]
                self.git(*args, cwd=path)
        self.test(path, 'integration-'+stamp)
        head = self.git('rev-parse', 'HEAD', cwd=path)
        self.git('update-ref', 'refs/heads/'+name, head, old or '0'*40)
        state = {'branch':name, 'commit':head, 'base':self.ref('upstream/main'),
                 'features':{b:self.ref(b) for b in self.series['features']}, 'tested':True}
        state_file.write_text(json.dumps(state, indent=2)+'\n')
        self.git('worktree', 'remove', str(path))
        return state

    def setup(self):
        if self.git('config', '--get', 'core.hooksPath', check=False).returncode == 0:
            raise WorkflowError('Existing hooksPath: install/review the guard explicitly rather than replacing it')
        common = Path(self.git('rev-parse', '--path-format=absolute', '--git-common-dir'))
        source = self.root/'fork/guard.py';hook = common/'hooks/pre-push'
        if hook.exists() and 'OTV_FORK_GUARD_V1' not in hook.read_text():
            raise WorkflowError('Existing pre-push hook is not owned by this workflow; refusing to replace it')
        hook.parent.mkdir(exist_ok=True);shutil.copyfile(source, hook);hook.chmod(0o755)
        exclude = common/'info/exclude';text = exclude.read_text() if exclude.exists() else ''
        with exclude.open('a') as f:
            for entry in ('/.local/', '/fork/node_modules/'):
                if entry not in text.splitlines():
                    f.write('\n'+entry+'\n')
        for key, value in {'remote.upstream.pushurl':'DISABLED', 'remote.pushDefault':'origin', 'push.default':'simple',
                           'pull.ff':'only', 'rebase.autoStash':'false', 'rebase.updateRefs':'false'}.items():
            self.git('config', key, value)
        return {'guard':'installed', 'upstreamPush':'DISABLED', 'privateData':'.local/ stays ignored across feature checkouts'}


def main():
    parser = argparse.ArgumentParser(description='Source-first fork workflow. No command pushes or deploys to a TV.')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status', help='local refs/profile state; no network').add_argument('--json', action='store_true')
    sub.add_parser('setup', help='install owned local publication guard and safe Git defaults')
    sub.add_parser('feature', help='new independent worktree from upstream/main').add_argument('name')
    sub.add_parser('update', help='preview; --apply fetches, rebases and tests clean branches').add_argument('--apply', action='store_true')
    sub.add_parser('integrate', help='rebuild and test disposable livingroom ref from selected features')
    build = sub.add_parser('build', help='create ignored source/profile app tree, optionally an IPK; never install')
    build.add_argument('--ref', default='livingroom');build.add_argument('--profile', default='livingroom');build.add_argument('--package', action='store_true')
    audit_parser = sub.add_parser('audit-public', help='check all fork-only commits for obvious private artifacts/details')
    audit_parser.add_argument('ref', nargs='?', default='HEAD')
    diff = sub.add_parser('pr-diff', help='review one independent feature against upstream, never integration')
    diff.add_argument('feature')
    args = parser.parse_args()
    try:
        flow = Workflow(find_root())
        if args.command == 'status':
            data = flow.status()
            if not args.json:
                print('Upstream '+data['upstream'][:12]+' · local refs only')
                print('Source '+data['branch']+(' · uncommitted changes' if data['dirty'] else ' · clean'))
                for name, commit in data['features'].items():print('  '+name+'  '+commit[:12])
                print('Profiles '+(', '.join(data['profiles']) or 'none')+' · no TV contacted')
                return
        elif args.command == 'setup':data = flow.setup()
        elif args.command == 'feature':data = {'worktree':str(flow.feature(args.name).relative_to(flow.root)), 'base':'upstream/main', 'note':'Add to fork/series.json only when ready to integrate.'}
        elif args.command == 'update':data = flow.update(args.apply)
        elif args.command == 'integrate':data = flow.integrate()
        elif args.command == 'build':
            out, manifest = create_build(flow.root, args.ref, args.profile, args.package)
            data = {'build':str(out.relative_to(flow.root)), 'state':manifest['state'], **manifest['summary'], 'bytes':manifest['bytes'], 'package':manifest.get('package')}
        elif args.command == 'audit-public':
            errors = audit(flow.root, args.ref)
            if errors:raise WorkflowError('\n'.join(errors))
            data = {'ref':args.ref, 'audit':'passed; still review the diff before publication'}
        elif args.command == 'pr-diff':
            if args.feature not in flow.features():raise WorkflowError('Use an independent feature, not main, workflow or livingroom')
            errors = audit(flow.root, args.feature)
            if errors:raise WorkflowError('\n'.join(errors))
            print(flow.git('diff', '--stat', 'upstream/main...'+args.feature));return
        print(json.dumps(data, indent=2))
    except (WorkflowError, BuildError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print('Stopped: '+str(error), file=sys.stderr);raise SystemExit(1)
