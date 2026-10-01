#!/usr/bin/env python3
"""Build Hakyll inputs from local cinema records. No network or third-party packages."""
import collections
import datetime
import html
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parent.parent


def esc(value):
    return html.escape(str(value), quote=True)


def slug(value):
    text = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
    return re.sub('[^a-z0-9]+', '-', text).strip('-')


def read_review(path):
    text = path.read_text(encoding='utf-8')
    if not text.startswith('---\n') or '\n---\n' not in text[4:]:
        raise ValueError(f'{path}: expected front matter')
    header, body = text[4:].split('\n---\n', 1)
    meta = {}
    for line in header.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        key, value = line.split(':', 1)
        try:
            meta[key] = json.loads(value.strip())
        except json.JSONDecodeError:
            meta[key] = value.strip()
    return meta, body.strip()


def rating(value):
    if value in (None, ''):
        return ''
    number = float(value)
    if not 0.5 <= number <= 5 or number * 2 != int(number * 2):
        raise ValueError(f'Invalid rating: {value}')
    return f'<span class="rating" aria-label="{number:g} out of 5">{number:g}/5</span>'


def film_url(film):
    return '/films/' + film['slug'] + '/'


def director_url(person):
    return '/directors/' + slug(person['name']) + '-' + str(person['id']) + '/'


def anchor(url, label, css=''):
    return f'<a href="{esc(url)}"' + (f' class="{css}"' if css else '') + f'>{esc(label)}</a>'


def directors(film):
    return ', '.join(anchor(director_url(p), p['name']) for p in film.get('directors', []))


def image_markup(record):
    if not record.get('image'):
        return ''
    path = record['image']
    if not path.startswith('/images/') or '..' in Path(path).parts or not (ROOT / path.lstrip('/')).is_file():
        raise ValueError(f'Image must be an existing local /images/ file: {path}')
    if not record.get('image_alt'):
        raise ValueError('Images require image_alt text')
    caption = '<figcaption>' + esc(record['image_caption']) + '</figcaption>' if record.get('image_caption') else ''
    return f'<figure class="film-image"><img src="{esc(path)}" alt="{esc(record["image_alt"])}" loading="lazy">{caption}</figure>'


def load_content(root=ROOT):
    data = root / 'cinema'
    films = json.loads((data / 'films.json').read_text())
    viewings = json.loads((data / 'viewings.json').read_text())
    people = json.loads((data / 'directors.json').read_text())
    ids, slugs = set(), set()
    for film in films:
        if film['id'] in ids or film['slug'] in slugs:
            raise ValueError('Duplicate film ID or slug')
        if not re.fullmatch('[a-z0-9-]+', film['slug']):
            raise ValueError('Film slug must contain lowercase letters, numbers and hyphens')
        ids.add(film['id']); slugs.add(film['slug'])
        rating(film.get('rating'))
    viewing_ids = set()
    viewing_films = {}
    for viewing in viewings:
        if viewing['film'] not in ids or viewing['id'] in viewing_ids:
            raise ValueError('Invalid viewing film or duplicate viewing ID')
        viewing_ids.add(viewing['id'])
        viewing_films[viewing['id']] = viewing['film']
        datetime.date.fromisoformat(viewing['date'])
        rating(viewing.get('rating'))
    reviews, review_ids = [], set()
    for path in sorted((data / 'reviews').glob('*.md')):
        meta, body = read_review(path)
        if meta['film'] not in ids or meta['id'] in review_ids or not re.fullmatch('[A-Za-z0-9-]+', meta['id']):
            raise ValueError(f'Invalid review film or duplicate/unsafe ID: {path}')
        review_ids.add(meta['id'])
        if meta.get('viewing') and viewing_films.get(meta['viewing']) != meta['film']:
            raise ValueError(f'Review viewing does not belong to its film: {path}')
        if not isinstance(meta.get('draft', True), bool):
            raise ValueError(f'draft must be true or false: {path}')
        datetime.date.fromisoformat(meta['date'])
        if meta.get('watched_date'):
            datetime.date.fromisoformat(meta['watched_date'])
        rating(meta.get('rating'))
        if not meta.get('draft', True):
            if not re.sub(r'<!--.*?-->', '', body, flags=re.S).strip():
                raise ValueError(f'Published review has no text: {path}')
            reviews.append(dict(meta, body=body))
    return films, viewings, people, reviews


