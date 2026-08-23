"""集中配置。所有环境变量只在这里读一次。

设计约束（来自 SPEC §8.1）：
  - 缺必需变量时启动即失败，且错误必须指明缺哪个、怎么补
  - 条件必需项按 LLM_PROVIDER 分支校验
  - CPU 环境自动降级 compute_type —— float16 / int8_float16 在 CTranslate2
    的 CPU 后端上不可用，不降级会在转写阶段才炸
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["claude", "openai_compat", "null"]
WhisperDevice = Literal["cuda", "cpu"]

# CTranslate2 的 CPU 后端不支持这些，命中即降级
_CUDA_ONLY_COMPUTE_TYPES = frozenset({"float16", "int8_float16"})
_CPU_FALLBACK_COMPUTE_TYPE = "int8"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 数据与媒体 ----
    # MVP 用 SQLite；换 Postgres 只需改这一行 + JobsRepository 的出队实现
    database_url: str = "sqlite+pysqlite:////data/de_nachhall.db"
    media_root: Path = Path("/data/media")

    # ---- LLM（分章 + 标题 + 逐句中文翻译，单次调用） ----
    llm_provider: LLMProvider = "claude"
    llm_model: str = "claude-sonnet-5"
    anthropic_api_key: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None

    # ---- 网络 ----
    # 变量名与 HTTPS_PROXY 环境变量同名，宿主已导出的代理直接生效，不用另配一份。
    # worker 容器用 network_mode: host 才够得着宿主的 127.0.0.1:7897（SPEC §11.3 B1）。
    https_proxy: str | None = None

    # ---- 转写 ----
    transcript_lang: str = "de"
    whisper_model: str = "large-v3"
    whisper_device: WhisperDevice = "cuda"
    # 默认 int8_float16 而非 float16 —— Sprint 0 实测 float16 在 6GB 卡上 OOM
    whisper_compute_type: str = "int8_float16"

    # ---- 切分 ----
    # 目标词数而非阈值。bestfit 就近取优，不设硬上限。
    chunk_target_words: int = 22

    # ---- 回声 ----
    record_timeout_s: int = 180

    # ---- worker ----
    worker_poll_interval_s: int = 2

    @model_validator(mode="after")
    def _downgrade_compute_type_on_cpu(self) -> Settings:
        """CPU 上把 CUDA 专用的 compute_type 降为 int8。

        无条件降级，不看用户是否显式设置——因为 float16 / int8_float16
        在 CPU 后端根本跑不起来，"尊重用户设置"只会把失败推迟到转写阶段。
        """
        if self.whisper_device == "cpu" and self.whisper_compute_type in _CUDA_ONLY_COMPUTE_TYPES:
            object.__setattr__(self, "whisper_compute_type", _CPU_FALLBACK_COMPUTE_TYPE)
        return self

    @model_validator(mode="after")
    def _validate_ranges(self) -> Settings:
        if self.chunk_target_words < 5:
            raise ValueError("CHUNK_TARGET_WORDS 至少为 5，太小会把句子切碎到无法跟读。")
        if self.record_timeout_s < 10:
            raise ValueError("RECORD_TIMEOUT_S 至少为 10 秒。")
        if self.worker_poll_interval_s < 1:
            raise ValueError("WORKER_POLL_INTERVAL_S 至少为 1 秒。")
        return self


class LLMConfigError(RuntimeError):
    """LLM 凭据缺失。只有真正要调 LLM 的进程才关心。"""


def require_llm_credentials(settings: Settings) -> None:
    """按 LLM_PROVIDER 分支校验条件必需项。**由 worker 在启动时调用。**

    刻意不放在 Settings 的校验器里 —— 那样 api 也会被卡住，而 api
    从头到尾不碰 LLM（enrich 只发生在 worker）。放进去的后果实测过：
    api 能起来、/api/health 返回 200，但每条真实请求都 500，
    因为 Settings 直到第一次要 DB session 时才构造。

    错误必须说明怎么补。
    """
    if settings.llm_provider == "claude" and not settings.anthropic_api_key:
        raise LLMConfigError(
            "LLM_PROVIDER=claude 时必须设置 ANTHROPIC_API_KEY。"
            "在 .env 中填入，或改用 LLM_PROVIDER=null 跳过分章与翻译。"
        )

    if settings.llm_provider == "openai_compat":
        missing = [
            name
            for name, value in (
                ("LLM_API_KEY", settings.llm_api_key),
                ("LLM_BASE_URL", settings.llm_base_url),
            )
            if not value
        ]
        if missing:
            raise LLMConfigError(
                f"LLM_PROVIDER=openai_compat 时必须设置 {' 与 '.join(missing)}。"
                "例如千问：LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """全局单例。调用点一律用它，不要各处 new Settings()。"""
    return Settings()
