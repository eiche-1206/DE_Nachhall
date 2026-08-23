"""所有 Enrich 供应商共享的 prompt 与 JSON Schema。

**这个文件是单一事实来源。** ClaudeEnricher 与 OpenAICompatEnricher
都从这里取 prompt 和 schema，谁都不许自己写一份 —— 否则换供应商时
输出契约会悄悄漂移，而漂移只会在数据入库后才被发现。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from de_nachhall.providers.enrich.base import ChapterOut, EnrichResult, SentenceIn

TOOL_NAME = "emit_chapters_and_translations"

SYSTEM_PROMPT = """\
你在为德语听说训练工具处理一期德语新闻的逐句转写。

任务有两件，一次完成：

1. 分章 —— 把句子按**新闻条目**切成若干章节。一期新闻通常由 4–6 条
   彼此独立的报道组成（如森林火灾、学校罢课、体育）。章节边界必须落在
   话题真正切换的地方，不要按时长平均分。给每章起一个德语标题，取自
   该条新闻的核心事实，8 个词以内。

2. 翻译 —— 把**每一句**翻成简体中文。面向 B2–C1 的德语学习者，翻译要
   准确、自然，不要逐词硬译，也不要意译到丢失信息。专有名词保留原文
   并在首次出现时括注中文。

硬性要求：
- 章节必须覆盖全部句子，不重叠、不留空隙。
- start_sentence_idx 与 end_sentence_idx 都是闭区间，用输入给的 idx。
- 第一章的 start 必须是最小 idx，最后一章的 end 必须是最大 idx。
- translations 必须包含每一个输入句子的 idx，一个都不能少。
"""

# 两家供应商共用。Claude 走 tool-use 的 input_schema，
# OpenAI 兼容端走 response_format 的 json_schema，结构相同。
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chapters": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "德语标题，8 词以内"},
                    "start_sentence_idx": {"type": "integer"},
                    "end_sentence_idx": {"type": "integer"},
                },
                "required": ["title", "start_sentence_idx", "end_sentence_idx"],
                "additionalProperties": False,
            },
        },
        "translations": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "idx": {"type": "integer"},
                    "zh": {"type": "string"},
                },
                "required": ["idx", "zh"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["chapters", "translations"],
    "additionalProperties": False,
}


def build_user_message(sentences: Sequence[SentenceIn]) -> str:
    """把句子编成模型可读的编号列表。"""
    lines = [f"{s.idx}\t{s.text}" for s in sentences]
    return (
        f"共 {len(sentences)} 句，格式为「idx<TAB>德语原文」：\n\n"
        + "\n".join(lines)
        + "\n\n请输出分章与逐句翻译。"
    )


class ContractViolation(ValueError):
    """模型输出不满足契约。调用方据此判定失败并回落降级路径。"""


def parse_and_validate(raw: dict[str, Any] | str, sentences: Sequence[SentenceIn]) -> EnrichResult:
    """解析模型输出并做**结构性**校验。

    校验的是契约本身，不是内容质量：覆盖完整、无重叠、无缺句。
    这些错一旦入库，前端会显示空白章节或缺失翻译，且难以定位。
    """
    data = json.loads(raw) if isinstance(raw, str) else raw

    idxs = [s.idx for s in sentences]
    if not idxs:
        return EnrichResult(chapters=[], translations={})
    lo, hi = min(idxs), max(idxs)

    raw_chapters = data.get("chapters") or []
    if not raw_chapters:
        raise ContractViolation("chapters 为空")

    chapters: list[ChapterOut] = []
    for i, c in enumerate(sorted(raw_chapters, key=lambda x: x["start_sentence_idx"])):
        start, end = int(c["start_sentence_idx"]), int(c["end_sentence_idx"])
        if start > end:
            raise ContractViolation(f"第 {i} 章 start({start}) > end({end})")
        if chapters and start != chapters[-1].end_sentence_idx + 1:
            prev_end = chapters[-1].end_sentence_idx
            raise ContractViolation(
                f"第 {i} 章与上一章不连续：上章止于 {prev_end}，本章始于 {start}"
            )
        title = (c.get("title") or "").strip() or None
        chapters.append(
            ChapterOut(idx=i, title=title, start_sentence_idx=start, end_sentence_idx=end)
        )

    if chapters[0].start_sentence_idx != lo:
        raise ContractViolation(f"首章未从 {lo} 开始，实际 {chapters[0].start_sentence_idx}")
    if chapters[-1].end_sentence_idx != hi:
        raise ContractViolation(f"末章未止于 {hi}，实际 {chapters[-1].end_sentence_idx}")

    translations: dict[int, str] = {}
    for t in data.get("translations") or []:
        zh = (t.get("zh") or "").strip()
        if zh:
            translations[int(t["idx"])] = zh

    missing = sorted(set(idxs) - translations.keys())
    if missing:
        preview = ", ".join(map(str, missing[:8]))
        more = f" 等 {len(missing)} 句" if len(missing) > 8 else ""
        raise ContractViolation(f"缺少句子的翻译：idx {preview}{more}")

    return EnrichResult(chapters=chapters, translations=translations)
