"""API 层测试。用 TestClient 打真实路由，DB 换成临时 SQLite。

重点：
  * 错误形状在所有路由一致 —— 前端只写一次解析
  * Range 的三种响应（200 / 206 / 416）—— seek 全靠它
  * 首页列表**没有** chunk_count 字段（PRD F1.2：首页只谈时长）
  * ready_partial 的素材 chunks 可取但 chapters 为空
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from de_nachhall.config import Settings
from de_nachhall.db.models import (
    Base,
    Chapter,
    Chunk,
    IngestJob,
    Media,
    Sentence,
    Source,
    Subscription,
    User,
    UserMedia,
)
from de_nachhall.db.session import create_db_engine
from de_nachhall.deps import get_db, settings
from de_nachhall.ingest.ytdlp import ProbeResult, YtdlpError
from de_nachhall.main import app

UID = 1
VIDEO = b"0123456789" * 100  # 1000 字节，方便算 Range


@pytest.fixture()
def env(tmp_path: Path):  # type: ignore[no-untyped-def]
    engine = create_db_engine(f"sqlite+pysqlite:///{tmp_path/'t.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    db.add_all([User(id=UID, name="me"), Source(id=1, name="logo!", kind="official")])
    db.flush()
    db.add(Subscription(user_id=UID, source_id=1))
    db.commit()

    media_root = tmp_path / "media"
    cfg = Settings(
        database_url=f"sqlite+pysqlite:///{tmp_path/'t.db'}",
        media_root=media_root,
        llm_provider="null",
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[settings] = lambda: cfg
    yield TestClient(app), db, media_root
    app.dependency_overrides.clear()
    db.close()


def mk_media(db, **kw) -> Media:  # type: ignore[no-untyped-def]
    base = dict(
        source_url=f"https://x.invalid/{kw.get('title', 'a')}",
        source_id=1,
        origin="official",
        title="logo! vom Freitag",
        published_on=date(2026, 8, 21),
        duration_ms=491000,
        status="ready",
    )
    base.update(kw)
    m = Media(**base)
    db.add(m)
    db.commit()
    return m


def mk_text(db, m: Media, *, titled: bool) -> None:  # type: ignore[no-untyped-def]
    db.add_all([
        Sentence(media_id=m.id, idx=0, start_ms=0, end_ms=3000, text="Hallo.",
                 word_count=1, translation_zh="你好。"),
        Sentence(media_id=m.id, idx=1, start_ms=3000, end_ms=6000, text="Welt.",
                 word_count=1, translation_zh="世界。"),
    ])
    ch = Chapter(media_id=m.id, idx=0, title="Gruß" if titled else None,
                 start_sentence_idx=0, end_sentence_idx=1, start_ms=0, end_ms=6000)
    db.add(ch)
    db.flush()
    db.add(Chunk(media_id=m.id, chapter_id=ch.id, idx=0, start_sentence_idx=0,
                 end_sentence_idx=1, start_ms=0, end_ms=6000, text="Hallo. Welt.", word_count=2))
    db.commit()


# ==================== 基础 ====================


def test_health(env) -> None:  # type: ignore[no-untyped-def]
    c, _, _ = env
    assert c.get("/api/health").json() == {"status": "ok"}


def test_openapi_generates(env) -> None:  # type: ignore[no-untyped-def]
    c, _, _ = env
    spec = c.get("/openapi.json").json()
    paths = spec["paths"]
    for p in ["/api/media", "/api/media/{media_id}", "/api/media/{media_id}/chunks",
              "/api/media/{media_id}/stream", "/api/sources"]:
        assert p in paths, p


def test_error_shape_is_uniform(env) -> None:  # type: ignore[no-untyped-def]
    c, _, _ = env
    for url in ["/api/media/999", "/api/media/999/chunks", "/api/media/999/stream"]:
        body = c.get(url).json()
        assert set(body) == {"error"}, url
        assert set(body["error"]) == {"code", "message"}, url
        assert body["error"]["message"], url


def test_validation_error_uses_same_shape(env) -> None:  # type: ignore[no-untyped-def]
    c, _, _ = env
    r = c.post("/api/media", json={"url": "x"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


# ==================== 时间线 ====================


def test_timeline_orders_by_date_then_id(env) -> None:  # type: ignore[no-untyped-def]
    c, db, _ = env
    mk_media(db, title="old", published_on=date(2026, 8, 1))
    mk_media(db, title="new", published_on=date(2026, 8, 21))
    mk_media(db, title="undated", published_on=None)
    got = [i["title"] for i in c.get("/api/media").json()["items"]]
    assert got == ["new", "old", "undated"]


def test_list_item_has_no_chunk_count(env) -> None:  # type: ignore[no-untyped-def]
    """PRD F1.2：首页只谈时长。字段不存在，前端就没法把它渲染出来。"""
    c, db, _ = env
    m = mk_media(db)
    mk_text(db, m, titled=True)
    item = c.get("/api/media").json()["items"][0]
    assert "chunk_count" not in item
    assert item["duration_ms"] == 491000


def test_processing_item_carries_progress(env) -> None:  # type: ignore[no-untyped-def]
    c, db, _ = env
    m = mk_media(db, status="processing")
    db.add(IngestJob(media_id=m.id, stage="transcribing", percent=42))
    db.commit()
    item = c.get("/api/media").json()["items"][0]
    assert item["job"]["stage"] == "transcribing"
    assert item["job"]["percent"] == 42


def test_ready_item_omits_job(env) -> None:  # type: ignore[no-untyped-def]
    c, db, _ = env
    m = mk_media(db, status="ready")
    db.add(IngestJob(media_id=m.id, stage="ready", percent=100))
    db.commit()
    assert c.get("/api/media").json()["items"][0]["job"] is None


def test_status_filter(env) -> None:  # type: ignore[no-untyped-def]
    c, db, _ = env
    mk_media(db, title="a", status="ready")
    mk_media(db, title="b", status="failed")
    got = c.get("/api/media", params={"status": "failed"}).json()["items"]
    assert [i["title"] for i in got] == ["b"]


# ==================== 详情与 chunks ====================


def test_detail_exposes_chapters_when_titled(env) -> None:  # type: ignore[no-untyped-def]
    c, db, _ = env
    m = mk_media(db)
    mk_text(db, m, titled=True)
    body = c.get(f"/api/media/{m.id}").json()
    assert [ch["title"] for ch in body["chapters"]] == ["Gruß"]
    assert body["chapters"][0]["chunk_count"] == 1
    assert body["chunk_count"] == 1


def test_partial_media_has_chunks_but_no_chapters(env) -> None:  # type: ignore[no-untyped-def]
    """转写完成即可跟读：chunks 有值，chapters 还空着。"""
    c, db, _ = env
    m = mk_media(db, status="ready_partial")
    mk_text(db, m, titled=False)
    body = c.get(f"/api/media/{m.id}").json()
    assert body["chapters"] == []
    assert body["chunk_count"] == 1
    assert len(c.get(f"/api/media/{m.id}/chunks").json()["chunks"]) == 1


def test_chunks_join_sentence_translations(env) -> None:  # type: ignore[no-untyped-def]
    c, db, _ = env
    m = mk_media(db)
    mk_text(db, m, titled=True)
    chunk = c.get(f"/api/media/{m.id}/chunks").json()["chunks"][0]
    assert chunk["translation_zh"] == "你好。世界。"
    assert chunk["chapter_idx"] == 0


def test_chunks_without_translation_is_null(env) -> None:  # type: ignore[no-untyped-def]
    c, db, _ = env
    m = mk_media(db)
    mk_text(db, m, titled=False)
    db.query(Sentence).update({Sentence.translation_zh: None})
    db.commit()
    assert c.get(f"/api/media/{m.id}/chunks").json()["chunks"][0]["translation_zh"] is None


# ==================== 导入 ====================


class FakeYtdlp:
    def __init__(self, result) -> None:  # type: ignore[no-untyped-def]
        self.result = result
        self.calls = 0

    def probe(self, url: str) -> ProbeResult:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def patch_ytdlp(monkeypatch: pytest.MonkeyPatch, fake: FakeYtdlp) -> None:
    import de_nachhall.routers.media as mod

    monkeypatch.setattr(mod, "Ytdlp", lambda **kw: fake)


def ok_probe(**kw) -> ProbeResult:  # type: ignore[no-untyped-def]
    base = dict(title="logo! vom Freitag, 21. August 2026", duration_ms=491000,
                platform="ZDF", thumbnail_url=None, has_video=True,
                upload_date="20260821", raw={"extractor_key": "ZDF"})
    base.update(kw)
    return ProbeResult(**base)  # type: ignore[arg-type]


def test_import_returns_real_metadata(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c, db, _ = env
    patch_ytdlp(monkeypatch, FakeYtdlp(ok_probe()))
    body = c.post("/api/media", json={"url": "https://www.logo.de/x-100.html"}).json()
    assert body["title"] == "logo! vom Freitag, 21. August 2026"
    assert body["duration_ms"] == 491000
    assert body["already_exists"] is False
    assert db.query(IngestJob).count() == 1


def test_import_is_idempotent_per_url(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """同一 URL 只转写一次（SPEC A7）。"""
    c, db, _ = env
    fake = FakeYtdlp(ok_probe())
    patch_ytdlp(monkeypatch, fake)
    url = "https://www.logo.de/x-100.html"
    first = c.post("/api/media", json={"url": url}).json()
    second = c.post("/api/media", json={"url": url}).json()
    assert second["already_exists"] is True
    assert second["media_id"] == first["media_id"]
    assert db.query(Media).count() == 1
    assert fake.calls == 1  # 第二次连 probe 都不该跑


@pytest.mark.parametrize(
    "err,status,code",
    [
        (YtdlpError("UNSUPPORTED_SITE", "这个站点抓不了。"), 400, "UNSUPPORTED_SITE"),
        (YtdlpError("INVALID_URL", "这不像一个网址。"), 400, "INVALID_URL"),
        (YtdlpError("PROBE_FAILED", "这个视频已经不在了。"), 502, "PROBE_FAILED"),
    ],
)
def test_import_failure_codes(env, monkeypatch, err, status, code) -> None:  # type: ignore[no-untyped-def]
    c, _, _ = env
    patch_ytdlp(monkeypatch, FakeYtdlp(err))
    r = c.post("/api/media", json={"url": "https://x.invalid/a"})
    assert r.status_code == status
    assert r.json()["error"]["code"] == code


def test_import_rejects_audio_only(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c, _, _ = env
    patch_ytdlp(monkeypatch, FakeYtdlp(ok_probe(has_video=False)))
    r = c.post("/api/media", json={"url": "https://x.invalid/a"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "AUDIO_NOT_SUPPORTED"


def test_import_error_messages_all_differ(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """四种失败的文案必须不同，否则分流没有意义。"""
    c, _, _ = env
    msgs = set()
    for err in [
        YtdlpError("UNSUPPORTED_SITE", "这个站点抓不了。支持 YouTube、ZDF、ARD 等常见视频站。"),
        YtdlpError("INVALID_URL", "这不像一个网址，检查是否漏了 https://"),
        YtdlpError("PROBE_FAILED", "这个视频已经不在了。"),
    ]:
        patch_ytdlp(monkeypatch, FakeYtdlp(err))
        msgs.add(c.post("/api/media", json={"url": "https://x.invalid/a"}).json()["error"]["message"])
    patch_ytdlp(monkeypatch, FakeYtdlp(ok_probe(has_video=False)))
    msgs.add(c.post("/api/media", json={"url": "https://x.invalid/b"}).json()["error"]["message"])
    assert len(msgs) == 4


# ==================== 重试与删除 ====================


def test_retry_clears_error_and_keeps_stage(env) -> None:  # type: ignore[no-untyped-def]
    """从记录的阶段续跑 —— stage 不能被重置，否则已下载的文件白下。"""
    c, db, _ = env
    m = mk_media(db, status="failed")
    db.add(IngestJob(media_id=m.id, stage="transcribing", percent=30,
                     error_code="TRANSCRIBE_FAILED", error_detail="显存不足"))
    db.commit()
    assert c.post(f"/api/media/{m.id}/retry").status_code == 200
    job = db.query(IngestJob).one()
    db.refresh(job)
    assert job.stage == "transcribing"
    assert job.error_code is None


def test_retry_on_healthy_media_is_conflict(env) -> None:  # type: ignore[no-untyped-def]
    c, db, _ = env
    m = mk_media(db, status="ready")
    r = c.post(f"/api/media/{m.id}/retry")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NOT_RETRYABLE"


def test_delete_rejects_subscription_media(env) -> None:  # type: ignore[no-untyped-def]
    c, db, _ = env
    m = mk_media(db, origin="official")
    r = c.delete(f"/api/media/{m.id}")
    assert r.status_code == 403
    assert "取消订阅" in r.json()["error"]["message"]


def test_delete_removes_user_media_and_files(env, tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, db, media_root = env
    m = mk_media(db, origin="user", source_id=None)
    db.add(UserMedia(user_id=UID, media_id=m.id))
    db.commit()
    d = media_root / str(m.id)
    d.mkdir(parents=True)
    (d / "video.mp4").write_bytes(b"x")

    assert c.delete(f"/api/media/{m.id}").status_code == 204
    assert db.query(Media).count() == 0
    assert not d.exists()


# ==================== Range ====================


@pytest.fixture()
def streamable(env):  # type: ignore[no-untyped-def]
    c, db, media_root = env
    m = mk_media(db, status="ready")
    d = media_root / str(m.id)
    d.mkdir(parents=True)
    (d / "video.mp4").write_bytes(VIDEO)
    m.video_path = f"{m.id}/video.mp4"
    db.commit()
    return c, m


def test_stream_without_range_advertises_support(streamable) -> None:  # type: ignore[no-untyped-def]
    c, m = streamable
    r = c.get(f"/api/media/{m.id}/stream")
    assert r.status_code == 200
    assert r.headers["accept-ranges"] == "bytes"
    assert r.content == VIDEO


@pytest.mark.parametrize(
    "header,expect_range,expect_body",
    [
        ("bytes=100-200", "bytes 100-200/1000", VIDEO[100:201]),
        ("bytes=0-0", "bytes 0-0/1000", VIDEO[0:1]),
        ("bytes=900-", "bytes 900-999/1000", VIDEO[900:]),
        ("bytes=-50", "bytes 950-999/1000", VIDEO[950:]),
        ("bytes=0-99999", "bytes 0-999/1000", VIDEO),
    ],
)
def test_stream_partial_content(streamable, header, expect_range, expect_body) -> None:  # type: ignore[no-untyped-def]
    c, m = streamable
    r = c.get(f"/api/media/{m.id}/stream", headers={"Range": header})
    assert r.status_code == 206
    assert r.headers["content-range"] == expect_range
    assert r.headers["content-length"] == str(len(expect_body))
    assert r.content == expect_body


@pytest.mark.parametrize("header", ["bytes=1000-1100", "bytes=2000-", "bytes=abc"])
def test_stream_out_of_range(streamable, header) -> None:  # type: ignore[no-untyped-def]
    c, m = streamable
    r = c.get(f"/api/media/{m.id}/stream", headers={"Range": header})
    assert r.status_code == 416
    assert r.headers["content-range"] == "bytes */1000"


def test_stream_before_ready_is_conflict(env) -> None:  # type: ignore[no-untyped-def]
    c, db, _ = env
    m = mk_media(db, status="processing")
    r = c.get(f"/api/media/{m.id}/stream")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NOT_READY"


def test_stream_missing_file_is_actionable(env) -> None:  # type: ignore[no-untyped-def]
    c, db, _ = env
    m = mk_media(db, status="ready")
    m.video_path = f"{m.id}/video.mp4"
    db.commit()
    r = c.get(f"/api/media/{m.id}/stream")
    assert r.status_code == 404
    assert "重试" in r.json()["error"]["message"]


def test_thumb(env) -> None:  # type: ignore[no-untyped-def]
    c, db, media_root = env
    m = mk_media(db)
    d = media_root / str(m.id)
    d.mkdir(parents=True)
    (d / "thumb.jpg").write_bytes(b"\xff\xd8jpeg")
    m.thumb_path = f"{m.id}/thumb.jpg"
    db.commit()
    r = c.get(f"/api/media/{m.id}/thumb")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


# ==================== sources ====================


def test_sources_lists_subscriptions(env) -> None:  # type: ignore[no-untyped-def]
    c, _, _ = env
    items = c.get("/api/sources").json()["items"]
    assert [s["name"] for s in items] == ["logo!"]
