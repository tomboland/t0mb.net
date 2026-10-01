#!/usr/bin/env python3
"""Build locally and publish public files to the release Git repository."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess


def run(*args, cwd=None, capture=False):
    return subprocess.run(args, cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.home() / 'repos/t0mb.net-release')
    parser.add_argument('--allow-dirty', action='store_true', help='Record that the build includes uncommitted source changes')
    parser.add_argument('--no-push', action='store_true', help='Build and commit locally without publishing')
    args = parser.parse_args()
    source = Path(__file__).resolve().parent.parent
    repo = args.repo.resolve()
    os.environ['PATH'] = str(Path.home() / '.ghcup/bin') + ':' + os.environ['PATH']
    gitdir = Path(run('git', 'rev-parse', '--absolute-git-dir', cwd=repo, capture=True).strip())
    with (gitdir / 'publish.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if run('git', 'status', '--porcelain', cwd=repo, capture=True):
            raise SystemExit('Release checkout has uncommitted changes.')
        if run('git', 'branch', '--show-current', cwd=repo, capture=True).strip() != 'main':
            raise SystemExit('Release checkout must be on main.')
        dirty = bool(run('git', 'status', '--porcelain', cwd=source, capture=True))
        if dirty and not args.allow_dirty:
            raise SystemExit('Commit source changes first, or explicitly use --allow-dirty.')
        commit = run('git', 'rev-parse', 'HEAD', cwd=source, capture=True).strip()
        run('git', '-c', 'core.hooksPath=/dev/null', 'pull', '--ff-only', 'origin', 'main', cwd=repo)
        run('cabal', 'build', 'exe:site', cwd=source)
        # Rebuild site output to remove stale pages; compiled dependencies remain cached.
        run('cabal', 'exec', 'site', '--', 'rebuild', cwd=source)
        output = source / '_site'
        if not (output / 'index.html').is_file():
            raise SystemExit('Build did not produce index.html')
        files = {}
        for path in sorted(output.rglob('*')):
            if path.is_symlink():
                raise SystemExit(f'Refusing symlink in output: {path}')
            if path.is_file():
                files[path.relative_to(output).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        if run('git', 'rev-parse', 'HEAD', cwd=source, capture=True).strip() != commit:
            raise SystemExit('Source commit changed during the build; retry.')
        if not dirty and run('git', 'status', '--porcelain', cwd=source, capture=True):
            raise SystemExit('Source files changed during the build; commit them and retry.')
        if (repo / 'site').is_symlink():
            raise SystemExit('Release site directory must not be a symlink.')
        run('rsync', '-a', '--delete', str(output) + '/', str(repo / 'site') + '/')
        manifest = {'version': 1, 'source_commit': commit, 'source_dirty': dirty, 'files': files}
        (repo / 'release.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        run('git', 'add', '--', 'site', 'release.json', cwd=repo)
        if run('git', 'diff', '--cached', '--name-only', cwd=repo, capture=True):
            run('git', 'commit', '-m', f'Publish site from {commit[:12]}' + (' (uncommitted changes)' if dirty else ''), cwd=repo)
        if not args.no_push:
            run('git', 'push', 'origin', 'main', cwd=repo)
        print('Release prepared' if args.no_push else 'Release published; servers will pick it up on their next timer run.')


if __name__ == '__main__':
    main()
