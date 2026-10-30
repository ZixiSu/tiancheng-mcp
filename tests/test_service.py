import asyncio
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
import io
import zipfile

from cryptography.fernet import Fernet
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import create_app, Settings, VisibleText


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = ROOT.parents[1] / "work" / "test-state" / uuid.uuid4().hex
        self.temp.mkdir(parents=True)
        self.cfg = Settings(self.temp / "keys.db", Fernet.generate_key(), public_origin="http://127.0.0.1", allow_test_http=True)
        self.users = {"session_a_123": {"id": "a", "username": "alice", "approved": True, "disabled": False},
                      "session_b_123": {"id": "b", "username": "bob", "approved": False, "disabled": False}}
        self.calls, self.mode = [], "ok"
        self.app = create_app(self.cfg, httpx.MockTransport(self.mock))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://127.0.0.1")
        self.key_a = self.app.store.issue("a", "session_a_123")
        self.key_b = self.app.store.issue("b", "session_b_123")
        if self._testMethodName != "test_skill_script_over_real_http":
            self.started, self.stopped = asyncio.Event(), asyncio.Event()
            async def manage():
                async with self.app.mcp.session_manager.run():
                    self.started.set()
                    await self.stopped.wait()
            self.manager = asyncio.create_task(manage())
            await self.started.wait()

    async def asyncTearDown(self):
        await self.client.aclose()
        if hasattr(self, "manager"):
            self.stopped.set()
            await self.manager

    def mock(self, request):
        session = request.headers.get("cookie", "").removeprefix("qt_session=")
        self.calls.append((request.url.path, session))
        if request.url.path == "/member/me":
            return httpx.Response(200, json={"user": self.users.get(session), "csrf": "must_not_leave_upstream"})
        if self.mode == "timeout":
            raise httpx.ReadTimeout("timeout")
        if self.mode == "redirect":
            return httpx.Response(302, headers={"location": "https://example.invalid"})
        if self.mode == "malformed":
            return httpx.Response(200, text="not json")
        if self.mode == "oversize":
            return httpx.Response(200, content=b"x" * (self.cfg.max_response + 1))
        if request.url.path == "/member/search":
            if self.mode == "empty":
                return httpx.Response(200, json={"results": []})
            return httpx.Response(200, json={"results": [{"id": 123 if self.mode == "numeric_id" else "sample_1", "title": "AI研究", "text": "研究证据", "date": "2026-10-21", "private": "not_returned"}]})
        if request.url.path == "/member/source":
            if self.mode == "large_pdf":
                return httpx.Response(200, content=b"%PDF-1.7" + b"x" * (3 * 1024 * 1024), headers={"content-type": "application/pdf"})
            if self.mode == "pdf":
                return httpx.Response(200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"})
            return httpx.Response(200, text="<html><script>secret-script</script><p>正文研究</p><p>资料日期未知</p></html>", headers={"content-type": "text/html; charset=utf-8"})
        if request.url.path == "/courses/list":
            return httpx.Response(200, json={"collections": [{"id": "c1", "title": "独立付费课", "published": 1, "price": 39900, "member_included": False, "unlocked": False, "video_url": "not_returned"}, {"id": "c2", "published": 1, "catalog_hidden": True, "title": "hidden"}]})
        return httpx.Response(404)

    async def rpc(self, method, params=None, key=None):
        key = key or self.key_a["token"]
        return await self.client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                                      headers={"Authorization": "Bearer " + key, "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25"})

    async def tool(self, name, arguments=None, key=None):
        r = await self.rpc("tools/call", {"name": name, "arguments": arguments or {}}, key)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["result"]

    async def test_official_client_discovery_tools_resources_prompts(self):
        self.client.headers.update({"Authorization": "Bearer " + self.key_a["token"]})
        if True:
            async with streamable_http_client("http://127.0.0.1/mcp", http_client=self.client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    init = await session.initialize()
                    self.assertIn("量化天成", init.serverInfo.name)
                    names = {t.name for t in (await session.list_tools()).tools}
                    self.assertEqual(names, {"get_service_info", "get_my_access", "search_research", "read_research_source", "list_courses", "get_review_entry"})
                    result = await session.call_tool("search_research", {"query": "AI"})
                    self.assertFalse(result.isError)
                    self.assertIn("研究证据", str(result))
                    resources = await session.list_resources()
                    self.assertTrue(resources.resources)
                    resource = await session.read_resource("tiancheng://usage")
                    self.assertIn("常驻协作要求", str(resource))
                    prompts = await session.list_prompts()
                    self.assertEqual(prompts.prompts[0].name, "research_brief")
                    prompt = await session.get_prompt("research_brief", {"topic": "AI"})
                    self.assertIn("来源", str(prompt))

    async def test_missing_and_forged_key(self):
        self.assertEqual((await self.client.post("/mcp", json={})).status_code, 401)
        self.assertEqual((await self.rpc("tools/list", key="tc_" + "x" * 43)).status_code, 401)

    async def test_expired_and_revoked_keys(self):
        self.app.store.revoke("a", self.key_a["id"])
        self.assertEqual((await self.rpc("tools/list")).status_code, 401)
        with sqlite3.connect(self.cfg.db_path) as db:
            db.execute("UPDATE keys SET expires=0 WHERE id=?", (self.key_b["id"],))
        self.assertEqual((await self.rpc("tools/list", key=self.key_b["token"])).status_code, 401)

    async def test_member_downgrade_immediate(self):
        self.users["session_a_123"]["approved"] = False
        result = await self.tool("search_research", {"query": "AI"})
        self.assertTrue(result["isError"])
        self.assertIn("MEMBERSHIP_REQUIRED", str(result))
        self.assertFalse(any(p == "/member/search" for p, _ in self.calls))

    async def test_disabled_and_expired_session(self):
        self.users["session_a_123"]["disabled"] = True
        self.assertEqual((await self.rpc("tools/list")).status_code, 403)
        del self.users["session_a_123"]
        self.assertEqual((await self.rpc("tools/list")).status_code, 401)

    async def test_free_user_courses_no_unlock(self):
        result = await self.tool("list_courses", key=self.key_b["token"])
        data = result["structuredContent"]["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["price"], 39900)
        self.assertFalse(data[0]["unlocked"])
        self.assertNotIn("video_url", str(result))

    async def test_free_user_cannot_read_source(self):
        result = await self.tool("read_research_source", {"source_id": "sample_1"}, self.key_b["token"])
        self.assertTrue(result["isError"])
        self.assertFalse(any(p == "/member/source" for p, _ in self.calls))

    async def test_customer_isolation(self):
        await self.tool("list_courses", key=self.key_b["token"])
        self.assertTrue(all(s == "session_b_123" for _, s in self.calls))
        self.calls.clear()
        await self.tool("search_research", {"query": "AI"})
        self.assertTrue(all(s == "session_a_123" for _, s in self.calls))

    async def test_key_api_self_service_and_cross_user(self):
        headers = {"Cookie": "qt_session=session_a_123", "Origin": "http://127.0.0.1"}
        created = await self.client.post("/mcp-keys", headers=headers, json={})
        self.assertEqual(created.status_code, 201)
        own = await self.client.get("/mcp-keys", headers=headers)
        self.assertNotIn("token", own.text)
        self.assertNotIn(self.key_b["id"], own.text)
        denied = await self.client.request("DELETE", "/mcp-keys", headers=headers, json={"id": self.key_b["id"]})
        self.assertEqual(denied.status_code, 404)
        revoked = await self.client.request("DELETE", "/mcp-keys", headers=headers, json={"id": created.json()["id"]})
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual((await self.rpc("tools/list", key=created.json()["token"])).status_code, 401)

    async def test_key_api_login_origin_and_key_limit(self):
        self.assertEqual((await self.client.post("/mcp-keys", json={})).status_code, 401)
        headers = {"Cookie": "qt_session=session_a_123"}
        self.assertEqual((await self.client.post("/mcp-keys", headers=headers, json={})).status_code, 403)
        headers["Origin"] = "https://evil.invalid"
        self.assertEqual((await self.client.post("/mcp-keys", headers=headers, json={})).status_code, 403)
        headers["Origin"] = "http://127.0.0.1"
        for _ in range(4):
            self.assertEqual((await self.client.post("/mcp-keys", headers=headers, json={})).status_code, 201)
        self.assertEqual((await self.client.post("/mcp-keys", headers=headers, json={})).status_code, 429)

    async def test_no_plaintext_secrets_on_disk(self):
        raw = self.cfg.db_path.read_bytes()
        self.assertNotIn(self.key_a["token"].encode(), raw)
        self.assertNotIn(b"session_a_123", raw)
        self.assertNotIn(self.cfg.encryption_key, raw)

    async def test_empty_not_failure_and_unknown_date(self):
        self.mode = "empty"
        result = await self.tool("search_research", {"query": "none"})
        self.assertFalse(result.get("isError", False))
        self.assertEqual(result["structuredContent"]["data"], [])
        self.assertIsNone(result["structuredContent"]["business_date"])

    async def test_upstream_failures_no_fabricated_data(self):
        for mode in ("timeout", "redirect", "malformed", "oversize"):
            self.mode = mode
            result = await self.tool("search_research", {"query": "AI"})
            self.assertTrue(result["isError"], mode)
            self.assertNotIn('"data": []', str(result))

    async def test_source_html_and_pdf(self):
        result = await self.tool("read_research_source", {"source_id": "sample_1"})
        self.assertIn("正文研究", str(result))
        self.assertNotIn("secret-script", str(result))
        self.mode = "pdf"
        result = await self.tool("read_research_source", {"source_id": "sample_1"})
        self.assertFalse(result["structuredContent"]["extracted"])
        self.assertIsNone(result["structuredContent"]["data"])

    async def test_visible_text_hidden_content_and_value_separators(self):
        parser = VisibleText()
        parser.feed('<div hidden><p>hidden1</p></div><span style="display: none !important">hidden2</span><p aria-hidden="true">hidden3</p><script>hidden4</script><p>2025年营收100<br>2026年营收200</p><table><tr><td>收入</td><td>100</td><td>200</td></tr></table>')
        text = ''.join(parser.parts)
        self.assertNotIn('hidden', text)
        self.assertIn('100\n2026', text)
        self.assertIn('收入\t100\t200', text)

    async def test_numeric_source_id_survives_search_and_read(self):
        self.mode = 'numeric_id'
        result = await self.tool('search_research', {'query': 'AI'})
        ident = result['structuredContent']['data'][0]['id']
        self.assertEqual(ident, '123')
        self.assertTrue(result['structuredContent']['data'][0]['source_url'].endswith('id=123'))
        result = await self.tool('read_research_source', {'source_id': ident})
        self.assertFalse(result.get('isError', False))

    async def test_large_pdf_returns_original_link_without_download(self):
        self.mode = 'large_pdf'
        result = await self.tool('read_research_source', {'source_id': '123'})
        self.assertFalse(result.get('isError', False))
        self.assertEqual(result['structuredContent']['status'], 'open_original_pdf_on_website')
        self.assertFalse(result['structuredContent']['extracted'])

    async def test_rate_request_size_host_and_origin(self):
        self.cfg.rpm = 1
        await self.rpc("tools/list")
        limited = await self.rpc("tools/list")
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.headers["retry-after"], "60")
        self.assertEqual((await self.client.get("/mcp-connect", headers={"Host": "evil.invalid"})).status_code, 403)
        self.assertEqual((await self.client.get("/mcp-connect", headers={"Origin": "https://evil.invalid"})).status_code, 403)
        huge = await self.client.post("/mcp-keys", content=b"x" * 65537)
        self.assertEqual(huge.status_code, 413)

    async def test_tools_schema_validation(self):
        result = await self.tool("search_research", {"query": "AI", "limit": 1000})
        self.assertTrue(result["isError"])
        result = await self.tool("search_research", {"query": "AI", "category": "unknown"})
        self.assertTrue(result["isError"])

    async def test_connect_page_headers(self):
        response = await self.client.get("/mcp-connect")
        self.assertEqual(response.status_code, 200)
        self.assertIn("创建个人密钥", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])

    async def test_skill_download_has_no_credentials(self):
        response = await self.client.get("/mcp-skill.zip")
        self.assertEqual(response.status_code, 200)
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        self.assertEqual(len(archive.namelist()), 3)
        for name in archive.namelist():
            self.assertTrue(name.startswith("tiancheng-research/"))
            self.assertNotIn(self.key_a["token"].encode(), archive.read(name))

    async def test_skill_script_over_real_http(self):
        # Bound loopback socket; uvicorn never opens a browser or foreground window.
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(self.app, log_level="critical", access_log=False))
        worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        worker.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                await asyncio.sleep(.03)
            self.assertTrue(server.started)
            env = dict(os.environ, TC_MCP_TOKEN=self.key_a["token"], TC_MCP_URL=f"http://127.0.0.1:{port}/mcp", PYTHONIOENCODING="utf-8")
            script = str(ROOT / "skills/tiancheng-research/scripts/call.py")
            result = await asyncio.to_thread(subprocess.run, [sys.executable, script, "get_my_access"], env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["structuredContent"]["research_member"])
            env["TC_MCP_TOKEN"] = "YOUR_PERSONAL_KEY"
            result = await asyncio.to_thread(subprocess.run, [sys.executable, script, "--list"], env=env, capture_output=True, text=True, encoding="utf-8", timeout=10)
            self.assertNotEqual(result.returncode, 0)
        finally:
            server.should_exit = True
            await asyncio.to_thread(worker.join, 5)
            sock.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
