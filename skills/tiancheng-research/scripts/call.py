"""Dependency-free MCP HTTP caller; read token from local environment only."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def run(method, params=None):
    token = os.environ.get("TC_MCP_TOKEN", "").strip()
    if not token.startswith("tc_") or len(token) != 46:
        raise ValueError("请在本地配置真实的 TC_MCP_TOKEN；不接受占位密钥")
    url = os.environ.get("TC_MCP_URL", "https://lhtc2026.com/mcp")
    u = urlsplit(url)
    if u.username or u.password or u.fragment or u.query or not (u.scheme == "https" or (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1"))):
        raise ValueError("仅支持HTTPS或本机测试URL，密钥不可放在URL中")
    opener = build_opener(NoRedirect())
    session = None

    def send(payload):
        nonlocal session
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25"}
        if session:
            headers["Mcp-Session-Id"] = session
        request = Request(url, json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers, method="POST")
        with opener.open(request, timeout=30) as response:
            session = response.headers.get("Mcp-Session-Id", session)
            raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError("服务响应过大")
            if response.status == 202:
                return None
            if "application/json" not in response.headers.get("Content-Type", ""):
                raise ValueError("此脚本要求服务启用JSON响应；请改用原生MCP客户端")
            data = json.loads(raw)
            if "error" in data:
                raise ValueError("MCP协议请求失败")
            return data.get("result")

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-11-25", "capabilities": {},
        "clientInfo": {"name": "tiancheng-skill", "version": "0.1.0"}}})
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    result = send({"jsonrpc": "2.0", "id": 2, "method": method, "params": params or {}})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="量化天成 MCP 调用")
    parser.add_argument("tool", nargs="?")
    parser.add_argument("--list", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--args", default="{}")
    group.add_argument("--args-file")
    args = parser.parse_args()
    try:
        if not args.list and not args.tool:
            parser.error("提供工具名或 --list")
        params = json.loads(Path(args.args_file).read_text(encoding="utf-8-sig") if args.args_file else args.args)
        if not isinstance(params, dict):
            raise ValueError("参数必须是JSON对象")
        result = run("tools/list" if args.list else "tools/call", None if args.list else {"name": args.tool, "arguments": params})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result and result.get("isError"):
            sys.exit(2)
    except HTTPError as exc:
        print(f"请求失败 HTTP {exc.code}；401请重新领取密钥，403检查权限，429请稍后重试。", file=sys.stderr)
        sys.exit(1)
    except (URLError, TimeoutError):
        print("无法连接量化天成服务，请稍后再试。", file=sys.stderr)
        sys.exit(1)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
