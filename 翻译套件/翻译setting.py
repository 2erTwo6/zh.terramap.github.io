#!/usr/bin/env python3
"""
泰拉瑞亚地图查看器 settings.js 汉化脚本 (最终版 v2)
支持字段: Name, Anchor, Variety 及其他文本字段
"""

from __future__ import annotations

import re
import json
import time
import os
import sys
import hashlib
import shutil
import traceback
from datetime import datetime
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("✗ 请先安装 openai: pip install openai")
    sys.exit(1)

# ======================== 配置区 ========================
API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL = os.environ.get("MODEL", "deepseek-ai/DeepSeek-V3.2")

INPUT_FILE = "settings.js"
OUTPUT_FILE = "settings_cn.js"
CACHE_FILE = "translation_cache.json"
LOG_FILE = "translation_log.txt"
REVIEW_FILE = "translation_review.json"
BACKUP_DIR = "backups"

BATCH_SIZE = 50
MAX_RETRIES = 5
RETRY_BASE_DELAY = 3
REQUEST_INTERVAL = 1.5
MAX_TOKENS = 4096

TRANSLATION_MODE = "replace"

DRY_RUN = False
SKIP_CATEGORIES = []

# ---- 需要翻译的字段及其分类标签 ----
# 格式: (JS字段名, 缓存分类前缀, 翻译提示词描述)
TRANSLATABLE_FIELDS = [
    ("Name",    "",          "名称"),
    ("Anchor",  "Anchor",   "锚点方位"),
    ("Variety", "Variety",  "变体/样式描述"),
]

# ---- 固定词汇表（不调API，直接替换）----
# 适用于值域小且确定的字段，如 Anchor
STATIC_DICT = {
    # Anchor 方位
    "Bottom":       "底部",
    "Top":          "顶部",
    "Left":         "左侧",
    "Right":        "右侧",
    "Center":       "中间",
    "Wall":         "墙壁",
    "None":         "无",
    "Ground":       "地面",
    "Ceiling":      "天花板",
    "SolidSide":    "实心侧面",
    "AlternateTop": "备选顶部",
}
# ========================================================


def get_message_content(message) -> str:
    if message.content:
        return message.content
    if hasattr(message, 'reasoning_content') and message.reasoning_content:
        return message.reasoning_content
    if hasattr(message, 'text') and message.text:
        return message.text
    return ""


class TranslationLogger:
    def __init__(self, log_file: str):
        self.log_file = log_file
        self.start_time = datetime.now()
        self.api_calls = 0
        self.api_failures = 0
        self.tokens_used = 0
        self._write(f"\n{'=' * 60}")
        self._write(f"翻译会话开始: {self.start_time.isoformat()}")
        self._write(f"模型: {MODEL}")
        self._write(f"{'=' * 60}")

    def _write(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}"
        print(line)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def info(self, msg: str):    self._write(f"ℹ {msg}")
    def success(self, msg: str): self._write(f"✓ {msg}")
    def warning(self, msg: str): self._write(f"⚠ {msg}")
    def error(self, msg: str):   self._write(f"✗ {msg}")

    def api_call(self, tokens: int = 0):
        self.api_calls += 1
        self.tokens_used += tokens

    def api_failure(self):
        self.api_failures += 1

    def summary(self):
        elapsed = (datetime.now() - self.start_time).total_seconds()
        self._write(f"\n{'=' * 60}")
        self._write(f"会话总结:")
        self._write(f"  耗时: {elapsed:.1f}秒")
        self._write(f"  API调用: {self.api_calls}次 (失败{self.api_failures}次)")
        self._write(f"  Token消耗: ~{self.tokens_used}")
        self._write(f"{'=' * 60}")


