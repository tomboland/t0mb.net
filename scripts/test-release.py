#!/usr/bin/env python3
"""Exercise deployment against a real local Git remote and temporary web root."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

spec = importlib.util.spec_from_file_location('release', Path(__file__).with_name('deploy-release.py'))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    remote, writer, reader, web = [root / n for n in ('remote', 'writer', 'reader', 'web')]
    run('git', 'init', '--bare', '--initial-branch=main', str(remote))
    run('git', 'clone', str(remote), str(writer))
    run('git', '-C', str(writer), 'config', 'user.name', 'Test')
    run('git', '-C', str(writer), 'config', 'user.email', 'test@example.test')
    (writer / 'site').mkdir()

    def publish(content, corrupt=False):
        (writer / 'site/index.html').write_text(content)
        (writer / 'release.json').write_text(json.dumps({'version': 1, 'files': {
            'index.html': 'wrong' if corrupt else hashlib.sha256(content.encode()).hexdigest()}}))
        run('git', '-C', str(writer), 'add', '.')
        run('git', '-C', str(writer), 'commit', '-m', content)
        run('git', '-C', str(writer), 'push', 'origin', 'main')

    publish('first')
    run('git', 'clone', str(remote), str(reader))
    os.setxattr(reader / 'site', 'user.release-test', b'checkout directory attribute')
    os.setxattr(reader / 'site/index.html', 'user.release-test', b'checkout file attribute')
    (web / 'public').mkdir(parents=True)
    (web / 'public/index.html').write_text('legacy')
    release.deploy(reader, web)
    assert (web / 'previous/index.html').read_text() == 'legacy'
    assert (web / 'public/index.html').read_text() == 'first'
    first = (web / 'public').resolve()
    assert 'user.release-test' not in os.listxattr(first)
    assert 'user.release-test' not in os.listxattr(first / 'index.html')
    release.deploy(reader, web)
    publish('second')
    release.deploy(reader, web)
    assert (web / 'previous').resolve() == first
    assert (web / 'public/index.html').read_text() == 'second'
    publish('broken', corrupt=True)
    try:
        release.deploy(reader, web)
    except ValueError:
        pass
    else:
        raise AssertionError('Corrupt release accepted')
    assert (web / 'public/index.html').read_text() == 'second'
    (reader / 'site/extra').write_text('extra')
    try:
        release.verify(reader / 'site', json.loads((reader / 'release.json').read_text()))
    except ValueError:
        pass
    else:
        raise AssertionError('Unexpected file accepted')
print('PASS: initial migration, repeat deployment, release switch, rollback copy, corrupt release rejection')
