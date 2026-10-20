# Physical collection

`collection.json` is the editable source of truth (schema 2). Initial import
scripts, photographs and research logs are preserved in Git at `3803b1d`;
they are not required to maintain or build the collection.

## Relationships

- **Film:** `films.json` holds the canonical identity, optional typed TMDB ID,
  ratings and tags. Viewings and reviews refer to its stable local ID.
- **Work:** a collection content record links to that film through
  `catalogue_film_id`. Unlinked works can be curated later.
- **Edition:** label, imprint, formats, barcode, catalogue number, packaging and
  release date; its contents reference one or more works, with cut, supplement
  role and season/episode coverage where relevant.
- **Copy:** the owned instance of an edition, with condition, location,
  acquisition date and ownership status. Two copies need not mean two editions.

A box set is one edition containing multiple works. Different editions can share
one film. Ownership never creates a viewing or implies watched/liked/rated.
Unknown metadata remains null or empty, rather than guessed. Edition notes are
for useful release facts; copy notes are for the particular physical copy.

Local IDs are permanent relational keys; slugs are for film-page URLs, not joins.
TMDB movie and television IDs have separate namespaces. Keep existing IDs and
slugs stable when correcting titles or metadata.

## Add and maintain

Run from the repository root. These are illustrative examples; use actual IDs
from search output. Collection commands run offline without a TMDB token.

```sh
python3 scripts/collection.py search "RoboCop"
python3 scripts/collection.py show edition-0123

# New work, edition and owned copy:
python3 scripts/collection.py add "A new film" --year 2026 \
  --label Arrow --format "4K UHD" --catalogue-number FCD0000

# Another release of an existing work:
python3 scripts/collection.py add "Existing film" --work work-0123 \
  --new-edition --label Kino --format Blu-ray --packaging steelbook

# Another copy of the same release:
python3 scripts/collection.py copy edition-0123 --location "Living room"

# A box containing existing works:
python3 scripts/collection.py add "Double feature" \
  --work work-0123 --work work-0456 --label Criterion

# A season set:
python3 scripts/collection.py add "A series" --kind tv_series \
  --coverage "Season 1" --format DVD

python3 scripts/collection.py edit edition-0123 --label "Arrow Academy" \
  --format Blu-ray --catalogue-number FCD1234
python3 scripts/collection.py set-copy shelf-0123 --condition faulty \
  --notes "Disc freezes"
```

Repeat `--format` for multi-format packages. `--contains "Title"` adds a new box
constituent; prefer `--work` when the identity already exists. Barcodes are strings,
including leading zeroes, not automatic lookups. Duplicate titles require explicit
selection of an existing work/copy/edition rather than silent merging.

For film identity, first check `films.json` for an existing entry. If absent:

```sh
python3 scripts/cinema.py film --tmdb-id 123 --unwatched
python3 scripts/collection.py link work-0123 PRINTED_FILM_ID
```

`--unwatched` creates no viewing. TMDB credentials stay outside the repository;
see [cinema workflow](README.md). For work titles/years, individual cuts, detailed
coverage and disc specifications, edit `collection.json` directly and validate.
CLI writes are locked and atomic; avoid manual edits while a writer is running.

## Validate and export

```sh
python3 scripts/validate-cinema.py
python3 scripts/count-collection.py
python3 scripts/collection.py export
```

`validate-cinema.py` checks the collection and its film/viewing/review relationships.
Exports go to ignored `generated/collection/collection.csv` and `collection.json`.
They are local snapshots, not editable sources; CSV edits do not write back.
The JSON export includes private copy details: do not publish it wholesale.

## Website

The build reads the live sources directly. `/films/collection/` provides search
and label/format filters. Stable edition pages list contents; linked works lead
to canonical film pages with reviews, viewing history and **My editions**.
Unlinked works retain their own collection pages. Existing work-page URLs remain
valid after linking. Private copy notes, locations and acquisition data are not
rendered. Build/preview and review-writing instructions are in [README.md](README.md).
