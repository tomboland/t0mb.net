# Film collection

The source of truth is here: `films.json` holds film identities and optional
TMDB references; `viewings.json` holds separate dated viewings; `reviews/*.md`
holds your writing. `directors.json` is a saved TMDB filmography snapshot.
The original matching audit in `data/film-matching/` is historical evidence,
not the live catalogue. Keep this directory backed up with the repository.

## Write the first review

Edit `reviews/the-400-blows-1959.md`. Write below the second `---`, set `date` to
your publication date, and change `draft: true` to `draft: false` when ready.
Drafts are absent from public pages, lists and generated source files.
Ratings, a viewing date, images and spoiler notices are all optional.

Front matter uses one value per line. Quote strings with double quotes;
use `true`/`false` for flags. Keep a review's `id` and film's `slug` stable:
they determine permanent URLs. More than one review can refer to the same film.
Imported reviews retain their dates and original Letterboxd links.
Review filenames use film titles and release years, with dates (and a numeric
suffix if needed) to distinguish repeat reviews. Renaming a file does not change
its permanent URL; the front-matter `id` controls that.

## Feature reviews on the homepage

Add `featured: true` to a review's front matter to feature it on the homepage.
The homepage randomly selects three featured published reviews on each page load.
Without JavaScript, it shows the three newest featured reviews. If fewer than
three are featured, it shows all of them and fills spare places with recent
reviews without duplicates. Drafts never appear,
even if featured. Recent writing, the writing archive and RSS remain chronological.
Remove the field or set `featured: false` to unfeature a review. The flag belongs
to the individual review, so repeat reviews of one film can be selected separately.

## Like films

Set `"liked": true` or `"liked": false` on a film in `films.json`. Film pages
and listings show ♥ for liked films and ♡ for films not marked as liked.
The flag belongs to the film, independently of ratings, reviews and tags;
`favourite` remains a separate, more selective collection. Missing flags show ♡.

The original Letterboxd export stores film likes in `likes/films.csv`.
To backfill older imported records without overwriting any existing flags:

```sh
python3 scripts/import-letterboxd.py /path/to/letterboxd-export.zip --likes-only
```

This matches exact Letterboxd film URLs and reports likes outside the catalogue
without adding those films. Subsequent local changes remain authoritative.

## Tag films

Tags belong to films, independently of ratings and featured reviews. Use any
labels you like; for example, `favourite` creates a collection of favourite films.
From the source checkout:

```sh
python3 scripts/cinema.py tag the-400-blows-1959 favourite "coming of age"
python3 scripts/cinema.py tag the-400-blows-1959 favourite --remove
```

These are examples, not preselected tags. You can also add a `tags` array to a
film record in `cinema/films.json`, such as `"tags": ["favourite", "coming of age"]`.
Spelling is case-insensitive and repeated whitespace is normalised; duplicate
tags count only once per film. Labels retain their display spelling. Tags appear
on film pages and catalogue listings. Each links to its film collection, also
reachable from **Tags** in the film navigation. Tag pages include poster thumbnails.
Removing a tag from its last film removes that tag's generated page.

Commit your changes, then run `bash deploy.sh` to build and publish them.

## Build and preview

From the repository root (using the existing Haskell toolchain):

```sh
export PATH="$HOME/.ghcup/bin:$PATH"
cabal build exe:site
cabal exec site -- build
python3 -m http.server 8000 --directory _site
```

Open `http://localhost:8000/films/`. Hakyll reads the cinema JSON and review
Markdown directly; no API key, separate Pandoc executable or network is needed.
`_site/` is disposable build output: never edit it.

Presentation lives in `templates/cinema/`, relationships and template contexts
in `src/Cinema.hs`, full-review embedding in `src/CinemaRendering.hs`, and routes
in `site.hs`. Shared publishing pages live in `src/Publishing.hs`. Edit the homepage introduction in
`content/home.md` and the cinema information page in `content/films-about.md`.
Python scripts only manage/import source data and artwork. `cabal exec site --
watch` also picks up cinema changes, including new film and tag pages.

Run `python3 scripts/test-cinema.py` after compiling to check cinema rendering
against isolated fixtures, including incremental updates and draft removal.

## Log a film in one step

