#!/usr/bin/env python3
"""Privacy-safe OpenAI usage telemetry for training automation logs."""

from __future__ import annotations

import json


def _integer(value) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def log_openai_usage(stage: str, response: dict, request_body: dict | None = None) -> None:
    """Log token counters only; never prompt or response content."""
    usage = response.get("usage") if isinstance(response, dict) else {}
    usage = usage if isinstance(usage, dict) else {}
    input_details = usage.get("input_tokens_details")
    input_details = input_details if isinstance(input_details, dict) else {}
    output_details = usage.get("output_tokens_details")
    output_details = output_details if isinstance(output_details, dict) else {}

    request_chars = 0
    if isinstance(request_body, dict):
        request_chars = len(json.dumps(request_body, ensure_ascii=False, separators=(",", ":")))

    model = str(response.get("model") or "") if isinstance(response, dict) else ""
    print(
        "OPENAI_USAGE "
        f"stage={stage} model={model or 'unknown'} "
        f"request_chars={request_chars} "
        f"input_tokens={_integer(usage.get('input_tokens'))} "
        f"cached_tokens={_integer(input_details.get('cached_tokens'))} "
        f"output_tokens={_integer(usage.get('output_tokens'))} "
        f"reasoning_tokens={_integer(output_details.get('reasoning_tokens'))} "
        f"total_tokens={_integer(usage.get('total_tokens'))}",
        flush=True,
    )
