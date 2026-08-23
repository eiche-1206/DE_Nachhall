"""Claude 实现。用 tool-use 强制结构化输出。

prompt 与 schema **一律从 contract.py 取**，本文件不许自己写一份 ——
否则换供应商时输出契约会悄悄漂移，而漂移只在数据入库后才被发现。
"""

from __future__ import annotations

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

# 一期约 120 句，输出含逐句翻译，需要较大预算
_MAX_TOKENS = 16000


class ClaudeEnricher:
    name = "claude"

    def __init__(self, api_key: str, model: str = "claude-sonnet-5", client: Any = None) -> None:
        self.model = model
        self._client = client
        self._api_key = api_key

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def enrich(self, sentences: Sequence[SentenceIn]) -> EnrichResult:
        if not sentences:
            return EnrichResult(chapters=[], translations={})

        try:
            resp = self._get_client().messages.create(
                model=self.model,
                max_tokens=_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=[
                    {
                        "name": TOOL_NAME,
                        "description": "输出分章结果与逐句中文翻译",
                        "input_schema": OUTPUT_SCHEMA,
                    }
                ],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                messages=[{"role": "user", "content": build_user_message(sentences)}],
            )
        except Exception as e:  # noqa: BLE001 —— SDK 异常类型多，一律转成 EnrichError
            raise EnrichError(f"Claude 调用失败：{e}") from e

        payload = _extract_tool_input(resp)
        if payload is None:
            raise EnrichError("Claude 未按要求调用工具，无结构化输出。")

        try:
            result = parse_and_validate(payload, sentences)
        except (ContractViolation, KeyError, TypeError, ValueError) as e:
            raise EnrichError(f"Claude 输出不满足契约：{e}") from e

        log.info(
            "claude enriched: %d chapters, %d translations",
            len(result.chapters),
            len(result.translations),
        )
        return result


def _extract_tool_input(resp: Any) -> dict[str, Any] | None:
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", "") == TOOL_NAME:
            data = getattr(block, "input", None)
            if isinstance(data, dict):
                return data
    return None


_: EnrichProvider = ClaudeEnricher(api_key="")
