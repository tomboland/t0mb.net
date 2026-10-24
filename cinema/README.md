# Film collection

The source of truth is here: `films.json` holds film identities and optional
TMDB references; `viewings.json` holds separate dated viewings; `reviews/*.md`
holds your writing. `directors.json` is a saved TMDB filmography snapshot.
`entries.json` preserves non-viewing diary notes; reviews can link to these without
inventing watched events. Keep this directory backed up with the repository.

## Physical collection and everyday tools

Start with the [everyday command guide](../scripts/README.md). The main entry
point is `cinema.py`: `add` records metadata, `own` records a physical release,
`seen` marks watched with an unknown date, and `log` records a dated viewing.
The dedicated terminal application and commands share a service layer; see the command guide for current controls.

See [the collection model and commands](COLLECTION.md) for editions, box sets,
owned copies and links to canonical films. The website reads these sources directly.

| Tool | Purpose |
|---|---|
| `scripts/cinema.py` | Search/add films, log viewings, write reviews and manage film tags |
| `scripts/collection.py` | Add/edit editions and copies referencing canonical films; export the collection |
| `scripts/validate-cinema.py` | Check identities and relationships across the live data |
| `scripts/count-collection.py` | Count physical films separately from packages and TV series |
| `scripts/refresh-artwork.py` | Fetch missing artwork |
| `scripts/refresh-directors.py` | Refresh saved director filmographies |
| `scripts/export-cinema.py` | Export personal history or compact public recommendation data |

Initial import/reconciliation tooling and evidence are retained in Git at
`3803b1d`, not in the working tree. Daily tools need no import files or photographs.

Edition contents, viewings and reviews share the canonical film IDs directly.
Omit unrecorded optional fields rather than filling them with nulls or empty lists.
The small `collection-redirects.json` map preserves old URLs only.

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

Pass `--liked` when logging a viewing to mark the film as liked:

```sh
python3 scripts/cinema.py log "Don't Look Now" --year 1973 --liked --review
```

This also works with `review`. Omitting `--liked` preserves the existing like
status. Likes belong to the film, not the individual viewing.

Set `"liked": true` or `"liked": false` on a film in `films.json`. Film pages
and listings show ♥ for liked films and ♡ for films not marked as liked.
The flag belongs to the film, independently of ratings, reviews and tags;
`favourite` remains a separate, more selective collection. Missing flags show ♡.

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
The build also runs the public exporter using Python 3 and PyYAML (`python3-yaml`
on Debian/Ubuntu). No tokenizer package is required for builds.
`_site/` is disposable build output: never edit it.

Presentation lives in `templates/cinema/`, relationships and template contexts
in `src/Cinema.hs`, full-review embedding in `src/CinemaRendering.hs`, and routes
in `site.hs`. Shared publishing pages live in `src/Publishing.hs`. Edit the homepage introduction in
`content/home.md` and the cinema information page in `content/films-about.md`.
Python scripts only manage source data and artwork. `cabal exec site --
watch` also picks up cinema changes, including new film and tag pages.

Run `python3 scripts/test-cinema.py` after compiling to check cinema rendering
against isolated fixtures, including incremental updates and draft removal.

## Interactive authoring

The [cinema application guide](../scripts/README.md) documents local browsing,
TMDB selection, disc entry and editor-based reviews. Run
`python3 scripts/cinema.py` to browse, or
`python3 scripts/cinema.py search whiplash` to find a film and choose an action.

`python3 scripts/cinema.py review whiplash` records a viewing and opens your
`VISUAL`/`EDITOR` with a populated draft. Saving an unchanged draft cancels;
successful edits are validated before the viewing is saved. Reviews stay drafts
until you publish them. The former `watch` command is now `log`; TMDB metadata
imports use `add --tmdb-id ID`, while `film` creates manual records.


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
python3 scripts/refresh-artwork.py --token-file /private/tmdb-token
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

## Public LLM data — automatic on every build

The normal build/publish workflow creates **`/films/data/`**. Nothing needs to be
exported or uploaded manually. The film navigation includes a Data link.

| File | Contents |
|---|---|
| `taste.txt` | All catalogue titles, directors, ratings, likes, tags, viewing status, ownership and dated viewings |
| `reviews.txt` | Full published review Markdown, with explicit film/viewing/non-viewing-note associations |
| `editions.txt` | Optional owned release titles, labels, imprints, formats, cuts and coverage |
| `manifest.json` | Revision, timestamp, counts, sizes, checksums and fallback-part URLs |
| `links-index.json` | Small index of reference-to-webpage groups; fetch only the films you need to cite |

Each of the three text sections also has a JSON alternative. Fetch text **or**
JSON, not both. JSON tables declare their columns once. The short numeric film
references are export-local; they never replace permanent source IDs. Never mix
sections from different revisions.

For normal recommendations, load taste/history and full reviews. Ownership flags
are already included, so edition details are only needed for release-specific
questions. If a tool truncates a file, use its `fallback_parts` listed in the
manifest instead. These smaller files preserve all records and full review prose.
Every text file includes final counts/revision markers to help detect truncation.

Copy the reusable instruction from `/films/data/` into the LLM's system prompt.
It needs web-fetching capability. Freshness means the latest **deployed snapshot**,
not unpublished edits or data held in an LLM's previous conversation/cache.
Check the manifest/revision when starting a new conversation. The exporter cannot
force a third-party browsing system to refresh its own cache.

Public fields are explicitly selected: no drafts, source paths, internal audit
metadata, copy notes, storage locations or acquisition details. Non-viewing notes
contribute dates/references only, not private note prose. Reviews remain exact
Markdown; ratings are not inferred or summarised. Old fallback parts are removed
when rebuilding after reviews are unpublished.

To inspect the same output locally without building the site:

```sh
python3 scripts/export-cinema.py --public
```

This writes ignored `generated/cinema-public/` files. It does not deploy anything.
Rendering lives in the shared `scripts/cinema_export.py` module. The Hakyll build
calls the existing export CLI and publishes its output with the normal pages.

## Export viewing history for an LLM

Run `python3 scripts/export-cinema.py` to create
`generated/cinema-export/film-context.txt` and `film-context.json`. Attach the
text file to another LLM for a self-contained account of your watched films,
likes, favourites, ratings, dated viewings and full review text. The JSON file
contains the same evidence in structured form; you only need to send one.
Both include interpretation guidance and collection counts.

The export uses current local sources and runs offline. It preserves separate
film, viewing and review ratings, repeated viewings and original review metadata.
Unfinished drafts are excluded unless you pass `--include-drafts`. Image links
remain in review text, but image files are not bundled. Generated exports are
ignored by Git; regenerate them after updating the collection. Use
`--output-dir PATH` to save elsewhere.

## Checks

```sh
python3 scripts/validate-cinema.py
python3 scripts/test-collection.py
python3 scripts/test-cinema-relations.py
python3 scripts/test-cinema-export.py
python3 scripts/test-collection-counts.py
node scripts/test-collection-filters.cjs
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
