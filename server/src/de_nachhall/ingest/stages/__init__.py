"""四个阶段的实现，以及按配置组装它们的工厂。"""

from __future__ import annotations

from de_nachhall.config import Settings
from de_nachhall.ingest.ffmpeg import Ffmpeg
from de_nachhall.ingest.runner import StageFn
from de_nachhall.ingest.stages.download import DownloadStage
from de_nachhall.ingest.stages.enrich import EnrichStage
from de_nachhall.ingest.stages.transcode import TranscodeStage
from de_nachhall.ingest.stages.transcribe import TranscribeStage
from de_nachhall.ingest.ytdlp import Ytdlp
from de_nachhall.providers.enrich.factory import build_enricher
from de_nachhall.providers.transcript.base import TranscriptProvider
from de_nachhall.providers.transcript.platform_subs import PlatformSubsProvider

__all__ = [
    "DownloadStage",
    "EnrichStage",
    "TranscodeStage",
    "TranscribeStage",
    "build_stages",
]


def _transcript_providers(settings: Settings) -> list[TranscriptProvider]:
    """顺序即优先级：平台字幕 → Whisper。

    faster_whisper 延迟导入：api 容器故意不装它（省 2 GB 镜像），
    在模块顶层导入会让 api 起不来。
    """
    providers: list[TranscriptProvider] = [PlatformSubsProvider(proxy=settings.https_proxy)]
    try:
        from de_nachhall.providers.transcript.faster_whisper import FasterWhisperProvider
    except ImportError:
        return providers

    providers.append(
        FasterWhisperProvider(
            model_size=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    )
    return providers


def build_stages(settings: Settings) -> dict[str, StageFn]:
    ytdlp = Ytdlp(proxy=settings.https_proxy)
    ffmpeg = Ffmpeg()
    return {
        "downloading": DownloadStage(settings.media_root, ytdlp),
        "transcoding": TranscodeStage(settings.media_root, ffmpeg),
        "transcribing": TranscribeStage(
            settings.media_root,
            _transcript_providers(settings),
            lang=settings.transcript_lang,
            target_words=settings.chunk_target_words,
        ),
        "enriching": EnrichStage(
            build_enricher(settings), target_words=settings.chunk_target_words
        ),
    }
