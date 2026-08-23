"""config 的行为测试。重点是两处容易在部署时才炸的规则。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from de_nachhall.config import LLMConfigError, Settings, require_llm_credentials

BASE = {"anthropic_api_key": "sk-test"}


class TestComputeTypeDowngrade:
    """CPU 上必须降级，否则失败会推迟到转写阶段才暴露。"""

    @pytest.mark.parametrize("given", ["float16", "int8_float16"])
    def test_cuda_only_types_downgrade_on_cpu(self, given: str) -> None:
        s = Settings(**BASE, whisper_device="cpu", whisper_compute_type=given)
        assert s.whisper_compute_type == "int8"

    def test_cpu_keeps_already_valid_type(self) -> None:
        s = Settings(**BASE, whisper_device="cpu", whisper_compute_type="int8")
        assert s.whisper_compute_type == "int8"

    def test_cuda_keeps_float16_family(self) -> None:
        s = Settings(**BASE, whisper_device="cuda", whisper_compute_type="int8_float16")
        assert s.whisper_compute_type == "int8_float16"

    def test_default_is_int8_float16_not_float16(self) -> None:
        # Sprint 0 实测：float16 在 6GB 卡上 OOM
        assert Settings(**BASE).whisper_compute_type == "int8_float16"


class TestLLMCredentials:
    """凭据校验**不在 Settings 里**，由 worker 启动时显式调用。

    放进 Settings 的校验器有个实测踩过的后果：api 从头到尾不碰 LLM，
    却会因为缺 key 而无法构造 Settings —— 而 Settings 是第一次要
    DB session 时才构造的，于是 /api/health 返回 200、每条数据请求 500。
    """

    def test_settings_alone_never_requires_llm_key(self) -> None:
        # api 进程就是这样起的：不给任何 LLM 凭据也必须能构造
        s = Settings(llm_provider="claude", anthropic_api_key=None)
        assert s.llm_provider == "claude"

    def test_claude_requires_key(self) -> None:
        with pytest.raises(LLMConfigError) as e:
            require_llm_credentials(Settings(llm_provider="claude", anthropic_api_key=None))
        assert "ANTHROPIC_API_KEY" in str(e.value)

    def test_openai_compat_names_every_missing_var(self) -> None:
        with pytest.raises(LLMConfigError) as e:
            require_llm_credentials(Settings(llm_provider="openai_compat"))
        msg = str(e.value)
        assert "LLM_API_KEY" in msg
        assert "LLM_BASE_URL" in msg

    def test_openai_compat_names_only_the_missing_one(self) -> None:
        with pytest.raises(LLMConfigError) as e:
            require_llm_credentials(Settings(llm_provider="openai_compat", llm_api_key="sk-x"))
        msg = str(e.value)
        assert "LLM_BASE_URL" in msg
        assert "LLM_API_KEY 与" not in msg

    def test_openai_compat_ok_when_complete(self) -> None:
        s = Settings(
            llm_provider="openai_compat",
            llm_api_key="sk-x",
            llm_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            llm_model="qwen-plus",
        )
        require_llm_credentials(s)
        assert s.llm_model == "qwen-plus"

    def test_null_provider_needs_no_credentials(self) -> None:
        # NullEnricher 是降级路径，不该因为缺 key 而无法启动
        require_llm_credentials(Settings(llm_provider="null"))


class TestDefaults:
    def test_chunk_target_is_22(self) -> None:
        assert Settings(**BASE).chunk_target_words == 22

    def test_record_timeout_is_180(self) -> None:
        assert Settings(**BASE).record_timeout_s == 180

    @pytest.mark.parametrize(
        "field,value",
        [("chunk_target_words", 3), ("record_timeout_s", 5), ("worker_poll_interval_s", 0)],
    )
    def test_out_of_range_rejected(self, field: str, value: int) -> None:
        with pytest.raises(ValidationError):
            Settings(**BASE, **{field: value})
