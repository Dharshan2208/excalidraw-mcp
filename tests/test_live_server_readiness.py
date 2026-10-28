"""Deterministic regression tests for LiveCanvasServer startup synchronization, readiness, and lifecycle contracts.

Validates that start() only returns after Uvicorn has bound its listening socket and
can accept immediate connections without arbitrary sleeps, handles timeouts and exceptions,
reclaims partially started resources, and cleanly manages shutdown/restart cycles.
"""

import asyncio
import errno
import json
import socket
import unittest
from unittest.mock import patch

import httpx
from websockets.sync.client import connect as ws_connect

from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.live_server import LiveCanvasServer
from excalidraw_mcp.service import SceneService


class LiveServerReadinessTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.server = LiveCanvasServer(self.service, host="127.0.0.1", port=0)

    def tearDown(self):
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass
        try:
            self.service.stop_live_server()
        except Exception:
            pass

    def test_start_immediate_http_connection_without_sleep(self):
        """start() must not return until HTTP requests can be handled immediately with zero sleep."""
        res = self.server.start(port=0)
        self.assertEqual(res["status"], "started")
        self.assertTrue(self.server.is_running)
        self.assertGreater(res["port"], 0)

        # Immediate HTTP request on the very next instruction
        url = f"{res['url']}/api/health"
        resp = httpx.get(url, timeout=2.0)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["element_count"], 0)

    def test_start_immediate_raw_socket_connection(self):
        """Raw TCP socket connects immediately upon start() returning, proving socket is in listen state."""
        res = self.server.start(port=0)
        port = res["port"]

        # Raw TCP connection without any delay
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_sock:
            client_sock.settimeout(2.0)
            client_sock.connect(("127.0.0.1", port))
            client_sock.sendall(b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            response = b""
            while True:
                chunk = client_sock.recv(4096)
                if not chunk:
                    break
                response += chunk

        self.assertTrue(response.startswith(b"HTTP/1.1 200 OK"))
        self.assertIn(b'"status":"healthy"', response)

    def test_start_immediate_websocket_connection(self):
        """WebSocket clients can connect and perform real-time bidirectional sync immediately after start()."""
        res = self.server.start(port=0)
        ws_url = f"ws://127.0.0.1:{res['port']}/ws"

        # Immediate WebSocket handshake
        with ws_connect(ws_url, open_timeout=2.0) as ws:
            init_msg = json.loads(ws.recv(timeout=2.0))
            self.assertEqual(init_msg["type"], "init")

            # Client sends update
            ws.send(json.dumps({
                "type": "update",
                "scene": {
                    "type": "excalidraw",
                    "version": 2,
                    "elements": [
                        {"id": "rect-ready", "type": "rectangle", "x": 100, "y": 100, "width": 80, "height": 40}
                    ]
                }
            }))

            # Polling wait for websocket message processing by server thread
            import time
            for _ in range(50):
                if self.service.state.all():
                    break
                time.sleep(0.01)
            
            elements = self.service.state.all()
            self.assertEqual(len(elements), 1)
            self.assertEqual(elements[0]["id"], "rect-ready")

    def test_port_conflict_raises_actionable_scene_error(self):
        """Binding on an already occupied port raises SceneError with actionable error details and cleans up."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        occupied_port = sock.getsockname()[1]

        try:
            with self.assertRaises(SceneError) as ctx:
                self.server.start(port=occupied_port)

            err_msg = str(ctx.exception)
            self.assertIn(str(occupied_port), err_msg)
            self.assertIn("already in use", err_msg.lower())
            self.assertFalse(self.server.is_running)
            self.assertIsNone(self.server.server)
            self.assertIsNone(self.server.thread)
        finally:
            sock.close()

    def test_startup_timeout_behavior_cleans_up_safely(self):
        """Startup timeout raises SceneError and safely cleans up partial threads and sockets."""
        from excalidraw_mcp.live_server import _LiveCanvasUvicornServer

        real_startup = _LiveCanvasUvicornServer.startup

        async def slow_startup(server_self, sockets=None):
            await asyncio.sleep(0.4)
            return await real_startup(server_self, sockets=sockets)

        with patch.object(_LiveCanvasUvicornServer, "startup", slow_startup):
            with self.assertRaises(SceneError) as ctx:
                self.server.start(port=0, timeout=0.1)

            self.assertIn("timed out after 0.1s", str(ctx.exception))
            self.assertFalse(self.server.is_running)
            self.assertIsNone(self.server.server)
            self.assertIsNone(self.server.thread)

    def test_startup_exception_propagation(self):
        """Exceptions raised in server thread before readiness are propagated as SceneError."""
        def broken_run(*args, **kwargs):
            raise RuntimeError("Fatal hardware socket subsystem failure")

        with patch("uvicorn.Server.serve", side_effect=broken_run):
            with self.assertRaises(SceneError) as ctx:
                self.server.start(port=0, timeout=2.0)

            self.assertIn("Fatal hardware socket subsystem failure", str(ctx.exception))
            self.assertFalse(self.server.is_running)
            self.assertIsNone(self.server.server)
            self.assertIsNone(self.server.thread)

    def test_repeated_start_returns_already_running(self):
        """Subsequent start() calls on an already running server return already_running without error."""
        first = self.server.start(port=0)
        self.assertEqual(first["status"], "started")
        port = first["port"]

        second = self.server.start(port=port)
        self.assertEqual(second["status"], "already_running")
        self.assertEqual(second["port"], port)
        self.assertTrue(self.server.is_running)

    def test_slow_startup_within_timeout_succeeds(self):
        """Slow server startup that completes within the timeout limit succeeds and is immediately usable."""
        from excalidraw_mcp.live_server import _LiveCanvasUvicornServer

        real_startup = _LiveCanvasUvicornServer.startup

        async def slow_startup(server_self, sockets=None):
            await asyncio.sleep(0.2)
            return await real_startup(server_self, sockets=sockets)

        with patch.object(_LiveCanvasUvicornServer, "startup", slow_startup):
            res = self.server.start(port=0, timeout=2.0)
            self.assertEqual(res["status"], "started")
            self.assertTrue(self.server.is_running)

            resp = httpx.get(f"{res['url']}/api/health", timeout=2.0)
            self.assertEqual(resp.status_code, 200)

    def test_clean_shutdown_and_restart_cycle(self):
        """Server can be started, stopped, and restarted cleanly without port leakage or deadlocks."""
        # First start
        res1 = self.server.start(port=0)
        self.assertEqual(res1["status"], "started")
        port1 = res1["port"]
        self.assertTrue(self.server.is_running)

        # Stop
        stop_res1 = self.server.stop()
        self.assertEqual(stop_res1["status"], "stopped")
        self.assertFalse(self.server.is_running)

        # Verify port is released: socket connection refused
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_sock:
            test_sock.settimeout(1.0)
            with self.assertRaises((ConnectionRefusedError, OSError)):
                test_sock.connect(("127.0.0.1", port1))

        # Restart
        res2 = self.server.start(port=0)
        self.assertEqual(res2["status"], "started")
        self.assertTrue(self.server.is_running)

        # Verify restarted server is accepting HTTP
        resp = httpx.get(f"{res2['url']}/api/health", timeout=2.0)
        self.assertEqual(resp.status_code, 200)

        # Stop again
        stop_res2 = self.server.stop()
        self.assertEqual(stop_res2["status"], "stopped")
        self.assertFalse(self.server.is_running)

    def test_service_start_live_server_integration(self):
        """SceneService.start_live_server() integrates with readiness contract and clears failed instance."""
        res = self.service.start_live_server(port=0)
        self.assertEqual(res["status"], "started")
        status = self.service.get_live_server_status()
        self.assertTrue(status["is_running"])

        self.service.stop_live_server()
        status_stopped = self.service.get_live_server_status()
        self.assertFalse(status_stopped["is_running"])

    def test_signal_handlers_installed_and_restored_on_lifecycle(self):
        """Signal handlers are installed on server start and restored on server stop."""
        import signal
        from excalidraw_mcp.live_server import _handle_exit_signal

        orig_sigint = signal.getsignal(signal.SIGINT)
        res = self.server.start(port=0)
        self.assertEqual(res["status"], "started")

        # Handlers should now be registered
        current_sigint = signal.getsignal(signal.SIGINT)
        self.assertEqual(current_sigint, _handle_exit_signal)

        # Stop server
        self.server.stop()

        # Handlers should be restored
        restored_sigint = signal.getsignal(signal.SIGINT)
        self.assertEqual(restored_sigint, orig_sigint)

    def test_sigterm_stops_active_servers_cleanly(self):
        """Receiving SIGTERM triggers graceful server shutdown and socket closure."""
        import signal
        from excalidraw_mcp.live_server import _handle_exit_signal

        res = self.server.start(port=0)
        port = res["port"]
        self.assertTrue(self.server.is_running)

        # Simulate SIGTERM signal delivery to handler
        with patch("os.kill") as mock_kill, patch("sys.exit") as mock_exit:
            _handle_exit_signal(signal.SIGTERM, None)

        self.assertFalse(self.server.is_running)
        self.assertIsNone(self.server.server)
        self.assertIsNone(self.server.thread)

        # Verify socket connection refused (port is free)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_sock:
            test_sock.settimeout(1.0)
            with self.assertRaises((ConnectionRefusedError, OSError)):
                test_sock.connect(("127.0.0.1", port))

    def test_sigint_triggers_graceful_shutdown_and_raises_keyboard_interrupt(self):
        """Receiving SIGINT shuts down the server and propagates KeyboardInterrupt to main thread."""
        import signal
        from excalidraw_mcp.live_server import _handle_exit_signal

        res = self.server.start(port=0)
        port = res["port"]
        self.assertTrue(self.server.is_running)

        with self.assertRaises(KeyboardInterrupt):
            _handle_exit_signal(signal.SIGINT, None)

        self.assertFalse(self.server.is_running)
        self.assertIsNone(self.server.server)
        self.assertIsNone(self.server.thread)

        # Verify socket released
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_sock:
            test_sock.settimeout(1.0)
            with self.assertRaises((ConnectionRefusedError, OSError)):
                test_sock.connect(("127.0.0.1", port))

    def test_atexit_hook_stops_active_servers(self):
        """atexit handler ensures active background servers are stopped on interpreter shutdown."""
        from excalidraw_mcp.live_server import _handle_atexit

        res = self.server.start(port=0)
        self.assertTrue(self.server.is_running)

        _handle_atexit()

        self.assertFalse(self.server.is_running)
        self.assertIsNone(self.server.server)
        self.assertIsNone(self.server.thread)

    def test_subprocess_sigterm_graceful_shutdown(self):
        """Subprocess running LiveCanvasServer cleanly shuts down upon receiving SIGTERM."""
        import subprocess
        import sys

        script = """
import time
from excalidraw_mcp.service import SceneService
from excalidraw_mcp.live_server import LiveCanvasServer

service = SceneService()
server = LiveCanvasServer(service, host="127.0.0.1", port=0)
res = server.start()
print(f"READY:{res['port']}", flush=True)
while True:
    time.sleep(0.1)
"""
        proc = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True)
        try:
            line = proc.stdout.readline()
            self.assertTrue(line.startswith("READY:"))
            port = int(line.strip().split(":")[1])

            import signal
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=3.0)

            # Port should be released immediately
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                with self.assertRaises((ConnectionRefusedError, OSError)):
                    s.connect(("127.0.0.1", port))
        finally:
            if proc.stdout:
                proc.stdout.close()
            if proc.poll() is None:
                proc.kill()


if __name__ == "__main__":
    unittest.main()
