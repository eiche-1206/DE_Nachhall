"""Provider 层测试。网络与 GPU 都不碰，只测可确定的行为。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from de_nachhall.providers.enrich.base import EnrichError, EnrichProvider, SentenceIn
from de_nachhall.providers.enrich.claude import ClaudeEnricher, _extract_tool_input
from de_nachhall.providers.enrich.contract import TOOL_NAME
from de_nachhall.providers.enrich.factory import build_enricher
from de_nachhall.providers.enrich.null import NullEnricher
from de_nachhall.providers.enrich.openai_compat import OpenAICompatEnricher
from de_nachhall.providers.transcript.base import MediaRef, TranscribeError, TranscriptProvider
from de_nachhall.providers.transcript.faster_whisper import FasterWhisperProvider
from de_nachhall.providers.transcript.platform_subs import (
    PlatformSubsProvider,
    pick_subtitle_lang,
)
from de_nachhall.providers.transcript.vtt import parse_vtt

FIXTURES = Path(__file__).parent / "fixtures"


class TestVttParser:
    def test_parses_real_zdf_subtitles(self) -> None:
        frags = parse_vtt((FIXTURES / "logo_20260821.vtt").read_text(encoding="utf-8"))
        assert len(frags) == 175
        assert frags[0].text.startswith("Seepferdchen sind")
        assert frags[0].start_ms == 560

    def test_joins_multiline_cue(self) -> None:
        frags = parse_vtt(
            "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nSeepferdchen sind\ntotal faszinierend.\n"
        )
        assert frags[0].text == "Seepferdchen sind total faszinierend."

    def test_strips_inline_tags(self) -> None:
        frags = parse_vtt("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n<v Anna>Hallo</v>\n")
        assert frags[0].text == "Hallo"

    def test_strips_speaker_dash(self) -> None:
        frags = parse_vtt("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n- Guten Tag.\n")
        assert frags[0].text == "Guten Tag."

    def test_accepts_srt_style_comma_timestamps(self) -> None:
        frags = parse_vtt("WEBVTT\n\n00:00:01,500 --> 00:00:02,750\nJa.\n")
        assert (frags[0].start_ms, frags[0].end_ms) == (1500, 2750)

    def test_skips_zero_length_and_empty(self) -> None:
        vtt = (
            "WEBVTT\n\n00:00:01.000 --> 00:00:01.000\nleer\n\n"
            "00:00:02.000 --> 00:00:03.000\n\n\n"
            "00:00:04.000 --> 00:00:05.000\nOk.\n"
        )
        frags = parse_vtt(vtt)
        assert [f.text for f in frags] == ["Ok."]

    def test_idx_is_continuous(self) -> None:
        frags = parse_vtt((FIXTURES / "logo_20260821.vtt").read_text(encoding="utf-8"))
        assert [f.idx for f in frags] == list(range(len(frags)))


class TestSubtitleLangPick:
    @pytest.mark.parametrize("key", ["de", "deu", "ger", "de-DE"])
    def test_accepts_german_aliases(self, key: str) -> None:
        # ZDF 用 deu，YouTube 用 de —— 两边都要认
        assert pick_subtitle_lang({"subtitles": {key: [{}]}}, "de") == key

    def test_ignores_automatic_captions(self) -> None:
        # 机器转的字幕不比 Whisper 好，还多一次网络往返
        probe = {"subtitles": {}, "automatic_captions": {"de": [{}]}}
        assert pick_subtitle_lang(probe, "de") is None

    def test_returns_none_for_other_languages(self) -> None:
        assert pick_subtitle_lang({"subtitles": {"en": [{}], "fr": [{}]}}, "de") is None

    def test_empty_probe(self) -> None:
        assert pick_subtitle_lang({}, "de") is None


class TestPlatformSubsProvider:
    def test_returns_none_without_matching_track(self) -> None:
        # 返回 None 而不是抛错 —— 这是「不适用」，要回落 Whisper
        p = PlatformSubsProvider()
        ref = MediaRef(media_id=1, source_url="https://x", probe={"subtitles": {"en": [{}]}})
        assert p.transcribe(ref, "de") is None

    def test_satisfies_protocol(self) -> None:
        assert isinstance(PlatformSubsProvider(), TranscriptProvider)


class TestFasterWhisperProvider:
    def test_defaults_to_int8_float16(self) -> None:
        # Sprint 0 实测 float16 在 6GB 卡上 OOM
        assert FasterWhisperProvider().compute_type == "int8_float16"

    def test_missing_wav_raises_with_actionable_message(self) -> None:
        p = FasterWhisperProvider()
        with pytest.raises(TranscribeError, match="转码"):
            p.transcribe(MediaRef(media_id=1, source_url="x", wav_path=None), "de")

    def test_nonexistent_wav_raises(self, tmp_path: Path) -> None:
        p = FasterWhisperProvider()
        ref = MediaRef(media_id=1, source_url="x", wav_path=tmp_path / "nope.wav")
        with pytest.raises(TranscribeError):
            p.transcribe(ref, "de")

    def test_satisfies_protocol(self) -> None:
        assert isinstance(FasterWhisperProvider(), TranscriptProvider)


class TestMediaRef:
    def test_platform_from_extractor_key(self) -> None:
        ref = MediaRef(media_id=1, source_url="x", probe={"extractor_key": "ZDF"})
        assert ref.platform == "ZDF"

    def test_platform_none_when_absent(self) -> None:
        assert MediaRef(media_id=1, source_url="x").platform is None


SENTS = [SentenceIn(idx=i, text=f"Satz {i}.") for i in range(4)]


class _FakeBlock:
    def __init__(self, data: dict, name: str = TOOL_NAME) -> None:
        self.type, self.name, self.input = "tool_use", name, data


class _FakeResp:
    def __init__(self, blocks: list) -> None:
        self.content = blocks


class _FakeClient:
    def __init__(self, resp: object = None, exc: Exception | None = None) -> None:
        self._resp, self._exc = resp, exc
        self.messages = self

    def create(self, **kw: object) -> object:
        self.last_kwargs = kw
        if self._exc:
            raise self._exc
        return self._resp


GOOD = {
    "chapters": [{"title": "A", "start_sentence_idx": 0, "end_sentence_idx": 3}],
    "translations": [{"idx": i, "zh": f"句{i}"} for i in range(4)],
}


class TestClaudeEnricher:
    def test_happy_path(self) -> None:
        c = ClaudeEnricher("k", client=_FakeClient(_FakeResp([_FakeBlock(GOOD)])))
        r = c.enrich(SENTS)
        assert r.chapters[0].title == "A"
        assert r.translations[2] == "句2"
        assert r.degraded is False

    def test_forces_tool_use(self) -> None:
        fake = _FakeClient(_FakeResp([_FakeBlock(GOOD)]))
        ClaudeEnricher("k", client=fake).enrich(SENTS)
        assert fake.last_kwargs["tool_choice"] == {"type": "tool", "name": TOOL_NAME}

    def test_uses_shared_contract_not_its_own(self) -> None:
        from de_nachhall.providers.enrich.contract import OUTPUT_SCHEMA, SYSTEM_PROMPT

        fake = _FakeClient(_FakeResp([_FakeBlock(GOOD)]))
        ClaudeEnricher("k", client=fake).enrich(SENTS)
        assert fake.last_kwargs["system"] is SYSTEM_PROMPT
        assert fake.last_kwargs["tools"][0]["input_schema"] is OUTPUT_SCHEMA

    def test_api_failure_becomes_enrich_error(self) -> None:
        c = ClaudeEnricher("k", client=_FakeClient(exc=RuntimeError("429")))
        with pytest.raises(EnrichError, match="Claude 调用失败"):
            c.enrich(SENTS)

    def test_no_tool_block_is_enrich_error(self) -> None:
        c = ClaudeEnricher("k", client=_FakeClient(_FakeResp([])))
        with pytest.raises(EnrichError, match="未按要求调用工具"):
            c.enrich(SENTS)

    def test_contract_violation_becomes_enrich_error(self) -> None:
        bad = {
            "chapters": [{"title": "A", "start_sentence_idx": 0, "end_sentence_idx": 1}],
            "translations": GOOD["translations"],
        }
        c = ClaudeEnricher("k", client=_FakeClient(_FakeResp([_FakeBlock(bad)])))
        with pytest.raises(EnrichError, match="不满足契约"):
            c.enrich(SENTS)

    def test_empty_input_short_circuits(self) -> None:
        c = ClaudeEnricher("k", client=_FakeClient(exc=AssertionError("不该被调用")))
        assert c.enrich([]).chapters == []

    def test_extract_ignores_wrong_tool_name(self) -> None:
        assert _extract_tool_input(_FakeResp([_FakeBlock(GOOD, name="other")])) is None


class TestNullEnricher:
    def test_single_chapter_covering_everything(self) -> None:
        r = NullEnricher().enrich(SENTS)
        assert len(r.chapters) == 1
        assert (r.chapters[0].start_sentence_idx, r.chapters[0].end_sentence_idx) == (0, 3)

    def test_marked_degraded_with_no_title_no_translation(self) -> None:
        r = NullEnricher().enrich(SENTS)
        assert r.degraded is True
        assert r.chapters[0].title is None
        assert r.translations == {}

    def test_empty_input(self) -> None:
        assert NullEnricher().enrich([]).chapters == []

    def test_satisfies_protocol(self) -> None:
        assert isinstance(NullEnricher(), EnrichProvider)


# ==================== OpenAICompatEnricher ====================
#
# 一个实现覆盖 GPT / 千问 / DeepSeek / Ollama，差别只在 base_url 与 model。
# 所以这里验的是「契约校验有没有真的生效」，而不是某一家的返回格式。

class _Msg:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str | None) -> None:
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content: str | None) -> None:
        self.choices = [_Choice(content)]


class _Completions:
    def __init__(self, content: object) -> None:
        self.content = content
        self.kwargs: dict = {}

    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.kwargs = kwargs
        if isinstance(self.content, Exception):
            raise self.content
        return _Resp(self.content)


class _Client:
    def __init__(self, content: object) -> None:
        self.chat = type("C", (), {"completions": _Completions(content)})()


def _oc(content) -> OpenAICompatEnricher:  # type: ignore[no-untyped-def]
    return OpenAICompatEnricher(
        api_key="k", base_url="https://x.invalid/v1", model="qwen-plus", client=_Client(content)
    )


def test_openai_compat_parses_valid_output() -> None:
    sents = [SentenceIn(idx=0, text="Hallo."), SentenceIn(idx=1, text="Welt.")]
    payload = json.dumps(
        {
            "chapters": [
                {"idx": 0, "title": "Gruß", "start_sentence_idx": 0, "end_sentence_idx": 1}
            ],
            "translations": [{"idx": 0, "zh": "你好。"}, {"idx": 1, "zh": "世界。"}],
        }
    )
    r = _oc(payload).enrich(sents)
    assert r.chapters[0].title == "Gruß"
    assert r.translations[1] == "世界。"


def test_openai_compat_rejects_bad_json() -> None:
    with pytest.raises(EnrichError) as e:
        _oc("不是 JSON").enrich([SentenceIn(idx=0, text="Hallo.")])
    assert "JSON" in str(e.value)


def test_openai_compat_rejects_empty_content() -> None:
    with pytest.raises(EnrichError):
        _oc(None).enrich([SentenceIn(idx=0, text="Hallo.")])


def test_openai_compat_wraps_transport_error() -> None:
    with pytest.raises(EnrichError) as e:
        _oc(ConnectionError("连不上")).enrich([SentenceIn(idx=0, text="Hallo.")])
    assert "qwen-plus" in str(e.value)


def test_openai_compat_empty_input_skips_call() -> None:
    p = _oc("{}")
    assert p.enrich([]).chapters == []


def test_openai_compat_can_degrade_to_json_object() -> None:
    """部分兼容端点不支持 json_schema；契约校验在本地，所以退化是安全的。"""
    p = OpenAICompatEnricher(
        api_key="k", base_url="b", model="m", client=_Client("{}"), use_json_schema=False
    )
    assert p._response_format() == {"type": "json_object"}


def test_factory_routes_by_provider() -> None:
    from de_nachhall.config import Settings

    assert build_enricher(
        Settings(llm_provider="null", anthropic_api_key=None)
    ).name == "null"
    assert build_enricher(
        Settings(llm_provider="claude", anthropic_api_key="k")
    ).name == "claude"
    assert build_enricher(
        Settings(llm_provider="openai_compat", llm_api_key="k", llm_base_url="b")
    ).name == "openai_compat"


# ==================== 词级时间戳 ====================
#
# segment 级的 start/end 带着 VAD 的静音余量。跟读时每段前后各多出几百
# 毫秒空白，一段一段累积起来很难受，所以边界要贴到真正的语音上。

from de_nachhall.providers.transcript.faster_whisper import _speech_span  # noqa: E402


class _Word:
    def __init__(self, word: str, start: float, end: float) -> None:
        self.word, self.start, self.end = word, start, end


class _Seg:
    def __init__(self, start: float, end: float, words=None) -> None:  # type: ignore[no-untyped-def]
        self.start, self.end, self.words = start, end, words


def test_speech_span_trims_leading_silence() -> None:
    seg = _Seg(10.0, 15.0, [_Word(" Hallo", 10.8, 11.2), _Word(" Welt", 11.3, 11.9)])
    start, end = _speech_span(seg)
    assert start == 10.8  # 不是 10.0
    assert 11.9 < end <= 15.0  # 加了尾部余量，但不越过 segment 末尾


def test_speech_span_pad_never_exceeds_segment_end() -> None:
    """尾部余量必须钳住，否则会侵入下一段。"""
    seg = _Seg(10.0, 11.9, [_Word(" Hallo", 10.8, 11.2), _Word(" Welt", 11.3, 11.9)])
    _, end = _speech_span(seg)
    assert end == 11.9


def test_speech_span_falls_back_without_words() -> None:
    """整段没有词（拟声、纯标点）时退回 segment 边界，不能返回空区间。"""
    assert _speech_span(_Seg(3.0, 4.5, [])) == (3.0, 4.5)
    assert _speech_span(_Seg(3.0, 4.5, None)) == (3.0, 4.5)


def test_speech_span_survives_bogus_word_times() -> None:
    """词级时间戳偶尔会给出倒序或零长区间。"""
    seg = _Seg(3.0, 4.5, [_Word(" x", 4.4, 4.0)])
    assert _speech_span(seg) == (3.0, 4.5)


def test_speech_span_ignores_blank_words() -> None:
    seg = _Seg(10.0, 15.0, [_Word("  ", 10.0, 10.1), _Word(" Hallo", 10.8, 11.2)])
    start, _ = _speech_span(seg)
    assert start == 10.8
