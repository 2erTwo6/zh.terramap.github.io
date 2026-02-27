#!/usr/bin/env python3
"""
泰拉瑞亚地图查看器 names.js 汉化脚本
用法：
  1. 配置下方的 API 参数
  2. 将原始 names.js 放在同目录下
  3. python translate_names.py
  4. 输出 names_cn.js
"""

import re
import json
import time
import os
import requests
from pathlib import Path

# ============== 配置区 ==============
API_URL = "https://api.siliconflow.cn/v1/chat/completions"  # 你的 LLM API 地址
API_KEY = ""                           # 你的 API Key
MODEL = "deepseek-ai/DeepSeek-V3.2"                                          # 模型名称

INPUT_FILE = "names.js"
OUTPUT_FILE = "names_cn.js"
PROGRESS_FILE = "translate_progress.json"  # 断点续传进度文件

BATCH_SIZE = 80        # 每批处理多少行（根据模型上下文窗口调整）
MAX_RETRIES = 3        # 每批最大重试次数
RETRY_DELAY = 5        # 重试间隔（秒）
REQUEST_DELAY = 1      # 每批请求间隔（秒），防止限流
# ====================================


def parse_names_js(filepath: str) -> list[dict]:
    """
    解析 names.js，提取每一行的结构信息。
    返回列表，每个元素：
      { "type": "entry", "key": "BloodMoonMonolith", "value": "Blood Moon Monolith", "raw": '  BloodMoonMonolith: "Blood Moon Monolith",' }
      或
      { "type": "other", "raw": "const names = {" }
    """
    lines = Path(filepath).read_text(encoding="utf-8").splitlines()
    parsed = []
    # 匹配形如：  SomeKey: "Some Value",
    pattern = re.compile(r'^(\s*)(\w+):\s*"((?:[^"\\]|\\.)*)"(,?)(.*)$')

    for line in lines:
        m = pattern.match(line)
        if m:
            indent, key, value, comma, trailing = m.groups()
            parsed.append({
                "type": "entry",
                "indent": indent,
                "key": key,
                "value": value,
                "comma": comma,
                "trailing": trailing,
                "raw": line,
            })
        else:
            parsed.append({
                "type": "other",
                "raw": line,
            })
    return parsed


def build_batch_prompt(entries: list[dict]) -> str:
    """构建发给 LLM 的翻译提示词"""
    lines = []
    for e in entries:
        lines.append(f'{e["key"]}|{e["value"]}')

    entries_text = "\n".join(lines)

    prompt = f"""你是泰拉瑞亚(Terraria)游戏的专业翻译员。请将下面的英文物品/NPC/方块名称翻译为泰拉瑞亚官方简体中文译名。

重要规则：
1. 严格使用泰拉瑞亚官方中文版的译名，不要自己编造翻译
2. 如果是专有名词（如联动内容 Palworld、跨界物品等）且你不确定官方译名，保留英文原文
3. 如果是 NPC 名字（如人名），且无官方中文译名，保留英文原文
4. 输出格式必须严格为：每行 "key|中文翻译"，不要加任何额外解释
5. 行数必须与输入完全一致，不要遗漏任何行
6. Music Box (XXX) 翻译为 "音乐盒 (XXX中文)"

输入：
{entries_text}

输出："""

    return prompt


def call_llm(prompt: str) -> str:
    """调用 LLM API"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,  # 低温度，尽量确定性输出
        "max_tokens": 8192,
    }
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def parse_llm_response(response: str, expected_keys: list[str]) -> dict[str, str]:
    """
    解析 LLM 返回的 key|中文翻译 格式。
    返回 {key: 中文翻译} 字典。
    """
    translations = {}
    lines = response.strip().splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 尝试解析 key|value 格式
        if "|" in line:
            parts = line.split("|", 1)
            key = parts[0].strip()
            value = parts[1].strip()
            # 去掉可能的引号
            value = value.strip('"').strip("'")
            translations[key] = value

    return translations


def load_progress() -> dict[str, str]:
    """加载已有翻译进度"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_progress(progress: dict[str, str]):
    """保存翻译进度"""
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def main():
    print(f"📖 解析 {INPUT_FILE} ...")
    parsed = parse_names_js(INPUT_FILE)

    entries = [p for p in parsed if p["type"] == "entry"]
    print(f"📊 共找到 {len(entries)} 个词条，{len(parsed)} 行总计")

    # 加载已有进度
    progress = load_progress()
    print(f"📂 已有翻译进度：{len(progress)} 条")

    # 找出还需要翻译的
    todo = [e for e in entries if e["key"] not in progress]
    print(f"📝 待翻译：{len(todo)} 条")

    if todo:
        # 分批处理
        batches = [todo[i:i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]
        print(f"📦 分为 {len(batches)} 批，每批 {BATCH_SIZE} 条\n")

        for batch_idx, batch in enumerate(batches):
            print(f"🔄 正在处理第 {batch_idx + 1}/{len(batches)} 批 "
                  f"({len(batch)} 条)...")

            prompt = build_batch_prompt(batch)
            expected_keys = [e["key"] for e in batch]

            for retry in range(MAX_RETRIES):
                try:
                    response = call_llm(prompt)
                    translations = parse_llm_response(response, expected_keys)

                    # 检查是否所有 key 都有翻译
                    missing = [k for k in expected_keys if k not in translations]
                    if missing:
                        print(f"  ⚠️ 缺少 {len(missing)} 个翻译: {missing[:5]}...")
                        if retry < MAX_RETRIES - 1:
                            print(f"  🔁 重试中...")
                            time.sleep(RETRY_DELAY)
                            continue
                        else:
                            # 最后一次重试仍缺少，用原文填充
                            print(f"  ⚠️ 使用原文填充缺失项")
                            for e in batch:
                                if e["key"] not in translations:
                                    translations[e["key"]] = e["value"]

                    # 合并到进度
                    progress.update(translations)
                    save_progress(progress)

                    translated_count = len([k for k in expected_keys if k in translations])
                    print(f"  ✅ 成功翻译 {translated_count}/{len(batch)} 条")
                    break

                except Exception as ex:
                    print(f"  ❌ 出错: {ex}")
                    if retry < MAX_RETRIES - 1:
                        print(f"  🔁 {RETRY_DELAY}秒后重试...")
                        time.sleep(RETRY_DELAY)
                    else:
                        print(f"  ❌ 跳过此批次，使用原文")
                        for e in batch:
                            if e["key"] not in progress:
                                progress[e["key"]] = e["value"]
                        save_progress(progress)

            time.sleep(REQUEST_DELAY)

    # 生成输出文件
    print(f"\n📝 生成 {OUTPUT_FILE} ...")
    output_lines = []
    for p in parsed:
        if p["type"] == "entry":
            key = p["key"]
            cn_value = progress.get(key, p["value"])
            # 转义双引号
            cn_value = cn_value.replace('\\', '\\\\').replace('"', '\\"')
            line = f'{p["indent"]}{key}: "{cn_value}"{p["comma"]}{p["trailing"]}'
            output_lines.append(line)
        else:
            output_lines.append(p["raw"])

    Path(OUTPUT_FILE).write_text("\n".join(output_lines), encoding="utf-8")

    print(f"\n🎉 完成！")
    print(f"   输入: {INPUT_FILE} ({len(entries)} 个词条)")
    print(f"   输出: {OUTPUT_FILE}")
    print(f"   进度: {PROGRESS_FILE}")
    print(f"\n💡 确认翻译无误后，将 {OUTPUT_FILE} 重命名为 {INPUT_FILE} 即可使用")


if __name__ == "__main__":
    main()
