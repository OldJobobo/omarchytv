import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build import BuildError, create_build, member, webp_size
from guard import audit, pre_push
from workflow import Workflow, WorkflowError


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()


class GitWorkflowTests(unittest.TestCase):
    def setUp(self):
        parent = Path(os.environ.get('OTV_TEST_TMP', Path(__file__).resolve().parents[2]/'.local/test-tmp'))
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.base = Path(self.temp.name)
        self.up = self.base/'upstream';self.up.mkdir()
        git(self.up, 'init', '-b', 'main')
        self.identity(self.up)
        (self.up/'base.txt').write_text('base\n');git(self.up, 'add', '.');git(self.up, 'commit', '-m', 'Initial fixture')
        self.root = self.base/'fork'
        subprocess.run(['git', 'clone', '-q', str(self.up), str(self.root)], check=True)
        self.identity(self.root)
        git(self.root, 'remote', 'rename', 'origin', 'upstream')
        git(self.root, 'remote', 'add', 'origin', str(self.base/'publish-target.git'))
        (self.root/'.git/info/exclude').write_text('/.local/\n/fork/node_modules/\n')
        git(self.root, 'checkout', '-b', 'fork/workflow')
        (self.root/'fork').mkdir()
        (self.root/'fork/series.json').write_text(json.dumps({'schema':1, 'workflowBranch':'fork/workflow',
            'integrationBranch':'livingroom', 'features':['fix/example', 'feat/another']}))
        shutil.copyfile(Path(__file__).resolve().parents[1]/'guard.py', self.root/'fork/guard.py')
        git(self.root, 'add', '.');git(self.root, 'commit', '-m', 'Workflow fixture')
        self.flow = Workflow(self.root)
        self.paths = {}
        for name in self.flow.series['features']:
            p = self.flow.feature(name);self.paths[name] = p
            (p/(name.replace('/', '-')+'.txt')).write_text(name+'\n')
            git(p, 'add', '.');git(p, 'commit', '-m', name)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def identity(root):
        git(root, 'config', 'user.name', 'Workflow Test')
        git(root, 'config', 'user.email', 'workflow@example.invalid')
        git(root, 'config', 'commit.gpgsign', 'false')

    def refs(self):
        return {b:self.flow.ref(b) for b in ['main', 'fork/workflow', *self.flow.features()]}

    def test_features_start_at_upstream_without_workflow_files(self):
        for name in self.paths:
            self.assertEqual(git(self.root, 'merge-base', name, 'upstream/main'), self.flow.ref('upstream/main'))
            self.assertEqual(git(self.root, 'ls-tree', name, 'fork/series.json'), '')
        self.assertEqual(self.flow.ref('main'), self.flow.ref('upstream/main'))

    def test_integrate_tests_and_keeps_main_and_feature_refs(self):
        before = self.refs();first = self.flow.integrate()
        self.assertEqual(before, self.refs())
        self.assertTrue(first['tested'])
        for name in self.paths:
            git(self.root, 'merge-base', '--is-ancestor', name, 'livingroom')
        again = self.flow.integrate()
        self.assertEqual(first['features'], again['features'])
        self.assertEqual(before, self.refs())

    def test_integration_never_overwrites_unrecorded_user_ref(self):
        git(self.root, 'branch', 'livingroom', 'main')
        before = self.flow.ref('livingroom')
        with self.assertRaisesRegex(WorkflowError, 'unrecorded/user'):
            self.flow.integrate()
        self.assertEqual(before, self.flow.ref('livingroom'))

    def test_failed_tests_do_not_promote_candidate(self):
        first = self.flow.integrate()
        p = self.root/'webos/tests/fail.test.js';p.parent.mkdir(parents=True)
        p.write_text('throw new Error("expected test failure");\n')
        git(self.root, 'add', '.');git(self.root, 'commit', '-m', 'Failing test fixture')
        with self.assertRaisesRegex(WorkflowError, 'Tests failed'):
            self.flow.integrate()
        self.assertEqual(first['commit'], self.flow.ref('livingroom'))

    def test_dirty_feature_blocks_update_without_stash_or_ref_mutation(self):
        p = self.paths['fix/example'];pending = p/'unfinished.txt';pending.write_text('keep this\n')
        before = self.refs()
        with self.assertRaisesRegex(WorkflowError, 'Uncommitted work'):
            self.flow.update(apply=True)
        self.assertEqual(before, self.refs());self.assertEqual(pending.read_text(), 'keep this\n')

    def test_preview_has_no_network_or_ref_changes(self):
        before = self.refs();data = self.flow.update()
        self.assertEqual(data['action'], 'preview');self.assertEqual(before, self.refs())
        self.assertFalse((self.root/'.local/updates').exists())

    def test_real_fetch_rebases_clean_features_and_preserves_private_profile(self):
        profile = self.root/'.local/profiles/private.json';profile.parent.mkdir(parents=True);profile.write_text('keep private\n')
        old = self.flow.ref('upstream/main')
        (self.up/'base.txt').write_text('upstream advances\n');git(self.up, 'add', '.');git(self.up, 'commit', '-m', 'Upstream advance')
        result = self.flow.update(apply=True)
        self.assertNotEqual(old, result['upstream']);self.assertEqual(self.flow.ref('main'), result['upstream'])
        for name in self.paths:
            git(self.root, 'merge-base', '--is-ancestor', 'upstream/main', name)
        self.assertEqual(profile.read_text(), 'keep private\n')
        self.flow.integrate()

    def test_rebase_conflict_is_retained_without_resetting_feature(self):
        p = self.paths['fix/example']
        (p/'base.txt').write_text('feature edit\n');git(p, 'add', '.');git(p, 'commit', '-m', 'Conflicting feature fixture')
        before = self.flow.ref('fix/example')
        (self.up/'base.txt').write_text('different upstream edit\n');git(self.up, 'add', '.');git(self.up, 'commit', '-m', 'Conflicting upstream fixture')
        with self.assertRaisesRegex(WorkflowError, 'Rebase stopped'):
            self.flow.update(apply=True)
        self.assertEqual(before, self.flow.ref('fix/example'))
        self.assertIn('<<<<<<<', (p/'base.txt').read_text())
        record = json.loads(next((self.root/'.local/updates').glob('*.json')).read_text())
        self.assertEqual(record['blocked']['branch'], 'fix/example')

    def test_publication_guard_scans_leaks_removed_before_tip(self):
        p = self.paths['fix/example'];secret = p/'.local/private.json';secret.parent.mkdir();secret.write_text('{}\n')
        git(p, 'add', '-f', '.local/private.json');git(p, 'commit', '-m', 'Accidental fixture artifact')
        git(p, 'rm', '.local/private.json');git(p, 'commit', '-m', 'Remove accidental artifact')
        self.assertTrue(any('artifact path' in e for e in audit(self.root, 'fix/example')))

    def test_private_detail_and_upstream_push_are_blocked(self):
        p = self.paths['fix/example'];address = '192.'+'168.'+'7.8'
        (p/'device.txt').write_text('device '+address+'\n');git(p, 'add', '.');git(p, 'commit', '-m', 'Private-detail fixture')
        self.assertTrue(any('value withheld' in e for e in audit(self.root, 'fix/example')))
        self.assertTrue(pre_push(self.root, 'upstream', str(self.up), []))
        line = 'refs/heads/fix/example '+self.flow.ref('fix/example')+' refs/heads/fix/example '+'0'*40
        self.assertTrue(pre_push(self.root, 'origin', str(self.base/'publish-target.git'), [line]))

    def test_setup_is_owned_repeatable_and_preserves_other_hooks(self):
        self.flow.setup();self.flow.setup()
        hook = self.root/'.git/hooks/pre-push';self.assertIn('OTV_FORK_GUARD_V1', hook.read_text())
        self.assertEqual(git(self.root, 'remote', 'get-url', '--push', 'upstream'), 'DISABLED')
        hook.write_text('#!/bin/sh\necho user hook\n')
        with self.assertRaisesRegex(WorkflowError, 'not owned'):
            self.flow.setup()
        self.assertIn('user hook', hook.read_text())

    def test_overlay_guard_refuses_to_mask_changed_source(self):
        helper = self.root/'webos/app/rooted/helper.sh';helper.parent.mkdir(parents=True);helper.write_text('# changed upstream\n')
        git(self.root, 'add', '.');git(self.root, 'commit', '-m', 'App fixture')
        profile = self.root/'.local/profiles/test';profile.mkdir(parents=True)
        (profile/'profile.json').write_text('{"schema":1}')
        (profile/'assets.json').write_text('{}')
        (profile/'overlay-base.json').write_text(json.dumps({'rooted/helper.sh':'0'*64}))
        with self.assertRaisesRegex(BuildError, 'overlay base changed'):
            create_build(self.root, 'fork/workflow', 'test')


