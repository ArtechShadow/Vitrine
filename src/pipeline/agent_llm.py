# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""OpenAI-compatible client for the local **DiffusionGemma** agent LLM (ADR-013).

DiffusionGemma 26B-A4B (Gemma-4 MoE, ~4B active params, Q8_0) runs on the GPU
host, served as an OpenAI-compatible HTTP endpoint by the llama.cpp
``llama-diffusion-gemma-visual-server`` (PR #24423) behind a thin stdio->HTTP
wrapper (``llm-server/diffusiongemma-lan-server.py``). It is the pipeline's
reasoner/overseer tool and **replaces the never-wired gemma-4 ``agent-vlm``**
(see ``llm-server/GEMMA4-HYBRID.md`` and ``DiffusionGemma-INTEGRATION.md``).

KEY CONSTRAINTS of this build (do not treat it like a normal chat model):

* **TEXT-ONLY.** The architecture is multimodal but this GGUF build accepts
  text messages only. Image inputs raise :class:`AgentLLMError`. Visual artifact
  triage (FR-27) must therefore use the ``claude_code`` oversight backend until
  a vision-capable build is staged; DiffusionGemma reasons over text/metadata
  (captions, COLMAP stats, gate numbers), not pixels.
* **Length is set by ``n_blocks``** (256 tokens/block), not ``max_tokens``.
  Total answer <= ``n_blocks * 256``; it stops early on end-of-text.
* **Deterministic given ``seed``.** ``temperature``/``top_p`` are ignored by the
  entropy-bound diffusion sampler.
* **Single context — serialize requests.** The backend holds one model context;
  do NOT fan out concurrent calls against this endpoint.
* **12288-token context** (prompt + answer). HTTP 500 ``toolong`` => trim.

The clean answer is ``choices[0].message.content``; the model's thinking, when
present, is in ``message.reasoning_content``.

CLI:  python -m pipeline.agent_llm [health|chat "<prompt>"]
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

from pipeline import endpoints

#: Model id advertised by the server (``GET /v1/models``).
DEFAULT_AGENT_LLM_MODEL = "diffusiongemma-26B-A4B-it-Q8_0"


class AgentLLMError(RuntimeError):
    """Raised on transport failure, a non-2xx response, or an unsupported
    (image) request against the text-only endpoint."""


@dataclass
class AgentLLMResult:
    content: str
    reasoning: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    model: str = ""


def _has_image_content(messages: list[dict[str, Any]]) -> bool:
    """True if any message carries OpenAI multimodal image parts. DiffusionGemma
    is text-only, so such a request must fail fast rather than silently drop the
    image."""
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") in (
                    "image_url", "input_image", "image",
                ):
                    return True
    return False


