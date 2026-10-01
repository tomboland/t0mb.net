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

## Build and preview

From the repository root (Python 3 and the existing Haskell toolchain required):

```sh
export PATH="$HOME/.ghcup/bin:$PATH"
cabal build exe:site
cabal exec site -- build
python3 -m http.server 8000 --directory _site
```

Open `http://localhost:8000/films/`. Every `site build` regenerates the film
section from these files before Hakyll runs. It requires no API key, Pandoc
executable or network connection. `generated/` and `_site/` are disposable
build outputs: never edit them. For Hakyll's watch mode, run
`python3 scripts/build-films.py` after changing cinema source files.

## Add a film, viewing or review

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
No film artwork is fetched from TMDB. Its attribution logo is served locally.

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
python3 scripts/test-cinema.py
```
