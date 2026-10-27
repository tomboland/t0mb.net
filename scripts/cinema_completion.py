"""Native Carapace specs and offline, read-only completion candidates.

The spec comes from argparse; catalogue values are read afresh on each Tab.
This module's executable interface is private to the generated spec.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import shlex
import sys

from cinema_data import ROOT


def candidates(field, root):
    def read(name, default):
        try:
            return json.loads((root / 'cinema' / (name + '.json')).read_text())
        except (OSError, ValueError):
            return default

    films = read('films', [])
    collection = read('collection', {})
    if field in ('film', 'query', 'tmdb_id'):
        rows = []
        for film in films:
            description = f"{film['title']} ({film.get('year') or '?'})"
            if field == 'tmdb_id':
                value = film.get('tmdb', {}).get('id')
            elif field == 'query':
                value = film['title']
            else:
                value = film.get('slug') or film['id']
            if value is not None:
                rows.append((str(value), description))
        return rows
    if field == 'tags':
        selected = os.environ.get('C_ARG0')
        if os.environ.get('C_FLAG_REMOVE') == 'true':
            films = [f for f in films if selected in (f['id'], f.get('slug'))]
        values = [tag for film in films for tag in film.get('tags', [])]
    elif field == 'director':
        values = [d['name'] for d in read('directors', [])]
        values += [d['name'] for f in films for d in f.get('directors', [])]
    elif field == 'label':
        values = [label['name'] for label in collection.get('labels', [])]
    elif field == 'location':
        values = [copy.get('location', '') for copy in collection.get('copies', [])]
    elif field == 'cut':
        values = [item.get('cut', '') for e in collection.get('editions', []) for item in e.get('contents', [])]
    elif field in ('packaging', 'title'):
        values = [e.get(field, '') for e in collection.get('editions', [])]
    elif field == 'year':
        values = [str(year) for year in range(datetime.date.today().year + 1, 1877, -1)]
    elif field == 'date':
        today = datetime.date.today()
        return [(str(today), 'Today'), (str(today - datetime.timedelta(days=1)), 'Yesterday')]
    else:
        values = []
    return [(value, '') for value in sorted(set(values)) if value]


def spec(parser, root=ROOT):
    """Generate the native spec, retaining descriptions and repeated flags."""
    helper = shlex.join([sys.executable, str(Path(__file__).resolve())])

    def values(action, command):
        if action.choices is not None:
            return [str(value) for value in action.choices]
        if action.type is Path:
            return ['$directories' if action.dest == 'root' else '$files']
        if action.dest == 'rating':
            return [f'{half / 2:g}\t{half / 2:g} stars' for half in range(1, 11)]
        field = action.dest
        if field == 'title' and command == 'film':
            return []  # A new film title is free text.
        if field in {'film', 'query', 'tmdb_id', 'tags', 'director', 'label',
                     'location', 'cut', 'packaging', 'title', 'year', 'date'}:
            # The flag value is read from the environment by Python, never
            # interpolated into shell source (paths may contain shell syntax).
            return [f'$({helper} {field} {shlex.quote(str(root))})']
        return []

    def command_spec(current, name, description):
        node = dict(name=name, description=description, flags={},
                    completion=dict(flag={}, positional=[]))
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                helps = {entry.dest: entry.help for entry in action._choices_actions}
                node['commands'] = [command_spec(child, key, helps[key])
                                    for key, child in action.choices.items()]
                continue
            if action.dest == 'root' and current is not parser:
                continue  # Inherited from the root's persistent flag.
            if action.help == argparse.SUPPRESS:
                continue
            choices = values(action, name)
            if action.option_strings:
                flag = ', '.join(action.option_strings)
                if isinstance(action, argparse._AppendAction):
                    flag += '*'
                if action.nargs != 0:
                    flag += '='
                target = node.setdefault('persistentflags', {}) if action.dest == 'root' else node['flags']
                target[flag] = action.help or action.dest.replace('_', ' ')
                if choices:
                    key = action.option_strings[-1].lstrip('-')
                    node['completion']['flag'][key] = choices
            elif action.nargs in ('+', '*'):
                node['completion']['positionalany'] = choices
            else:
                node['completion']['positional'].append(choices)
        return node

    return command_spec(parser, 'cinema', parser.description)


def main():
    field, default_root = sys.argv[1:]
    root = Path(os.environ.get('C_FLAG_ROOT') or default_root).expanduser()
    # TSV is Carapace's value/description protocol. Keep each candidate on one
    # line even if imported metadata contains control characters.
    clean = lambda value: ' '.join(str(value).split())
    for value, description in candidates(field, root):
        print(clean(value) + '\t' + clean(description))


if __name__ == '__main__':
    main()
