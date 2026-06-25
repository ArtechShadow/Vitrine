#!/usr/bin/env python3
"""Tiny UE 5.8 native-MCP client (Streamable HTTP) for driving the editor.

Usage (inside the vitrine-unreal container):
  python3 umcp.py list_toolsets
  python3 umcp.py describe <toolset>
  python3 umcp.py call <toolset> <tool> '<json-args>'     # toolset tool
  python3 umcp.py call - <tool> '<json-args>'             # top-level tool
  python3 umcp.py raw <method> '<json-params>'            # raw JSON-RPC
"""
import sys, json, requests

BASE = "http://127.0.0.1:8000/mcp"
H = {"Content-Type": "application/json",
     "Accept": "application/json, text/event-stream",
     "Origin": "http://127.0.0.1:8000"}


def _parse(text):
    text = text.strip()
    if text.startswith("event:") or "\ndata:" in text or text.startswith("data:"):
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except Exception:
                    pass
        return {"raw": text}
    try:
        return json.loads(text)
    except Exception:
        return {"raw": text}


def session():
    r = requests.post(BASE, headers=H, timeout=30, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "vitrine", "version": "1"}}})
    return r.headers.get("Mcp-Session-Id")


def rpc(method, params, sid=None):
    sid = sid or session()
    h = dict(H); h["Mcp-Session-Id"] = sid
    r = requests.post(BASE, headers=h, timeout=120, json={
        "jsonrpc": "2.0", "id": 2, "method": method, "params": params})
    return _parse(r.text)


def call_tool(toolset, tool, args, sid=None):
    p = {"tool_name": tool, "arguments": args}
    if toolset and toolset != "-":
        p["toolset_name"] = toolset
    return rpc("tools/call", {"name": "call_tool", "arguments": p}, sid)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list_toolsets"
    sid = session()
    if cmd == "list_toolsets":
        out = rpc("tools/call", {"name": "list_toolsets", "arguments": {}}, sid)
    elif cmd == "describe":
        out = rpc("tools/call", {"name": "describe_toolset",
                                 "arguments": {"toolset_name": sys.argv[2]}}, sid)
    elif cmd == "call":
        args = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
        out = call_tool(sys.argv[2], sys.argv[3], args, sid)
    elif cmd == "raw":
        out = rpc(sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}, sid)
    else:
        out = {"error": f"unknown cmd {cmd}"}
    print(json.dumps(out, indent=1)[:4000])
