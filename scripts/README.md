# Everyday cinema commands

Run from the repository root. `python3 scripts/cinema.py --help` lists commands;
append `--help` to a command to see its options.

| Intent | Command |
|---|---|
| Search your catalogue | `python3 scripts/cinema.py search "Don't Look Now"` |
| Browse TMDB | `python3 scripts/cinema.py search "Don't Look Now" --tmdb` |
| Add catalogue metadata only | `python3 scripts/cinema.py add "Don't Look Now" --year 1973` |
| Record a disc you own | `python3 scripts/cinema.py own "Don't Look Now" --label StudioCanal --format "4K UHD"` |
| Watched before, date unknown | `python3 scripts/cinema.py seen "Antichrist" --year 2009` |
| Log a viewing today | `python3 scripts/cinema.py log "Don't Look Now" --liked --rating 4.5 --review` |

`add`, `own`, `seen` and `log` reuse an exact local title, ID or slug. Missing
titles are searched on TMDB. In a terminal, choose a numbered TMDB result;
`q` or Ctrl-C cancels. Use `--year` for remakes, `--tmdb` to search remotely even
when the title matches locally, or `--tmdb-id ID` to select an exact movie.
In noninteractive use, only a unique exact title match is selected automatically;
ambiguous/inexact results stop and print IDs.

Uncached requests need a TMDB token in `~/.config/t0mb.net/tmdb-token`, the file
named by `TMDB_TOKEN_FILE`, or `--token-file PATH`. Manual films remain supported
through `cinema.py film --title TITLE --year YEAR --unwatched`.

## Ownership

`own` creates a release and one owned copy without marking the film watched.
If editions already contain that film, it offers another copy of a listed
edition or a new edition. Use `--new-edition` to explicitly choose a new release.
When choosing another copy, the existing release metadata is retained; flags
such as `--format` and `--label` only apply to new editions.
Optional details include `--edition-title`, `--barcode`, `--catalogue-number`,
`--cut`, `--location` and repeated `--format` flags for multi-format packages.

For box sets, editing releases, copy condition and ownership changes, use
`collection.py`; see [the collection guide](../cinema/COLLECTION.md).

## Viewing history

`seen` marks a film watched without a date, diary entry or owned copy. It can
be repeated safely and preserves existing dated viewings. Optional `--liked`
and `--rating` update the film's like and overall rating.

`log` creates a dated viewing, defaulting to today. Use `--date YYYY-MM-DD`
for an earlier viewing and `--rewatch` for a repeat. Its `--rating` belongs to
that viewing; `--liked` belongs to the film and omission preserves its status.
Each successful `log` call adds a viewing, even for the same film and date.

`--review` creates a Markdown draft and prints its path. Edit it and set
`draft: false` when ready to publish on the next build. No editor is launched
automatically.

`add` records metadata only. Existing watched status, ownership and reviews are
preserved. The older `film` command keeps its original default of marking a
new film watched unless `--unwatched` is supplied; prefer `add` or `seen` for
explicit intent.

## Supporting tools

- `validate-cinema.py`: check sources and relationships.
- `count-collection.py`: collection counts.
- `export-cinema.py`: regenerate `generated/cinema-export/film-context.txt` and JSON.
- `refresh-artwork.py`, `refresh-directors.py`: refresh saved TMDB data.
- `test-*`: regression checks.
- `cinema_data.py`, `collection_data.py`, `cinema_export.py`, `tmdb_api.py`,
  `review_files.py`: internal shared modules.
- `publish-release.py`, `deploy-release.py`: publishing infrastructure;
  use `bash deploy.sh` as the normal entry point.

Commands do not commit or deploy. Generated exports are snapshots; regenerate
them after changes. Full diary/review documentation is in
[cinema/README.md](../cinema/README.md).
