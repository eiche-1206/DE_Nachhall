"""降级实现。不调用任何 API。

这不是占位 —— 它是 PRD O8 的降级路径。LLM 失败时：
    单章节、无标题、无翻译，但 **chunk 照常可切、跟读照常可用**。
"""

from __future__ import annotations

from collections.abc import Sequence

from de_nachhall.providers.enrich.base import (
    ChapterOut,
    EnrichProvider,
    EnrichResult,
    SentenceIn,
)


class NullEnricher:
    name = "null"

    def enrich(self, sentences: Sequence[SentenceIn]) -> EnrichResult:
        if not sentences:
            return EnrichResult(chapters=[], translations={}, degraded=True)
        idxs = [s.idx for s in sentences]
        return EnrichResult(
            chapters=[
                ChapterOut(
                    idx=0,
                    title=None,
                    start_sentence_idx=min(idxs),
                    end_sentence_idx=max(idxs),
                )
            ],
            translations={},
            degraded=True,
        )


_: EnrichProvider = NullEnricher()
