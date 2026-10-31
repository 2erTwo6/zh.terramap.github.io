# Bundled wiki summaries

`zh-CN-<bucket>.json` contains the intro extract of each item's article on the
[Chinese Terraria Wiki](https://terraria.wiki.gg/zh/wiki/), keyed by item ID and split
into buckets of 1,000 IDs so the app only downloads the part a click needs.

```json
{ "757": { "t": "泰拉刃", "extract": "泰拉刃 是一把困难模式、世纪之花后的剑……" } }
```

- Source: <https://terraria.wiki.gg/zh/wiki/>
- License: [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). The app shows
  the attribution and a link to the full article in the summary dialog.
- Fetched with the MediaWiki `extracts` API; translations themselves follow the wiki,
  with the existing translation kept where the wiki has no page for a name.

Regenerate everything (requires network access to the wiki):

```sh
python3 scripts/sync-wiki.py
```

`--names` only refreshes `src/i18n/blockNames/zh-CN.json`, `--summaries` only refreshes
this directory, and `--refresh` bypasses the `.wiki-cache/` download cache.
