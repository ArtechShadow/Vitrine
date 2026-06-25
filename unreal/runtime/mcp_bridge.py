#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LichtFeld Studio Authors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Vitrine -> Unreal Engine 5.8 MCP bridge (ADR-016).

A dependency-light HTTP service that lets the Vitrine agent and pipeline drive
the Unreal Engine 5.8 container.  It bridges two distinct UE control surfaces
and exposes a unified JSON API on a single port so pipeline code and the agent
never need to know which UE transport to use.

Two UE control surfaces (ADR-016 D-2, D-3)
-------------------------------------------
Web Remote Control  (``UE_REMOTE_CONTROL_URL``, default ``http://unreal:30010``)
    Unicast HTTP REST; works natively over Docker bridge networks. This is the
    *primary* and most reliable surface.  Shapes used here:

    ``GET  /remote/info``                     liveness / info
    ``PUT  /remote/object/call``              call a function on a UE object
    ``PUT  /remote/object/property``          read / set actor properties
    ``PUT  /remote/preset``                   apply a named preset

First-party UE MCP plugin (``UE_MCP_URL``, default ``http://unreal:8000/mcp``)
    HTTP+SSE JSON-RPC MCP endpoint (experimental, UE 5.8+). Used for tool
    introspection and actor/lighting/automation tools when available.  The
    bridge falls back to Web Remote Control if the MCP endpoint is not up.

AVOID the multicast Python-remote-exec endpoint on port 6766: it uses UDP
multicast which is not forwarded over standard Docker bridge networks (ADR-016).

Environment variables
---------------------
UE_REMOTE_CONTROL_URL   Web Remote Control base URL (default http://unreal:30010)
UE_MCP_URL              First-party MCP base URL (default http://unreal:8000/mcp)
BRIDGE_PORT             Port this bridge listens on (default 9100)
VITRINE_USD             Path (inside UE container) to the USD scene file
                        (default /usd_input/scene.usda)
UE_REQUEST_TIMEOUT      Per-request timeout in seconds (default 30)

Usage
-----
Run this bridge inside any container that can reach the Unreal container over
v2g-net or visionclaw_network::

    python3 scripts/unreal/mcp_bridge.py

Then call it from the pipeline or agent::

    GET  http://unreal-bridge:9100/health
    POST http://unreal-bridge:9100/import_usd     {"usd_path": "/usd_input/scene.usda"}
    POST http://unreal-bridge:9100/assemble
    POST http://unreal-bridge:9100/render         {"output_path": "/renders/frame.png", ...}
    GET  http://unreal-bridge:9100/scene_info
    PUT  http://unreal-bridge:9100/remote/object/call   <raw RC payload>
"""

from __future__ import annotations

import http.server
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Optional requests import (preferred transport when available)
# ---------------------------------------------------------------------------

try:
    import requests as _requests  # type: ignore
    _HAS_REQUESTS = True
except ImportError:  # pragma: no cover - stdlib fallback exercised in tests
    _requests = None  # type: ignore
    _HAS_REQUESTS = False


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("unreal.mcp_bridge")


# ---------------------------------------------------------------------------
# Environment-driven configuration
# ---------------------------------------------------------------------------

_DEFAULT_RC_URL = "http://unreal:30010"
_DEFAULT_MCP_URL = "http://unreal:8000/mcp"
_DEFAULT_PORT = 9100
_DEFAULT_USD = "/usd_input/scene.usda"
_DEFAULT_TIMEOUT = 5.0

# Retry / backoff parameters for UE startup wait.
_HEALTH_RETRY_COUNT = 3
_HEALTH_RETRY_BASE_S = 1.0  # exponential base
_HEALTH_RETRY_MAX_S = 4.0

# Web Remote Control route table (unicast HTTP, container-safe).
_RC_ROUTE_INFO = "/remote/info"
_RC_ROUTE_CALL = "/remote/object/call"
_RC_ROUTE_PROPERTY = "/remote/object/property"
_RC_ROUTE_PRESET = "/remote/preset"

# Bridge HTTP API routes.
_BRIDGE_ROUTE_HEALTH = "/health"
_BRIDGE_ROUTE_IMPORT_USD = "/import_usd"
_BRIDGE_ROUTE_ASSEMBLE = "/assemble"
_BRIDGE_ROUTE_RENDER = "/render"
_BRIDGE_ROUTE_SCENE_INFO = "/scene_info"
_BRIDGE_ROUTE_RC_PASSTHROUGH = "/remote/object/call"


# ---------------------------------------------------------------------------
# Typed configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class BridgeConfig:
    """Runtime configuration for the UE MCP bridge.

    Attributes:
        rc_url: Web Remote Control base URL (UE_REMOTE_CONTROL_URL env var).
        mcp_url: First-party MCP base URL (UE_MCP_URL env var).
        bridge_port: Port this bridge HTTP server listens on (BRIDGE_PORT).
        vitrine_usd: Default USD scene path inside the UE container
            (VITRINE_USD).  Passed to UsdStageActor commands when the caller
            does not supply an explicit ``usd_path``.
        request_timeout: Per-request HTTP timeout in seconds
            (UE_REQUEST_TIMEOUT).
    """

    rc_url: str = field(
        default_factory=lambda: os.environ.get("UE_REMOTE_CONTROL_URL", _DEFAULT_RC_URL)
    )
    mcp_url: str = field(
        default_factory=lambda: os.environ.get("UE_MCP_URL", _DEFAULT_MCP_URL)
    )
    bridge_port: int = field(
        default_factory=lambda: int(os.environ.get("BRIDGE_PORT", str(_DEFAULT_PORT)))
    )
    vitrine_usd: str = field(
        default_factory=lambda: os.environ.get("VITRINE_USD", _DEFAULT_USD)
    )
    request_timeout: float = field(
        default_factory=lambda: float(os.environ.get("UE_REQUEST_TIMEOUT", str(_DEFAULT_TIMEOUT)))
    )


# ---------------------------------------------------------------------------
# UE transport error
# ---------------------------------------------------------------------------


class UnrealBridgeError(RuntimeError):
    """Raised on any HTTP or transport failure toward the Unreal container."""


# ---------------------------------------------------------------------------
# Low-level HTTP transport (requests preferred, urllib fallback)
# ---------------------------------------------------------------------------


class _Transport:
    """Thin HTTP transport; uses ``requests`` if importable, urllib otherwise."""

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        if _HAS_REQUESTS:
            self._session: Optional[Any] = _requests.Session()
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            adapter = HTTPAdapter(max_retries=Retry(total=0))
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)
        else:
            self._session = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get(self, url: str, *, timeout: Optional[float] = None) -> Any:
        return self._request("GET", url, body=None, timeout=timeout)

    def post(self, url: str, body: dict, *, timeout: Optional[float] = None) -> Any:
        return self._request("POST", url, body=body, timeout=timeout)

    def put(self, url: str, body: dict, *, timeout: Optional[float] = None) -> Any:
        return self._request("PUT", url, body=body, timeout=timeout)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        url: str,
        body: Optional[dict],
        timeout: Optional[float],
    ) -> Any:
        t = self.timeout if timeout is None else timeout
        if self._session is not None:
            return self._req_requests(method, url, body, t)
        return self._req_urllib(method, url, body, t)

    def _req_requests(
        self,
        method: str,
        url: str,
        body: Optional[dict],
        timeout: float,
    ) -> Any:
        try:
            resp = self._session.request(method, url, json=body, timeout=timeout)
        except _requests.exceptions.RequestException as exc:
            raise UnrealBridgeError(f"Transport error {method} {url}: {exc}") from exc
        if resp.status_code >= 400:
            raise UnrealBridgeError(
                f"HTTP {resp.status_code} {method} {url}: {resp.text[:500]}"
            )
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError as exc:
            raise UnrealBridgeError(
                f"Non-JSON response {method} {url}: {resp.text[:200]}"
            ) from exc

    def _req_urllib(
        self,
        method: str,
        url: str,
        body: Optional[dict],
        timeout: float,
    ) -> Any:
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        headers: dict[str, str] = {}
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        req = Request(url, data=encoded, method=method, headers=headers)
        try:
            with urlopen(req, timeout=timeout) as resp:
                payload = resp.read()
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise UnrealBridgeError(
                f"HTTP {exc.code} {method} {url}: {detail}"
            ) from exc
        except (URLError, OSError) as exc:
            raise UnrealBridgeError(f"Transport error {method} {url}: {exc}") from exc

        if not payload:
            return {}
        try:
            return json.loads(payload)
        except (ValueError, json.JSONDecodeError) as exc:
            raise UnrealBridgeError(
                f"Non-JSON response {method} {url}: {payload[:200]!r}"
            ) from exc


# ---------------------------------------------------------------------------
# Unreal Remote Control client
# ---------------------------------------------------------------------------


class UnrealRemoteControl:
    """Thin client for the UE 5.8 Web Remote Control REST API (:30010).

    All calls target the unicast HTTP REST surface which forwards correctly
    over Docker bridge/overlay networks (unlike the multicast UDP :6766 Python
    remote-exec socket).

    Parameters
    ----------
    rc_url:
        Base URL of the Web Remote Control server
        (e.g. ``http://unreal:30010``).
    transport:
        ``_Transport`` instance shared with the MCP surface.
    """

    def __init__(self, rc_url: str, transport: _Transport) -> None:
        self._base = rc_url.rstrip("/")
        self._t = transport

    # ------------------------------------------------------------------
    # Liveness
    # ------------------------------------------------------------------

    def ping(self) -> dict:
        """GET /remote/info — returns editor state if UE is up."""
        return self._t.get(self._base + _RC_ROUTE_INFO)

    def is_alive(self) -> bool:
        """Return True if the Web Remote Control endpoint responds."""
        try:
            self.ping()
            return True
        except UnrealBridgeError as exc:
            logger.debug("RC ping failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Core REST shapes
    # ------------------------------------------------------------------

    def call(self, object_path: str, function_name: str, parameters: Optional[dict] = None) -> dict:
        """PUT /remote/object/call — invoke a function on a UE actor/object.

        Parameters
        ----------
        object_path:
            Full UE object path, e.g.
            ``/Game/Maps/Vitrine_Main.Vitrine_Main:PersistentLevel.UsdStageActor_0``.
        function_name:
            The Blueprint/UFUNCTION name to call.
        parameters:
            Dict of parameter name -> value forwarded as ``Parameters`` in the
            Web Remote Control JSON body.

        Returns
        -------
        dict
            Response body from the Remote Control API.
        """
        body: dict[str, Any] = {
            "ObjectPath": object_path,
            "FunctionName": function_name,
        }
        if parameters:
            body["Parameters"] = parameters
        logger.debug("RC call: %s::%s %s", object_path, function_name, parameters)
        return self._t.put(self._base + _RC_ROUTE_CALL, body)

    def set_property(self, object_path: str, property_name: str, property_value: Any) -> dict:
        """PUT /remote/object/property — write a property on a UE object."""
        body: dict[str, Any] = {
            "ObjectPath": object_path,
            "PropertyName": property_name,
            "PropertyValue": property_value,
            "Access": "WRITE_ACCESS",
        }
        return self._t.put(self._base + _RC_ROUTE_PROPERTY, body)

    def get_property(self, object_path: str, property_name: str) -> dict:
        """PUT /remote/object/property with READ_ACCESS — read a property."""
        body: dict[str, Any] = {
            "ObjectPath": object_path,
            "PropertyName": property_name,
            "Access": "READ_ACCESS",
        }
        return self._t.put(self._base + _RC_ROUTE_PROPERTY, body)

    def apply_preset(self, preset_name: str, preset_data: Optional[dict] = None) -> dict:
        """PUT /remote/preset — apply a named Remote Control preset."""
        body: dict[str, Any] = {"PresetName": preset_name}
        if preset_data:
            body.update(preset_data)
        return self._t.put(self._base + _RC_ROUTE_PRESET, body)

    def raw_call(self, payload: dict) -> dict:
        """Low-level PUT /remote/object/call with a fully-formed payload dict.

        Useful as a passthrough for callers that build the RC body themselves.
        """
        return self._t.put(self._base + _RC_ROUTE_CALL, payload)


# ---------------------------------------------------------------------------
# Unreal MCP client (first-party plugin, port 8000, experimental)
# ---------------------------------------------------------------------------


class UnrealMCPClient:
    """Thin JSON-RPC client for the UE 5.8 first-party MCP plugin (:8000/mcp).

    This surface is experimental in UE 5.8 and may be unavailable or have a
    different tool catalogue depending on the build.  The bridge treats it as
    optional: all pipeline operations have a Web Remote Control (:30010)
    equivalent as the stable fallback.

    Parameters
    ----------
    mcp_url:
        Full MCP endpoint URL, e.g. ``http://unreal:8000/mcp``.
    transport:
        ``_Transport`` instance.
    """

    def __init__(self, mcp_url: str, transport: _Transport) -> None:
        self._url = mcp_url
        self._t = transport
        self._next_id = 1

    def _rpc(self, method: str, params: Optional[dict] = None) -> Any:
        body: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
        }
        if params is not None:
            body["params"] = params
        self._next_id += 1
        resp = self._t.post(self._url, body)
        if isinstance(resp, dict) and "error" in resp:
            err = resp["error"]
            raise UnrealBridgeError(f"MCP error on {method}: {err}")
        return resp.get("result") if isinstance(resp, dict) else resp

    def ping(self) -> Any:
        return self._rpc("ping")

    def is_alive(self) -> bool:
        try:
            self.ping()
            return True
        except UnrealBridgeError as exc:
            logger.debug("MCP ping failed: %s", exc)
            return False

    def list_tools(self) -> list:
        """Retrieve the tool catalogue from the first-party MCP plugin."""
        result = self._rpc("tools/list")
        return result.get("tools", []) if isinstance(result, dict) else []

    def call_tool(self, tool_name: str, arguments: Optional[dict] = None) -> Any:
        """Invoke a named MCP tool."""
        params: dict[str, Any] = {"name": tool_name}
        if arguments:
            params["arguments"] = arguments
        return self._rpc("tools/call", params)


# ---------------------------------------------------------------------------
# High-level bridge operations
# ---------------------------------------------------------------------------


@dataclass
class BridgeResult:
    """Result of a bridge operation.

    Attributes:
        ok: Whether the operation succeeded.
        data: Payload returned by UE (dict) or an empty dict on failure.
        error: Human-readable error message when ``ok`` is False.
        duration_s: Wall-clock seconds consumed by the operation.
    """

    ok: bool
    data: dict
    error: Optional[str] = None
    duration_s: float = 0.0

    def as_dict(self) -> dict:
        d: dict[str, Any] = {"ok": self.ok, "data": self.data, "duration_s": self.duration_s}
        if self.error is not None:
            d["error"] = self.error
        return d


class UnrealBridge:
    """Unified control surface for the UE 5.8 container.

    Combines Web Remote Control (:30010) as the primary, reliable transport
    with the first-party MCP plugin (:8000) as a secondary/introspection
    surface.  All high-level pipeline operations (import_usd, assemble,
    render, scene_info) talk through Web Remote Control; the MCP surface is
    available for tool introspection and richer editor automation when present.

    Parameters
    ----------
    config:
        ``BridgeConfig`` instance (reads env vars on construction).
    """

    def __init__(self, config: Optional[BridgeConfig] = None) -> None:
        self.cfg = config or BridgeConfig()
        self._transport = _Transport(timeout=self.cfg.request_timeout)
        self.rc = UnrealRemoteControl(self.cfg.rc_url, self._transport)
        self.mcp = UnrealMCPClient(self.cfg.mcp_url, self._transport)
        logger.info(
            "UnrealBridge init: RC=%s  MCP=%s  port=%d  usd=%s",
            self.cfg.rc_url, self.cfg.mcp_url, self.cfg.bridge_port, self.cfg.vitrine_usd,
        )

    # ------------------------------------------------------------------
    # Liveness / health
    # ------------------------------------------------------------------

    def health(self, *, retries: int = _HEALTH_RETRY_COUNT) -> BridgeResult:
        """Probe UE Web Remote Control with exponential backoff.

        This is the canonical liveness check for the pipeline: UE can take
        30–90 s to fully start even after the container is up.

        Parameters
        ----------
        retries:
            Total number of attempts before declaring UE unreachable.

        Returns
        -------
        BridgeResult
            ``ok=True`` and ``data`` carrying the /remote/info payload when
            reachable; ``ok=False`` with ``error`` otherwise.
        """
        t0 = time.monotonic()
        delay = _HEALTH_RETRY_BASE_S
        last_exc: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                info = self.rc.ping()
                rc_alive = True
            except UnrealBridgeError as exc:
                info = {}
                rc_alive = False
                last_exc = exc

            mcp_alive = self.mcp.is_alive()
            elapsed = time.monotonic() - t0

            if rc_alive:
                logger.info(
                    "UE health OK (attempt %d/%d, %.1fs): RC=up MCP=%s",
                    attempt, retries, elapsed, "up" if mcp_alive else "down",
                )
                return BridgeResult(
                    ok=True,
                    data={"rc_info": info, "mcp_alive": mcp_alive},
                    duration_s=elapsed,
                )

            logger.warning(
                "UE health attempt %d/%d failed (%.1fs): %s; retrying in %.0fs",
                attempt, retries, elapsed, last_exc, delay,
            )
            if attempt < retries:
                time.sleep(delay)
                delay = min(delay * 2, _HEALTH_RETRY_MAX_S)

        elapsed = time.monotonic() - t0
        err = f"UE not reachable after {retries} attempts: {last_exc}"
        logger.error(err)
        return BridgeResult(ok=False, data={}, error=err, duration_s=elapsed)

    # ------------------------------------------------------------------
    # USD import (highest-fidelity live Stage Actor path — ADR-016 D-3)
    # ------------------------------------------------------------------

    def import_usd(self, usd_path: Optional[str] = None) -> BridgeResult:
        """Spawn a UsdStageActor pointing at ``usd_path`` (live reference).

        This is the highest-fidelity import path: the prim hierarchy + `v2g:*`
        customData are preserved because the USD is loaded as a *live reference*
        (not baked into .uasset), and ``import_usd_stage.py`` has already
        mirrored the `v2g:*` metadata onto Actor tags for Blueprint/MCP access.

        Under the hood this drives the headless commandlet via Web Remote
        Control's object-call surface to invoke the EditorLevelLibrary API.
        The commandlet itself (``scripts/unreal/import_usd_stage.py``) must
        already have been run inside the UE container (e.g. via the
        ``assemble`` operation) to have a live Stage Actor in the level.  This
        operation is idempotent: it sets the ``root_layer`` property on any
        existing Stage Actor.

        Parameters
        ----------
        usd_path:
            Path to the ``.usda`` file as seen from *inside* the UE container.
            Defaults to ``VITRINE_USD`` env var / ``/usd_input/scene.usda``.

        Returns
        -------
        BridgeResult
            ``ok=True`` on success with the RC response in ``data``.
        """
        usd = usd_path or self.cfg.vitrine_usd
        t0 = time.monotonic()
        logger.info("import_usd: loading Stage Actor from %s", usd)
        try:
            resp = self.rc.call(
                object_path="/Script/USDStageImporter.Default__UsdStageActor",
                function_name="SetRootLayer",
                parameters={"NewRootLayer": usd},
            )
            elapsed = time.monotonic() - t0
            logger.info("import_usd OK (%.1fs): %s", elapsed, resp)
            return BridgeResult(ok=True, data=resp, duration_s=elapsed)
        except UnrealBridgeError as exc:
            elapsed = time.monotonic() - t0
            err = f"import_usd failed for {usd}: {exc}"
            logger.error(err)
            return BridgeResult(ok=False, data={}, error=err, duration_s=elapsed)

    # ------------------------------------------------------------------
    # Scene assembly (run the import_usd_stage.py commandlet)
    # ------------------------------------------------------------------

    def assemble(self, usd_path: Optional[str] = None) -> BridgeResult:
        """Trigger the headless USD-import commandlet via Web Remote Control.

        Invokes the ``ExecutePythonScript`` function on the Python editor
        subsystem — this is equivalent to running::

            UnrealEditor-Cmd <proj> -run=pythonscript -script=import_usd_stage.py

        but driven over the HTTP RC surface so it works in the running editor
        or a ``-nullrhi`` commandlet container (no GPU needed for assembly).

        The commandlet ``scripts/unreal/import_usd_stage.py`` must be present
        inside the UE container at the path expected by UE's Python plugin
        (typically ``/usd_input/import_usd_stage.py`` or mapped via a project
        plugin folder).

        Parameters
        ----------
        usd_path:
            Override ``VITRINE_USD`` env var for this assembly run.
        """
        usd = usd_path or self.cfg.vitrine_usd
        t0 = time.monotonic()
        script_body = (
            f"import os; os.environ['VITRINE_USD'] = '{usd}'; "
            "exec(open('/usd_input/import_usd_stage.py').read())"
        )
        logger.info("assemble: running import commandlet for %s", usd)
        try:
            resp = self.rc.call(
                object_path="/Script/PythonScriptPlugin.Default__PythonScriptLibrary",
                function_name="ExecutePythonScript",
                parameters={"PythonScript": script_body},
            )
            elapsed = time.monotonic() - t0
            logger.info("assemble OK (%.1fs)", elapsed)
            return BridgeResult(ok=True, data=resp, duration_s=elapsed)
        except UnrealBridgeError as exc:
            elapsed = time.monotonic() - t0
            err = f"assemble failed: {exc}"
            logger.error(err)
            return BridgeResult(ok=False, data={}, error=err, duration_s=elapsed)

    # ------------------------------------------------------------------
    # Offscreen render (MovieRenderQueue, Lumen, -RenderOffscreen)
    # ------------------------------------------------------------------

    def render(
        self,
        output_path: Optional[str] = None,
        width: int = 1920,
        height: int = 1080,
        preset: Optional[str] = None,
    ) -> BridgeResult:
        """Trigger an offscreen MovieRenderQueue render via Web Remote Control.

        The UE container must have been started with ``-RenderOffscreen`` and a
        Lumen/Vulkan GPU path (see ADR-016: Path Tracer unavailable on Linux).
        For non-render assembly (import + save) use ``assemble`` with
        ``-nullrhi`` instead.

        Parameters
        ----------
        output_path:
            Destination path *inside the UE container* for the rendered output
            (e.g. ``/renders/frame.png``).  Defaults to
            ``/renders/vitrine_frame.png``.
        width:
            Render width in pixels (default 1920).
        height:
            Render height in pixels (default 1080).
        preset:
            Optional Remote Control preset name to apply before rendering.
        """
        out = output_path or "/renders/vitrine_frame.png"
        t0 = time.monotonic()
        logger.info("render: output=%s %dx%d preset=%s", out, width, height, preset)

        if preset:
            try:
                self.rc.apply_preset(preset)
            except UnrealBridgeError as exc:
                logger.warning("render: preset %s failed (continuing): %s", preset, exc)

        try:
            resp = self.rc.call(
                object_path="/Script/MovieRenderPipelineEditor.Default__MoviePipelineEditorBlueprintLibrary",
                function_name="RenderQueueWithExecutorInstance",
                parameters={
                    "OutputPath": out,
                    "ResolutionX": width,
                    "ResolutionY": height,
                },
            )
            elapsed = time.monotonic() - t0
            logger.info("render queued OK (%.1fs): %s", elapsed, resp)
            return BridgeResult(ok=True, data=resp, duration_s=elapsed)
        except UnrealBridgeError as exc:
            elapsed = time.monotonic() - t0
            err = f"render failed: {exc}"
            logger.error(err)
            return BridgeResult(ok=False, data={}, error=err, duration_s=elapsed)

    # ------------------------------------------------------------------
    # Scene introspection
    # ------------------------------------------------------------------

    def scene_info(self) -> BridgeResult:
        """Return a snapshot of the current UE level / actor state.

        Queries Web Remote Control /remote/info and (if the MCP plugin is up)
        the first-party MCP tool catalogue, so the caller gets a combined view
        of both control surfaces in one call.

        Returns
        -------
        BridgeResult
            ``data`` carries ``rc_info`` (raw /remote/info dict) and
            ``mcp_tools`` (list of tool names from the first-party MCP, or
            empty when MCP is not available).
        """
        t0 = time.monotonic()
        rc_info: dict = {}
        mcp_tools: list = []

        try:
            rc_info = self.rc.ping()
        except UnrealBridgeError as exc:
            logger.warning("scene_info: RC ping failed: %s", exc)

        if self.mcp.is_alive():
            try:
                mcp_tools = self.mcp.list_tools()
            except UnrealBridgeError as exc:
                logger.warning("scene_info: MCP list_tools failed: %s", exc)

        elapsed = time.monotonic() - t0
        data = {"rc_info": rc_info, "mcp_tools": mcp_tools}
        ok = bool(rc_info)
        err = None if ok else "UE Web Remote Control did not respond"
        return BridgeResult(ok=ok, data=data, error=err, duration_s=elapsed)

    # ------------------------------------------------------------------
    # Generic RC passthrough
    # ------------------------------------------------------------------

    def remote_object_call(self, payload: dict) -> BridgeResult:
        """Pass a fully-formed Web Remote Control body to PUT /remote/object/call.

        Use this when the pipeline or agent needs to call an arbitrary UE
        function not covered by the higher-level operations above.

        Parameters
        ----------
        payload:
            Dict with at least ``ObjectPath`` and ``FunctionName``.  Optional
            ``Parameters`` dict forwarded verbatim.
        """
        t0 = time.monotonic()
        try:
            resp = self.rc.raw_call(payload)
            elapsed = time.monotonic() - t0
            return BridgeResult(ok=True, data=resp, duration_s=elapsed)
        except UnrealBridgeError as exc:
            elapsed = time.monotonic() - t0
            err = f"remote_object_call failed: {exc}"
            logger.error(err)
            return BridgeResult(ok=False, data={}, error=err, duration_s=elapsed)


# ---------------------------------------------------------------------------
# HTTP server (thin JSON bridge)
# ---------------------------------------------------------------------------


def _read_body(request: http.server.BaseHTTPRequestHandler) -> dict:
    """Read and parse a JSON request body; return empty dict on missing body."""
    length = int(request.headers.get("Content-Length", 0))
    if not length:
        return {}
    raw = request.rfile.read(length)
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, json.JSONDecodeError):
        return {}


def _make_handler(bridge: UnrealBridge) -> type:
    """Build a BaseHTTPRequestHandler class closed over ``bridge``."""

    class Handler(http.server.BaseHTTPRequestHandler):
        """Minimal JSON HTTP handler for the Vitrine->UE bridge."""

        # Suppress the default per-request log line; we use logger.
        def log_message(self, fmt: str, *args: Any) -> None:  # type: ignore[override]
            logger.debug("HTTP %s", fmt % args)

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _bad_method(self) -> None:
            self._send_json(405, {"error": "method not allowed"})

        def do_GET(self) -> None:
            if self.path == _BRIDGE_ROUTE_HEALTH:
                result = bridge.health()
                self._send_json(200 if result.ok else 503, result.as_dict())
            elif self.path == _BRIDGE_ROUTE_SCENE_INFO:
                result = bridge.scene_info()
                self._send_json(200 if result.ok else 503, result.as_dict())
            else:
                self._send_json(404, {"error": f"unknown route: {self.path}"})

        def do_POST(self) -> None:
            body = _read_body(self)
            if self.path == _BRIDGE_ROUTE_IMPORT_USD:
                result = bridge.import_usd(usd_path=body.get("usd_path"))
            elif self.path == _BRIDGE_ROUTE_ASSEMBLE:
                result = bridge.assemble(usd_path=body.get("usd_path"))
            elif self.path == _BRIDGE_ROUTE_RENDER:
                result = bridge.render(
                    output_path=body.get("output_path"),
                    width=int(body.get("width", 1920)),
                    height=int(body.get("height", 1080)),
                    preset=body.get("preset"),
                )
            else:
                self._send_json(404, {"error": f"unknown route: {self.path}"})
                return
            self._send_json(200 if result.ok else 502, result.as_dict())

        def do_PUT(self) -> None:
            body = _read_body(self)
            if self.path == _BRIDGE_ROUTE_RC_PASSTHROUGH:
                result = bridge.remote_object_call(body)
                self._send_json(200 if result.ok else 502, result.as_dict())
            else:
                self._send_json(404, {"error": f"unknown route: {self.path}"})

    return Handler


def serve(bridge: Optional[UnrealBridge] = None, config: Optional[BridgeConfig] = None) -> None:
    """Start the bridge HTTP server (blocking).

    Parameters
    ----------
    bridge:
        Pre-built ``UnrealBridge`` instance; one is created from ``config``
        when not supplied.
    config:
        ``BridgeConfig`` used when ``bridge`` is ``None``.
    """
    cfg = config or BridgeConfig()
    b = bridge or UnrealBridge(cfg)
    handler_cls = _make_handler(b)
    server = http.server.HTTPServer(("", cfg.bridge_port), handler_cls)
    logger.info(
        "Vitrine->UE bridge listening on :%d  (RC->%s  MCP->%s)",
        cfg.bridge_port, cfg.rc_url, cfg.mcp_url,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("bridge shutting down")
    finally:
        server.server_close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    serve()