The local catalogue, diary and Markdown reviews are the source of truth. No
Letterboxd account or export is needed. From the repository root:

```sh
# Diary only; viewing date defaults to today:
python3 scripts/cinema.py log "The Human Condition I: No Greater Love"

# Diary plus a linked Markdown draft (the command prints the file to edit):
python3 scripts/cinema.py log "The Human Condition I: No Greater Love" --review

# Or supply the review now; it will be published on the next build:
python3 scripts/cinema.py log "The Human Condition I: No Greater Love" --review "Your review here."
```

These are alternative commands. Each successful `log` invocation creates one
new viewing, so run just the one that matches what you want to record.

The command reuses an existing film by ID, slug or exact title. Otherwise it
searches TMDB and adds the film implicitly, including director metadata, poster,
thumbnail and backdrop where available. Ambiguous or inexact search results ask
you to choose; noninteractive runs stop and print IDs instead of guessing.
Use `--year 1959` to narrow a title search, or skip search with `--tmdb-id 31217`.

Configure your existing TMDB **API read access token** once in your shell:

```sh
export TMDB_TOKEN_FILE=/path/to/your/existing-tmdb-token
```

Alternatively, store the token at `~/.config/t0mb.net/tmdb-token`, or pass
`--token-file PATH` to a command. Keep credentials outside this repository.
Cached requests can work without a token; uncached TMDB requests need one.

Optional logging flags:

```sh
python3 scripts/cinema.py log --tmdb-id 31217 --date 2026-10-02 --rating 4.5 --review
```

`--date` is the watched date; omit it for today. Ratings are optional, from 0.5
to 5 in half steps. Add `--rewatch` for a repeat viewing. Review publication dates
default to today independently of the watched date and can be edited in Markdown.

With bare `--review`, write in the generated file and set `draft: false` when
ready. With `--review "text"`, the file contains that text and `draft: false`.
Both forms link the review to the new viewing and copy its date and rating.
You can add post tags, spoiler notices and other front matter afterwards.

Existing local metadata, artwork overrides and reviews are preserved. Available
artwork is reused; missing imported files are downloaded. Network work completes
before saving the diary entry, so an artwork download failure can be retried
without creating another viewing. A film with no TMDB artwork remains text-only.
Manually created films without a TMDB reference can still be logged, but cannot
automatically fetch artwork; the command tells you when this applies.

Nothing is committed or deployed automatically. Preview, review the source and
image changes, commit them, then run `bash deploy.sh` as usual. Ordinary Hakyll
builds remain offline.

## Lower-level film, viewing and review commands

These remain available for manual metadata, logging an already-known film, or
creating a review of an existing viewing without adding another diary entry.

```sh
# Without TMDB (repeat --director for co-directors):
python3 scripts/cinema.py film --title "A film" --year 2026 --director "A director"

# Or fetch metadata and the director filmography once, explicitly:
python3 scripts/cinema.py film --tmdb-id 147 --token-file /private/path/tmdb-token

# Use the printed film ID or its slug. The 400 Blows is already present:
python3 scripts/cinema.py watch the-400-blows-1959 --date 2026-10-01
python3 scripts/cinema.py review the-400-blows-1959
```

The TMDB example refuses duplicates, so use the ID of a film not already in
the catalogue. Keep credentials outside the repository. A film's local ID
does not depend on TMDB, so unavailable records and manual films work normally.

`watch` accepts optional `--rating 4.5` and `--rewatch`. Each call creates a
separate viewing, even on the same date. `review` accepts `--viewing VIEWING_ID`
to link to one, copying its date and optional rating. A review need not be
linked to a viewing. Publication date and watched date remain separate.

Films marked watched without dates appear in the catalogue but not the diary.
Diary ratings belong to individual viewings; the optional `rating` in
`films.json` is a separate overall rating imported from Letterboxd. Neither
is automatically substituted for the other. Empty ratings render no score.

## Photographs

Put your photographs in `images/films/`. Add inline Markdown such as:

```md
![Description of the image](/images/films/the-400-blows/example.jpg)
```