class TranslationCache:
    def __init__(self, cache_file: str, logger: TranslationLogger):
        self.cache_file = cache_file
        self.logger = logger
        self.data = self._load()
        self.dirty = False

    def _load(self) -> dict:
        if not os.path.exists(self.cache_file):
            return {"_meta": {"version": 3, "created": datetime.now().isoformat()},
                    "translations": {}}
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "_meta" not in data:
                self.logger.warning("检测到v1缓存格式，自动迁移")
                return {
                    "_meta": {"version": 3, "migrated": datetime.now().isoformat()},
                    "translations": {f"_legacy::{k}": v for k, v in data.items()}
                }
            return data
        except json.JSONDecodeError:
            self.logger.error(f"缓存文件损坏: {self.cache_file}")
            bak = self.cache_file + ".bak"
            if os.path.exists(bak):
                self.logger.info("尝试从备份恢复缓存...")
                try:
                    with open(bak, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
            self.logger.warning("创建新缓存")
            return {"_meta": {"version": 3}, "translations": {}}

    def _make_key(self, category: str, name: str) -> str:
        return f"{category}::{name}"

    def get(self, category: str, name: str) -> str | None:
        key = self._make_key(category, name)
        result = self.data["translations"].get(key)
        if result is None:
            legacy_key = f"_legacy::{name}"
            result = self.data["translations"].get(legacy_key)
        return result

    def put(self, category: str, name: str, translation: str):
        key = self._make_key(category, name)
        self.data["translations"][key] = translation
        self.dirty = True

    def save(self):
        if not self.dirty:
            return
        self.data["_meta"]["last_saved"] = datetime.now().isoformat()
        self.data["_meta"]["count"] = len(self.data["translations"])
        tmp_file = self.cache_file + ".tmp"
        bak_file = self.cache_file + ".bak"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            with open(tmp_file, "r", encoding="utf-8") as f:
                json.load(f)
            if os.path.exists(self.cache_file):
                shutil.copy2(self.cache_file, bak_file)
            shutil.move(tmp_file, self.cache_file)
            self.dirty = False
        except Exception as e:
            self.logger.error(f"缓存保存失败: {e}")
            if os.path.exists(tmp_file):
                os.remove(tmp_file)

    @property
    def size(self) -> int:
        return len(self.data["translations"])


def compute_file_hash(filepath: str) -> str:
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_file(filepath: str, backup_dir: str, logger: TranslationLogger):
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = Path(filepath).name
    backup_path = os.path.join(backup_dir, f"{filename}.{timestamp}.bak")
    shutil.copy2(filepath, backup_path)
    logger.info(f"已备份: {backup_path}")
    return backup_path


def extract_field_values(content: str, field_name: str, logger: TranslationLogger) -> list[str]:
    """提取指定字段的所有唯一值"""
    pattern = rf'''{field_name}:\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')'''
    matches = re.findall(pattern, content)

    seen = set()
    unique = []
    for m in matches:
        val = m[0] if m[0] else m[1]
        val = val.replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')
        if val and val not in seen:
            seen.add(val)
            unique.append(val)

    return unique


def extract_names_by_section(content: str, logger: TranslationLogger) -> dict[str, list[str]]:
    """提取 Name 字段（按 section 分类）"""
    sections_config = [
        ("GlobalColors", "全局颜色/环境名称"),
        ("Tiles", "方块/图格名称"),
        ("Walls", "墙壁名称"),
        ("Items", "物品名称"),
        ("Npcs", "NPC名称"),
        ("ItemPrefix", "物品前缀/修饰词"),
    ]

    categories = {}

    for section_key, category_name in sections_config:
        pattern = rf'{section_key}\s*:\s*\['
        match = re.search(pattern, content)
        if not match:
            logger.warning(f"未找到 section: {section_key}")
            continue

        start = match.end()
        bracket_depth = 1
        pos = start
        in_string = False
        string_char = None
        escape_next = False

        while pos < len(content) and bracket_depth > 0:
            ch = content[pos]
            if escape_next:
                escape_next = False
                pos += 1
                continue
            if ch == '\\':
                escape_next = True
                pos += 1
                continue
            if in_string:
                if ch == string_char:
                    in_string = False
            else:
                if ch in ('"', "'"):
                    in_string = True
                    string_char = ch
                elif ch == '[':
                    bracket_depth += 1
                elif ch == ']':
                    bracket_depth -= 1
            pos += 1

        section_content = content[start:pos - 1]
        name_pattern = r'''Name:\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')'''
        matches = re.findall(name_pattern, section_content)

        seen = set()
        unique_names = []
        for m in matches:
            name = m[0] if m[0] else m[1]
            name = name.replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')
            if name not in seen:
                seen.add(name)
                unique_names.append(name)

        categories[category_name] = unique_names
        logger.info(f"  {category_name} ({section_key}): {len(unique_names)} 条唯一名称")

    return categories


def extract_extra_fields(content: str, logger: TranslationLogger) -> dict[str, list[str]]:
    """提取 Name 以外的可翻译字段（Anchor, Variety 等）"""
    extra_categories = {}

    for field_name, cache_prefix, desc in TRANSLATABLE_FIELDS:
        if field_name == "Name":
            continue  # Name 由 extract_names_by_section 单独处理

        values = extract_field_values(content, field_name, logger)

        # 过滤掉静态词典已覆盖的
        need_translate = [v for v in values if v not in STATIC_DICT]
        static_hit = len(values) - len(need_translate)

        category_key = f"{desc}（{field_name}）"
        extra_categories[category_key] = need_translate

        logger.info(f"  {category_key}: {len(values)} 条唯一值"
                     f"（静态词典命中 {static_hit}，需API翻译 {len(need_translate)}）")

    return extra_categories


def validate_translation_response(
    names: list[str],
    translations: dict[str, str],
    logger: TranslationLogger
) -> dict[str, str]:
    validated = {}
    issues = []

    for name in names:
        if name not in translations:
            issues.append(f"缺失翻译: '{name}'")
            validated[name] = name
            continue

        translated = translations[name]

        if name and not translated:
            issues.append(f"空翻译: '{name}' → ''")
            validated[name] = name
            continue

        dangerous_patterns = ['\n', '\r', '\x00']
        has_danger = False
        for dp in dangerous_patterns:
            if dp in translated:
                issues.append(f"危险字符: '{name}' → '{translated[:50]}'")
                has_danger = True
                break
        if has_danger:
            validated[name] = name
            continue

        if len(name) > 3 and len(translated) > len(name) * 5:
            issues.append(f"长度异常: '{name}'({len(name)}) → '{translated[:50]}'({len(translated)})")

        # 检查括号丢失并自动补全
        if '(' in name and '(' not in translated and '（' not in translated:
            paren_match = re.search(r'\(([^)]*)\)', name)
            if paren_match:
                inner = paren_match.group(1)
                translated = f"{translated}（{inner}）"
                issues.append(f"括号补全: '{name}' → '{translated}'")

        validated[name] = translated

    if issues:
        logger.warning(f"校验发现 {len(issues)} 个问题:")
        for issue in issues[:10]:
            logger.warning(f"  - {issue}")
        if len(issues) > 10:
            logger.warning(f"  ... 共 {len(issues)} 个")

    return validated


def parse_ai_response(response_text: str, names: list[str], logger: TranslationLogger) -> dict[str, str] | None:
    text = response_text.strip()

    # 策略1: 直接解析
    try:
        result = json.loads(text)
        parsed = _extract_from_parsed(result, names)
        if parsed and len(parsed) >= len(names) * 0.5:
            return parsed
    except json.JSONDecodeError:
        pass

    # 策略2: markdown 代码块
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if json_match:
        try:
            result = json.loads(json_match.group(1))
            parsed = _extract_from_parsed(result, names)
            if parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    # 策略3: 找 { } 范围
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace >= 0 and last_brace > first_brace:
        try:
            result = json.loads(text[first_brace:last_brace + 1])
            parsed = _extract_from_parsed(result, names)
            if parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    # 策略4: 修复常见 JSON 错误
    try:
        cleaned = re.sub(r',\s*([}\]])', r'\1', text)
        cleaned = re.sub(r"'", '"', cleaned)
        first_brace = cleaned.find('{')
        last_brace = cleaned.rfind('}')
        if first_brace >= 0 and last_brace > first_brace:
            result = json.loads(cleaned[first_brace:last_brace + 1])
            parsed = _extract_from_parsed(result, names)
            if parsed:
                logger.warning("通过 JSON 修复策略解析成功")
                return parsed
    except Exception:
        pass

    # 策略5: 从思维链提取
    json_blocks = re.findall(r'\{[^{}]*"translations"[^{}]*\[[\s\S]*?\]\s*\}', text)
    for block in json_blocks:
        try:
            result = json.loads(block)
            parsed = _extract_from_parsed(result, names)
            if parsed:
                logger.warning("从思维链中提取到翻译JSON")
                return parsed
        except json.JSONDecodeError:
            continue

    logger.error(f"所有解析策略均失败，原始返回前300字符: {text[:300]}")
    return None


def _extract_from_parsed(result: dict, names: list[str]) -> dict[str, str] | None:
    translations = {}

    if "translations" in result and isinstance(result["translations"], list):
        for item in result["translations"]:
            if isinstance(item, dict):
                en = item.get("en", item.get("original", item.get("name", "")))
                zh = item.get("zh", item.get("translation", item.get("cn", "")))
                if en:
                    translations[en] = zh
        if translations:
            return translations

    if all(isinstance(v, str) for v in result.values()):
        return dict(result)

    for key in ("results", "data", "output"):
        if key in result and isinstance(result[key], dict):
            sub = result[key]
            if all(isinstance(v, str) for v in sub.values()):
                return dict(sub)

    return translations if translations else None


def translate_batch_safe(
    client: OpenAI,
    names: list[str],
    category: str,
    logger: TranslationLogger,
    cache: TranslationCache
) -> dict[str, str]:
    system_prompt = f"""你是泰拉瑞亚(Terraria)游戏的专业翻译员。请将游戏中的英文文本翻译为简体中文。

当前翻译的类别是：「{category}」

要求：
1. 使用泰拉瑞亚官方中文翻译（参考Steam中文版/Wiki）
2. 保持专有名词准确性
3. 空字符串保持为空
4. 数量必须与输入完全一致，顺序一致
5. 如果原文包含括号如 "Name (Variant)"，翻译后必须保留括号，使用中文括号，如 "名称（变体）"
6. 对于方位词如 Top/Bottom/Left/Right 翻译为 顶部/底部/左侧/右侧
7. 对于描述性短语要翻译完整，如 "Right Indent A" → "右缩进 A"

严格返回JSON格式：
{{"translations": [{{"en": "原文1", "zh": "译文1"}}, {{"en": "原文2", "zh": "译文2"}}]}}

注意：只返回JSON，不要返回任何其他内容。"""

    names_list = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(names))
    user_prompt = f"翻译以下泰拉瑞亚的「{category}」（共{len(names)}条）：\n\n{names_list}"

    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"    API调用 (尝试 {attempt + 1}/{MAX_RETRIES})...")

            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=MAX_TOKENS,
                timeout=120,
            )

            tokens = 0
            if response.usage:
                tokens = response.usage.total_tokens
            logger.api_call(tokens)

            raw_text = get_message_content(response.choices[0].message)
            if not raw_text:
                raise ValueError("API返回空内容")

            logger.info(f"    收到响应: {len(raw_text)} 字符, {tokens} tokens")

            translations = parse_ai_response(raw_text, names, logger)
            if translations is None:
                raise ValueError("无法解析API返回")

            validated = validate_translation_response(names, translations, logger)

            coverage = sum(1 for n in names if n in validated and validated[n] != n) / max(len(names), 1)
            if coverage < 0.3 and len(names) > 5:
                logger.warning(f"    翻译覆盖率过低: {coverage:.0%}")
                if attempt < MAX_RETRIES - 1:
                    logger.info(f"    重试以获取更好的结果...")
                    time.sleep(RETRY_BASE_DELAY)
                    continue

            return validated

        except Exception as e:
            last_error = e
            logger.api_failure()
            logger.error(f"    失败: {type(e).__name__}: {e}")
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.info(f"    等待 {delay}s 后重试...")
                time.sleep(delay)

    logger.error(f"  批次翻译彻底失败 ({last_error})，使用降级策略")

    if len(names) > 10:
        logger.info(f"  降级: 拆分为每批10条重试...")
        result = {}
        for i in range(0, len(names), 10):
            sub_batch = names[i:i + 10]
            try:
                sub_result = translate_batch_safe(client, sub_batch, category, logger, cache)
                result.update(sub_result)
                for name in sub_batch:
                    if name in sub_result:
                        cache.put(category, name, sub_result[name])
                cache.save()
                time.sleep(REQUEST_INTERVAL)
            except Exception:
                for name in sub_batch:
                    result[name] = name
        return result

    return {name: name for name in names}