class BoundedAssetsTests(unittest.TestCase):
    @staticmethod
    def frame(width, height, flags=0):
        data = bytes([flags, 0, 0, 0])+(width-1).to_bytes(3, 'little')+(height-1).to_bytes(3, 'little')
        body = b'WEBPVP8X'+len(data).to_bytes(4, 'little')+data
        return b'RIFF'+len(body).to_bytes(4, 'little')+body

    def test_still_dimensions_and_bounds(self):
        self.assertEqual(webp_size(self.frame(1920, 1080)), (1920, 1080))
        for width, height in [(3840, 2160), (1921, 1080), (1920, 1081)]:
            with self.assertRaisesRegex(BuildError, 'at most'):
                webp_size(self.frame(width, height))

    def test_animation_and_invalid_media_rejected(self):
        with self.assertRaisesRegex(BuildError, 'Animated'):
            webp_size(self.frame(100, 100, 2))
        with self.assertRaises(BuildError):webp_size(b'not an image')
        with self.assertRaises(BuildError):webp_size(self.frame(100, 100)[:-1])

    def test_path_traversal_is_rejected(self):
        for name in ('../outside', '/absolute', 'a/../../outside', 'a\\outside'):
            with self.assertRaises(BuildError):member(Path.cwd(), name)


if __name__ == '__main__':
    unittest.main()
