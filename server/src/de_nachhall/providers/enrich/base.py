"""EnrichProvider 协议。

一次调用同时产出三样东西：新闻条目边界、条目标题、逐句中文翻译。
合并成一次是因为分章需要通读全文，而翻译也需要上下文 —— 拆成两次
调用等于让模型读两遍，没有收益。

三条硬约束（SPEC §4.1）：
  1. prompt 与 JSON Schema 只有一份，放在 contract.py，所有实现共享。
     换供应商不得改变输出契约。
  2. enrich 必须幂等 —— 重试时用同样的 sentences 应得到可用结果。
  3. 任何供应商失败都回落 NullEnricher，**不跨供应商重试**。
     自动换家会让「为什么这期翻译质量不一样」变得无法解释。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SentenceIn:
    """输入给模型的句子。只带 idx 与文本，不带时间戳 —— 模型用不上。"""

    idx: int
    text: str


@dataclass(frozen=True)
class ChapterOut:
    idx: int
    title: str | None
    start_sentence_idx: int
    end_sentence_idx: int


@dataclass(frozen=True)
class EnrichResult:
    chapters: list[ChapterOut]
    translations: dict[int, str] = field(default_factory=dict)
    # True 表示走了降级路径：无分章、无翻译，但 chunk 照常可切
    degraded: bool = False

    @property
    def has_titles(self) -> bool:
        return any(c.title for c in self.chapters)


class EnrichError(RuntimeError):
    """供应商调用失败。上层据此回落 NullEnricher，不重试第二家。"""


@runtime_checkable
class EnrichProvider(Protocol):
    name: str

    def enrich(self, sentences: Sequence[SentenceIn]) -> EnrichResult: ...
