"""OpenAI 兼容端点。**一个实现覆盖四家**。

GPT、千问（DashScope 兼容模式）、DeepSeek、Ollama 都提供 OpenAI 兼容的
/chat/completions，差别只在 base_url 与 model：

    GPT       LLM_BASE_URL=https://api.openai.com/v1              LLM_MODEL=gpt-4.1
    千问      LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
                                                                  LLM_MODEL=qwen-plus
    DeepSeek  LLM_BASE_URL=https://api.deepseek.com/v1            LLM_MODEL=deepseek-chat
    Ollama    LLM_BASE_URL=http://host.docker.internal:11434/v1   LLM_MODEL=qwen2.5:14b

所以真正需要单独实现的只有 Claude（Messages API 形态不同）。

prompt 与 schema 从 contract.py 取，与 ClaudeEnricher **共用同一份**。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from de_nachhall.providers.enrich.base import (
    EnrichError,
    EnrichProvider,
    EnrichResult,
    SentenceIn,
)
from de_nachhall.providers.enrich.contract import (
    OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
    TOOL_NAME,
    ContractViolation,
    build_user_message,
    parse_and_validate,
)

log = logging.getLogger(__name__)

_MAX_TOKENS = 16000


class OpenAICompatEnricher:
    name = "openai_compat"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        client: Any = None,
        use_json_schema: bool = True,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url
        self._client = client
        # 部分兼容端点不支持 json_schema，只支持 json_object。
        # 契约校验在 parse_and_validate 里，所以退化到 json_object 仍然安全。
        self.use_json_schema = use_json_schema

    def _get_client(self) -> Any:
        if self._client is None:
            import openai

            self._client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def _response_format(self) -> dict[str, Any]:
        if self.use_json_schema:
            return {
                "type": "json_schema",
                "json_schema": {"name": TOOL_NAME, "strict": True, "schema": OUTPUT_SCHEMA},
            }
        return {"type": "json_object"}

    def enrich(self, sentences: Sequence[SentenceIn]) -> EnrichResult:
        if not sentences:
            return EnrichResult(chapters=[], translations={})

        try:
            resp = self._get_client().chat.completions.create(
                model=self.model,
                max_tokens=_MAX_TOKENS,
                response_format=self._response_format(),
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_message(sentences)},
                ],
            )
        except Exception as e:  # noqa: BLE001
            raise EnrichError(f"{self.model} 调用失败：{e}") from e

        content = _extract_content(resp)
        if not content:
            raise EnrichError(f"{self.model} 返回空内容。")

        try:
            result = parse_and_validate(json.loads(content), sentences)
        except json.JSONDecodeError as e:
            raise EnrichError(f"{self.model} 输出不是合法 JSON：{e}") from e
        except (ContractViolation, KeyError, TypeError, ValueError) as e:
            raise EnrichError(f"{self.model} 输出不满足契约：{e}") from e

        log.info(
            "%s enriched: %d chapters, %d translations",
            self.model, len(result.chapters), len(result.translations),
        )
        return result


def _extract_content(resp: Any) -> str | None:
    choices = getattr(resp, "choices", None) or []
    if not choices:
        return None
    msg = getattr(choices[0], "message", None)
    text = getattr(msg, "content", None)
    return text if isinstance(text, str) and text.strip() else None


_: EnrichProvider = OpenAICompatEnricher(api_key="", base_url="", model="")
