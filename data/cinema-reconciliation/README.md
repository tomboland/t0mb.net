# Cinema reconciliation — first applied batch

## Applied on 19 October 2026

- **97 collection work records** now refer to **95 existing canonical identities**
  in `cinema/films.json`. All 95 have typed TMDB references. The work link resolves
  canonical metadata at export time rather than maintaining a second TMDB record.
- Explicit review → viewing links added to **246 imported reviews**, giving **254**
  linked reviews in total. Matching required the same film ID, same Letterboxd entry
  URL, a unique viewing and no watched-date conflict.
- **16 published reviews** with no recorded watched date remain standalone; the
  unpublished 400 Blows draft also remains unlinked. No fictional viewing events.
- No film IDs, film slugs, review IDs, review bodies, ratings, viewing dates, liked
  flags or watched assertions were changed. All 951 physical copies remain.

[`confirmed-links.json`](confirmed-links.json) records the explicit evidence-reviewed
identity decisions (including photo references and selected publisher sources).
This is not an automatic title-only matching rule. [`applied.json`](applied.json)
records before/after values for recovery and inspection. `reconcile-cinema.py`
preflights the batch, defaults to dry-run and is idempotent:

```sh
python3 scripts/reconcile-cinema.py
# Apply a newly reviewed decision batch only when intended:
python3 scripts/reconcile-cinema.py --apply
```

The first batch covers previously year-confirmed identities and identifiable films
on the additional favourite shelf. Examples: Arrow RoboCop → 1987, not the 2014
remake; Hobo with a Shotgun → 2011 feature, not the 2007 short; 12 Monkeys → Terry
Gilliam's film, not the TV series. Chernobyl retains its existing TMDB **TV** identity.
The other collection work records remain provisional; no mass deduplication occurred.

## Letterboxd export check

Compared against `~/Downloads/letterboxd-tombardier-2026-10-01-19-02-utc.zip` without
reimporting or overwriting local changes:

- Export contains 268 reviews. 262 are still represented in the local review files.
- The six omitted reviews match existing intentional exclusions: four Twin Peaks
  pilot/episode logs, one Diario di una Segretaria, and the misplaced review of the
  2007 Hobo with a Shotgun short. The corrected feature review is retained.
- Five imported review bodies differ from the original export: Kwaidan, Invasion
  of the Body Snatchers, The Great White Silence, M, and The Wizard of Oz. These local
  edits were preserved, not replaced by older export content.
- The original archive contains no deleted/orphaned review rows to recover.
- The Piano Teacher has three separate diary IDs dated **18 May 2026**
  (`lb-eq1O83`, `lb-eq2Avf`, `lb-eqx1T9`). Owner confirmed on 19 October 2026:
  the first two were flippant entries and the third an earnest review. These are
  intentional entries, not three genuine viewings and not accidental duplicates.
  Preserve all three entries/reviews; do not deduplicate or represent them as
  three confirmed viewing occasions. Historical diary rows remain unchanged.
- 345 catalogue films are known watched without dated viewing events. Their watched
  flags remain intact; missing dates are not interpreted as unwatched.

Future fresh imports now populate explicit review/viewing IDs using the same
unique same-film/URL/date criteria. Existing installations still refuse a full
reimport, preserving local authoring.

## Integration-ready output

```sh
python3 scripts/audit-cinema-relations.py
python3 scripts/export-cinema-integration.py
python3 scripts/export-shelf.py
```

- `generated/cinema-integration.json`: joined canonical identity, typed TMDB link,
  film/review URLs, public review summaries, viewing events and confirmed physical
  editions. Multiple releases of the same work join under one canonical ID.
- Private shelf locations, acquisition details, copy notes, photos and draft reviews
  are excluded by an allowlist. This file is **not published automatically**.
- `owned: true` means confirmed linked holdings; `owned: null` means unknown because
  reconciliation is incomplete, not “unowned”. Physical holdings include loaned
  copies; sold/disposed/lost copies do not count as current holdings.
- `shelf.json` now includes `resolved_contents`, resolving linked canonical titles,
  years, TMDB references and existing film URLs while retaining release titles.
- `generated/cinema-relations/unlinked-works.csv` is the remaining research queue:
  1,075 work records, of which 513 have title-based candidates and 562 have no exact
  title candidate. It includes edition IDs, photos and catalogue numbers for research.
  These are not counts of unique films, and no-match does not imply a new/unwatched film.

The separate edition-metadata backlog remains: 886 copies lack a label and/or format.
These are different questions from canonical identity linking.

## Not yet changed

No public ownership panels or routes, no canonical `works.json` migration, and no
new owned-only films inserted into `films.json`. The existing renderer's watched-only
assumptions still need changing before expanding that catalogue. This is a validated
bridge using the existing canonical IDs, not a claim that all identities are merged.

Checks: `test-cinema-integration.py` (4 tests), `test-collection.py` (7),
`test-cinema-cli.py` (14), plus a fresh import of the actual Letterboxd ZIP into
a temporary directory: 246 valid links and repeat-import protection verified.
All 246 live Markdown diffs were checked: exactly one added front-matter field
per file, with no removed or changed prose lines.