def replace_field_values(
    content: str,
    field_name: str,
    translation_map: dict[str, str],
    logger: TranslationLogger
) -> str:
    """替换指定字段的值"""
    replacement_count = 0

    def replace_match(match):
        nonlocal replacement_count
        full_match = match.group(0)
        prefix = match.group(1)
        quote = match.group(2)
        original = match.group(3)

        if quote == '"':
            real_name = original.replace('\\"', '"').replace('\\\\', '\\')
        else:
            real_name = original.replace("\\'", "'").replace('\\\\', '\\')

        translated = translation_map.get(real_name)
        if translated is None or translated == real_name:
            return full_match

        if quote == '"':
            escaped = translated.replace('\\', '\\\\').replace('"', '\\"')
        else:
            escaped = translated.replace('\\', '\\\\').replace("'", "\\'")

        replacement_count += 1
        return f'{prefix}{quote}{escaped}{quote}'

    pattern = rf'''({field_name}:\s*)(["'])((?:(?!\2|\\).|\\.)*)\2'''
    result = re.sub(pattern, replace_match, content)

    logger.info(f"  字段 {field_name}: 替换 {replacement_count} 处")
    return result


def verify_js_integrity(original: str, modified: str, logger: TranslationLogger) -> bool:
    issues = []

    # 花括号、方括号：严格检查
    for char, counter_char, name in [
        ('{', '}', '花括号'),
        ('[', ']', '方括号'),
    ]:
        orig_open = original.count(char)
        orig_close = original.count(counter_char)
        mod_open = modified.count(char)
        mod_close = modified.count(counter_char)
        if orig_open != mod_open or orig_close != mod_close:
            issues.append(f"{name}数量变化: 原文({orig_open}/{orig_close}) → 修改后({mod_open}/{mod_close})")
        else:
            logger.info(f"  ✓ {name}: {orig_open}/{orig_close}")

    # 半角圆括号：允许减少（翻译为全角是正常行为）
    orig_po, orig_pc = original.count('('), original.count(')')
    mod_po, mod_pc = modified.count('('), modified.count(')')
    if mod_po > orig_po or mod_pc > orig_pc:
        issues.append(f"半角圆括号异常增加: ({orig_po}/{orig_pc}) → ({mod_po}/{mod_pc})")
    elif mod_po < orig_po:
        lost = orig_po - mod_po
        logger.info(f"  ✓ 半角圆括号: {orig_po} → {mod_po}（{lost}个被翻译为全角，正常）")
    else:
        logger.info(f"  ✓ 半角圆括号: {orig_po}/{orig_pc}")

    # 关键结构
    for keyword in ["var settings", "GlobalColors", "Tiles", "Walls", "Items", "Npcs",
                     "ItemPrefix", "hexToRgb", "function"]:
        if keyword in original and keyword not in modified:
            issues.append(f"关键结构丢失: {keyword}")

    structural_ok = all(kw in modified for kw in
                        ["var settings", "GlobalColors", "Tiles", "Walls", "Items", "Npcs", "ItemPrefix"]
                        if kw in original)
    if structural_ok:
        logger.info(f"  ✓ 关键结构完整")

    # Name 字段数量
    orig_names = len(re.findall(r'Name:', original))
    mod_names = len(re.findall(r'Name:', modified))
    if orig_names != mod_names:
        issues.append(f"Name字段数量变化: {orig_names} → {mod_names}")
    else:
        logger.info(f"  ✓ Name字段: {orig_names}")

    # 其他翻译字段数量
    for field_name, _, _ in TRANSLATABLE_FIELDS:
        if field_name == "Name":
            continue
        orig_c = len(re.findall(rf'{field_name}:', original))
        mod_c = len(re.findall(rf'{field_name}:', modified))
        if orig_c != mod_c:
            issues.append(f"{field_name}字段数量变化: {orig_c} → {mod_c}")
        elif orig_c > 0:
            logger.info(f"  ✓ {field_name}字段: {orig_c}")

    # 文件大小
    size_ratio = len(modified) / max(len(original), 1)
    if size_ratio < 0.5 or size_ratio > 3.0:
        issues.append(f"文件大小异常: 原{len(original)} → 现{len(modified)} (比率{size_ratio:.2f})")
    else:
        logger.info(f"  ✓ 文件大小: {len(original):,} → {len(modified):,} (×{size_ratio:.2f})")

    if issues:
        logger.error(f"完整性校验发现 {len(issues)} 个问题:")
        for issue in issues:
            logger.error(f"  ✗ {issue}")
        return False

    logger.success("完整性校验通过 ✓")
    return True


