"""LLM provider layer.

Supports two OpenAI-compatible providers — DeepSeek and Qwen (DashScope).

Select a provider with `--provider <deepseek|qwen>` (CLI) or the `PROVIDER`
environment variable (defaults to ``deepseek``). Model selection priority:

    1. `--model <id>` CLI flag
    2. per-provider env var (`DEEPSEEK_MODEL` / `QWEN_MODEL`)
    3. generic `MODEL` env var (DeepSeek only, for backward compatibility)
    4. provider default model

API keys come from ``OPENAI_API_KEY`` (DeepSeek, existing setup) and
``DASHSCOPE_API_KEY`` (Qwen).
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str
    api_key_env: str
    default_model: str
    model_env: str
    max_tokens: int = 65536
    honor_generic_model: bool = False
    extra_body: dict[str, Any] = field(default_factory=dict)
    supports_image_content: bool = False  # image switch: keep/drop image parts


PROVIDERS: dict[str, ProviderSpec] = {
    "deepseek": ProviderSpec(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="OPENAI_API_KEY",  # existing setup stores the DeepSeek key here
        default_model="deepseek-flash",
        model_env="DEEPSEEK_MODEL",
        max_tokens=65536,
        honor_generic_model=True,  # keep reading MODEL env (backward compat)
        extra_body={"reasoning_effort": "low", "temperature": 0.7},
        supports_image_content=True,  # DeepSeek-flash supports image content and v4-pro is text-only
    ),
    "qwen": ProviderSpec(
        name="qwen",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        default_model="qwen3.8-flash",
        model_env="QWEN_MODEL",
        max_tokens=8192,  # safe default for qwen-plus/max; raise if using qwen3
        honor_generic_model=False,  # MODEL currently holds a DeepSeek name
        extra_body={},
        supports_image_content=True,  # Qwen has vision models
    ),
}


class Provider:
    """A resolved provider: endpoint + credentials + model + provider-specific body."""

    def __init__(self, name: str, model: str | None = None, api_key: str | None = None):
        key = (name or "").strip().lower()
        if key not in PROVIDERS:
            raise ValueError(f"Unknown provider {name!r}; choose from {sorted(PROVIDERS)}")
        spec = PROVIDERS[key]
        self.name = spec.name
        self.spec = spec

        base_override = os.environ.get(f"{spec.name.upper()}_BASE_URL", "")
        if not base_override and spec.name == "deepseek":
            base_override = os.environ.get("OPENAI_BASE_URL", "")  # backward compat
        self.base_url = (base_override or spec.base_url).rstrip("/")

        self.api_key = api_key or os.environ.get(spec.api_key_env, "")
        if not self.api_key:
            raise ValueError(
                f"Missing API key for provider {self.name!r}; set {spec.api_key_env}"
            )

        env_model = os.environ.get(spec.model_env, "")
        if not env_model and spec.honor_generic_model:
            env_model = os.environ.get("MODEL", "")
        self.model = model or env_model or spec.default_model
        self.max_tokens = spec.max_tokens

    def send(self, history, tools=None) -> dict:
        """Post `history` to the provider and return the parsed response JSON."""
        return _post(self, history, tools)

    def __repr__(self) -> str:
        return f"Provider({self.name!r}, model={self.model!r}, base_url={self.base_url!r})"


def get_provider(
    name: str, *, model: str | None = None, api_key: str | None = None
) -> Provider:
    return Provider(name, model=model, api_key=api_key)


def image_path_to_data_url(image_path: str) -> str:
    """Encode an image file on disk as a ``data:...;base64,...`` URL."""
    path = Path(image_path).expanduser().resolve()
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        mime_type = "application/octet-stream"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{data}"


def _image_url_from_part(part: dict[str, Any]) -> str | None:
    """Extract a data/URL from an ``input_image`` or ``image_url`` content part."""
    image_url = part.get("image_url")
    if isinstance(image_url, dict):
        url = image_url.get("url")
        if isinstance(url, str) and url:
            return url
    elif isinstance(image_url, str) and image_url:
        return image_url

    url = part.get("url")
    if isinstance(url, str) and url:
        return url

    image_path = part.get("image_path")
    if isinstance(image_path, str) and image_path:
        return image_path_to_data_url(image_path)

    return None


def _normalize_content(content: Any, *, supports_images: bool) -> Any:
    """Normalize message content, encoding image paths and honoring the image switch.

    String content passes through unchanged. List content (text/image parts) is
    rebuilt in OpenAI format; image parts are dropped when ``supports_images``
    is False.
    """
    if not isinstance(content, list):
        return content

    parts: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if ptype in ("text", "input_text"):
            text = part.get("text")
            if isinstance(text, str) and text:
                parts.append({"type": "text", "text": text})
        elif ptype in ("image_url", "input_image"):
            if not supports_images:
                continue  # switch off -> drop image parts
            url = _image_url_from_part(part)
            if url is None:
                continue
            image_url: dict[str, Any] = {"url": url}
            detail = part.get("detail")
            if isinstance(detail, str) and detail:
                image_url["detail"] = detail
            parts.append({"type": "image_url", "image_url": image_url})
        else:
            parts.append(part)  # unknown part type: pass through unchanged
    return parts


def _post(provider: Provider, history, tools) -> dict:
    messages = []
    for m in history:
        if m.get("role") == "assistant":
            if m.get("content") is None and not m.get("tool_calls"):
                continue
        content = m.get("content")
        if isinstance(content, list):
            m = {
                **m,
                "content": _normalize_content(
                    content, supports_images=provider.spec.supports_image_content
                ),
            }
        messages.append(m)

    payload: dict[str, Any] = {
        "model": provider.model,
        "max_tokens": provider.max_tokens,
        "messages": messages,
    }
    payload.update(provider.spec.extra_body)
    if tools:
        payload["tools"] = tools

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        provider.base_url + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + provider.api_key,
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')}") from None
    except OSError as e:
        raise RuntimeError(f"Request failed: {e}") from None

    try:
        r = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Parse failed: {e}\nRaw response: {raw.decode(errors='replace')}") from None
    if r.get("error"):
        raise RuntimeError(f"API Error [{r['error'].get('type')}]: {r['error'].get('message')}")
    if not r.get("choices"):
        raise RuntimeError(f"Empty response: {raw.decode(errors='replace')}")
    return r
