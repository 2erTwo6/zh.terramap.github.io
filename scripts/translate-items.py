#!/usr/bin/env python3
"""Translate src/items.ts with an OpenAI-compatible chat completion API."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ENTRY_RE = re.compile(
    r"\{\s*name:\s*(?P<name>\"(?:\\.|[^\"\\])*\")\s*,\s*"
    r"id:\s*(?P<id>-?\d+)\s*\}",
    re.MULTILINE,
)
NAME_FIELD_RE = re.compile(r"^\s*name:\s*", re.MULTILINE)
ID_FIELD_RE = re.compile(r"^\s*id:\s*", re.MULTILINE)

SYSTEM_PROMPT = """你是 Terraria（泰拉瑞亚）游戏本地化专家。请把物品英文名翻译成简体中文。
要求：
1. 优先采用 Terraria 官方简体中文译名，保持专有名词和系列名称一致。
2. 只翻译物品名称，不添加解释、注音、英文括注或额外标点。
3. 保留原名中的数字、版本标记和必要符号；对于 ItemName.* 这类内部键，保持原文。
4. 除 ItemName.* 内部键、通用缩写或官方明确保留的品牌名外，不得直接照抄英文；专有名词应采用官方译名或合理音译。
5. 必须返回 JSON 对象，格式严格为 {"translations":[{"id":1,"name":"铁镐"}]}。
6. 每个输入 ID 必须且只能出现一次，不得遗漏或增加条目。"""


@dataclass(frozen=True)
class Item:
    item_id: int
    source_name: str
    name_start: int
    name_end: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use an LLM to create a hardcoded Simplified Chinese items.ts variant."
    )
    parser.add_argument("--input", type=Path, default=Path("src/items.ts"))
    parser.add_argument("--output", type=Path, default=Path("src/items.zh-CN.ts"))
    parser.add_argument(
        "--cache", type=Path, default=Path(".cache/items-zh-CN.json")
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        help="OpenAI-compatible API base URL (default: OPENAI_BASE_URL or OpenAI)",
    )
    parser.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="environment variable containing the API key",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL"),
        help="model name (default: OPENAI_MODEL)",
    )
    parser.add_argument("--batch-size", type=int, default=80)
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="number of translation batches to request concurrently (default: 4)",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument(
        "--max-items",
        type=int,
        help="translate only this many unique names; useful for a small API test",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and report the source structure without calling the API",
    )
    parser.add_argument(
        "--retry-unchanged",
        action="store_true",
        help="discard cached translations identical to their English source, except ItemName.* keys",
    )
    parser.add_argument(
        "--overwrite-source",
        action="store_true",
        help="allow --output to point to --input (not recommended)",
    )
    args = parser.parse_args()

    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    if args.retries < 1:
        parser.error("--retries must be at least 1")
    if args.max_items is not None and args.max_items < 1:
        parser.error("--max-items must be at least 1")
    if not args.dry_run and not args.model:
        parser.error("--model or OPENAI_MODEL is required")

    input_path = args.input.resolve()
    output_path = args.output.resolve()
    if input_path == output_path and not args.overwrite_source:
        parser.error(
            "refusing to overwrite the source; choose another --output or pass "
            "--overwrite-source"
        )
    return args


def parse_items(source: str) -> list[Item]:
    items: list[Item] = []
    for match in ENTRY_RE.finditer(source):
        name_token = match.group("name")
        source_name = json.loads(name_token)
        items.append(
            Item(
                item_id=int(match.group("id")),
                source_name=source_name,
                name_start=match.start("name"),
                name_end=match.end("name"),
            )
        )

    name_fields = len(NAME_FIELD_RE.findall(source))
    id_fields = len(ID_FIELD_RE.findall(source))
    if not items or len(items) != name_fields or len(items) != id_fields:
        raise ValueError(
            "unsupported items.ts structure: "
            f"parsed {len(items)} entries, found {name_fields} name fields and "
            f"{id_fields} id fields"
        )

    ids = [item.item_id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("items.ts contains duplicate item IDs")
    return items


def load_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("translations"), dict):
        raise ValueError(f"unsupported cache format: {path}")
    translations = data["translations"]
    if not all(
        isinstance(source, str) and isinstance(target, str) and target.strip()
        for source, target in translations.items()
    ):
        raise ValueError(f"cache contains invalid translations: {path}")
    return translations


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(text)
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def save_cache(path: Path, translations: dict[str, str]) -> None:
    data = {"version": 1, "translations": translations}
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, count=1)
        stripped = re.sub(r"\s*```$", "", stripped, count=1)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("model response does not contain a JSON object") from None
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model response JSON must be an object")
    return value


def validate_response(data: dict[str, Any], batch: list[tuple[int, str]]) -> dict[int, str]:
    rows = data.get("translations")
    if not isinstance(rows, list):
        raise ValueError("model response is missing a translations array")

    expected_ids = {item_id for item_id, _ in batch}
    translated: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each translation must be an object")
        item_id = row.get("id")
        name = row.get("name")
        if not isinstance(item_id, int) or item_id not in expected_ids:
            raise ValueError(f"unexpected translation ID: {item_id!r}")
        if item_id in translated:
            raise ValueError(f"duplicate translation ID: {item_id}")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"translation for ID {item_id} is empty")
        if "\n" in name or "\r" in name:
            raise ValueError(f"translation for ID {item_id} contains a newline")
        translated[item_id] = name.strip()

    missing = expected_ids - translated.keys()
    if missing:
        raise ValueError(f"model response omitted IDs: {sorted(missing)}")
    return translated


def request_translation(
    api_base: str,
    api_key: str,
    model: str,
    batch: list[tuple[int, str]],
    timeout: float,
) -> dict[int, str]:
    user_payload = {
        "items": [{"id": item_id, "name": name} for item_id, name in batch]
    }
    body = {
        "model": model,
        "temperature": 0,
        "thinking": {"type": "disabled"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False),
            },
        ],
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response_data = json.loads(response.read().decode("utf-8"))
    try:
        content = response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError(f"unexpected API response: {response_data!r}") from error
    if not isinstance(content, str):
        raise ValueError("API response message content is not text")
    return validate_response(extract_json_object(content), batch)


def translate_with_retries(
    args: argparse.Namespace,
    api_key: str,
    batch: list[tuple[int, str]],
) -> dict[int, str]:
    last_error: Exception | None = None
    for attempt in range(1, args.retries + 1):
        try:
            return request_translation(
                args.api_base, api_key, args.model, batch, args.timeout
            )
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
            last_error = error
            if attempt == args.retries:
                break
            delay = min(30.0, 2 ** (attempt - 1)) + random.random()
            print(
                f"Batch failed ({attempt}/{args.retries}): {error}; "
                f"retrying in {delay:.1f}s",
                file=sys.stderr,
            )
            time.sleep(delay)
    raise RuntimeError(f"batch failed after {args.retries} attempts: {last_error}")


def render_output(source: str, items: list[Item], translations: dict[str, str]) -> str:
    chunks: list[str] = []
    cursor = 0
    for item in items:
        target_name = translations.get(item.source_name)
        if target_name is None:
            raise ValueError(f"missing translation for {item.source_name!r}")
        chunks.append(source[cursor : item.name_start])
        chunks.append(json.dumps(target_name, ensure_ascii=False))
        cursor = item.name_end
    chunks.append(source[cursor:])
    return "".join(chunks)


def main() -> int:
    args = parse_args()
    source = args.input.read_text(encoding="utf-8")
    items = parse_items(source)
    unique_names: dict[str, int] = {}
    for item in items:
        unique_names.setdefault(item.source_name, item.item_id)

    print(
        f"Parsed {len(items)} items, {len(unique_names)} unique names, "
        f"IDs {min(item.item_id for item in items)}..{max(item.item_id for item in items)}"
    )
    if args.dry_run:
        print("Dry run complete; no API request or output file was created.")
        return 0

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise ValueError(f"environment variable {args.api_key_env} is not set")

    translations = load_cache(args.cache)
    if args.retry_unchanged:
        unchanged = [
            source_name
            for source_name, target_name in translations.items()
            if source_name == target_name and not source_name.startswith("ItemName.")
        ]
        for source_name in unchanged:
            del translations[source_name]
        if unchanged:
            save_cache(args.cache, translations)
            print(f"Discarded {len(unchanged)} unchanged cached translations.")
    pending = [
        (item_id, source_name)
        for source_name, item_id in unique_names.items()
        if source_name not in translations
    ]
    if args.max_items is not None:
        pending = pending[: args.max_items]

    batches = [
        pending[offset : offset + args.batch_size]
        for offset in range(0, len(pending), args.batch_size)
    ]
    total_batches = len(batches)
    if batches:
        print(
            f"Translating {len(pending)} unique names in {total_batches} batches "
            f"with concurrency {min(args.concurrency, total_batches)}...",
            flush=True,
        )
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {
            executor.submit(translate_with_retries, args, api_key, batch): (
                batch_number,
                batch,
            )
            for batch_number, batch in enumerate(batches, start=1)
        }
        for future in as_completed(futures):
            batch_number, batch = futures[future]
            translated_by_id = future.result()
            for item_id, source_name in batch:
                translations[source_name] = translated_by_id[item_id]
            save_cache(args.cache, translations)
            print(
                f"Completed batch {batch_number}/{total_batches}; "
                f"cached {len(translations)}/{len(unique_names)} unique names",
                flush=True,
            )

    missing_names = [name for name in unique_names if name not in translations]
    if missing_names:
        print(
            f"Stopped with {len(missing_names)} untranslated unique names. "
            "Run again without --max-items to finish; the cache has been saved."
        )
        return 0

    output = render_output(source, items, translations)
    parsed_output = parse_items(output)
    if [item.item_id for item in parsed_output] != [item.item_id for item in items]:
        raise ValueError("generated output changed item IDs or item order")
    atomic_write_text(args.output, output)
    print(f"Wrote {len(items)} translated items to {args.output}")
    print(f"Translation cache: {args.cache}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
