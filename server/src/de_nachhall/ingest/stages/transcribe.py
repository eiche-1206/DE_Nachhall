"""transcribing —— 按优先级依次尝试 Provider，得到 fragments，再合并成句。

选路不是「猜」，是按 Provider 自报的适用性走（SPEC §4.2）：
Provider 返回 None = 这条路不适用（如平台没德语字幕），换下一个；
抛 TranscribeError = 真的坏了，直接失败，不再往下试 ——
显存不足时静默降级到别的实现，只会让用户拿到一份质量莫名其妙的字幕。

这一阶段结束后 media 变 ready_partial，跟读已可用，所以这里
必须把 chunks 也切出来（单章形态），不能等 enriching。
"""

from __future__ import annotations

import logging
from pathlib import Path

from de_nachhall.chunking.chunker import build_chunks
from de_nachhall.chunking.sentences import Fragment as FragIn
from de_nachhall.chunking.sentences import merge_fragments_to_sentences
from de_nachhall.ingest.runner import StageContext, StageError
from de_nachhall.ingest.workspace import Workspace
from de_nachhall.providers.enrich.base import ChapterOut
from de_nachhall.providers.transcript.base import (
    FragmentOut,
    MediaRef,
    TranscribeError,
    TranscriptProvider,
)
from de_nachhall.repositories.text import TextRepository

log = logging.getLogger(__name__)


class TranscribeStage:
    def __init__(
        self,
        media_root: Path,
        providers: list[TranscriptProvider],
        lang: str = "de",
        target_words: int = 22,
    ) -> None:
        self.media_root = Path(media_root)
        self.providers = providers
        self.lang = lang
        self.target_words = target_words

    def __call__(self, ctx: StageContext) -> None:
        ws = Workspace.for_media(self.media_root, ctx.media.id)
        ref = MediaRef(
            media_id=ctx.media.id,
            source_url=ctx.media.source_url,
            wav_path=ws.wav if ws.wav.exists() else None,
            probe=ws.read_probe(),
        )

        fragments = self._run_providers(ctx, ref)
        if not fragments:
            raise StageError(
                "TRANSCRIBE_EMPTY",
                "没能从这个视频里得到任何文本，可能是纯音乐或没有语音。",
            )

        repo = TextRepository(ctx.db)
        repo.replace_fragments(ctx.media.id, fragments)
        ctx.report(80)

        sentences = merge_fragments_to_sentences(
            [FragIn(idx=f.idx, start_ms=f.start_ms, end_ms=f.end_ms, text=f.text)
             for f in fragments]
        )
        repo.replace_sentences(ctx.media.id, sentences)
        ctx.report(90)

        # 单章占位：enriching 会用真实章节整体替换掉
        chapters = [
            ChapterOut(
                idx=0,
                title=None,
                start_sentence_idx=sentences[0].idx,
                end_sentence_idx=sentences[-1].idx,
            )
        ]
        chunks = build_chunks(sentences, [], self.target_words)
        repo.replace_chapters_and_chunks(ctx.media.id, chapters, chunks, sentences)

        ctx.report(100)
        log.info(
            "media %s transcribed: %d fragments → %d sentences → %d chunks",
            ctx.media.id, len(fragments), len(sentences), len(chunks),
        )

    def _run_providers(self, ctx: StageContext, ref: MediaRef) -> list[FragmentOut]:
        if not self.providers:
            raise StageError("NO_TRANSCRIBER", "没有可用的转写实现，检查服务配置。")

        step = 70 // max(len(self.providers), 1)
        for i, p in enumerate(self.providers):
            ctx.report(5 + i * step)
            try:
                got = p.transcribe(ref, self.lang)
            except TranscribeError as e:
                # 真坏了：不静默换实现，让用户看见原因
                raise StageError("TRANSCRIBE_FAILED", str(e)) from e
            if got:
                log.info("media %s: transcript from %s (%d fragments)",
                         ctx.media.id, p.name, len(got))
                return got
            log.info("media %s: %s not applicable, next", ctx.media.id, p.name)
        return []
