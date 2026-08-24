"""本地 GPU 转写，作为无平台字幕时的兜底。

Sprint 0 实测（RTX 3060 Laptop，6144 MiB 总显存，桌面占约 1 GB）：

    large-v3 · float16       → CUDA out of memory        ✗
    large-v3 · int8_float16  → 61.6 s / 491.6 s 音频      ✓  8.0× 实时
                               词准确率 98.2%

**默认必须是 int8_float16。** float16 的纸面显存占用是 3.1 GB，看似放得下
6 GB，但加上桌面占用与 beam search 的 KV cache 就 OOM 了。

已知缺陷：德语复合词会被拆开（Dopingkontrolle → Doping Kontrolle）。
这是选「平台字幕优先」的主要理由。
"""

from __future__ import annotations

import logging
from typing import Any

from de_nachhall.providers.transcript.base import (
    FragmentOut,
    MediaRef,
    TranscribeError,
    TranscriptProvider,
)

log = logging.getLogger(__name__)

_OOM_HINT = (
    "显存不足。把 WHISPER_DEVICE 改为 cpu（会慢到数分钟但能跑完），"
    "或换更小的 WHISPER_MODEL（如 medium）。"
)


# 末尾留一点余量：正好切在最后一个词的词尾会把爆破音的收尾剪掉，
# 听起来像被掐断。钳在 Whisper 自己给的 segment 末尾之内，不会越界到下一段。
_TAIL_PAD_S = 0.08


def _speech_span(seg: Any) -> tuple[float, float]:
    """从词级时间戳取真正的语音区间。

    没有词（极少数情况，比如整段是拟声或标点）时退回 segment 边界。
    """
    words = [w for w in (getattr(seg, "words", None) or []) if str(w.word).strip()]
    if not words:
        return float(seg.start), float(seg.end)
    start = float(words[0].start)
    end = min(float(words[-1].end) + _TAIL_PAD_S, float(seg.end))
    # 词级时间戳偶尔会给出倒序或零长区间，兜一下
    return (start, end) if end > start else (float(seg.start), float(seg.end))


class FasterWhisperProvider:
    name = "faster_whisper"

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        compute_type: str = "int8_float16",
        download_root: str | None = "/models",
        beam_size: int = 5,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.download_root = download_root
        self.beam_size = beam_size
        self._model: Any = None

    def _load(self) -> Any:
        """常驻加载，不卸载 —— 单用户场景下重复加载（约 5 秒）的开销
        远大于占着显存。"""
        if self._model is None:
            from faster_whisper import WhisperModel

            log.info("loading whisper %s on %s/%s", self.model_size, self.device, self.compute_type)
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=self.download_root,
            )
        return self._model

    def transcribe(self, media: MediaRef, lang: str) -> list[FragmentOut] | None:
        if media.wav_path is None or not media.wav_path.exists():
            raise TranscribeError("缺少音频文件，转码阶段可能未完成。")

        try:
            model = self._load()
            segments, _info = model.transcribe(
                str(media.wav_path),
                language=lang,
                vad_filter=True,
                # 开着它，边界才贴到真正的语音上。
                # segment 级的 start/end 带着 VAD 的静音余量 —— 跟读时
                # 每段前后各多出几百毫秒的空白，一段一段累积起来很难受。
                word_timestamps=True,
                beam_size=self.beam_size,
            )
            out: list[FragmentOut] = []
            for seg in segments:
                text = seg.text.strip()
                if not text:
                    continue
                start_s, end_s = _speech_span(seg)
                out.append(
                    FragmentOut(
                        idx=len(out),
                        start_ms=int(start_s * 1000),
                        end_ms=int(end_s * 1000),
                        text=text,
                    )
                )
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                raise TranscribeError(_OOM_HINT) from e
            raise TranscribeError(f"转写失败：{e}") from e
        except ImportError as e:
            raise TranscribeError(
                "faster-whisper 未安装。api 镜像刻意不含它，转写只在 worker 容器里跑。"
            ) from e

        if not out:
            raise TranscribeError("转写结果为空，音频可能是静音或损坏。")
        log.info("whisper produced %d fragments", len(out))
        return out


_: TranscriptProvider = FasterWhisperProvider()
