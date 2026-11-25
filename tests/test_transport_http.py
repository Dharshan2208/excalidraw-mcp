"""Unit and integration tests for Streamable HTTP transport and CLI configuration."""

import asyncio
import io
import os
import socket
import sys
import unittest
from unittest.mock import MagicMock, patch

from fastmcp import Client
import httpx
import uvicorn

from excalidraw_mcp.server import (
    _is_loopback_host,
    create_server,
    main,
    parse_cli_args,
    run,
)


class TestTransportCliParsing(unittest.TestCase):
    def test_default_cli_args(self):
        with patch.dict(os.environ, {}, clear=True):
            opts = parse_cli_args([])
            self.assertEqual(opts.transport, "stdio")
            self.assertEqual(opts.host, "127.0.0.1")
            self.assertEqual(opts.port, 8000)
            self.assertIsNone(opts.path)

    def test_explicit_cli_flags(self):
        opts = parse_cli_args([
            "--transport", "streamable-http",
            "--host", "0.0.0.0",
            "--port", "9090",
            "--path", "/api/mcp",
        ])
        self.assertEqual(opts.transport, "streamable-http")
        self.assertEqual(opts.host, "0.0.0.0")
        self.assertEqual(opts.port, 9090)
        self.assertEqual(opts.path, "/api/mcp")

    def test_env_var_defaults(self):
        env = {
            "EXCALIDRAW_TRANSPORT": "streamable-http",
            "EXCALIDRAW_HOST": "192.168.1.50",
            "EXCALIDRAW_PORT": "8443",
            "EXCALIDRAW_HTTP_PATH": "/custom_mcp",
        }
        with patch.dict(os.environ, env, clear=True):
            opts = parse_cli_args([])
            self.assertEqual(opts.transport, "streamable-http")
            self.assertEqual(opts.host, "192.168.1.50")
            self.assertEqual(opts.port, 8443)
            self.assertEqual(opts.path, "/custom_mcp")

    def test_invalid_transport_raises(self):
        with self.assertRaises(SystemExit):
            with patch("sys.stderr", new=io.StringIO()):
                parse_cli_args(["--transport", "ftp"])

    def test_invalid_port_raises(self):
        with self.assertRaises(SystemExit):
            with patch("sys.stderr", new=io.StringIO()):
                parse_cli_args(["--port", "70000"])

        with self.assertRaises(SystemExit):
            with patch("sys.stderr", new=io.StringIO()):
                parse_cli_args(["--port", "0"])

    def test_version_cli_flag(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with patch("sys.stdout", stdout):
                parse_cli_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("exca-mcp", stdout.getvalue())

    def test_help_lists_subcommands(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with patch("sys.stdout", stdout):
                parse_cli_args(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("install-skills", stdout.getvalue())

    def test_server_fastmcp_version_configured(self):
        from excalidraw_mcp.server import create_server, get_server_version
        server = create_server()
        self.assertEqual(server.version, get_server_version())


class TestLoopbackSecurityCheck(unittest.TestCase):
    def test_loopback_hosts(self):
        self.assertTrue(_is_loopback_host("127.0.0.1"))
        self.assertTrue(_is_loopback_host("localhost"))
        self.assertTrue(_is_loopback_host("::1"))
        self.assertTrue(_is_loopback_host("127.0.0.2"))

    def test_non_loopback_hosts(self):
        self.assertFalse(_is_loopback_host("0.0.0.0"))
        self.assertFalse(_is_loopback_host("::"))
        self.assertFalse(_is_loopback_host("192.168.1.100"))
        self.assertFalse(_is_loopback_host("10.0.0.1"))
        self.assertFalse(_is_loopback_host("remote.server.internal"))


class TestMainDispatch(unittest.TestCase):
    @patch("excalidraw_mcp.server.mcp.run")
    def test_main_stdio_default(self, mock_run):
        main([])
        mock_run.assert_called_once_with(show_banner=False)

    @patch("excalidraw_mcp.server.mcp.run")
    def test_main_streamable_http_loopback(self, mock_run):
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            main(["--transport", "streamable-http", "--port", "8080"])
        mock_run.assert_called_once_with(
            show_banner=False,
            transport="streamable-http",
            host="127.0.0.1",
            port=8080,
        )
        self.assertEqual(stderr.getvalue(), "")

    @patch("excalidraw_mcp.server.mcp.run")
    def test_main_streamable_http_warning_on_non_loopback(self, mock_run):
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            main(["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8080", "--path", "/mcp"])
        mock_run.assert_called_once_with(
            show_banner=False,
            transport="streamable-http",
            host="0.0.0.0",
            port=8080,
            path="/mcp",
        )
        self.assertIn("WARNING: Excalidraw MCP server is binding to non-loopback address '0.0.0.0'", stderr.getvalue())
        self.assertIn("does not enforce authentication", stderr.getvalue())

    @patch("excalidraw_mcp.installer.run_install_skills_cli")
    def test_main_delegates_to_installer(self, mock_install):
        mock_install.return_value = 0
        with self.assertRaises(SystemExit) as ctx:
            main(["install-skills", "--claude", "--dry-run"])
        self.assertEqual(ctx.exception.code, 0)
        mock_install.assert_called_once_with(["--claude", "--dry-run"])

    @patch("excalidraw_mcp.server.mcp.run")
    def test_run_helper(self, mock_run):
        run()
        mock_run.assert_called_once_with(show_banner=False)


class TestStreamableHttpIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_streamable_http_end_to_end(self):
        server = create_server(toolset="full")

        # Bind to ephemeral port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]

        app = server.http_app(transport="streamable-http")
        config = uvicorn.Config(app, log_level="error")
        uvicorn_server = uvicorn.Server(config)

        server_task = asyncio.create_task(uvicorn_server.serve(sockets=[sock]))
        await asyncio.sleep(0.3)

        url = f"http://127.0.0.1:{port}/mcp"
        try:
            # Verify /health endpoint
            async with httpx.AsyncClient() as http_client:
                health_resp = await http_client.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
                self.assertEqual(health_resp.status_code, 200)
                health_data = health_resp.json()
                self.assertEqual(health_data["status"], "healthy")
                self.assertEqual(health_data["version"], "0.5.0")

            async with Client(url, timeout=5) as client:
                tools = await client.list_tools()
                tool_names = [t.name for t in tools]
                self.assertIn("create_shape", tool_names)
                self.assertIn("inspect_scene", tool_names)
                self.assertIn("scene_storage", tool_names)

                # Execute a tool over Streamable HTTP
                res = await client.call_tool("inspect_scene", {"mode": "summary"})
                self.assertFalse(res.is_error)
                self.assertIn("element_count", res.content[0].text)
        finally:
            uvicorn_server.should_exit = True
            try:
                await asyncio.wait_for(server_task, timeout=3.0)
            except (asyncio.TimeoutError, Exception):
                pass
