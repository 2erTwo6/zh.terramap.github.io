#!/usr/bin/env python3
"""Translate src/tiles.ts with an OpenAI-compatible chat completion API."""

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


FIELD_RE = re.compile(
    r"^(?P<indent>\s*)(?P<field>name|variety):\s*"
    r"(?P<value>\"(?:\\.|[^\"\\])*\")",
    re.MULTILINE,
)
NAME_FIELD_RE = re.compile(r"^\s*name:\s*", re.MULTILINE)
VARIETY_FIELD_RE = re.compile(r"^\s*variety:\s*", re.MULTILINE)
TOP_LEVEL_ID_RE = re.compile(r"^    id:\s*(-?\d+),?", re.MULTILINE)

SYSTEM_PROMPT = """你是 Terraria（泰拉瑞亚）游戏本地化专家。请把方块、家具、植物、装饰物及其贴图变体名称翻译成简体中文。
要求：
1. 优先采用 Terraria 官方简体中文译名，保持材料、生态、家具系列和专有名词一致。
2. field 为 name 时翻译对象名称；field 为 variety 时翻译外观、颜色、尺寸、方向、状态或样式描述。
3. 只返回对应中文文本，不添加解释、注音、英文括注或无关标点。
4. 保留数字、A/B/C 等变体标记、坐标意义和必要符号；On/Off、Left/Right、Large/Small 等应翻译。
5. 除内部键、通用缩写或官方明确保留的品牌名外，不得直接照抄英文；专有名词应采用官方译名或合理音译。
6. 必须返回 JSON 对象，格式严格为 {"translations":[{"id":0,"text":"土块"}]}。
7. 每个输入 id 必须且只能出现一次，不得遗漏、修改或增加 id。"""


