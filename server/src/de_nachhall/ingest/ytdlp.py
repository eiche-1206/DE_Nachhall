"""yt-dlp 封装：probe 与下载。

**不维护站点白名单**（SPEC §5.3）。能不能抓由 yt-dlp 说了算，
它覆盖上千站点，白名单既不完备又要持续跟进。

probe 提到提交阶段执行：一次调用同时拿到「能否抓 / 标题 / 时长 /
是否纯音频 / 缩略图 / 平台」，换来即时且准确的错误反馈。
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_URL_SHAPE = re.compile(r"^https?://[^\s/]+\.[^\s/]+", re.I)

_UNSUPPORTED_MSG = "这个站点抓不了。支持 YouTube、ZDF、ARD 等常见视频站。"

# yt-dlp 的报错文本 → 面向用户的错误码。
# 四种失败必须分开说：用户的下一步动作完全不同。
_ERROR_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("unsupported url", "UNSUPPORTED_SITE", _UNSUPPORTED_MSG),
    ("no suitable extractor", "UNSUPPORTED_SITE", _UNSUPPORTED_MSG),
    ("video unavailable", "PROBE_FAILED", "这个视频已经不在了。"),
    ("has been removed", "PROBE_FAILED", "这个视频已经不在了。"),
    ("not available in your country", "PROBE_FAILED",
     "这个视频在当前网络下看不到，可能有地域限制。"),
    ("geo restricted", "PROBE_FAILED",
     "这个视频在当前网络下看不到，可能有地域限制。"),
    ("sign in", "PROBE_FAILED", "这个视频需要登录才能看，暂时抓不了。"),
    ("private video", "PROBE_FAILED", "这是私享视频，抓不了。"),
    ("members-only", "PROBE_FAILED", "这个视频仅会员可见，抓不了。"),
)


class YtdlpError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ProbeResult:
    title: str
    duration_ms: int | None
    platform: str | None
    thumbnail_url: str | None
    has_video: bool
    upload_date: str | None
    raw: dict[str, Any]


def looks_like_url(url: str) -> bool:
    return bool(_URL_SHAPE.match(url.strip()))


def _classify(stderr: str) -> YtdlpError:
    low = stderr.lower()
    for needle, code, msg in _ERROR_PATTERNS:
        if needle in low:
            return YtdlpError(code, msg)

    # 404 有两种含义，靠 extractor 区分：
    #   [generic] —— 没有专用 extractor，等于站点不支持
    #   [zdf] 等  —— 有 extractor 但页面没了，等于视频下架
    # ZDF 的下架实测报的是 "Failed to download fallback metadata: HTTP Error 404"，
    # 不含 "video unavailable"，所以上面的关键词表接不住，必须补这条。
    if "404" in low or "not found" in low:
        if "[generic]" in low:
            return YtdlpError("UNSUPPORTED_SITE", _UNSUPPORTED_MSG)
        return YtdlpError("PROBE_FAILED", "这个视频已经不在了。")

    tail = stderr.strip().splitlines()[-1][:200] if stderr.strip() else ""
    return YtdlpError("PROBE_FAILED", f"抓取失败：{tail}" if tail else "抓取失败。")


class Ytdlp:
    def __init__(self, bin_path: str = "yt-dlp", proxy: str | None = None,
                 timeout_s: int = 180) -> None:
        self.bin = bin_path
        self.proxy = proxy
        self.timeout_s = timeout_s

    def _base(self) -> list[str]:
        cmd = [self.bin, "--no-warnings", "--no-playlist"]
        if self.proxy:
            cmd += ["--proxy", self.proxy]
        return cmd

    def probe(self, url: str) -> ProbeResult:
        if not looks_like_url(url):
            raise YtdlpError("INVALID_URL", "这不像一个网址，检查是否漏了 https://")

        try:
            proc = subprocess.run(
                [*self._base(), "--dump-single-json", "--skip-download", url],
                capture_output=True, text=True, timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired as e:
            raise YtdlpError("PROBE_FAILED", "读取视频信息超时，检查网络或代理。") from e

        if proc.returncode != 0:
            raise _classify(proc.stderr)

        try:
            info: dict[str, Any] = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise YtdlpError("PROBE_FAILED", "视频信息解析失败。") from e

        has_video = any(
            f.get("vcodec") not in (None, "none") for f in info.get("formats") or []
        ) or info.get("vcodec") not in (None, "none")

        dur = info.get("duration")
        return ProbeResult(
            title=str(info.get("title") or url),
            duration_ms=int(float(dur) * 1000) if dur else None,
            platform=info.get("extractor_key") or info.get("extractor"),
            thumbnail_url=info.get("thumbnail"),
            has_video=bool(has_video),
            upload_date=info.get("upload_date"),
            raw=info,
        )

    def download(self, url: str, out_dir: Path, basename: str = "video") -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        tmpl = str(out_dir / f"{basename}.%(ext)s")
        try:
            proc = subprocess.run(
                [*self._base(),
                 "-f", "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b",
                 "--merge-output-format", "mp4",
                 "-o", tmpl, url],
                capture_output=True, text=True, timeout=self.timeout_s * 10,
            )
        except subprocess.TimeoutExpired as e:
            raise YtdlpError("DOWNLOAD_FAILED", "下载超时，可重试。") from e

        if proc.returncode != 0:
            err = _classify(proc.stderr)
            raise YtdlpError("DOWNLOAD_FAILED", err.message)

        files = sorted(out_dir.glob(f"{basename}.*"))
        media = [f for f in files if f.suffix.lower() in (".mp4", ".mkv", ".webm", ".ts")]
        if not media:
            raise YtdlpError("DOWNLOAD_FAILED", "下载完成但找不到视频文件。")
        return media[0]

    def download_thumbnail(self, url: str, out_dir: Path) -> Path | None:
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [*self._base(), "--skip-download", "--write-thumbnail",
                 "--convert-thumbnails", "jpg",
                 "-o", str(out_dir / "thumb.%(ext)s"), url],
                capture_output=True, text=True, timeout=60, check=False,
            )
        except subprocess.TimeoutExpired:
            return None
        found = sorted(out_dir.glob("thumb.*"))
        return found[0] if found else None
