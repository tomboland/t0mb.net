#!/usr/bin/env python3
"""Pull and validate a built release, then switch the public symlink."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import time


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), '-c', 'core.hooksPath=/dev/null', *args], text=True).strip()


def verify(site, manifest):
    if site.is_symlink() or not site.is_dir():
        raise ValueError('Release site must be a real directory')
    if manifest.get('version') != 1 or not isinstance(manifest.get('files'), dict):
        raise ValueError('Unsupported release manifest')
    files = manifest['files']
    if 'index.html' not in files or not files:
        raise ValueError('Release must contain index.html')
    actual = set()
    for p in site.rglob('*'):
        if p.is_symlink():
            raise ValueError('Symlinks are not allowed in releases')
        if p.is_file():
            actual.add(p.relative_to(site).as_posix())
    if actual != set(files):
        raise ValueError('Release file list does not match manifest')
    for name, digest in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name:
            raise ValueError('Unsafe release path')
        if hashlib.sha256((site / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Release checksum mismatch: {name}')


def link(target, dest):
    temporary = dest.with_name('.' + dest.name + '.next')
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(temporary, dest)


def deploy(repo, root):
    if git(repo, 'status', '--porcelain'):
        raise ValueError('Deployment checkout has local changes')
    if git(repo, 'branch', '--show-current') != 'main':
        raise ValueError('Deployment checkout must be on main')
    git(repo, 'pull', '--ff-only', 'origin', 'main')
    commit = git(repo, 'rev-parse', 'HEAD')
    manifest = json.loads((repo / 'release.json').read_text())
    verify(repo / 'site', manifest)
    releases = root / 'releases'
    releases.mkdir(exist_ok=True)
    destination = releases / commit
    public = root / 'public'
    if public.is_symlink() and public.resolve() == destination:
        verify(destination, manifest)
        print(f'Already deployed: {commit}')
        return
    if not destination.exists():
        with tempfile.TemporaryDirectory(prefix='.release-', dir=releases) as tmp:
            staged = Path(tmp) / 'site'
            shutil.copytree(repo / 'site', staged)
            for p in staged.rglob('*'):
                p.chmod(0o755 if p.is_dir() else 0o644)
            staged.chmod(0o755)
            verify(staged, manifest)
            staged.rename(destination)
    else:
        verify(destination, manifest)
    previous = None
    if public.is_symlink():
        previous = os.readlink(public)
    elif public.exists():
        # One-time directory migration; preserve the old site and restore it on failure.
        legacy = releases / ('legacy-' + str(time.time_ns()))
        public.rename(legacy)
        previous = str(legacy.relative_to(root))
    try:
        link(str(destination.relative_to(root)), public)
    except Exception:
        if previous and not public.exists():
            link(previous, public)
        raise
    if previous:
        link(previous, root / 'previous')
    print(f'Deployed: {commit}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', required=True, type=Path)
    p.add_argument('--root', required=True, type=Path)
    args = p.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    with (args.root / '.deploy.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        deploy(args.repo.resolve(), args.root.resolve())


if __name__ == '__main__':
    main()
