"""enriching —— 分章、章节标题、逐句中文翻译，然后按真实章节重切 chunk。

**这一阶段永不让整条素材失败**（PRD O8）。到这里 media 已经是
ready_partial，跟读已经能用；因为翻译拿不到就把整期标红，是拿已经
到手的价值去赌一个可选功能。所以任何 EnrichError 都回落 NullEnricher，
结果是「单章、无标题、无翻译」，跟读不受影响。

不跨供应商重试：自动换一家会让「为什么这期翻译不一样」无法解释。
"""

from __future__ import annotations

import logging

from de_nachhall.chunking.chunker import ChapterRange, build_chunks
from de_nachhall.chunking.sentences import Sentence as SentenceRow
from de_nachhall.ingest.runner import StageContext
from de_nachhall.providers.enrich.base import EnrichError, EnrichProvider, EnrichResult, SentenceIn
from de_nachhall.providers.enrich.null import NullEnricher
from de_nachhall.repositories.text import TextRepository

log = logging.getLogger(__name__)


class EnrichStage:
    def __init__(self, provider: EnrichProvider, target_words: int = 22) -> None:
        self.provider = provider
        self.target_words = target_words

    def __call__(self, ctx: StageContext) -> None:
        repo = TextRepository(ctx.db)
        sentences = repo.load_sentences(ctx.media.id)
        if not sentences:
            log.warning("media %s: no sentences to enrich", ctx.media.id)
            ctx.report(100)
            return

        ctx.report(10)
        payload = [SentenceIn(idx=s.idx, text=s.text) for s in sentences]

        try:
            result = self.provider.enrich(payload)
        except EnrichError as e:
            log.warning("media %s: %s failed, degrading — %s", ctx.media.id, self.provider.name, e)
            result = NullEnricher().enrich(payload)
        except Exception as e:  # noqa: BLE001 —— 供应商 SDK 什么都可能抛
            log.exception("media %s: %s crashed, degrading", ctx.media.id, self.provider.name)
            del e
            result = NullEnricher().enrich(payload)

        ctx.report(60)
        self._persist(ctx, repo, sentences, result)
        ctx.report(100)

    def _persist(self, ctx: StageContext, repo: TextRepository,
                 sentences: list[SentenceRow], result: EnrichResult) -> None:
        chapters = result.chapters
        if not chapters:
            chapters = NullEnricher().enrich(
                [SentenceIn(idx=s.idx, text=s.text) for s in sentences]
            ).chapters

        ranges = [
            ChapterRange(
                idx=c.idx,
                start_sentence_idx=c.start_sentence_idx,
                end_sentence_idx=c.end_sentence_idx,
            )
            for c in chapters
        ]
        chunks = build_chunks(sentences, ranges, self.target_words)
        repo.replace_chapters_and_chunks(ctx.media.id, chapters, chunks, sentences)
        n = repo.apply_translations(ctx.media.id, result.translations)

        log.info(
            "media %s enriched%s: %d chapters, %d chunks, %d translations",
            ctx.media.id, "（降级）" if result.degraded else "",
            len(chapters), len(chunks), n,
        )