@dataclass(frozen=True)
class TextField:
    field: str
    source_text: str
    value_start: int
    value_end: int

    @property
    def key(self) -> str:
        return f"{self.field}\0{self.source_text}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use an LLM to hardcode Simplified Chinese tile names and varieties."
    )
    parser.add_argument("--input", type=Path, default=Path("src/tiles.ts"))
    parser.add_argument("--output", type=Path, default=Path("src/tiles.zh-CN.ts"))
    parser.add_argument(
        "--cache", type=Path, default=Path(".cache/tiles-zh-CN.json")
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
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--retries", type=int, default=6)
    parser.add_argument(
        "--max-texts",
        type=int,
        help="translate only this many unique field/text pairs for a small API test",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and report the source structure without calling the API",
    )
    parser.add_argument(
        "--retry-unchanged",
        action="store_true",
        help="discard cached translations identical to their English source",
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
    if args.max_texts is not None and args.max_texts < 1:
        parser.error("--max-texts must be at least 1")
    if not args.dry_run and not args.model:
        parser.error("--model or OPENAI_MODEL is required")
    if args.input.resolve() == args.output.resolve() and not args.overwrite_source:
        parser.error(
            "refusing to overwrite the source; choose another --output or pass "
            "--overwrite-source"
        )
    return args


def parse_fields(source: str) -> list[TextField]:
    fields = [
        TextField(
            field=match.group("field"),
            source_text=json.loads(match.group("value")),
            value_start=match.start("value"),
            value_end=match.end("value"),
        )
        for match in FIELD_RE.finditer(source)
    ]
    expected_names = len(NAME_FIELD_RE.findall(source))
    expected_varieties = len(VARIETY_FIELD_RE.findall(source))
    parsed_names = sum(field.field == "name" for field in fields)
    parsed_varieties = sum(field.field == "variety" for field in fields)
    if (
        not fields
        or parsed_names != expected_names
        or parsed_varieties != expected_varieties
    ):
        raise ValueError(
            "unsupported tiles.ts structure: "
            f"parsed {parsed_names}/{expected_names} name fields and "
            f"{parsed_varieties}/{expected_varieties} variety fields"
        )

    ids = parse_top_level_ids(source)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("tiles.ts has no top-level IDs or contains duplicate IDs")
    return fields


def parse_top_level_ids(source: str) -> list[int]:
    return [int(value) for value in TOP_LEVEL_ID_RE.findall(source)]


def load_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("translations"), dict):
        raise ValueError(f"unsupported cache format: {path}")
    translations = data["translations"]
    if not all(
        isinstance(key, str)
        and "\0" in key
        and isinstance(target, str)
        and target.strip()
        for key, target in translations.items()
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


def validate_response(
    data: dict[str, Any], batch: list[tuple[str, str, str]]
) -> dict[str, str]:
    rows = data.get("translations")
    if not isinstance(rows, list):
        raise ValueError("model response is missing a translations array")

    expected_ids = set(range(len(batch)))
    translated_by_id: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each translation must be an object")
        item_id = row.get("id")
        text = row.get("text")
        if not isinstance(item_id, int) or item_id not in expected_ids:
            raise ValueError(f"unexpected translation ID: {item_id!r}")
        if item_id in translated_by_id:
            raise ValueError(f"duplicate translation ID: {item_id}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"translation for ID {item_id} is empty")
        if "\n" in text or "\r" in text:
            raise ValueError(f"translation for ID {item_id} contains a newline")
        translated_by_id[item_id] = text.strip()

    missing = expected_ids - translated_by_id.keys()
    if missing:
        raise ValueError(f"model response omitted IDs: {sorted(missing)}")
    return {
        key: translated_by_id[item_id]
        for item_id, (key, _, _) in enumerate(batch)
    }


def request_translation(
    api_base: str,
    api_key: str,
    model: str,
    batch: list[tuple[str, str, str]],
    timeout: float,
) -> dict[str, str]:
    user_payload = {
        "texts": [
            {"id": item_id, "field": field, "text": text}
            for item_id, (_, field, text) in enumerate(batch)
        ]
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
    batch: list[tuple[str, str, str]],
) -> dict[str, str]:
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


def render_output(
    source: str, fields: list[TextField], translations: dict[str, str]
) -> str:
    chunks: list[str] = []
    cursor = 0
    for field in fields:
        target_text = translations.get(field.key)
        if target_text is None:
            raise ValueError(f"missing translation for {field.key!r}")
        chunks.append(source[cursor : field.value_start])
        chunks.append(json.dumps(target_text, ensure_ascii=False))
        cursor = field.value_end
    chunks.append(source[cursor:])
    return "".join(chunks)


def main() -> int:
    args = parse_args()
    source = args.input.read_text(encoding="utf-8")
    fields = parse_fields(source)
    source_ids = parse_top_level_ids(source)
    unique_fields: dict[str, TextField] = {}
    for field in fields:
        unique_fields.setdefault(field.key, field)

    name_count = sum(field.field == "name" for field in fields)
    variety_count = sum(field.field == "variety" for field in fields)
    unique_names = sum(field.field == "name" for field in unique_fields.values())
    unique_varieties = sum(
        field.field == "variety" for field in unique_fields.values()
    )
    print(
        f"Parsed {len(source_ids)} tiles, {name_count} name fields "
        f"({unique_names} unique), and {variety_count} variety fields "
        f"({unique_varieties} unique); IDs {min(source_ids)}..{max(source_ids)}"
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
            key
            for key, target_text in translations.items()
            if key.split("\0", 1)[1] == target_text
        ]
        for key in unchanged:
            del translations[key]
        if unchanged:
            save_cache(args.cache, translations)
            print(f"Discarded {len(unchanged)} unchanged cached translations.")

    pending = [
        (key, field.field, field.source_text)
        for key, field in unique_fields.items()
        if key not in translations
    ]
    if args.max_texts is not None:
        pending = pending[: args.max_texts]

    batches = [
        pending[offset : offset + args.batch_size]
        for offset in range(0, len(pending), args.batch_size)
    ]
    total_batches = len(batches)
    if batches:
        print(
            f"Translating {len(pending)} unique texts in {total_batches} batches "
            f"with concurrency {min(args.concurrency, total_batches)}...",
            flush=True,
        )
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {
            executor.submit(translate_with_retries, args, api_key, batch): batch_number
            for batch_number, batch in enumerate(batches, start=1)
        }
        for future in as_completed(futures):
            batch_number = futures[future]
            translations.update(future.result())
            save_cache(args.cache, translations)
            print(
                f"Completed batch {batch_number}/{total_batches}; "
                f"cached {len(translations)}/{len(unique_fields)} unique texts",
                flush=True,
            )

    missing_keys = [key for key in unique_fields if key not in translations]
    if missing_keys:
        print(
            f"Stopped with {len(missing_keys)} untranslated unique texts. "
            "Run again without --max-texts to finish; the cache has been saved."
        )
        return 0

    output = render_output(source, fields, translations)
    output_fields = parse_fields(output)
    if [field.field for field in output_fields] != [field.field for field in fields]:
        raise ValueError("generated output changed field count or order")
    if parse_top_level_ids(output) != source_ids:
        raise ValueError("generated output changed tile IDs or tile order")
    atomic_write_text(args.output, output)
    print(f"Wrote {len(fields)} translated fields to {args.output}")
    print(f"Translation cache: {args.cache}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
