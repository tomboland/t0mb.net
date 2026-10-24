# Cinema application

Run `python3 scripts/cinema.py` to open the local database browser. The site
remains static: the application edits the existing JSON and Markdown sources.
The terminal interface and its command interface call `cinema_service.Catalogue`
directly; neither invokes the former authoring CLI.

Requires Python 3, curses (included with Linux Python), PyYAML and jsonschema.
The Python dependencies are listed in `scripts/requirements-cinema.txt`.

| Intent | Command |
|---|---|
| Browse local films and collection | `python3 scripts/cinema.py browse` |
| Search TMDB and choose an action | `python3 scripts/cinema.py search whiplash` |
| Search local records offline | `python3 scripts/cinema.py search whiplash --local` |
| Search without opening the selector | `python3 scripts/cinema.py search whiplash --plain` |
| Find a film and add a disc | `python3 scripts/cinema.py own whiplash` |
| Log a viewing and write a review | `python3 scripts/cinema.py review whiplash` |
| Log without a review | `python3 scripts/cinema.py log whiplash --rating 4.5` |
| Add catalogue metadata only | `python3 scripts/cinema.py add --tmdb-id 244786` |
| Mark watched with an unknown date | `python3 scripts/cinema.py seen whiplash` |

All examples are single-line commands suitable for Nushell. `--help` lists
options. Titles resolve to existing local identities where possible; TMDB
results use arrow-key selection. Unattended writes require an explicit local
ID/slug or `--tmdb-id`. Search defaults to TMDB, without a `--tmdb` flag.

## Terminal controls

Select a film and choose **Open on TMDB** to open its linked entry in your browser.
This works for local films with a TMDB identity and TMDB search results; no API
token is needed to open the link. If the browser cannot launch, the URL is shown
for copying. Film rows include the original title when it differs, and filtering
matches either title. From a collection edition, choose **Films in this edition**
and select the film to access its actions.

Use arrow keys and Enter to select, type to filter, Ctrl-U to clear, and Esc
to return. The selector preserves its filter and position when returning from
an action. TMDB results fill in director and country of origin progressively;
missing country data stays unknown. Select a field to edit its prefilled value,
then Enter to accept it. Forms save explicitly; cancelling modified forms asks
whether to discard the edits. Optional edition fields can be skipped with Save.

The film browser offers owned/not-owned, watched/unwatched/unknown, and owned
without a recorded viewing filters. Unknown viewing status stays distinct from
explicitly unwatched. Text filtering also searches director and displayed format.
The collection browser filters title, label, format, contents and location, and
edits edition metadata, formats, per-film cuts, copy condition and ownership.
A box set appears once as an edition, with its constituent films accessible.

## Ownership

`own` imports missing film metadata and artwork and adds an edition and copy,
without asserting a viewing. Existing editions offer another copy or a new
edition. For direct commands, use `--new-edition` to acknowledge another release.

```nu
python3 scripts/cinema.py own --tmdb-id 244786 --format "4K UHD" --label "Sony"
```

Use repeated `--format` for multi-format packages. Optional flags include
`--edition-title`, `--cut`, `--notes`, `--location`, `--packaging` and `--barcode`.
The separate `collection.py` remains a low-level box-set/import utility; it is
not used as the application's backend. See [collection details](../cinema/COLLECTION.md).

## Reviews and viewing history

`review` (or `log --review`) opens `$VISUAL`, falling back to `$EDITOR`, with a
populated Markdown template. Editor arguments are supported without shell
execution. In Nushell, for example: `$env.VISUAL = "nvim"`. GUI editors must
be configured to wait, such as `code --wait`.

The viewing and review are saved only after successful editing and validation.
An unchanged/empty review or a failed editor cancels the operation. Invalid
metadata offers to reopen the editor. Temporary drafts are retained under `/tmp`
for recovery, including if a later artwork download or save fails. Keep identity
and viewing fields unchanged in the template; use the viewing form to set them.
Reviews remain unpublished drafts. Publish later by setting `draft: false`.

`--date YYYY-MM-DD` defaults to today; `--rating` is optional (0.5–5, half steps),
`--rewatch` records a repeat, and `--liked` marks the film liked. Each successful
viewing command creates a new viewing. `seen` asserts watched without a date.
`film --title TITLE --year YEAR --director NAME` adds manual metadata without
asserting watched status; `--unwatched` explicitly marks it unwatched.
`tag FILM TAG... [--remove]` manages film tags.

## Storage and contracts

`cinema/schemas/*.schema.json` describe films, editions/copies, viewings and review
front matter. Application saves validate schemas plus collection references.
Optional fields and existing extension metadata are preserved. Changes reject
stale snapshots, use atomic per-file replacements, and roll back ordinary write
failures. This is file storage, not a crash-atomic database transaction; keep Git
backups and avoid concurrent authoring with older utilities.

Use `python3 scripts/test-cinema-app.py` and `python3 scripts/test-cinema-cli.py`
for offline service, terminal interaction and command tests. TMDB credentials
are read from `~/.config/t0mb.net/tmdb-token`, `TMDB_TOKEN_FILE`, or
`--token-file PATH`. Local browsing needs no network or token.

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