For an optional banner, add `image: "/images/films/the-400-blows/example.jpg"`
and `image_alt: "Description"` to a review's front matter (or equivalent JSON
fields on a film). `image_caption` is optional. Images retain their proportions.
New TMDB films added with `log` or `film` import artwork automatically and serve it
locally. To refresh or backfill artwork separately (normal builds stay offline):

```sh
python3 scripts/import-film-images.py --token-file /private/tmdb-token
```

Existing API metadata in `/tmp/t0mb-tmdb-cache` can be reused without a token.
Use `--film the-400-blows-1959` to import just one film. Downloads already present
are reused. Imported choices are saved separately in `cinema/artwork.json`;
image files are in `images/films/tmdb/`. Commit both after importing.

Film pages use a backdrop, falling back to a poster. Small poster thumbnails
appear in the catalogue, diary, review listings and watched director filmographies.
Films without artwork stay text-only. Review bodies keep your own inline photographs.

To override artwork, edit the film record in `cinema/films.json`:

```json
"poster": "/images/films/my-poster.jpg",
"poster_alt": "Description of my poster",
"thumbnail": "/images/films/my-small-poster.jpg",
"image": "/images/films/my-banner.jpg",
"image_alt": "Description of my banner"
```

All paths must refer to existing local files. `thumbnail` is optional and otherwise
uses your overridden poster. `image_caption` is optional. Set `poster` or `image`
to `false` to suppress that artwork; `thumbnail: false` hides listing thumbnails.
Imports never overwrite these fields. An overridden `image` affects only the film
page; review images are managed in their own Markdown.

## Letterboxd and metadata

Write and revise here first, then copy the review to Letterboxd. Add an optional
`letterboxd_url` to its front matter after publishing the copy. This build does
not post to Letterboxd or automatically overwrite your local writing.

`python3 scripts/refresh-directors.py --token-file /private/path/tmdb-token`
explicitly refreshes saved director filmographies; ordinary builds use the
snapshot. Filmography entries outside your watched catalogue appear as muted
text. Watched films without reviews remain muted links to their viewing history.

The initial import excludes Twin Peaks and Diario di una Segretaria. The
misplaced Hobo with a Shotgun review is omitted because its corrected feature
review already exists. The short's watched entry remains, without the feature's
rating or review. Original records remain in the Letterboxd ZIP and matching audit.

## Checks

```sh
python3 scripts/test-film-matching.py
python3 scripts/test-cinema-cli.py
python3 scripts/test-cinema.py
```

## Colours and film palettes

All colour controls live in `css/palette.css`. In browser DevTools, select the
`html` element and edit the `:root` variables to experiment. `--accent` changes
links, ratings and highlights; `--bg`, `--panel`, `--text`, `--secondary`,
`--muted`, `--border` and `--input-border` control the other colours.
`--row-odd`, `--row-even` and `--row-hover` control listing backgrounds; their
defaults follow the base palette. Visible rows alternate even after filtering.
The file includes suggested amber colours to try. DevTools edits are temporary;
copy them into the CSS file and rebuild to keep them.

For a curated film palette, add `"theme": "your-theme"` to that film in
`cinema/films.json`, then define `html[data-film-theme="your-theme"]` in
`css/palette.css` with your colour overrides (a commented example is provided).
Use lowercase letters, digits and hyphens for theme names. Its film page and
all its reviews inherit that palette, including page chrome; catalogue, diary,
director, tag and homepage listings retain the site's default palette.
Omitted colours inherit the default. Removing the film's `theme` field restores
the default, and an undefined theme name also falls back to it. No film palettes
are assigned by default. Check text, muted labels and links against both row
backgrounds when curating a palette.

## Reviews on film pages

Film pages display all published reviews, newest first, with their dates, ratings
and spoiler notices. Each retains a permanent standalone page. Reviews longer
than 220 words get a 100-word preview and a “more…” / “less…” control in browsers
with JavaScript; without JavaScript, every review is shown in full. Drafts are
excluded. The thresholds live in `js/film-reviews.js`.

## Tag your writing

Add `tags: [cinema, photography]` to review front matter to describe the review
itself. These optional post tags link to `/tags/` pages containing matching notes
and published reviews. They also appear on full reviews embedded in film pages.
Draft reviews never contribute to public tag pages. Film collection tags remain
on film records and link to `/films/tags/`; they are not inherited by reviews.
