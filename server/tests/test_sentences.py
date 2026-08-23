"""sentences 的行为测试。

核心回归用真实数据：Sprint 0 从 ZDF 拉的官方德语字幕。
"""

from __future__ import annotations

from de_nachhall.chunking.sentences import Fragment, merge_fragments_to_sentences


def f(idx: int, text: str, start: int = 0, end: int = 1000) -> Fragment:
    return Fragment(idx=idx, start_ms=start, end_ms=end, text=text)


class TestRealData:
    """真实数据回归 —— 这是这一层唯一可信的验收方式。"""

    def test_fixture_has_expected_cues(self, logo_fragments: list[Fragment]) -> None:
        assert len(logo_fragments) == 175

    def test_merges_175_cues_into_118_sentences(self, logo_fragments: list[Fragment]) -> None:
        # Sprint 0 实测基线。数字变了说明合并规则被改动，需要重新审视。
        assert len(merge_fragments_to_sentences(logo_fragments)) == 118

    def test_no_text_is_lost(self, logo_fragments: list[Fragment]) -> None:
        src = " ".join(x.text for x in logo_fragments).split()
        got = " ".join(s.text for s in merge_fragments_to_sentences(logo_fragments)).split()
        assert got == src

    def test_timeline_is_monotonic_and_covering(self, logo_fragments: list[Fragment]) -> None:
        sents = merge_fragments_to_sentences(logo_fragments)
        assert sents[0].start_ms == logo_fragments[0].start_ms
        assert sents[-1].end_ms == logo_fragments[-1].end_ms
        for a, b in zip(sents, sents[1:], strict=False):
            assert a.end_ms <= b.start_ms or a.end_ms <= b.end_ms
            assert a.idx + 1 == b.idx

    def test_word_count_matches_text(self, logo_fragments: list[Fragment]) -> None:
        for s in merge_fragments_to_sentences(logo_fragments):
            assert s.word_count == len(s.text.split())


class TestSplitRules:
    def test_splits_on_period_question_exclaim(self) -> None:
        frags = [f(0, "Eins."), f(1, "Zwei?"), f(2, "Drei!")]
        assert len(merge_fragments_to_sentences(frags)) == 3

    def test_joins_display_line_breaks(self) -> None:
        # 这正是平台字幕的形态：一句话被拆成两个显示行
        frags = [f(0, "Seepferdchen sind"), f(1, "total faszinierende Tiere.")]
        out = merge_fragments_to_sentences(frags)
        assert len(out) == 1
        assert out[0].text == "Seepferdchen sind total faszinierende Tiere."

    def test_closing_quote_after_period_still_ends(self) -> None:
        frags = [f(0, 'Und damit hallo bei "logo!"'), f(1, "Weiter geht es.")]
        assert len(merge_fragments_to_sentences(frags)) == 2

    def test_ordinal_date_is_not_a_sentence_end(self) -> None:
        # 德语日期：21. August —— 句点不是句末
        frags = [f(0, "Das war am 21."), f(1, "August 2026 passiert.")]
        out = merge_fragments_to_sentences(frags)
        assert len(out) == 1

    def test_abbreviation_is_not_a_sentence_end(self) -> None:
        frags = [f(0, "Viele Tiere, z.B."), f(1, "Seepferdchen, leben dort.")]
        assert len(merge_fragments_to_sentences(frags)) == 1

    def test_trailing_unterminated_fragment_still_emitted(self) -> None:
        # 说话被截断或字幕缺句号时，内容不能丢
        frags = [f(0, "Fertig."), f(1, "Angefangen aber nicht")]
        out = merge_fragments_to_sentences(frags)
        assert len(out) == 2
        assert out[1].text == "Angefangen aber nicht"

    def test_empty_fragments_are_skipped(self) -> None:
        frags = [f(0, ""), f(1, "   "), f(2, "Nur dieser.")]
        out = merge_fragments_to_sentences(frags)
        assert len(out) == 1

    def test_empty_input(self) -> None:
        assert merge_fragments_to_sentences([]) == []
