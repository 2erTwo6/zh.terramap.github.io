#!/usr/bin/env python3
"""Sync Chinese names and wiki summaries from the Terraria Wiki.

Policy: the Chinese Terraria Wiki is the authority for a name. If the wiki
has no page/name for an entry, the translation already in the table is kept.
Only the zh-CN table is touched.

Names are read from the wiki's ID tables (item / wall / NPC), the prefix
table and the tile ID table (English and Chinese editions are joined by
tile ID + sub ID). Summaries are the intro extract of each item's article.

The wiki text is licensed CC BY-SA 3.0; see src/i18n/wiki/README.md.

Usage:
  python3 scripts/sync-wiki.py --names [--refresh]
  python3 scripts/sync-wiki.py --summaries [--refresh]
Both phases run when neither flag is given.
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".wiki-cache"
BLOCK_NAMES = ROOT / "src/i18n/blockNames/zh-CN.json"
WIKI_DIR = ROOT / "src/i18n/wiki"
UA = "TerraMap-zh-localization/1.0 (https://github.com/2erTwo6/zh.terramap.github.io)"
LIMIT = 0
WORKERS = 4
CJK = re.compile(r"[\u4e00-\u9fff]")

_VERSION_EN = re.compile(r"\s*\((?:[^()]*(?:version|unused|Desktop|Console|Mobile|Old-gen|3DS)[^()]*)\)\s*$", re.I)
_VERSION_ZH = re.compile(r"\s*[（(][^（）()]*(?:版|未使用|无法获取|未实现)[^（）()]*[）)]\s*$")
_QUALIFIER = re.compile(r"[（(](?:天然|未使用)[）)]$")


def request(lang: str, params: dict) -> dict:
    params.setdefault("format", "json")
    base = f"https://terraria.wiki.gg/{lang + '/' if lang else ''}api.php"
    data = urllib.parse.urlencode(params).encode()
    for attempt in range(3):
        req = urllib.request.Request(base, data=data, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(2 ** attempt)
        except urllib.error.URLError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def fetch(page: str, lang: str = "", cache: str | None = None) -> str:
    if cache and not REFRESH and (CACHE / cache).exists():
        return (CACHE / cache).read_text()
    text = request(lang, {"action": "parse", "page": page, "prop": "text"})["parse"]["text"]["*"]
    if cache:
        CACHE.mkdir(exist_ok=True)
        (CACHE / cache).write_text(text)
    time.sleep(0.2)
    return text


def text(cell: str) -> str:
    cell = re.sub(r"<sup.*?</sup>", "", cell, flags=re.S)
    cell = re.sub(r"<br\s*/?>", " ", cell)
    cell = re.sub(r"<[^>]+>", "", cell)
    return htmllib.unescape(cell).replace("\u00a0", " ").strip()


def rows(page: str):
    return re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S)


def cells(row: str) -> list[str]:
    return [text(cell) for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]


def strip_annotations(name: str) -> str:
    previous = None
    while previous != name:
        previous = name
        name = _VERSION_EN.sub("", name)
        name = _VERSION_ZH.sub("", name)
    return name.strip()


def load_names() -> dict:
    return json.loads(BLOCK_NAMES.read_text())


def item_names() -> dict[int, str]:
    names = {}
    for row in rows(fetch("物品 ID", cache="item_ids.html")):
        values = cells(row)
        if len(values) >= 3 and values[0].isdigit():
            names[int(values[0])] = strip_annotations(values[1])
    return names


def wall_names() -> dict[int, str]:
    names = {}
    for row in rows(fetch("墙 ID", cache="wall_ids.html")):
        values = cells(row)
        if len(values) >= 4 and values[0].isdigit():
            names[int(values[0])] = strip_annotations(values[1])
    return names


def npc_names() -> dict[int, str]:
    names = {}
    for row in rows(fetch("NPC ID", cache="npc_ids.html")):
        values = cells(row)
        if len(values) >= 3 and re.fullmatch(r"-?\d+", values[0]):
            names[int(values[0])] = strip_annotations(re.split(r"[（(]", values[1])[0])
    return names


def prefix_names() -> dict[str, str]:
    names = {}
    for row in rows(fetch("修饰语", cache="prefixes.html")):
        anchor = re.search(r'<span id="([A-Za-z][A-Za-z0-9 _&\'-]*)"', row)
        if not anchor:
            continue
        cell = next((cell for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S) if anchor.group(1) in cell), None)
        if cell and text(cell):
            names[anchor.group(1)] = text(cell)
    return names


def tile_names() -> dict[str, str]:
    english, chinese = {}, {}
    for part in range(1, 10):
        page = fetch(f"Tile IDs/Part{part}", cache=f"en_tile_{part}.html")
        for row in rows(page):
            values = cells(row)
            if len(values) >= 4 and values[0].isdigit() and values[3]:
                english[(int(values[0]), values[1])] = strip_annotations(values[3])
        page = fetch(f"图格 ID/第 {part} 部分", lang="zh", cache=f"zh_tile_{part}.html")
        for row in rows(page):
            values = cells(row)
            if len(values) >= 4 and values[0].isdigit() and values[3]:
                chinese[(int(values[0]), values[1])] = strip_annotations(values[3])
    by_name = {}
    for key, name in english.items():
        localized = chinese.get(key)
        if not localized or not CJK.search(localized):
            continue
        if name in by_name and by_name[name] != localized:
            continue  # ambiguous English name; keep our translation
        by_name.setdefault(name, localized)
    return by_name


def apply_names() -> None:
    table = load_names()
    items, walls, npcs, prefixes, tiles = item_names(), wall_names(), npc_names(), prefix_names(), tile_names()

    changed = {"tiles": 0, "walls": 0, "items": 0, "prefixes": 0, "npcs": 0}

    for key, current in table["tiles"].items():
        candidate = tiles.get(key)
        if candidate and candidate != current:
            table["tiles"][key] = candidate
            changed["tiles"] += 1

    for key, current in table["walls"].items():
        candidate = walls.get(int(key))
        if candidate and candidate != current:
            qualifier = _QUALIFIER.search(current)
            if qualifier and qualifier.group(0) not in candidate:
                candidate += qualifier.group(0)
            if candidate != current:
                table["walls"][key] = candidate
                changed["walls"] += 1

    for key, current in table["items"].items():
        candidate = items.get(int(key))
        if candidate and CJK.search(candidate) and candidate != current:
            table["items"][key] = candidate
            changed["items"] += 1

    for key, current in table["prefixes"].items():
        index = int(key)
        source = (ROOT / "src/itemPrefixes.ts").read_text()
        english = re.findall(r'name:\s*"([^"]*)"', source)[index]
        candidate = prefixes.get(english) or prefixes.get(english + "2")
        if candidate and candidate != current:
            table["prefixes"][key] = candidate
            changed["prefixes"] += 1

    for key, current in table["npcs"].items():
        candidate = npcs.get(int(key))
        # The wiki calls the town pets "城镇猫咪" etc.; the game's own name is used.
        if candidate and candidate != current and candidate != "城镇" + current:
            table["npcs"][key] = candidate
            changed["npcs"] += 1

    BLOCK_NAMES.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n")
    print("names updated:", ", ".join(f"{key} {value}" for key, value in changed.items()))


def fetch_summaries() -> None:
    table = load_names()
    items = item_names()
    titles = {int(key): items[int(key)] for key in table["items"] if int(key) in items}

    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    done_entries: dict[str, dict[str, str]] = {}
    for path in WIKI_DIR.glob("zh-CN-*.json"):
        done_entries.update(json.loads(path.read_text()))

    pending = [item_id for item_id in sorted(titles) if str(item_id) not in done_entries]
    if LIMIT:
        pending = pending[:LIMIT]
    print(f"summaries: {len(done_entries)} cached, {len(pending)} to fetch", flush=True)

    def save() -> None:
        buckets: dict[int, dict[str, dict[str, str]]] = {}
        for key, entry in done_entries.items():
            buckets.setdefault(int(key) // 1000, {})[key] = entry
        for bucket, entries in buckets.items():
            (WIKI_DIR / f"zh-CN-{bucket}.json").write_text(
                json.dumps(entries, ensure_ascii=False, separators=(",", ":")) + "\n"
            )

    def fetch_batch(batch: list[int]) -> dict[str, dict[str, str]]:
        response = request("zh", {
            "action": "query",
            "prop": "extracts",
            "exintro": "1",
            "explaintext": "1",
            "redirects": "1",
            "exlimit": "max",
            "titles": "|".join(titles[item_id] for item_id in batch),
        })["query"]
        alias = {}
        for entry in response.get("normalized", []) + response.get("redirects", []):
            alias[entry["from"]] = entry["to"]
        by_title = {page.get("title"): page for page in response.get("pages", {}).values()}
        found = {}
        for item_id in batch:
            title = titles[item_id]
            seen = set()
            while title in alias and title not in seen:
                seen.add(title)
                title = alias[title]
            page = by_title.get(title)
            extract = (page or {}).get("extract", "")
            if extract:
                found[str(item_id)] = {"t": page.get("title", title), "extract": extract}
        return found

    BATCH = 20
    batches = [pending[start:start + BATCH] for start in range(0, len(pending), BATCH)]
    failed: list[list[int]] = []
    finished = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch_batch, batch): batch for batch in batches}
        for future in as_completed(futures):
            try:
                done_entries.update(future.result())
            except Exception as error:
                failed.append(futures[future])
                print(f"batch failed: {error}", flush=True)
            finished += 1
            if finished % 20 == 0 or finished == len(batches):
                save()
                print(f"summaries {finished}/{len(batches)} batches", flush=True)

    for attempt in range(2):
        if not failed:
            break
        time.sleep(3)
        retry, failed = failed, []
        for batch in retry:
            try:
                done_entries.update(fetch_batch(batch))
            except Exception as error:
                failed.append(batch)
        save()
        print(f"retried, {len(failed)} batches still failing", flush=True)

    save()
    print("summary buckets:", {path.name: path.stat().st_size for path in sorted(WIKI_DIR.glob("zh-CN-*.json"))})


def main() -> None:
    global REFRESH, LIMIT, WORKERS
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", action="store_true")
    parser.add_argument("--summaries", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="fetch at most N summaries this run")
    parser.add_argument("--workers", type=int, default=4, help="concurrent requests (default 4)")
    args = parser.parse_args()
    REFRESH = args.refresh
    LIMIT = args.limit
    WORKERS = args.workers
    if args.names or not args.summaries:
        apply_names()
    if args.summaries or not args.names:
        fetch_summaries()


if __name__ == "__main__":
    main()
