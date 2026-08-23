"""契约层测试。

这一层的价值全在**结构性校验**：模型输出的章节覆盖不全或翻译缺句，
一旦入库，前端会显示空白章节或缺失翻译，而且很难定位到是哪一步出的错。
在解析处挡住，比在数据库里排查便宜得多。
"""

from __future__ import annotations

import pytest

from de_nachhall.providers.enrich.base import EnrichProvider, EnrichResult, SentenceIn
from de_nachhall.providers.enrich.contract import (
    OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
    ContractViolation,
    build_user_message,
    parse_and_validate,
)

SENTS = [SentenceIn(idx=i, text=f"Satz {i}.") for i in range(6)]


def payload(chapters, translations=None):  # type: ignore[no-untyped-def]
    return {
        "chapters": chapters,
        "translations": (
            translations
            if translations is not None
            else [{"idx": s.idx, "zh": f"句{s.idx}"} for s in SENTS]
        ),
    }


class TestHappyPath:
    def test_parses_two_chapters(self) -> None:
        r = parse_and_validate(
            payload(
                [
                    {"title": "Waldbrände", "start_sentence_idx": 0, "end_sentence_idx": 2},
                    {"title": "Schulstreik", "start_sentence_idx": 3, "end_sentence_idx": 5},
                ]
            ),
            SENTS,
        )
        assert [c.title for c in r.chapters] == ["Waldbrände", "Schulstreik"]
        assert r.translations[3] == "句3"
        assert r.degraded is False
        assert r.has_titles

    def test_accepts_json_string(self) -> None:
        import json

        raw = json.dumps(payload([{"title": "A", "start_sentence_idx": 0, "end_sentence_idx": 5}]))
        assert len(parse_and_validate(raw, SENTS).chapters) == 1

    def test_reorders_out_of_order_chapters(self) -> None:
        r = parse_and_validate(
            payload(
                [
                    {"title": "B", "start_sentence_idx": 3, "end_sentence_idx": 5},
                    {"title": "A", "start_sentence_idx": 0, "end_sentence_idx": 2},
                ]
            ),
            SENTS,
        )
        assert [c.title for c in r.chapters] == ["A", "B"]
        assert [c.idx for c in r.chapters] == [0, 1]

    def test_blank_title_becomes_none(self) -> None:
        r = parse_and_validate(
            payload([{"title": "   ", "start_sentence_idx": 0, "end_sentence_idx": 5}]), SENTS
        )
        assert r.chapters[0].title is None
        assert not r.has_titles


class TestStructuralViolations:
    def test_gap_between_chapters(self) -> None:
        with pytest.raises(ContractViolation, match="不连续"):
            parse_and_validate(
                payload(
                    [
                        {"title": "A", "start_sentence_idx": 0, "end_sentence_idx": 1},
                        {"title": "B", "start_sentence_idx": 3, "end_sentence_idx": 5},
                    ]
                ),
                SENTS,
            )

    def test_overlapping_chapters(self) -> None:
        with pytest.raises(ContractViolation, match="不连续"):
            parse_and_validate(
                payload(
                    [
                        {"title": "A", "start_sentence_idx": 0, "end_sentence_idx": 3},
                        {"title": "B", "start_sentence_idx": 2, "end_sentence_idx": 5},
                    ]
                ),
                SENTS,
            )

    def test_does_not_start_at_first_sentence(self) -> None:
        with pytest.raises(ContractViolation, match="首章"):
            parse_and_validate(
                payload([{"title": "A", "start_sentence_idx": 1, "end_sentence_idx": 5}]), SENTS
            )

    def test_does_not_cover_last_sentence(self) -> None:
        with pytest.raises(ContractViolation, match="末章"):
            parse_and_validate(
                payload([{"title": "A", "start_sentence_idx": 0, "end_sentence_idx": 4}]), SENTS
            )

    def test_reversed_range(self) -> None:
        with pytest.raises(ContractViolation, match=r"start\(4\) > end\(1\)"):
            parse_and_validate(
                payload(
                    [
                        {"title": "A", "start_sentence_idx": 0, "end_sentence_idx": 3},
                        {"title": "B", "start_sentence_idx": 4, "end_sentence_idx": 1},
                    ]
                ),
                SENTS,
            )

    def test_empty_chapters(self) -> None:
        with pytest.raises(ContractViolation, match="chapters 为空"):
            parse_and_validate(payload([]), SENTS)

    def test_missing_translations_are_named(self) -> None:
        good = [{"idx": s.idx, "zh": "x"} for s in SENTS if s.idx not in (2, 4)]
        with pytest.raises(ContractViolation, match=r"idx 2, 4"):
            parse_and_validate(
                payload([{"title": "A", "start_sentence_idx": 0, "end_sentence_idx": 5}], good),
                SENTS,
            )

    def test_blank_translation_counts_as_missing(self) -> None:
        tr = [{"idx": s.idx, "zh": "  " if s.idx == 1 else "x"} for s in SENTS]
        with pytest.raises(ContractViolation, match=r"idx 1"):
            parse_and_validate(
                payload([{"title": "A", "start_sentence_idx": 0, "end_sentence_idx": 5}], tr),
                SENTS,
            )


class TestSingleSourceOfTruth:
    """契约只能有一份 —— 这几条防止实现方各写各的。"""

    def test_schema_forbids_extra_properties(self) -> None:
        assert OUTPUT_SCHEMA["additionalProperties"] is False
        assert OUTPUT_SCHEMA["properties"]["chapters"]["items"]["additionalProperties"] is False

    def test_schema_requires_both_sections(self) -> None:
        assert set(OUTPUT_SCHEMA["required"]) == {"chapters", "translations"}

    def test_prompt_states_both_tasks(self) -> None:
        assert "分章" in SYSTEM_PROMPT
        assert "翻译" in SYSTEM_PROMPT

    def test_user_message_carries_every_sentence(self) -> None:
        msg = build_user_message(SENTS)
        assert f"共 {len(SENTS)} 句" in msg
        for s in SENTS:
            assert f"{s.idx}\t{s.text}" in msg


class TestProtocol:
    def test_null_like_impl_satisfies_protocol(self) -> None:
        class Stub:
            name = "stub"

            def enrich(self, sentences):  # type: ignore[no-untyped-def]
                return EnrichResult(chapters=[], degraded=True)

        assert isinstance(Stub(), EnrichProvider)

    def test_empty_input_returns_empty_result(self) -> None:
        r = parse_and_validate(payload([]), [])
        assert r.chapters == [] and r.translations == {}
