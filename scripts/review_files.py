"""Readable review filenames, independent of permanent review IDs and URLs."""


def review_path(directory, film_slug, date):
    base = directory / (film_slug + '.md')
    if not base.exists() and not any(directory.glob(film_slug + '-*.md')):
        return base
    dated = directory / (film_slug + '-' + date + '.md')
    number = 2
    while dated.exists():
        dated = directory / (film_slug + '-' + date + '-' + str(number) + '.md')
        number += 1
    return dated
