"""transcoding —— 重封装成可 seek 的 mp4，并抽出 16k 单声道 wav。

两件事都做完才算这一阶段完成：
  video.mp4  前端播放与 seek 的对象
  audio.wav  Whisper 的输入（平台有字幕时用不上，但转出来很便宜，且重试时省事）
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from de_nachhall.db.models import Media
from de_nachhall.ingest.ffmpeg import Ffmpeg, FfmpegError
from de_nachhall.ingest.runner import StageContext, StageError
from de_nachhall.ingest.workspace import Workspace

log = logging.getLogger(__name__)


def _usable(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


class TranscodeStage:
    def __init__(self, media_root: Path, ffmpeg: Ffmpeg) -> None:
        self.media_root = Path(media_root)
        self.ffmpeg = ffmpeg

    def __call__(self, ctx: StageContext) -> None:
        ws = Workspace.for_media(self.media_root, ctx.media.id)

        # 重试续跑：产物都在就直接复用。
        #
        # 这一条必须和 DownloadStage 的判断**对称**。它说「source 在**或**
        # video.mp4 在就算下载过了」，而本阶段成功后会把 source 删掉省磁盘 ——
        # 于是「已转码但 source 已清理」的目录再跑一遍时，下载被跳过、
        # 这里却报 SOURCE_MISSING，整条素材卡死在一个不可能自愈的状态。
        if _usable(ws.video) and _usable(ws.wav):
            log.info("media %s: reuse transcoded video + wav", ctx.media.id)
            self._record(ctx, ws, duration_ms=None)
            ctx.report(100)
            return

        src = ws.source()
        if src is None:
            raise StageError("SOURCE_MISSING", "找不到下载好的文件，请重试整条素材。")

        try:
            info = self.ffmpeg.probe(src)
        except FfmpegError as e:
            raise StageError("PROBE_FAILED", str(e)) from e

        fmt = Ffmpeg.format_name(info)
        ctx.report(10)

        try:
            if Ffmpeg.needs_remux(info):
                log.info("media %s: remux %s → mp4", ctx.media.id, fmt)
                self.ffmpeg.remux_to_mp4(src, ws.video)
            elif src.resolve() != ws.video.resolve():
                # 已经是 mp4 家族，但 moov 未必在头部；copy 一遍加 faststart 更稳
                log.info("media %s: %s 已是 mp4，仅加 faststart", ctx.media.id, fmt)
                try:
                    self.ffmpeg.remux_to_mp4(src, ws.video)
                except FfmpegError:
                    shutil.copy2(src, ws.video)
            ctx.report(60)
            self.ffmpeg.extract_wav(ws.video if ws.video.exists() else src, ws.wav)
        except FfmpegError as e:
            raise StageError("TRANSCODE_FAILED", str(e)) from e

        if not ws.video.exists() or ws.video.stat().st_size == 0:
            raise StageError("TRANSCODE_FAILED", "重封装后的视频是空的。")
        if not ws.wav.exists() or ws.wav.stat().st_size == 0:
            raise StageError("TRANSCODE_FAILED", "抽出来的音频是空的，这个视频可能没有声轨。")

        self._record(ctx, ws, duration_ms=Ffmpeg.duration_ms(info))

        # 产物齐了就删原始下载 —— 它和 video.mp4 几乎一样大，留着等于每期
        # 占双份磁盘。真要重来一遍，重试会从 downloading 重新拉。
        if src.resolve() != ws.video.resolve():
            saved = src.stat().st_size
            src.unlink(missing_ok=True)
        else:
            saved = 0

        ctx.report(100)
        log.info("media %s transcoded: video %.1f MB, wav %.1f MB（清理原始文件 %.1f MB）",
                 ctx.media.id, ws.video.stat().st_size / 1e6,
                 ws.wav.stat().st_size / 1e6, saved / 1e6)

    @staticmethod
    def _record(ctx: StageContext, ws: Workspace, duration_ms: int | None) -> None:
        fields: dict[Any, Any] = {Media.video_path: ws.rel(ws.video)}
        if ctx.media.duration_ms is None and duration_ms is not None:
            fields[Media.duration_ms] = duration_ms
        ctx.db.query(Media).filter(Media.id == ctx.media.id).update(fields)
        ctx.db.commit()
        ctx.db.refresh(ctx.media)
