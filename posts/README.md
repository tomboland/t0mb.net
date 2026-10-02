# Notes and micro-blog entries

Keep `content/home.md` for the short introduction. Add each new entry as
`posts/YYYY-MM-DD-short-description/index.md`:

```markdown
---
title: A short title
date: 2026-10-02
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
