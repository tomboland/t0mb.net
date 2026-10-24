# Physical collection

One catalogue, three kinds of record:

- **`films.json`:** canonical films, series, shorts and other programmes. Reviews,
  viewings and edition contents all reference the same `id`. TMDB is optional.
- **`collection.json` → `editions`:** release title, label/format and contents.
  Each content item has a `film` ID and, if recorded, a cut, coverage or role.
- **`collection.json` → `copies`:** physical instances of an edition.

Labels have their own small list in `collection.json`. That file uses schema 3;
there is no second collection-work catalogue and no linking step.

## Minimal records

An edition can be as small as:

```json
{
  "id": "edition-0952",
  "title": "Example release",
  "contents": [{"film": "CANONICAL_FILM_ID"}]
}
```

An ordinary copy needs only:

```json
{"id": "shelf-0952", "edition_id": "edition-0952"}
```

Optional fields are omitted until recorded. Missing copy `ownership` means
`owned`; missing `condition` means `unknown`, **not good**. Add `condition:
"faulty"` or `ownership: "sold"` when applicable. Other absent metadata means
unrecorded. Missing content `role` means unspecified; `main` and `supplement`
are explicit. Coverage is plain text, such as `"Season 1"`.

Films default to kind `film`, or `tv_series` when their TMDB type is `tv`.
Other kinds are explicit: documentary, tv_film, short, concert or calibration.
A missing `watched` field is not a claim of never watched. Viewing records imply
watched; `watched: true` preserves knowledge of watched films without dated entries.
Null/missing ratings mean unrated; false likes are not dislikes.

## Daily workflow

For a single-film purchase, use the title directly:

```sh
python3 scripts/cinema.py own "Don't Look Now" --year 1973 \
  --label StudioCanal --format "4K UHD"
```

This reuses a local film or lets you choose a TMDB result, imports missing film
metadata/artwork, and creates the release and copy without logging a viewing.
If the film already has editions, choose another copy or a new edition.
See [the everyday command guide](../scripts/README.md) for `seen` (watched with
unknown date), `log` (dated viewing) and `add` (catalogue only).

The lower-level collection commands below remain available for detailed edits
and box sets.

Run from the repository root. Examples use illustrative IDs; use actual results
from search. Collection commands run offline and never change films or viewing history.

```sh
# Search the canonical catalogue and physical editions:
python3 scripts/cinema.py search "RoboCop" --local
python3 scripts/collection.py search "RoboCop"

# Search TMDB when a film is missing locally (does not save anything):
python3 scripts/cinema.py search "Don't Look Now" --year 1973
# Use a TMDB ID from those results to add metadata/artwork, without a viewing:
python3 scripts/cinema.py add --tmdb-id TMDB_MOVIE_ID
# Then use the printed local ID or slug to record the disc you own:
python3 scripts/collection.py add "Don't Look Now" --film LOCAL_FILM_ID \
  --label StudioCanal --format "4K UHD"

# Add a release of an existing film (ID or slug):
python3 scripts/collection.py add "RoboCop" --film FILM_ID \
  --label Arrow --format "4K UHD"

# A unique exact catalogue title can be selected without --film:
python3 scripts/collection.py add "A known title" --year 1990 --format Blu-ray

# First add a genuinely new title, without logging a viewing:
python3 scripts/cinema.py film --title "A new film" --year 2026 --unwatched
# Or use cinema.py add --tmdb-id ID. Then use its printed local ID:
python3 scripts/collection.py add "A new film" --film PRINTED_ID --label Kino

# A different release, or another copy of the same release:
python3 scripts/collection.py add "RoboCop" --film FILM_ID \
  --new-edition --label Criterion --format Blu-ray
python3 scripts/collection.py copy edition-0123

# Box set: one edition/copy, several canonical titles:
python3 scripts/collection.py add "Double feature" --film FILM_ID_1 --film FILM_ID_2

# TV coverage belongs to the release, not another series identity:
python3 scripts/collection.py add "A series: season one" --film SERIES_ID \
  --coverage "Season 1" --format DVD

python3 scripts/collection.py show edition-0123
python3 scripts/collection.py edit edition-0123 --label "Arrow Academy" \
  --catalogue-number FCD1234
python3 scripts/collection.py set-copy shelf-0123 --condition faulty --notes "Disc freezes"
python3 scripts/collection.py set-copy shelf-0123 --condition unknown --notes ""
```

Ambiguous title matches stop and show choices; they never silently merge remakes.
TMDB search needs your configured token for uncached requests (see README.md).
It lists movie IDs, titles and years, and flags films already in your catalogue.
Local film search ignores punctuation, so `Dont look now` also matches
`Don't Look Now`. Add `--year` to narrow either local or TMDB film searches.
After watching, use `cinema.py log LOCAL_FILM_ID --review` to record the viewing
and start a review draft; owning a disc alone does not log a viewing.
Repeat `--format` for a multi-format package. Barcodes are strings preserving
leading zeroes, not automatic lookups. Add `--kind tv_series` (or another kind) to
manual `cinema.py film` additions when needed. Unknown years can be omitted.

For per-film cuts in boxes, detailed disc metadata or title corrections, edit the
JSON directly. Keep IDs and slugs stable. Avoid manual edits while a CLI writer
is running. Collection writes are locked, validated and atomic.

## Validate, export and publish

```sh
python3 scripts/validate-cinema.py
python3 scripts/count-collection.py
python3 scripts/collection.py export
```

Exports go to ignored `generated/collection/collection.csv` and `collection.json`.
They are snapshots, not editable sources. The JSON includes private copy details;
do not publish it wholesale.

The website reads live sources directly. `/films/collection/` provides search and
filters; edition contents lead straight to canonical film pages with reviews,
viewing history and **My editions**. Private copy notes, locations and acquisition
dates are not rendered.

`collection-redirects.json` is a compatibility map for pre-existing collection-work
URLs. It is not another catalogue and needs no entry for new films. Existing URLs
remain usable and link to the canonical film pages. Import history is in Git at
`3803b1d`; the previous model is at `73dbb9f`. Neither is needed for daily upkeep.

See [README.md](README.md) for reviews, diary logging and website publishing.