def build(root=ROOT):
    films, viewings, people, reviews = load_content(root)
    by_id = {f['id']: f for f in films}
    by_tmdb = {(f['tmdb']['type'], f['tmdb']['id']): f for f in films if f.get('tmdb')}
    by_film = collections.defaultdict(list)
    watches = collections.defaultdict(list)
    for viewing in sorted(viewings, key=lambda v: (v['date'], v['id']), reverse=True):
        watches[viewing['film']].append(viewing)
    for review in sorted(reviews, key=lambda r: (r['date'], r['id']), reverse=True):
        review['url'] = film_url(by_id[review['film']]) + 'reviews/' + review['id'] + '/'
        by_film[review['film']].append(review)
    known_people = {str(p['id']): p for p in people}
    for film in films:
        for person in film.get('directors', []):
            known_people.setdefault(str(person['id']), dict(person, filmography=[]))
    pages = {}
    def page(url, title, body):
        path = 'generated' + url + 'index.md'
        pages[path] = '---\ntitle: ' + json.dumps(title, ensure_ascii=False) + '\n---\n\n' + body + '\n'
    def review_list(items):
        return '<ul class="review-list">' + ''.join('<li><time datetime="' + r['date'] + '">' + r['date'] + '</time> ' + anchor(r['url'], r['title']) + ' ' + rating(r.get('rating')) + '</li>' for r in items) + '</ul>'
    def film_row(film):
        count = len(by_film[film['id']])
        status = f'{count} review' + ('s' if count != 1 else '') if count else 'no review'
        return f'<tr data-reviewed="{str(bool(count)).lower()}"><td>{anchor(film_url(film), film["title"], "reviewed" if count else "unreviewed")}</td><td>{esc(film["year"])}</td><td>{directors(film)}</td><td class="muted">{status}</td></tr>'
    def table(rows, columns):
        return '<div class="table-scroll"><table><thead><tr>' + ''.join('<th scope="col">' + c + '</th>' for c in columns) + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
    latest = sorted(reviews, key=lambda r: (r['date'], r['id']), reverse=True)
    intro = f'<h1>Films</h1><p>My viewing history, reviews and longer thoughts on films.</p><p class="muted">{len(films)} titles · {len(viewings)} logged viewings · {len(reviews)} reviews</p>'
    filters = '<div class="film-filters" hidden><label>Find a film <input type="search" id="film-search" placeholder="Title, year or director"></label><label><input type="checkbox" id="reviewed-only"> With a review</label><p id="filter-count" role="status" aria-live="polite"></p></div>'
    page('/films/', 'Films', intro + '<h2>Recent writing</h2>' + review_list(latest[:8]) + '<p>' + anchor('/films/reviews/', 'All reviews') + '</p><h2 id="catalogue">Watched catalogue</h2>' + filters + '<div id="film-catalogue">' + table([film_row(f) for f in sorted(films, key=lambda f: (f['title'].casefold(), f['year']))], ['Film', 'Year', 'Director', 'Writing']) + '</div>\n<script src="/js/films.js" defer></script>')
    page('/films/reviews/', 'Film reviews', '<h1>Reviews and analysis</h1>' + review_list(latest))

    def diary_rows(items):
        rows = []
        for v in items:
            film = by_id[v['film']]
            related = [r for r in by_film[v['film']] if
                       (v.get('letterboxd_url') and r.get('letterboxd_url') == v['letterboxd_url'])
                       or r.get('viewing') == v['id']]
            links = ' · '.join(anchor(r['url'], 'Review') for r in related)
            rewatch = '<span class="muted">rewatch</span>' if v.get('rewatch') else ''
            rows.append(f'<tr><td><time datetime="{v["date"]}">{v["date"]}</time></td><td>{anchor(film_url(film), film["title"])} <span class="muted">({esc(film["year"])})</span></td><td>{rating(v.get("rating"))}</td><td>{rewatch} {links}</td></tr>')
        return table(rows, ['Watched', 'Film', 'Rating', 'Notes'])
    years = sorted({v['date'][:4] for v in viewings}, reverse=True)
    diary = '<h1>Film diary</h1><p>Newest viewings first. Ratings appear only when I gave one.</p><nav aria-label="Diary years" class="year-nav">' + ' · '.join(anchor('#year-' + y, y) for y in years) + '</nav>'
    for year in years:
        diary += f'<h2 id="year-{year}">{year}</h2>' + diary_rows(sorted([v for v in viewings if v['date'].startswith(year)], key=lambda v: (v['date'], v['id']), reverse=True))
    page('/films/diary/', 'Film diary', diary)

    for film in films:
        own_reviews = by_film[film['id']]
        body = image_markup(film) + '<h1>' + esc(film['title']) + ' <span class="muted">(' + esc(film['year']) + ')</span></h1>'
        body += '<p class="film-meta">' + directors(film) + (' · ' + str(film['runtime']) + ' minutes' if film.get('runtime') else '') + '</p>'
        if film.get('original_title') and film['original_title'] != film['title']:
            body += '<p class="muted">' + esc(film['original_title']) + '</p>'
        body += '<h2>Writing</h2>' + (review_list(own_reviews) if own_reviews else '<p class="muted">Watched; no review yet.</p>')
        body += '<h2>Viewing history</h2>' + (diary_rows(watches[film['id']]) if watches[film['id']] else '<p class="muted">Watched, date not recorded.</p>')
        if film.get('rating'):
            body += '<p>Film rating: ' + rating(film['rating']) + '</p>'
        if film.get('tmdb'):
            tmdb = film['tmdb']
            body += '<p>' + anchor(f'https://www.themoviedb.org/{tmdb["type"]}/{tmdb["id"]}', 'Film details on TMDB') + '</p>'
        page(film_url(film), film['title'] + ' (' + film['year'] + ')', body)
        for review in own_reviews:
            head = '<p>' + anchor(film_url(film), film['title'] + ' (' + film['year'] + ')') + '</p>'
            head += image_markup(review) + '<h1>' + esc(review['title']) + '</h1><p class="film-meta">Published <time datetime="' + review['date'] + '">' + review['date'] + '</time>'
            if review.get('watched_date'):
                head += ' · Watched ' + esc(review['watched_date'])
            head += ' ' + rating(review.get('rating')) + '</p>'
            if review.get('spoilers'):
                head += '<p class="spoiler-notice">Contains spoilers.</p>'
            footer = '<hr><p>' + anchor(film_url(film), 'Film details and viewing history') + '</p>'
            others = [r for r in own_reviews if r['id'] != review['id']]
            if others:
                footer += '<h2>More of my writing on this film</h2>' + review_list(others)
            if review.get('letterboxd_url'):
                footer += '<p>' + anchor(review['letterboxd_url'], 'Also on Letterboxd') + '</p>'
            page(review['url'], review['title'], head + '\n\n' + review['body'] + '\n\n' + footer)

    listing = '<h1>Directors</h1><ul class="director-list">'
    for person in sorted(known_people.values(), key=lambda p: p['name'].casefold()):
        own = [f for f in films if any(str(d['id']) == str(person['id']) for d in f.get('directors', []))]
        if not own:
            continue
        listing += '<li>' + anchor(director_url(person), person['name']) + f' <span class="muted">{len(own)} watched</span></li>'
        entries = []
        included = set()
        for credit in person.get('filmography', []):
            film = by_tmdb.get(('movie', credit['tmdb_id']))
            if film:
                included.add(film['id'])
                label = anchor(film_url(film), film['title'], 'reviewed' if by_film[film['id']] else 'unreviewed')
                status = 'reviewed' if by_film[film['id']] else 'watched · no review'
                year = film['year']
            else:
                label = '<span class="muted">' + esc(credit['title']) + '</span>'
                status, year = 'not watched', credit['year']
            entries.append((year, credit['title'], f'<tr><td>{esc(year)}</td><td>{label}</td><td class="muted">{status}</td></tr>'))
        for film in own:
            if film['id'] not in included:
                status = 'reviewed' if by_film[film['id']] else 'watched · no review'
                entries.append((film['year'], film['title'], f'<tr><td>{esc(film["year"])}</td><td>{anchor(film_url(film), film["title"], "reviewed" if by_film[film["id"]] else "unreviewed")}</td><td class="muted">{status}</td></tr>'))
        body = '<h1>' + esc(person['name']) + f'</h1><p>{len(own)} watched · ' + str(sum(bool(by_film[f['id']]) for f in own)) + ' reviewed</p><h2>Directing filmography</h2><p class="muted">Reviewed films are highlighted. Unreviewed watched films still link to their viewing history.</p>'
        body += table([e[2] for e in sorted(entries, key=lambda e: (e[0] or '9999', e[1]))], ['Year', 'Film', 'Status'])
        page(director_url(person), person['name'], body)
    page('/directors/', 'Directors', listing + '</ul>')
    page('/films/about/', 'About the film collection', '<h1>About this collection</h1><p>My viewing history and writing, originally imported from Letterboxd. A viewing does not need a rating or a review. Some older watched films have no recorded viewing date.</p><h2>Credits</h2><p>Film metadata and directing filmographies are supplied by <a href="https://www.themoviedb.org">TMDB</a> and saved locally. Titles and years may reflect my original records.</p><a href="https://www.themoviedb.org"><img class="tmdb-logo" src="/images/tmdb.svg" alt="TMDB"></a><p>This product uses the TMDB API but is not endorsed or certified by TMDB.</p>')
    output = root / 'generated'
    output.mkdir(exist_ok=True)
    for name, content in pages.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text() != content:
            path.write_text(content, encoding='utf-8')
    for path in output.rglob('*.md'):
        if str(path.relative_to(root)) not in pages:
            path.unlink()
    # Hakyll does not remove obsolete outputs on incremental builds. Also
    # remove unpublished pages when generated/ was deleted between builds.
    for section in ('films', 'directors'):
        for published in (root / '_site' / section).rglob('*.html'):
            source = 'generated/' + str(published.relative_to(root / '_site').with_suffix('.md'))
            if source not in pages:
                published.unlink()
    print(f'Prepared {len(pages)} film-section pages ({len(reviews)} published reviews).')
    return pages


if __name__ == '__main__':
    build()
