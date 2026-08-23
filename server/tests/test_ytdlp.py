"""yt-dlp 封装测试。全部走假的 subprocess，不碰网络。

重点是**失败分流**：四种失败对用户的下一步动作完全不同 ——
换个站点 / 视频没了 / 挂代理 / 登录，文案必须能区分开。
"""

from __future__ import annotations

import json
import subprocess

import pytest

from de_nachhall.ingest.ytdlp import Ytdlp, YtdlpError, looks_like_url

INFO = {
    "title": "logo! vom 21. August 2026",
    "duration": 491.2,
    "extractor_key": "ZDF",
    "thumbnail": "https://example.invalid/t.jpg",
    "upload_date": "20260821",
    "formats": [{"vcodec": "h264", "acodec": "aac"}],
}


def fake_run(stdout: str = "", stderr: str = "", rc: int = 0):  # type: ignore[no-untyped-def]
    def run(cmd, **kw):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(cmd, rc, stdout, stderr)

    return run


@pytest.mark.parametrize(
    "url,ok",
    [
        ("https://www.logo.de/1234", True),
        ("http://zdf.de/x", True),
        ("logo.de/1234", False),
        ("随便写点字", False),
        ("", False),
    ],
)
def test_url_shape(url: str, ok: bool) -> None:
    assert looks_like_url(url) is ok


def test_probe_extracts_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", fake_run(json.dumps(INFO)))
    r = Ytdlp().probe("https://www.logo.de/1234")
    assert r.title == "logo! vom 21. August 2026"
    assert r.duration_ms == 491200
    assert r.platform == "ZDF"
    assert r.upload_date == "20260821"
    assert r.has_video is True


def test_probe_detects_audio_only(monkeypatch: pytest.MonkeyPatch) -> None:
    info = {**INFO, "formats": [{"vcodec": "none", "acodec": "mp3"}], "vcodec": "none"}
    monkeypatch.setattr(subprocess, "run", fake_run(json.dumps(info)))
    assert Ytdlp().probe("https://x.invalid/a").has_video is False


def test_probe_rejects_non_url() -> None:
    with pytest.raises(YtdlpError) as e:
        Ytdlp().probe("这不是网址")
    assert e.value.code == "INVALID_URL"


@pytest.mark.parametrize(
    "stderr,code,fragment",
    [
        ("ERROR: Unsupported URL: https://x.invalid/a", "UNSUPPORTED_SITE", "站点抓不了"),
        ("ERROR: Video unavailable", "PROBE_FAILED", "已经不在了"),
        ("ERROR: This video is not available in your country", "PROBE_FAILED", "地域限制"),
        ("ERROR: Sign in to confirm your age", "PROBE_FAILED", "需要登录"),
    ],
)
def test_failure_reasons_are_distinct(
    monkeypatch: pytest.MonkeyPatch, stderr: str, code: str, fragment: str
) -> None:
    monkeypatch.setattr(subprocess, "run", fake_run(stderr=stderr, rc=1))
    with pytest.raises(YtdlpError) as e:
        Ytdlp().probe("https://x.invalid/a")
    assert e.value.code == code
    assert fragment in e.value.message


def test_all_four_reasons_have_different_text() -> None:
    """四种失败的文案不能雷同，否则分流没有意义。"""
    from de_nachhall.ingest.ytdlp import _ERROR_PATTERNS

    msgs = {m for _, _, m in _ERROR_PATTERNS}
    assert len(msgs) >= 4


def test_probe_timeout_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(cmd, **kw):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(YtdlpError) as e:
        Ytdlp().probe("https://x.invalid/a")
    assert "代理" in e.value.message


def test_proxy_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def run(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, json.dumps(INFO), "")

    monkeypatch.setattr(subprocess, "run", run)
    Ytdlp(proxy="http://proxy.invalid:1080").probe("https://x.invalid/a")
    assert "--proxy" in seen[0]
    assert "http://proxy.invalid:1080" in seen[0]


def test_download_finds_output(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    def run(cmd, **kw):  # type: ignore[no-untyped-def]
        (tmp_path / "source.mp4").write_bytes(b"x")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    got = Ytdlp().download("https://x.invalid/a", tmp_path, basename="source")
    assert got.name == "source.mp4"


def test_download_reports_missing_output(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(subprocess, "run", fake_run())
    with pytest.raises(YtdlpError) as e:
        Ytdlp().download("https://x.invalid/a", tmp_path)
    assert e.value.code == "DOWNLOAD_FAILED"


@pytest.mark.parametrize(
    "stderr,code,fragment",
    [
        # ZDF 下架实测原文：不含 "video unavailable"，只有 404
        ("ERROR: [zdf] logo-x: Failed to download fallback metadata: HTTP Error 404: Not Found",
         "PROBE_FAILED", "已经不在了"),
        # 没有专用 extractor 时 yt-dlp 退到 generic，同样报 404，但含义相反
        ("ERROR: [generic] page: Unable to download webpage: HTTP Error 404: Not Found",
         "UNSUPPORTED_SITE", "站点抓不了"),
    ],
)
def test_404_is_split_by_extractor(
    monkeypatch: pytest.MonkeyPatch, stderr: str, code: str, fragment: str
) -> None:
    monkeypatch.setattr(subprocess, "run", fake_run(stderr=stderr, rc=1))
    with pytest.raises(YtdlpError) as e:
        Ytdlp().probe("https://x.invalid/a")
    assert e.value.code == code
    assert fragment in e.value.message
