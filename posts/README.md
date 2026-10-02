# Notes and micro-blog entries

Keep `content/home.md` for the short introduction. Add each new entry as
`posts/YYYY-MM-DD-short-description/index.md`:

```markdown
---
title: A short title
date: 2026-10-02
tags: [photography, landscape]
---

Your words go here. Markdown formatting works as usual.
```

Each entry gets its own page. The homepage shows the three latest entries in
full; `/notes/` contains every entry, newest first. Entries also appear in the
writing archive and the shared RSS feed (the latest 20 posts and film reviews).
Dates use `YYYY-MM-DD`; entries on the same day do not have an implied time.
Keep the directory name stable once published, as it determines the URL.

Every `posts/*/index.md` is published when the site is built; there is currently
no draft flag for notes. Keep unfinished text outside that pattern until ready.
Build and preview locally before publishing with the normal release process.

## Tags and photographs

`tags` is an optional YAML list of non-empty strings. Click a tag on a post,
review, or embedded review to see matching published writing, newest first.
`/tags/` lists all post tags. Case and repeated whitespace are ignored when
grouping tags; punctuation and non-Latin labels remain distinct. These tags
are separate from film collection tags under `/films/tags/`.

Keep photographs beside the entry and use a root-relative image URL such as
`![Description](/posts/2026-10-02-publishing-photos/sunset-skirrid.jpg)`.
Content images share the site's full-screen viewer. A photo post is an ordinary
post containing images; galleries do not require a separate content model yet.

## Publishing boundaries

Notes keep their directory-based URLs and publish automatically. Reviews retain
explicit `draft: false`, stable IDs, and their film/viewing relationships.
Both appear in the shared archive, RSS feed and post-tag pages.

`site.hs` connects Hakyll source rules and routes. `src/Publishing.hs` owns the
homepage, notes, archive, RSS and Hakyll tag-page rules. `src/View.hs` provides
shared metadata and escaped template helpers. Cinema data and review selection
live in `src/Cinema.hs`; film wrappers and full-review embedding live in
`src/CinemaRendering.hs`.

The `body` snapshot is rendered Markdown only. The `feed` snapshot is feed-ready
content without page navigation: notes use their body, reviews add publication
metadata, optional artwork and their Letterboxd link. Standalone wrappers are
applied separately. Embedded reviews use `body` and preserve namespaced anchors.
