"""ffmpeg / ffprobe 封装。

**重封装不是可选项**（SPEC §9.1a）。Sprint 0 的 V2b 卡在这里查了三层才发现：
yt-dlp 把 HLS 下载结果存成 .mp4，实际容器是 MPEG-TS。TS 没有 moov 索引，
浏览器 seek 不了，video.currentTime = X 之后 seeked 永远不来 —— 回声闭环
的每一步都要 seek，这条路不通产品就不成立。

所以 TASK-018 的「不重编码」要理解成「不重新编码码流」，而不是「不处理」。
    ffmpeg -c copy -bsf:a aac_adtstoasc -movflags +faststart
实测 8 分钟视频 0.46 s，代价可以忽略。
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# 已经是 mp4/mov 家族就不用换容器了，只有这些需要重封装
_NEEDS_REMUX = frozenset({"mpegts", "matroska", "webm", "matroska,webm", "flv", "avi"})


class FfmpegError(RuntimeError):
    pass


class Ffmpeg:
    def __init__(self, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
                 timeout_s: int = 900) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.timeout_s = timeout_s

    def _run(self, cmd: list[str], what: str) -> subprocess.CompletedProcess[str]:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout_s)
        except FileNotFoundError as e:
            raise FfmpegError(f"找不到 {cmd[0]}，请确认容器内已安装 ffmpeg。") from e
        except subprocess.TimeoutExpired as e:
            raise FfmpegError(f"{what}超时。") from e
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip().splitlines()
            raise FfmpegError(f"{what}失败：{tail[-1][:200] if tail else '未知错误'}")
        return proc

    # ---------- 探测 ----------

    def probe(self, path: Path) -> dict[str, Any]:
        proc = self._run(
            [self.ffprobe, "-v", "error", "-show_format", "-show_streams",
             "-of", "json", str(path)],
            "读取视频信息",
        )
        try:
            data: dict[str, Any] = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise FfmpegError("视频信息解析失败。") from e
        return data

    @staticmethod
    def format_name(info: dict[str, Any]) -> str:
        return str(info.get("format", {}).get("format_name") or "")

    @staticmethod
    def duration_ms(info: dict[str, Any]) -> int | None:
        raw = info.get("format", {}).get("duration")
        try:
            return int(float(raw) * 1000)
        except (TypeError, ValueError):
            return None

    @classmethod
    def needs_remux(cls, info: dict[str, Any]) -> bool:
        fmt = cls.format_name(info)
        # format_name 可能是 "mov,mp4,m4a,3gp,3g2,mj2" 这种逗号列表
        names = {n.strip() for n in fmt.split(",") if n.strip()}
        if "mp4" in names or "mov" in names:
            return False
        return bool(names & _NEEDS_REMUX) or bool(names)

    # ---------- 转换 ----------

    def remux_to_mp4(self, src: Path, dst: Path) -> None:
        """只换容器，码流原样拷贝。

        -map 0:v:0 -map 0:a:0  TS 常带多套 program 与 timed_id3，只取第一路视音频
        -bsf:a aac_adtstoasc    ADTS(AAC in TS) → ASC(AAC in mp4)，不转这个 mp4 播不出声
        -movflags +faststart    moov 提到文件头，浏览器不用下完全片就能 seek
        """
        tmp = dst.with_suffix(".tmp.mp4")
        self._run(
            [self.ffmpeg, "-y", "-loglevel", "error", "-i", str(src),
             "-map", "0:v:0", "-map", "0:a:0", "-c", "copy",
             "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", str(tmp)],
            "重封装视频",
        )
        tmp.replace(dst)

    def extract_wav(self, src: Path, dst: Path) -> None:
        """16 kHz 单声道 PCM —— faster-whisper 的原生输入格式，省一次内部重采样。"""
        tmp = dst.with_suffix(".tmp.wav")
        self._run(
            [self.ffmpeg, "-y", "-loglevel", "error", "-i", str(src),
             "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(tmp)],
            "提取音频",
        )
        tmp.replace(dst)
