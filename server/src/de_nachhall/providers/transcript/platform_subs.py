"""平台官方字幕优先。

Sprint 0 实测依据：
    ZDF / logo.de     4/4 有官方 deu VTT      几秒完成，拼写 100% 正确
    YouTube logo!     0/4 完全无字幕          必须回落 Whisper

选它而不是 Whisper 的理由：Whisper 的德语**复合词会拆错**
（Dopingkontrolle → Doping Kontrolle），这对德语学习者是实害。
代价是广播字幕按阅读速度压缩了约 10% 的词，但被删的多半是口吃重复。
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from de_nachhall.providers.transcript.base import FragmentOut, MediaRef, TranscriptProvider
from de_nachhall.providers.transcript.vtt import parse_vtt

log = logging.getLogger(__name__)

# 语言码在不同站点写法不一：ZDF 用 deu，YouTube 用 de
_LANG_ALIASES = {"de": ("de", "deu", "ger", "de-DE", "de-de")}


def pick_subtitle_lang(probe: dict[str, Any], lang: str) -> str | None:
    """从 probe 里找**上传的**字幕轨，自动生成的不算。

    automatic_captions 是机器转的，质量不比 Whisper 好，还多一次网络往返。
    """
    wanted = _LANG_ALIASES.get(lang, (lang,))
    subs = probe.get("subtitles") or {}
    for key in subs:
        if key in wanted or key.split("-")[0] in wanted:
            return str(key)
    return None


class PlatformSubsProvider:
    name = "platform_subs"

    def __init__(self, ytdlp_bin: str = "yt-dlp", proxy: str | None = None) -> None:
        self.ytdlp_bin = ytdlp_bin
        self.proxy = proxy

    def transcribe(self, media: MediaRef, lang: str) -> list[FragmentOut] | None:
        track = pick_subtitle_lang(media.probe, lang)
        if track is None:
            log.info("no uploaded %s subtitles for %s, falling back", lang, media.source_url)
            return None

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sub"
            cmd = [
                self.ytdlp_bin,
                "--skip-download",
                "--write-subs",
                "--sub-langs",
                track,
                "--sub-format",
                "vtt/srt/best",
                "--no-warnings",
                "-o",
                str(out),
                media.source_url,
            ]
            if self.proxy:
                cmd[1:1] = ["--proxy", self.proxy]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=180)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                # 拿不到字幕不是故障，是「这条路走不通」—— 回落 Whisper
                log.warning("subtitle fetch failed for %s: %s", media.source_url, e)
                return None

            files = sorted(Path(tmp).glob("sub*.vtt")) or sorted(Path(tmp).glob("sub*.srt"))
            if not files:
                return None
            frags = parse_vtt(files[0].read_text(encoding="utf-8", errors="replace"))

        if not frags:
            return None
        log.info("platform subtitles: %d fragments from %s", len(frags), track)
        return frags


_: TranscriptProvider = PlatformSubsProvider()
