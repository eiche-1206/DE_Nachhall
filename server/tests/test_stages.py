"""四个阶段的测试。

外部进程（yt-dlp / ffmpeg）全部替身。这里要验的是**编排决策**：
  * 纯音频是否被挡住
  * TS 是否走重封装、mp4 是否也加 faststart
  * 转写选路是否「None 换下一个、抛错就停」
  * enriching 失败是否真的不让整条素材失败
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from de_nachhall.chunking.sentences import Fragment as FragIn
from de_nachhall.chunking.sentences import merge_fragments_to_sentences
from de_nachhall.db.models import Base, Chapter, Chunk, Fragment, Media, Sentence, User
from de_nachhall.db.session import create_db_engine
from de_nachhall.ingest.ffmpeg import Ffmpeg
from de_nachhall.ingest.runner import StageContext, StageError
from de_nachhall.ingest.stages.download import DownloadStage
from de_nachhall.ingest.stages.enrich import EnrichStage
from de_nachhall.ingest.stages.transcode import TranscodeStage
from de_nachhall.ingest.stages.transcribe import TranscribeStage
from de_nachhall.ingest.workspace import Workspace
from de_nachhall.ingest.ytdlp import ProbeResult, YtdlpError
from de_nachhall.providers.enrich.base import ChapterOut, EnrichError, EnrichResult
from de_nachhall.providers.transcript.base import FragmentOut, TranscribeError
from de_nachhall.repositories.jobs import JobsRepository

URL = "https://www.logo.de/1234"


@pytest.fixture()
def db(tmp_path):  # type: ignore[no-untyped-def]
    engine = create_db_engine(f"sqlite+pysqlite:///{tmp_path/'t.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    s.add(User(id=1, name="me"))
    s.commit()
    yield s
    s.close()


@pytest.fixture()
def ctx(db, tmp_path):  # type: ignore[no-untyped-def]
    m = Media(source_url=URL, origin="user", title=URL, status="queued")
    db.add(m)
    db.commit()
    job = JobsRepository(db).enqueue(m.id)
    seen: list[int] = []
    return StageContext(db=db, media=m, job=job, report=seen.append), seen


# ==================== download ====================


class FakeYtdlp:
    def __init__(self, probe: ProbeResult | Exception, files: bool = True) -> None:
        self._probe = probe
        self.files = files
        self.downloaded = 0

    def probe(self, url: str) -> ProbeResult:
        if isinstance(self._probe, Exception):
            raise self._probe
        return self._probe

    def download(self, url: str, out_dir: Path, basename: str = "video") -> Path:
        self.downloaded += 1
        p = out_dir / f"{basename}.mp4"
        p.write_bytes(b"x" * 100 if self.files else b"")
        return p

    def download_thumbnail(self, url: str, out_dir: Path) -> Path | None:
        p = out_dir / "thumb.jpg"
        p.write_bytes(b"j")
        return p


def probe_ok(**kw) -> ProbeResult:  # type: ignore[no-untyped-def]
    base = dict(
        title="logo! vom 21. August 2026",
        duration_ms=491200,
        platform="ZDF",
        thumbnail_url=None,
        has_video=True,
        upload_date="20260821",
        raw={"extractor_key": "ZDF"},
    )
    base.update(kw)
    return ProbeResult(**base)  # type: ignore[arg-type]


def test_download_backfills_metadata(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, pcts = ctx
    DownloadStage(tmp_path, FakeYtdlp(probe_ok()))(c)
    assert c.media.title == "logo! vom 21. August 2026"
    assert c.media.platform == "ZDF"
    assert c.media.duration_ms == 491200
    assert str(c.media.published_on) == "2026-08-21"
    assert pcts[-1] == 100


def test_download_rejects_audio_only(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    with pytest.raises(StageError) as e:
        DownloadStage(tmp_path, FakeYtdlp(probe_ok(has_video=False)))(c)
    assert e.value.code == "AUDIO_NOT_SUPPORTED"


def test_download_propagates_ytdlp_code(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    err = YtdlpError("UNSUPPORTED_SITE", "这个站点抓不了。")
    with pytest.raises(StageError) as e:
        DownloadStage(tmp_path, FakeYtdlp(err))(c)
    assert e.value.code == "UNSUPPORTED_SITE"


def test_download_persists_probe_for_later_stages(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    DownloadStage(tmp_path, FakeYtdlp(probe_ok()))(c)
    ws = Workspace.for_media(tmp_path, c.media.id)
    assert ws.read_probe()["extractor_key"] == "ZDF"


def test_download_reuses_existing_on_retry(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """重试不该把几百 MB 再拉一遍。"""
    c, _ = ctx
    y = FakeYtdlp(probe_ok())
    stage = DownloadStage(tmp_path, y)
    stage(c)
    stage(c)
    assert y.downloaded == 1


def test_download_rejects_empty_file(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    with pytest.raises(StageError) as e:
        DownloadStage(tmp_path, FakeYtdlp(probe_ok(), files=False))(c)
    assert e.value.code == "DOWNLOAD_FAILED"


# ==================== transcode ====================


class FakeFfmpeg:
    def __init__(self, fmt: str = "mpegts") -> None:
        self.fmt = fmt
        self.remuxed = 0
        self.wavs = 0

    def probe(self, path: Path) -> dict:
        return {"format": {"format_name": self.fmt, "duration": "491.2"}}

    def remux_to_mp4(self, src: Path, dst: Path) -> None:
        self.remuxed += 1
        dst.write_bytes(b"m" * 50)

    def extract_wav(self, src: Path, dst: Path) -> None:
        self.wavs += 1
        dst.write_bytes(b"w" * 50)


def prepared(tmp_path: Path, media_id: int) -> Workspace:
    ws = Workspace.for_media(tmp_path, media_id)
    ws.ensure()
    (ws.root / "source.mp4").write_bytes(b"x" * 100)
    return ws


@pytest.mark.parametrize("fmt", ["mpegts", "matroska,webm"])
def test_transcode_remuxes_non_mp4(ctx, tmp_path, fmt: str) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    prepared(tmp_path, c.media.id)
    f = FakeFfmpeg(fmt)
    TranscodeStage(tmp_path, f)(c)
    assert f.remuxed == 1
    assert f.wavs == 1


def test_transcode_still_faststarts_mp4(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """mp4 也要过一遍 —— moov 在尾部的 mp4 同样 seek 不动。"""
    c, _ = ctx
    prepared(tmp_path, c.media.id)
    f = FakeFfmpeg("mov,mp4,m4a,3gp,3g2,mj2")
    TranscodeStage(tmp_path, f)(c)
    assert f.remuxed == 1


def test_transcode_records_video_path(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    prepared(tmp_path, c.media.id)
    TranscodeStage(tmp_path, FakeFfmpeg())(c)
    assert c.media.video_path == f"{c.media.id}/video.mp4"
    assert c.media.duration_ms == 491200


def test_transcode_without_source_fails(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    Workspace.for_media(tmp_path, c.media.id).ensure()
    with pytest.raises(StageError) as e:
        TranscodeStage(tmp_path, FakeFfmpeg())(c)
    assert e.value.code == "SOURCE_MISSING"


def test_transcode_detects_silent_video(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    prepared(tmp_path, c.media.id)

    f = FakeFfmpeg()
    f.extract_wav = lambda src, dst: dst.write_bytes(b"")  # type: ignore[assignment]
    with pytest.raises(StageError) as e:
        TranscodeStage(tmp_path, f)(c)
    assert "没有声轨" in e.value.message


@pytest.mark.parametrize(
    "fmt,expect",
    [
        ("mpegts", True),
        ("matroska,webm", True),
        ("mov,mp4,m4a,3gp,3g2,mj2", False),
        ("mp4", False),
    ],
)
def test_needs_remux_matrix(fmt: str, expect: bool) -> None:
    assert Ffmpeg.needs_remux({"format": {"format_name": fmt}}) is expect


# ==================== transcribe ====================


class FakeProvider:
    def __init__(self, name: str, result) -> None:  # type: ignore[no-untyped-def]
        self.name = name
        self.result = result
        self.calls = 0

    def transcribe(self, media, lang):  # type: ignore[no-untyped-def]
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def frags(n: int = 6) -> list[FragmentOut]:
    texts = [
        "Extrem starker Regen hatte dazu geführt,",
        "dass kleine Flüsse plötzlich riesig wurden.",
        "Viele Menschen konnten nicht gewarnt werden",
        "und starben.",
        "Und sehr viel wurde zerstört.",
        "Wie sieht es dort mittlerweile aus?",
    ][:n]
    return [
        FragmentOut(idx=i, start_ms=i * 3000, end_ms=(i + 1) * 3000, text=t)
        for i, t in enumerate(texts)
    ]


def test_transcribe_prefers_first_applicable(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    subs = FakeProvider("subs", frags())
    whisper = FakeProvider("whisper", frags())
    TranscribeStage(tmp_path, [subs, whisper])(c)
    assert subs.calls == 1
    assert whisper.calls == 0


def test_transcribe_falls_back_on_none(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    subs = FakeProvider("subs", None)
    whisper = FakeProvider("whisper", frags())
    TranscribeStage(tmp_path, [subs, whisper])(c)
    assert whisper.calls == 1
    assert c.db.query(Fragment).count() == 6


def test_transcribe_does_not_fall_back_on_error(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """显存不足时静默换实现，会给出一份质量莫名其妙的字幕。"""
    c, _ = ctx
    subs = FakeProvider("subs", TranscribeError("显存不足"))
    whisper = FakeProvider("whisper", frags())
    with pytest.raises(StageError) as e:
        TranscribeStage(tmp_path, [subs, whisper])(c)
    assert e.value.code == "TRANSCRIBE_FAILED"
    assert whisper.calls == 0


def test_transcribe_writes_all_four_layers(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """ready_partial 之后跟读就该能用，所以 chunk 必须此时已存在。"""
    c, _ = ctx
    TranscribeStage(tmp_path, [FakeProvider("subs", frags())])(c)
    assert c.db.query(Fragment).count() == 6
    assert c.db.query(Sentence).count() > 0
    assert c.db.query(Chapter).count() == 1
    assert c.db.query(Chunk).count() > 0


def test_transcribe_empty_is_actionable(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    with pytest.raises(StageError) as e:
        TranscribeStage(tmp_path, [FakeProvider("subs", [])])(c)
    assert e.value.code == "TRANSCRIBE_EMPTY"


def test_transcribe_without_providers_fails(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    with pytest.raises(StageError) as e:
        TranscribeStage(tmp_path, [])(c)
    assert e.value.code == "NO_TRANSCRIBER"


# ==================== enrich ====================


class FakeEnricher:
    name = "fake"

    def __init__(self, result) -> None:  # type: ignore[no-untyped-def]
        self.result = result

    def enrich(self, sentences):  # type: ignore[no-untyped-def]
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def seeded(c, tmp_path) -> int:  # type: ignore[no-untyped-def]
    TranscribeStage(tmp_path, [FakeProvider("subs", frags())])(c)
    return len(merge_fragments_to_sentences(
        [FragIn(idx=f.idx, start_ms=f.start_ms, end_ms=f.end_ms, text=f.text) for f in frags()]
    ))


def test_enrich_applies_chapters_and_translations(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    n = seeded(c, tmp_path)
    result = EnrichResult(
        chapters=[
            ChapterOut(idx=0, title="Ahrtal", start_sentence_idx=0, end_sentence_idx=0),
            ChapterOut(idx=1, title="Rest", start_sentence_idx=1, end_sentence_idx=n - 1),
        ],
        translations={0: "极强降雨导致小河暴涨。"},
    )
    EnrichStage(FakeEnricher(result))(c)

    titles = [r.title for r in c.db.query(Chapter).order_by(Chapter.idx)]
    assert titles == ["Ahrtal", "Rest"]
    assert c.db.query(Sentence).filter(Sentence.idx == 0).one().translation_zh is not None


def test_enrich_failure_does_not_fail_media(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """PRD O8：跟读已经能用了，不能为了可选的翻译把整期标红。"""
    c, _ = ctx
    seeded(c, tmp_path)
    EnrichStage(FakeEnricher(EnrichError("API 挂了")))(c)

    chapters = c.db.query(Chapter).all()
    assert len(chapters) == 1
    assert chapters[0].title is None
    assert c.db.query(Chunk).count() > 0


def test_enrich_survives_sdk_crash(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    seeded(c, tmp_path)
    EnrichStage(FakeEnricher(RuntimeError("SDK 内部炸了")))(c)
    assert c.db.query(Chunk).count() > 0


def test_enrich_rechunks_on_chapter_boundaries(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """章节是 chunk 合并的硬边界，分章后必须重切。"""
    c, _ = ctx
    n = seeded(c, tmp_path)
    before = c.db.query(Chunk).count()

    result = EnrichResult(
        chapters=[
            ChapterOut(idx=i, title=f"C{i}", start_sentence_idx=i, end_sentence_idx=i)
            for i in range(n)
        ],
        translations={},
    )
    EnrichStage(FakeEnricher(result))(c)
    after = c.db.query(Chunk).count()
    assert after >= before
    assert after == n  # 每句一章 → 每章一个 chunk


def test_enrich_chunk_idx_is_continuous(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """前端显示 ¶11 / 53，编号必须跨章连续且从 0 起。"""
    c, _ = ctx
    n = seeded(c, tmp_path)
    result = EnrichResult(
        chapters=[
            ChapterOut(idx=0, title="A", start_sentence_idx=0, end_sentence_idx=0),
            ChapterOut(idx=1, title="B", start_sentence_idx=1, end_sentence_idx=n - 1),
        ],
        translations={},
    )
    EnrichStage(FakeEnricher(result))(c)
    idxs = [r.idx for r in c.db.query(Chunk).order_by(Chunk.idx)]
    assert idxs == list(range(len(idxs)))


def test_enrich_without_sentences_is_noop(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = ctx
    EnrichStage(FakeEnricher(EnrichResult(chapters=[], translations={})))(c)
    assert c.db.query(Chunk).count() == 0


def test_transcode_drops_source_to_save_disk(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """原始下载与 video.mp4 几乎一样大，留着等于每期占双份磁盘。"""
    c, _ = ctx
    ws = prepared(tmp_path, c.media.id)
    TranscodeStage(tmp_path, FakeFfmpeg())(c)
    assert ws.source() is None
    assert ws.video.exists()


def test_download_skips_redownload_after_source_cleanup(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """source 被 transcode 清掉后重试 enriching，不该把视频再拉一遍。"""
    c, _ = ctx
    y = FakeYtdlp(probe_ok())
    DownloadStage(tmp_path, y)(c)
    TranscodeStage(tmp_path, FakeFfmpeg())(c)
    DownloadStage(tmp_path, y)(c)
    assert y.downloaded == 1


def test_transcode_reuses_existing_products(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """已转码但 source 已被清理的目录，重跑不能报 SOURCE_MISSING。

    DownloadStage 说「source 在**或** video.mp4 在就算下载过了」，而本阶段
    成功后会删掉 source 省磁盘。两边的续跑判断一旦不对称，这种目录会卡在
    一个不可能自愈的状态：下载被跳过，转码却说找不到源文件。
    """
    c, _ = ctx
    ws = Workspace.for_media(tmp_path, c.media.id)
    ws.ensure()
    ws.video.write_bytes(b"m" * 50)
    ws.wav.write_bytes(b"w" * 50)
    assert ws.source() is None

    f = FakeFfmpeg()
    TranscodeStage(tmp_path, f)(c)

    assert f.remuxed == 0  # 没重新转
    assert f.wavs == 0
    assert c.media.video_path == f"{c.media.id}/video.mp4"


def test_transcode_does_not_reuse_empty_products(ctx, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """空文件不算数 —— 上次转到一半崩了，得重来。"""
    c, _ = ctx
    ws = prepared(tmp_path, c.media.id)
    ws.video.write_bytes(b"")
    ws.wav.write_bytes(b"")

    f = FakeFfmpeg()
    TranscodeStage(tmp_path, f)(c)
    assert f.remuxed == 1
    assert f.wavs == 1
