#!/usr/bin/env python3
# OTV_FORK_GUARD_V1
"""Conservative fork publication guard; review is still required before pushing."""
import re
import subprocess
import sys
from pathlib import Path

PRIVATE_IP = re.compile(r'(?<![\w.])(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?![\w.])')
PRIVATE_KEY = re.compile(r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----')
HOME_PATH = re.compile(r'/(?:home|Users)/[A-Za-z0-9_.-]+/')
BINARY = ('.ipk', '.wgt', '.tar.gz', '.png', '.jpg', '.jpeg', '.webp', '.gif')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True)


def audit(root, ref):
    """Scan every fork-only commit, including leaks later removed from the tip."""
    problems = []
    commits = git(root, 'rev-list', 'upstream/main..'+ref).splitlines()
    for commit in commits:
        names = git(root, 'diff-tree', '--root', '--no-commit-id', '--name-only', '-r', '--diff-filter=ACM', commit).splitlines()
        for name in names:
            parts = Path(name).parts
            if '.local' in parts or (parts and parts[0] == 'backup') or name.lower().endswith(BINARY) or re.search(r'(^|/)(?:id_[^/]+|known_hosts[^/]*|[^/]+\.pem)$', name):
                problems.append(commit[:8]+': unpublished/private artifact path '+name)
        diff = git(root, 'show', '--format=', '--no-ext-diff', '--unified=0', commit)
        for line in diff.splitlines():
            if not line.startswith('+') or line.startswith('+++'):
                continue
            if PRIVATE_IP.search(line) or PRIVATE_KEY.search(line) or HOME_PATH.search(line):
                problems.append(commit[:8]+': possible device/host/credential detail in added text (value withheld)')
                break
    return problems


def pre_push(root, remote, url, lines):
    upstream = git(root, 'remote', 'get-url', 'upstream').strip().rstrip('/').removesuffix('.git')
    if remote == 'upstream' or url.rstrip('/').removesuffix('.git') == upstream:
        return ['Direct pushes to upstream are disabled; use a reviewed feature PR.']
    problems = []
    for line in lines:
        fields = line.split()
        if len(fields) != 4:
            return ['Malformed pre-push reference input']
        if set(fields[1]) == {'0'}:
            continue
        problems.extend(audit(root, fields[1]))
    return problems


if __name__ == '__main__':
    try:
        root = Path(git(Path.cwd(), 'rev-parse', '--show-toplevel').strip())
        errors = pre_push(root, sys.argv[1], sys.argv[2], sys.stdin.read().splitlines())
        if errors:
            print('Push blocked:\n  '+'\n  '.join(errors), file=sys.stderr)
            raise SystemExit(1)
    except (OSError, subprocess.CalledProcessError, IndexError) as error:
        print('Push guard could not verify this publication; refusing. '+str(error), file=sys.stderr)
        raise SystemExit(1)
