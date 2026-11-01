"""Off-device source/profile assembly. No install, SSH, Luna or network client."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
from datetime import datetime, timezone


class BuildError(RuntimeError):
    pass


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def member(root, name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name:
        raise BuildError('Unsafe profile/archive path: ' + name)
    result = root.joinpath(*p.parts)
    if not result.resolve().is_relative_to(root.resolve()):
        raise BuildError('Path escapes its owned directory: ' + name)
    if any(x.is_symlink() for x in [result, *result.parents] if x != root.parent):
        raise BuildError('Symlinked build/profile paths are not supported: ' + name)
    return result


def webp_size(raw):
    if raw[:4] != b'RIFF' or raw[8:12] != b'WEBP':
        raise BuildError('Wallpaper is not a WebP still')
    offset = 12
    size = None
    while offset + 8 <= len(raw):
        kind = raw[offset:offset+4]
        length = int.from_bytes(raw[offset+4:offset+8], 'little')
        data = raw[offset+8:offset+8+length]
        if len(data) != length:
            raise BuildError('Truncated WebP')
        if kind in (b'ANIM', b'ANMF') or (kind == b'VP8X' and data and data[0] & 2):
            raise BuildError('Animated wallpapers are not supported')
        if kind == b'VP8X' and len(data) >= 10:
            size = (1+int.from_bytes(data[4:7], 'little'), 1+int.from_bytes(data[7:10], 'little'))
        elif kind == b'VP8 ' and len(data) >= 10 and data[3:6] == b'\x9d\x01\x2a':
            size = (int.from_bytes(data[6:8], 'little') & 16383, int.from_bytes(data[8:10], 'little') & 16383)
        elif kind == b'VP8L' and len(data) >= 5 and data[0] == 47:
            bits = int.from_bytes(data[1:5], 'little')
            size = (1+(bits & 16383), 1+((bits >> 14) & 16383))
        offset += 8 + length + length % 2
    if not size or not (0 < size[0] <= 1920 and 0 < size[1] <= 1080):
        raise BuildError('Wallpaper must be a bounded still, at most 1920x1080')
    return size


def create_build(root, ref='livingroom', profile_name='livingroom', package=False):
    root = Path(root).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', profile_name):
        raise BuildError('Use a simple local profile name')
    profile_dir = member(root, '.local/profiles/' + profile_name)
    if not (profile_dir/'profile.json').is_file():
        raise BuildError('Missing ignored profile: .local/profiles/' + profile_name)
    if subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'], text=True).strip():
        raise BuildError('Commit or set aside source changes before a reproducible build')
    commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--verify', ref+'^{commit}'], text=True).strip()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = member(root, '.local/builds/'+commit[:12]+'-'+stamp)
    out.mkdir(parents=True)
    app = out/'app'
    archive = subprocess.check_output(['git', '-C', str(root), 'archive', commit, 'webos/app'])
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for entry in tar:
            if not entry.name.startswith('webos/app/'):
                continue
            relative = entry.name[len('webos/app/'):].rstrip('/')
            if not relative:
                continue
            target = member(app, relative)
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif entry.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(entry).read())
                target.chmod(entry.mode & 0o777)
            else:
                raise BuildError('Unsupported archive member: '+entry.name)
    assets = json.loads((profile_dir/'assets.json').read_text())
    for name, expected in assets.items():
        source = member(profile_dir/'assets', name)
        target = member(app, name)
        if sha(source) != expected:
            raise BuildError('Profile asset changed; review and update assets.json: '+name)
        if target.exists() and sha(target) != expected:
            raise BuildError('Asset would mask a changed upstream file: '+name)
        if source.suffix.lower() in ('.mp4', '.webm', '.gif', '.mov'):
            raise BuildError('Video/animated assets are outside this profile contract')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    for name, base_hash in json.loads((profile_dir/'overlay-base.json').read_text()).items():
        target = member(app, name)
        if not target.is_file() or sha(target) != base_hash:
            raise BuildError('Private overlay base changed upstream; review before rebasing: '+name)
        target.write_bytes(member(profile_dir/'overlay', name).read_bytes())
    env = {**os.environ, 'NODE_PATH':str(root/'fork/node_modules')}
    tool = root/'fork/render-profile.cjs'
    result = subprocess.run(['node', str(tool), str(app), str(profile_dir)], text=True, capture_output=True, env=env)
    (out/'render.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        raise BuildError('Profile/ES5 validation failed; see '+str((out/'render.log').relative_to(root)))
    summary = json.loads(result.stdout)
    catalog = json.loads((app/'omarchy_themes.json').read_text())
    dimensions = {}
    for paths in catalog['wallpapers'].values():
        for name in paths:
            image = member(app, name)
            if image.suffix.lower() != '.webp':
                raise BuildError('Wallpaper must be an optimized WebP still: '+name)
            dimensions[name] = webp_size(image.read_bytes())
    html = (app/'index.html').read_text()
    for font in re.findall(r'url\([\'"]?(fonts/[^\'"\)]+)', html):
        if not member(app, font).is_file():
            raise BuildError('Missing font asset: '+font)
    files = {f.relative_to(app).as_posix():sha(f) for f in sorted(app.rglob('*')) if f.is_file()}
    total = sum((app/n).stat().st_size for n in files)
    spec = json.loads((profile_dir/'profile.json').read_text())
    if total > spec.get('maxAppBytes', 6*1024*1024):
        raise BuildError('App exceeds the operator profile byte budget')
    epoch = int(subprocess.check_output(['git', '-C', str(root), 'show', '-s', '--format=%ct', commit], text=True))
    for f in app.rglob('*'):
        os.utime(f, (epoch, epoch))
    manifest = {'schema':1, 'state':'built-not-deployed', 'sourceCommit':commit, 'profile':profile_name,
                'summary':summary, 'bytes':total, 'files':files, 'wallpaperDimensions':dimensions,
                'profileFiles':{f.relative_to(profile_dir).as_posix():sha(f) for f in sorted(profile_dir.rglob('*')) if f.is_file()},
                'toolLockSha256':sha(root/'fork/package-lock.json')}
    if package:
        cli = root/'fork/node_modules/@webos-tools/cli/bin/ares-package.js'
        if not cli.is_file():
            raise BuildError('Run npm ci --prefix fork --ignore-scripts first')
        temp = member(root, '.local/tmp');temp.mkdir(exist_ok=True)
        proc = subprocess.run(['node', str(cli), '--no-minify', str(app), '-o', str(out)],
                              text=True, capture_output=True, env={**env, 'TMPDIR':str(temp)})
        (out/'package.log').write_text(proc.stdout+proc.stderr)
        if proc.returncode:
            raise BuildError('Packaging failed; see '+str((out/'package.log').relative_to(root)))
        packages = list(out.glob('*.ipk'))
        if len(packages) != 1:
            raise BuildError('Expected exactly one generated package')
        manifest['package'] = {'file':packages[0].name, 'sha256':sha(packages[0])}
        if files != {f.relative_to(app).as_posix():sha(f) for f in sorted(app.rglob('*')) if f.is_file()}:
            raise BuildError('The packager changed the validated app tree')
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (root/'.local/latest-build.json').write_text(json.dumps({'path':str(out.relative_to(root)), 'sourceCommit':commit, 'state':'built-not-deployed'}, indent=2)+'\n')
    return out, manifest
