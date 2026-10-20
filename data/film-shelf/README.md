# Shelf evidence and import history

## Current editable collection

The live source is now [`cinema/collection.json`](../../cinema/collection.json),
with separate works, editions, labels and owned copies. See the
[model and addition workflow](../../cinema/COLLECTION.md).
`cinema/shelf.csv` and `cinema/shelf.json` are generated exports; do not edit them.

## Photographs

- Original archive: `~/Downloads/myfilmsshelfphotos.zip`, 51 photographs.
- Additional archive: `~/Downloads/myfavouritefilmshelf.zip`, 10 photographs.
- [`photos.json`](photos.json) maps all 61 originals to ZIP filenames and SHA-256
  hashes, including each archive's identity. Images remain unmodified.
- Photo numbers are ZIP-order evidence IDs, not physical shelf numbering.
- The additional shelf contains 96 transcribed packages, taking the inventory
  from 855 to 951 copy records. Repeated titles are not assumed to be duplicate
  photographs of the same copy.

## Preserved evidence

- [`imports/shelf-transcription.csv`](imports/shelf-transcription.csv): frozen
  pre-normalisation transcription of all 951 packages. Historical input, not live data.
- [`imports/favourite-shelf.tsv`](imports/favourite-shelf.tsv): raw additional-shelf
  transcription, including visible label/imprint/format/catalogue numbers.
- [`imports/favourite-editions.json`](imports/favourite-editions.json): same import
  metadata mapped to stable shelf IDs.
- [`identifications.md`](identifications.md) and
  [`identifications.json`](identifications.json): research and owner confirmations
  resolving the original 68 review flags, with before/after snapshots.
- [`review.md`](review.md): generated identification questions plus a distinct
  edition-metadata enrichment queue. Resolved film identity does not mean every
  edition detail is known. Blank metadata remains unknown rather than guessed.

The original photos live outside public image routes. Neither the collection nor
these evidence files are automatically published. The watched-film catalogue,
reviews and diary are unchanged.

## Validate/export

```sh
python3 scripts/collection.py validate
python3 scripts/collection.py export
python3 scripts/test-collection.py
```

The exporter checks all 61 source hashes and foreign-key references. Manual additions
need no photograph; they record manual provenance. The old `export-shelf.py` command
still works as an alias. Editing the frozen transcription and rerunning migration
is not the curation workflow: migration refuses to overwrite the current source.