class AgentLLM:
    """Thin OpenAI-compatible client for the DiffusionGemma endpoint.

    Build with :meth:`from_config` (the normal path — reads
    ``cfg.endpoints.agent_llm_url`` / ``agent_llm_model``) or :meth:`from_env`
    (resolves ``V2G_AGENT_LLM_URL`` via the service resolver). The ``base_url``
    is the server root (e.g. ``http://localhost:8084``); routes are appended.
    """

    def __init__(self, base_url: str, model: str = DEFAULT_AGENT_LLM_MODEL,
                 timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        # Tolerate a base that already includes the OpenAI ``/v1`` suffix.
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[: -len("/v1")]
        self.model = model
        self.timeout = timeout

    # -- constructors --------------------------------------------------------

    @classmethod
    def from_config(cls, cfg: Any, timeout: float = 120.0) -> "AgentLLM":
        ep = getattr(cfg, "endpoints", None)
        base = getattr(ep, "agent_llm_url", None) or endpoints.DEFAULT_AGENT_LLM_URL
        model = getattr(ep, "agent_llm_model", None) or DEFAULT_AGENT_LLM_MODEL
        return cls(base, model, timeout)

    @classmethod
    def from_env(cls, env: Optional[dict[str, str]] = None,
                 timeout: float = 120.0) -> "AgentLLM":
        base = endpoints.resolve("agent_llm", env=env)
        src = os.environ if env is None else env
        model = (src.get("V2G_AGENT_LLM_MODEL") or "").strip() or DEFAULT_AGENT_LLM_MODEL
        return cls(base, model, timeout)

    # -- HTTP helpers --------------------------------------------------------

    def _post_json(self, route: str, payload: dict[str, Any],
                   timeout: float) -> dict[str, Any]:
        url = f"{self.base_url}{route}"
        data = json.dumps(payload).encode("utf-8")
        try:  # prefer requests when available (consistent with the rest of src/)
            import requests  # type: ignore

            resp = requests.post(url, data=data,
                                 headers={"Content-Type": "application/json"},
                                 timeout=timeout)
            if resp.status_code >= 400:
                raise AgentLLMError(f"{url} -> HTTP {resp.status_code}: {resp.text[:300]}")
            return resp.json()
        except ImportError:
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:  # noqa: PERF203
                body = e.read().decode("utf-8", "replace")[:300]
                raise AgentLLMError(f"{url} -> HTTP {e.code}: {body}") from e
            except (urllib.error.URLError, OSError) as e:
                raise AgentLLMError(f"{url} unreachable: {e}") from e

    def _get_json(self, route: str, timeout: float) -> dict[str, Any]:
        url = f"{self.base_url}{route}"
        try:
            import requests  # type: ignore

            resp = requests.get(url, timeout=timeout)
            return resp.json() if resp.status_code < 400 else {}
        except ImportError:
            try:
                with urllib.request.urlopen(url, timeout=timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
            except (urllib.error.URLError, OSError, ValueError):
                return {}
        except Exception:
            # Any transport error (connection refused, timeout, bad JSON) means the
            # agent LLM is simply unavailable. It is advisory (oversight/recovery
            # only) and must never crash the core reconstruct->decompose flow, so
            # degrade to "no data" — health() then reports unhealthy, not an error.
            return {}

    # -- API -----------------------------------------------------------------

    def health(self, timeout: float = 10.0) -> bool:
        """True iff the backend reports ``status == ok`` (model loaded)."""
        return self._get_json("/health", timeout).get("status") == "ok"

    def chat(self, messages: list[dict[str, Any]], *, n_blocks: int = 8,
             seed: int = 0, timeout: Optional[float] = None) -> AgentLLMResult:
        """Run one completion. ``messages`` is OpenAI chat format. ``n_blocks``
        caps the answer at ``n_blocks * 256`` tokens. Raises :class:`AgentLLMError`
        on transport failure or if an image part is present (text-only build)."""
        if _has_image_content(messages):
            raise AgentLLMError(
                "DiffusionGemma is text-only; image content is not supported. "
                "Use the claude_code oversight backend for visual artifact triage.")
        payload = {"model": self.model, "messages": messages,
                   "n_blocks": int(n_blocks), "seed": int(seed)}
        body = self._post_json("/v1/chat/completions", payload,
                               timeout if timeout is not None else self.timeout)
        try:
            msg = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise AgentLLMError(f"malformed response: {str(body)[:300]}") from e
        return AgentLLMResult(
            content=msg.get("content", ""),
            reasoning=msg.get("reasoning_content", ""),
            usage=body.get("usage", {}) or {},
            model=body.get("model", self.model),
        )

    def ask(self, prompt: str, *, system: Optional[str] = None,
            n_blocks: int = 8, seed: int = 0) -> str:
        """Convenience single-turn helper returning just the answer text."""
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, n_blocks=n_blocks, seed=seed).content


def check_agent_llm(cfg: Any = None, *, timeout: float = 15.0) -> dict[str, Any]:
    """Advisory connectivity probe for the agent LLM, used by preflight.

    Resolves the endpoint (from ``cfg`` or the environment), checks ``/health``,
    and — when healthy — issues a 1-block deterministic smoke chat. Never raises;
    returns a structured result so preflight can log PASS/WARN without blocking a
    dev run on an absent LLM (the LLM is only needed for the oversight/recovery
    path, not the core reconstruct->decompose flow).
    """
    client = AgentLLM.from_config(cfg) if cfg is not None else AgentLLM.from_env()
    result: dict[str, Any] = {
        "endpoint": client.base_url, "model": client.model,
        "healthy": False, "smoke_ok": False, "error": None,
    }
    try:
        result["healthy"] = client.health(timeout=min(timeout, 10.0))
        if result["healthy"]:
            out = client.chat(
                [{"role": "user", "content": "Reply with exactly: PONG"}],
                n_blocks=1, seed=0, timeout=timeout)
            result["smoke_ok"] = "PONG" in (out.content or "").upper()
            result["sample"] = (out.content or "")[:80]
    except AgentLLMError as e:
        result["error"] = str(e)
    return result


def _main(argv: Optional[list[str]] = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "health"
    client = AgentLLM.from_env()
    if cmd == "health":
        rep = check_agent_llm()
        print(json.dumps(rep, indent=2))
        return 0 if rep["healthy"] else 1
    if cmd == "chat":
        prompt = args[1] if len(args) > 1 else "Say hello in one sentence."
        print(client.ask(prompt, n_blocks=4))
        return 0
    print(f"unknown command {cmd!r}; use: health | chat \"<prompt>\"")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