## Owned-identity pass (19 October 2026)

`owned-identity-pass.json` preserves the complete pre-pass collection and the
reviewed merge groups. Consolidated 63 repeated work records, retaining all 951
physical packages, their editions, photographic provenance and condition data.
Remakes and film/TV name collisions remain separate. Reconciliation resolves
historical work IDs through merge history, so the original link decisions remain
usable. Box-set constituents are classified individually; Fire Walk with Me is
also linked from the Twin Peaks television box without creating a second film.

Run `python scripts/count-collection.py` to generate
`generated/collection-counts.json`, including an inspectable list of identities.
Current provisional count: 1,028 fiction/feature records + 15 documentaries +
9 television films = **1,052 films**. Shorts (7 enumerated), concerts (7), series
and calibration discs are separate. This is not a certified exhaustive count:
The owner confirmed Conan as the 1982 film (work-0366 merged into work-0868)
and Scarface Gold as the 1983 film only, without the 1932 original.
Short collections/bonus contents are not fully enumerated.
Series identities also still need further consolidation across season packages.
No viewing/review records were changed by this pass.

### External release references

Keep TMDB identity at work/film level. Edition identity instead needs barcode,
label/imprint, catalogue number, country, format and release date; retain source
URLs with the edition's evidence. These fields already exist in the collection.

- Blu-ray.com: https://www.blu-ray.com/movies/ — country-specific physical
  editions, box sets and formats. Useful manual reference; no documented public
  API verified in this research. Do not assume browsing access grants bulk reuse.
- My Movies: https://kb.mymovies.dk/KnowledgebaseArticle50063.aspx — documented
  barcode, disc-ID, IMDb and title lookup API. Their end-user integration route
  requires contact and a purchased API account; no purchase/integration initiated.
- TMDB: https://developer.themoviedb.org/reference/movie-release-dates — movie
  release dates are not identities for individual retail editions.

Recommendation: maintain our own edition records, with external reference URLs
and barcodes, rather than making the website dependent on an edition provider.

## Website linking pass

`linked-shelf-pass.json` journals 427 additional reviewed local identity links
(before/after records). 522 collection works now link to canonical records in total.
Local metadata, original-title aliases, previously researched box contents and
specific package evidence were used; there is no general title-only auto-match.
Photo reinspection resolved e.g. original Oldboy, Harakiri, Hero, Get Carter,
Point Blank and City on Fire. Six remake-prone titles were sent for owner confirmation.

The two flippant Piano Teacher entries were moved, not deleted, into
`cinema/entries.json`. Their original records are preserved in
`piano-diary-original.json`. The two review references changed from `viewing` to
`diary_entry`; review IDs, dates, bodies and URLs are unchanged. The third earnest
review still links to its viewing. This supersedes the earlier decision to leave
all three rows in viewings.json: there are now 419 viewing events and two notes.

## Reviewed TMDB pass

The six owner-confirmed originals were applied in `originals-confirmed.json`.
`tmdb-reviewed.json` contains 571 explicitly reviewed identities; the
`tmdb-applied-*.json` journals preserve before/after records and source snapshots.
These added 513 canonical entries and reused existing identities for the others.
There are now 1,099 linked collection records, 1,238 canonical entries, no duplicate
typed TMDB IDs and no broken references. All 725 pre-existing canonical entries,
951 edition records and 951 copies were preserved unchanged.

`tmdb-remaining.json` lists nine unlinked records: five film identity questions,
Wong Kar-wai's The Hand (original short versus extended standalone release), and
three calibration/demo discs that need no TMDB match. Breaking Bad series identity
is linked, but its separate Final Season case conflicts with the earlier owner
coverage statement; the coverage question remains open.

`nausicaa-metadata-correction.json` records a curated title/runtime correction
against primary sources; the current TMDB API response uses a shortened-release
alias/runtime. Preserve this correction when refreshing metadata.

## Owner confirmations, 20 October 2026

Applied all five confirmations in `tmdb-owner-confirmed-2026-10-20.json`:
Paprika (2006), Ghostbusters (1984), La Ronde (1950), Christine (1983),
and Jacques Rivette’s Secret défense (1998), whose edition is recorded as DVD.
Five links added (four new canonical entries, one existing identity reused).
Current totals: 1,104 linked collection records and 1,242 canonical entries;
1,051 physical films in 951 packages. Integrity audit: zero errors and zero
duplicate typed TMDB identities. No viewing or review records changed.

This supersedes the earlier remaining list: only The Hand version and three
calibration/demo discs remain unlinked. Breaking Bad coverage is still pending.

## Coverage clarification, 20 October 2026

Breaking Bad is complete across edition-0256 (box) and edition-0257 (Final Season).
Both link to canonical `tmdb-tv-1396`. Owner ambiguity is resolved.
The Hand was researched from Criterion’s World of Wong Kar Wai supplement list,
not read from a separate spine. It is the extended 2004 short, recorded as a
supplement/cut; only the external TMDB release-year reconciliation remains open.
See `coverage-confirmed-2026-10-20.json` for the before/after journal.
