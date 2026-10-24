"""JSON Schema contracts for local data; reference integrity lives in collection_data."""
import json
from pathlib import Path
from functools import lru_cache
from jsonschema import Draft202012Validator, FormatChecker


@lru_cache(maxsize=None)
def validator(name):
    path = Path(__file__).resolve().parents[1]/'cinema/schemas'/(name+'.schema.json')
    return Draft202012Validator(json.loads(path.read_text()), format_checker=FormatChecker())


def validate(name, value):
    errors = list(validator(name).iter_errors(value))
    if errors:
        error = errors[0]
        path = '.'.join(map(str,error.absolute_path)) or '<root>'
        raise ValueError(f'{name}.{path}: {error.message}')
