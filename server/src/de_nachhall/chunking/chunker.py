"""sentence → chunk：bestfit「就近取优」。

算法选择有实测依据（SPEC §4.4，logo! 2026-08-21 真实字幕）：

    greedy  thr=22   →  43 块 · 平均 27.6 词 · 4 个 >35 词的长块   ← 超标 25%
    bestfit t=22     →  53 块 · 平均 22.4 词 · 0 个长块            ← 采用

greedy 先塞进整句再检查，而平均句长 10.1 词，等于每次平均超出半句。
bestfit 在「加上这句」和「就此断开」之间选更接近目标的那个。

两条不可动的规则：
  * chapter 边界是硬边界，chunk 不可跨章
  * 不设硬上限 —— 单句本身超过 target 时独立成块。强行拆句会毁掉语感，
    而这正是整个 chunk 设计要避免的
"""

from __future__ import annotations

from dataclasses import dataclass

from de_nachhall.chunking.sentences import Sentence


@dataclass(frozen=True)
class ChapterRange:
    """章节的句子区间，闭区间。"""

    idx: int
    start_sentence_idx: int
    end_sentence_idx: int


@dataclass(frozen=True)
class Chunk:
    idx: int
    chapter_idx: int
    start_sentence_idx: int
    end_sentence_idx: int
    start_ms: int
    end_ms: int
    text: str
    word_count: int


def _flush(buf: list[Sentence], chapter_idx: int, next_idx: int) -> Chunk:
    text = " ".join(s.text for s in buf)
    return Chunk(
        idx=next_idx,
        chapter_idx=chapter_idx,
        start_sentence_idx=buf[0].idx,
        end_sentence_idx=buf[-1].idx,
        start_ms=buf[0].start_ms,
        end_ms=buf[-1].end_ms,
        text=text,
        word_count=sum(s.word_count for s in buf),
    )


def chunk_chapter(
    sentences: list[Sentence], target_words: int, chapter_idx: int = 0, start_idx: int = 0
) -> list[Chunk]:
    """对单章内的句子做 bestfit 切分。"""
    out: list[Chunk] = []
    buf: list[Sentence] = []
    buf_words = 0

    for s in sentences:
        if not buf:
            buf, buf_words = [s], s.word_count
            continue

        after = buf_words + s.word_count
        # 加上这句更接近目标（或一样近）就加，否则断开
        if abs(after - target_words) <= abs(buf_words - target_words):
            buf.append(s)
            buf_words = after
        else:
            out.append(_flush(buf, chapter_idx, start_idx + len(out)))
            buf, buf_words = [s], s.word_count

    if buf:
        out.append(_flush(buf, chapter_idx, start_idx + len(out)))
    return out


def build_chunks(
    sentences: list[Sentence], chapters: list[ChapterRange], target_words: int
) -> list[Chunk]:
    """按章切分，chunk.idx 全期连续（前端显示 ¶11 / 53）。

    chapters 为空时退化为单章覆盖全部句子 —— 这正是 NullEnricher
    降级后的形态，跟读照常可用。
    """
    if not sentences:
        return []

    by_idx = {s.idx: s for s in sentences}
    ranges = chapters or [
        ChapterRange(
            idx=0,
            start_sentence_idx=min(by_idx),
            end_sentence_idx=max(by_idx),
        )
    ]

    out: list[Chunk] = []
    for ch in sorted(ranges, key=lambda c: c.start_sentence_idx):
        block = [
            by_idx[i] for i in range(ch.start_sentence_idx, ch.end_sentence_idx + 1) if i in by_idx
        ]
        if block:
            out.extend(chunk_chapter(block, target_words, ch.idx, len(out)))
    return out
