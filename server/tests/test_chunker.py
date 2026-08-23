"""chunker 的回归测试。

核心是真实数据基线：Sprint 0 从 ZDF 拉的官方德语字幕。
这些数字是**算法选型的依据**，变了就说明行为被改动，必须重新审视。
"""

from __future__ import annotations

import pytest

from de_nachhall.chunking.chunker import ChapterRange, build_chunks, chunk_chapter
from de_nachhall.chunking.sentences import Fragment, Sentence, merge_fragments_to_sentences


def s(idx: int, words: int, start: int = 0, end: int = 1000) -> Sentence:
    text = " ".join(f"w{i}" for i in range(words))
    return Sentence(idx=idx, start_ms=start, end_ms=end, text=text, word_count=words)


@pytest.fixture(scope="module")
def sents(logo_fragments: list[Fragment]) -> list[Sentence]:
    return merge_fragments_to_sentences(logo_fragments)


class TestRealDataBaseline:
    """SPEC §4.4 的实测基线。数字变了要回头看是不是算法被改了。"""

    def test_target_22_yields_53_chunks(self, sents: list[Sentence]) -> None:
        assert len(build_chunks(sents, [], target_words=22)) == 53

    def test_average_word_count_hits_target(self, sents: list[Sentence]) -> None:
        chunks = build_chunks(sents, [], target_words=22)
        avg = sum(c.word_count for c in chunks) / len(chunks)
        # 参数名等于实际结果 —— 这正是 bestfit 相对 greedy 的关键优势
        assert 21.5 <= avg <= 23.0, f"平均 {avg:.1f} 词，偏离 target=22"

    def test_zero_long_chunks(self, sents: list[Sentence]) -> None:
        # greedy thr=22 会产生 4 个 >35 词的长块，bestfit 是 0 个
        chunks = build_chunks(sents, [], target_words=22)
        assert [c.word_count for c in chunks if c.word_count > 35] == []

    def test_word_range_is_narrow(self, sents: list[Sentence]) -> None:
        w = [c.word_count for c in build_chunks(sents, [], target_words=22)]
        assert min(w) >= 10 and max(w) <= 35, f"范围 {min(w)}–{max(w)} 过宽"

    def test_average_duration_around_9s(self, sents: list[Sentence]) -> None:
        chunks = build_chunks(sents, [], target_words=22)
        avg = sum(c.end_ms - c.start_ms for c in chunks) / len(chunks) / 1000
        assert 7.5 <= avg <= 10.5, f"平均 {avg:.1f}s"

    def test_no_text_lost(self, sents: list[Sentence]) -> None:
        src = " ".join(x.text for x in sents).split()
        got = " ".join(c.text for c in build_chunks(sents, [], 22)).split()
        assert got == src

    def test_idx_is_continuous(self, sents: list[Sentence]) -> None:
        chunks = build_chunks(sents, [], 22)
        assert [c.idx for c in chunks] == list(range(len(chunks)))

    def test_smaller_target_yields_more_chunks(self, sents: list[Sentence]) -> None:
        assert len(build_chunks(sents, [], 16)) > len(build_chunks(sents, [], 26))


class TestBestfitBehaviour:
    def test_prefers_closer_to_target(self) -> None:
        # 10+10=20 比 10 更接近 22 → 合并；再加 10 得 30，比 20 远 → 断开
        out = chunk_chapter([s(0, 10), s(1, 10), s(2, 10)], target_words=22)
        assert [c.word_count for c in out] == [20, 10]

    def test_oversized_single_sentence_stands_alone(self) -> None:
        # 不设硬上限：德语长句照样独立成块，不拆
        out = chunk_chapter([s(0, 40), s(1, 5)], target_words=22)
        assert out[0].word_count == 40

    def test_tie_prefers_merging(self) -> None:
        # 18 与 26 距 22 等距，规则是 <= 所以合并 —— 少一个碎块
        out = chunk_chapter([s(0, 18), s(1, 8)], target_words=22)
        assert len(out) == 1

    def test_single_sentence(self) -> None:
        assert len(chunk_chapter([s(0, 5)], 22)) == 1

    def test_empty(self) -> None:
        assert build_chunks([], [], 22) == []


class TestChapterBoundary:
    def test_never_merges_across_chapters(self) -> None:
        sents = [s(i, 5, i * 1000, i * 1000 + 900) for i in range(8)]
        chapters = [ChapterRange(0, 0, 3), ChapterRange(1, 4, 7)]
        out = build_chunks(sents, chapters, target_words=100)  # target 大到想合并一切
        assert len(out) == 2
        assert out[0].chapter_idx == 0 and out[0].end_sentence_idx == 3
        assert out[1].chapter_idx == 1 and out[1].start_sentence_idx == 4

    def test_idx_continues_across_chapters(self) -> None:
        sents = [s(i, 12, i * 1000, i * 1000 + 900) for i in range(8)]
        out = build_chunks(sents, [ChapterRange(0, 0, 3), ChapterRange(1, 4, 7)], 22)
        assert [c.idx for c in out] == list(range(len(out)))

    def test_no_chapters_degrades_to_single_chapter(self, sents: list[Sentence]) -> None:
        # NullEnricher 降级后的形态 —— 跟读照常可用
        out = build_chunks(sents, [], 22)
        assert all(c.chapter_idx == 0 for c in out)
        assert len(out) == 53

    def test_timeline_preserved(self) -> None:
        sents = [s(i, 12, i * 1000, i * 1000 + 900) for i in range(6)]
        out = build_chunks(sents, [], 22)
        assert out[0].start_ms == 0
        assert out[-1].end_ms == 5900
