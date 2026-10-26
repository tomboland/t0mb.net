"""Edit a staged review before committing its viewing to disk."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import yaml


def metadata(content):
    parts = content.split('---', 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError('Keep the YAML header between --- lines.')
    result = yaml.safe_load(parts[1])
    if not isinstance(result, dict):
        raise ValueError('Review metadata must be a mapping.')
    return result


def validate_review(content, original):
    before, after = metadata(original), metadata(content)
    from cinema_schema import validate
    validate('review', {k: v.isoformat() if hasattr(v, 'isoformat') else v for k, v in after.items()})
    for key in ('id', 'film', 'viewing', 'watched_date', 'rating', 'date'):
        if str(before.get(key)) != str(after.get(key)):
            raise ValueError(f'Keep {key} unchanged; edit viewing details in the viewing form.')
    if not isinstance(after.get('title'), str) or not after['title'].strip():
        raise ValueError('A review title is required.')
    if not isinstance(after.get('spoilers'), bool):
        raise ValueError('spoilers must be true or false.')


def edit_review(content):
    editor = os.environ.get('VISUAL') or os.environ.get('EDITOR')
    if not editor:
        raise ValueError('Set VISUAL or EDITOR to your preferred editor command.')
    fd, filename = tempfile.mkstemp(prefix='cinema-review-', suffix='.md')
    os.close(fd)
    path = Path(filename)
    path.write_text(content)
    while True:
        try:
            result = subprocess.run([*shlex.split(editor), str(path)])
            if result.returncode:
                print(f'Editor failed; draft retained at {path}. Nothing saved to catalogue.')
                return None
            edited = path.read_text()
            if edited == content or not edited.strip():
                print(f'Unchanged or empty review cancelled; draft retained at {path}.')
                return None
            validate_review(edited, content)
        except (ValueError, yaml.YAMLError) as error:
            print(f'{error}\nDraft retained at {path}.')
            if input('Reopen editor? [Y/n] ').strip().lower() not in ('', 'y', 'yes'):
                return None
            continue
        except BaseException:
            print(f'Draft retained at {path}.')
            raise
        print(f'Recovery draft retained at {path}.')
        return edited