def generate_review_file(
    all_categories: dict[str, list[str]],
    all_maps: dict[str, dict[str, str]],
    review_file: str,
    logger: TranslationLogger
):
    review_data = {
        "_说明": "此文件用于人工审查翻译质量",
        "_生成时间": datetime.now().isoformat(),
        "categories": {}
    }

    for category, names in all_categories.items():
        tmap = all_maps.get(category, {})
        items = []
        for name in names:
            translated = tmap.get(name, name)
            item = {"en": name, "zh": translated}
            if name == translated and name:
                item["_status"] = "未翻译"
            items.append(item)

        review_data["categories"][category] = {
            "total": len(items),
            "translated": sum(1 for it in items if it.get("_status") != "未翻译" or not it["en"]),
            "items": items
        }

    with open(review_file, "w", encoding="utf-8") as f:
        json.dump(review_data, f, ensure_ascii=False, indent=2)
    logger.info(f"审查文件已生成: {review_file}")


def translate_category(
    client: OpenAI,
    category: str,
    names: list[str],
    cache: TranslationCache,
    logger: TranslationLogger,
    static_dict: dict[str, str] | None = None,
) -> dict[str, str]:
    """翻译单个类别，返回 {原文: 译文} 映射"""
    translation_map = {}

    if category in SKIP_CATEGORIES:
        logger.info(f"跳过类别: {category}")
        for name in names:
            translation_map[name] = name
        return translation_map

    logger.info(f"\n{'─' * 50}")
    logger.info(f"📝 类别: {category} ({len(names)} 条)")

    to_translate = []
    for name in names:
        # 1. 先查静态词典
        if static_dict and name in static_dict:
            translation_map[name] = static_dict[name]
            continue
        # 2. 再查缓存
        cached = cache.get(category, name)
        if cached is not None:
            translation_map[name] = cached
        else:
            to_translate.append(name)

    static_hits = sum(1 for n in names if static_dict and n in static_dict) if static_dict else 0
    cache_hits = len(names) - len(to_translate) - static_hits
    logger.info(f"  静态词典: {static_hits}, 缓存命中: {cache_hits}, 需API翻译: {len(to_translate)}")

    if not to_translate:
        logger.success(f"  全部已有翻译 ✓")
        return translation_map

    total_batches = (len(to_translate) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(to_translate), BATCH_SIZE):
        batch = to_translate[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1

        logger.info(f"  批次 {batch_num}/{total_batches} ({len(batch)}条)")

        translations = translate_batch_safe(client, batch, category, logger, cache)

        for name in batch:
            translated = translations.get(name, name)
            translation_map[name] = translated
            cache.put(category, name, translated)

        cache.save()
        logger.success(f"  批次 {batch_num} 完成，缓存已保存")

        samples = [(n, translations.get(n, n)) for n in batch[:5]]
        for en, zh in samples:
            marker = "✓" if en != zh else "○"
            logger.info(f"    {marker} 「{en}」→「{zh}」")
        if len(batch) > 5:
            tc = sum(1 for n in batch if translations.get(n, n) != n)
            logger.info(f"    ... 共 {len(batch)} 条, 已翻译 {tc} 条")

        if i + BATCH_SIZE < len(to_translate):
            time.sleep(REQUEST_INTERVAL)

    return translation_map


def main():
    logger = TranslationLogger(LOG_FILE)
    logger.info("🎮 泰拉瑞亚 settings.js 汉化工具 (最终版 v2)")
    logger.info(f"配置: MODEL={MODEL}")
    logger.info(f"配置: BATCH_SIZE={BATCH_SIZE}, MODE={TRANSLATION_MODE}")
    logger.info(f"翻译字段: {', '.join(f[0] for f in TRANSLATABLE_FIELDS)}")

    # ---- 前置检查 ----
    if not os.path.exists(INPUT_FILE):
        logger.error(f"找不到输入文件: {INPUT_FILE}")
        logger.error(f"当前工作目录: {os.getcwd()}")
        sys.exit(1)

    if not API_KEY:
        logger.error("请设置 API_KEY（环境变量 OPENAI_API_KEY 或修改脚本配置区）")
        sys.exit(1)

    # ---- 备份 ----
    file_hash = compute_file_hash(INPUT_FILE)
    logger.info(f"输入文件 MD5: {file_hash}")
    backup_path = backup_file(INPUT_FILE, BACKUP_DIR, logger)

    # ---- 读取文件 ----
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    logger.info(f"文件大小: {len(content):,} 字符, {content.count(chr(10)) + 1:,} 行")

    # ---- 提取所有需要翻译的内容 ----
    logger.info("\n提取各字段内容...")

    # Name 字段（按 section 细分）
    logger.info("─ Name 字段（按 section 分类）:")
    name_categories = extract_names_by_section(content, logger)

    # 其他字段（Anchor, Variety 等）
    logger.info("─ 其他可翻译字段:")
    extra_categories = extract_extra_fields(content, logger)

    total_unique = sum(len(v) for v in name_categories.values()) + sum(len(v) for v in extra_categories.values())
    static_covered = sum(1 for cat_vals in extra_categories.values() for v in cat_vals if v in STATIC_DICT)
    logger.info(f"\n共计 {total_unique} 条唯一文本（静态词典覆盖 {len(STATIC_DICT)} 词）")

    if DRY_RUN:
        logger.info("\nDRY_RUN 模式，展示提取结果:")
        for cat, names in {**name_categories, **extra_categories}.items():
            logger.info(f"  {cat}:")
            for n in names[:10]:
                static_mark = " [静态]" if n in STATIC_DICT else ""
                logger.info(f"    - {n}{static_mark}")
            if len(names) > 10:
                logger.info(f"    ... 等 {len(names)} 条")
        return

    # ---- 初始化 ----
    cache = TranslationCache(CACHE_FILE, logger)
    logger.info(f"缓存已加载: {cache.size} 条")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    # ---- 测试 API ----
    logger.info("测试 API 连通性...")
    try:
        test_resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user",
                       "content": '将 "Dirt Block" 翻译为泰拉瑞亚中文，只回复：{"zh":"译文"}'}],
            max_tokens=MAX_TOKENS,
            timeout=30,
        )
        test_content = get_message_content(test_resp.choices[0].message).strip()
        if test_content:
            zh_match = re.search(r'[\u4e00-\u9fff]+', test_content)
            display = zh_match.group(0) if zh_match else test_content[:100]
            logger.success(f"API 连通: Dirt Block → {display}")
        else:
            logger.warning("API 连通但返回为空，继续...")
        if test_resp.usage:
            logger.api_call(test_resp.usage.total_tokens)
    except Exception as e:
        logger.error(f"API 连通测试失败: {e}")
        sys.exit(1)

    # ---- 翻译所有类别 ----
    # 合并所有翻译映射（按字段分组）
    all_categories = {}   # 用于审查文件
    field_maps = {}       # field_name → {原文: 译文}

    # 翻译 Name 字段
    name_map = {}
    for category, names in name_categories.items():
        cat_map = translate_category(client, category, names, cache, logger)
        name_map.update(cat_map)
        all_categories[category] = names
    field_maps["Name"] = name_map

    # 翻译其他字段
    for field_name, cache_prefix, desc in TRANSLATABLE_FIELDS:
        if field_name == "Name":
            continue

        category_key = f"{desc}（{field_name}）"
        names = extra_categories.get(category_key, [])

        if not names:
            logger.info(f"\n{category_key}: 无需API翻译的内容")
            # 静态词典的也要放进 field_maps
            field_maps[field_name] = dict(STATIC_DICT)
            continue

        # 用带前缀的缓存分类避免跨字段冲突
        actual_category = f"{cache_prefix}_{desc}" if cache_prefix else desc

        cat_map = translate_category(
            client, category_key, names, cache, logger,
            static_dict=STATIC_DICT
        )

        # 合并静态词典
        merged = dict(STATIC_DICT)
        merged.update(cat_map)
        field_maps[field_name] = merged
        all_categories[category_key] = names

    # ---- 替换文件内容 ----
    logger.info(f"\n{'─' * 50}")
    logger.info("替换各字段值...")
    new_content = content

    for field_name, _, _ in TRANSLATABLE_FIELDS:
        tmap = field_maps.get(field_name, {})
        if tmap:
            new_content = replace_field_values(new_content, field_name, tmap, logger)

    # ---- 完整性校验 ----
    logger.info("\n执行完整性校验...")
    integrity_ok = verify_js_integrity(content, new_content, logger)

    if not integrity_ok:
        logger.error("完整性校验失败！")
        emergency_output = OUTPUT_FILE + ".UNSAFE.js"
        with open(emergency_output, "w", encoding="utf-8") as f:
            f.write(new_content)
        logger.error(f"结果已保存到 {emergency_output}，请人工检查")
        logger.warning(f"原文件备份在: {backup_path}")
    else:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(new_content)
        logger.success(f"输出文件: {OUTPUT_FILE}")

    # ---- 审查文件 ----
    all_maps = {}
    for cat in all_categories:
        # 找对应的 field_map
        for fn, _, desc in TRANSLATABLE_FIELDS:
            category_key = f"{desc}（{fn}）"
            if cat == category_key:
                all_maps[cat] = field_maps.get(fn, {})
                break
        else:
            all_maps[cat] = field_maps.get("Name", {})

    generate_review_file(all_categories, all_maps, REVIEW_FILE, logger)

    # ---- 最终统计 ----
    cn_pattern = re.compile(r'[\u4e00-\u9fff]')
    stats = []
    for field_name, _, desc in TRANSLATABLE_FIELDS:
        field_values = re.findall(
            rf'''{field_name}:\s*["']([^"']*?)["']''', new_content
        )
        total = len(field_values)
        cn = sum(1 for v in field_values if cn_pattern.search(v))
        if total > 0:
            stats.append((field_name, desc, total, cn))

    logger.info(f"\n{'═' * 50}")
    logger.info(f"📊 最终统计:")
    for field_name, desc, total, cn in stats:
        rate = cn / max(total, 1) * 100
        logger.info(f"  {field_name}({desc}): {total}处, 含中文{cn}处, 汉化率{rate:.1f}%")

    total_all = sum(s[2] for s in stats)
    cn_all = sum(s[3] for s in stats)
    logger.info(f"  ────────────────────────")
    logger.info(f"  总计: {total_all}处, 含中文{cn_all}处, 汉化率{cn_all / max(total_all, 1) * 100:.1f}%")
    logger.info(f"  完整性: {'✓ 通过' if integrity_ok else '✗ 失败'}")
    logger.summary()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠ 用户中断，下次运行将从缓存继续")
    except Exception as e:
        print(f"\n\n✗ 未预期的错误: {e}")
        traceback.print_exc()
        print("缓存文件应已保存，下次运行可继续")