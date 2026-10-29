"""Live canvas server providing real-time bidirectional synchronization between Python backend and browser UI."""

import asyncio
import atexit
import json
import logging
import os
import signal
import socket
import sys
import threading
import time
from typing import Any

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect
import uvicorn

from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.renderer import render_scene_to_png

logger = logging.getLogger("excalidraw_mcp.live_server")

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Excalidraw Live Canvas</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body, html { width: 100%; height: 100%; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #121212; color: #f8f9fa; }
    #header {
      height: 48px; background: #1e1e1e; border-bottom: 1px solid #333; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; font-size: 14px;
    }
    .badge { padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
    .badge-live { background: #2b8a3e; color: #fff; }
    .badge-disconnected { background: #c92a2a; color: #fff; }
    .btn { background: #1971c2; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500; margin-left: 8px; text-decoration: none; display: inline-flex; align-items: center; }
    .btn:hover { background: #1864ab; }
    #canvas-container { width: 100%; height: calc(100% - 48px); position: relative; background: #ffffff; }
    #live-canvas { width: 100%; height: 100%; display: block; }
    #info-bar { position: absolute; bottom: 12px; left: 12px; background: rgba(30, 30, 30, 0.85); backdrop-filter: blur(4px); padding: 6px 12px; border-radius: 6px; font-size: 12px; border: 1px solid #444; color: #ced4da; pointer-events: none; }
  </style>
</head>
<body>
  <div id="header">
    <div style="display: flex; align-items: center; gap: 12px;">
      <span style="font-weight: 700; letter-spacing: -0.5px;">Excalidraw Live Canvas</span>
      <span id="status-badge" class="badge badge-disconnected">Connecting...</span>
    </div>
    <div style="display: flex; align-items: center;">
      <span id="rev-text" style="color: #adb5bd; margin-right: 12px;">Rev: 0 | Elements: 0</span>
      <button class="btn" onclick="syncFromBackend()">Refresh</button>
      <a class="btn" href="/api/screenshot" target="_blank">Screenshot PNG</a>
    </div>
  </div>
  <div id="canvas-container">
    <canvas id="live-canvas"></canvas>
    <div id="info-bar">Real-time bi-directional sync active</div>
  </div>

  <script>
    let ws = null;
    let currentScene = { elements: [], appState: {}, files: {} };
    let currentRevision = 0;

    const canvas = document.getElementById("live-canvas");
    const ctx = canvas.getContext("2d");
    const badge = document.getElementById("status-badge");
    const revText = document.getElementById("rev-text");

    function resizeCanvas() {
      const container = document.getElementById("canvas-container");
      canvas.width = container.clientWidth * window.devicePixelRatio;
      canvas.height = container.clientHeight * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
      renderScene();
    }
    window.addEventListener("resize", resizeCanvas);

    function renderScene() {
      const w = canvas.width / window.devicePixelRatio;
      const h = canvas.height / window.devicePixelRatio;
      ctx.clearRect(0, 0, w, h);

      const appState = currentScene.appState || {};
      ctx.fillStyle = appState.viewBackgroundColor || "#ffffff";
      ctx.fillRect(0, 0, w, h);

      const elements = (currentScene.elements || []).filter(el => !el.isDeleted);
      if (!elements.length) {
        ctx.fillStyle = "#adb5bd";
        ctx.font = "16px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("Excalidraw Canvas Empty", w / 2, h / 2);
        return;
      }

      // Compute bounding box
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      elements.forEach(el => {
        minX = Math.min(minX, el.x);
        minY = Math.min(minY, el.y);
        maxX = Math.max(maxX, el.x + (el.width || 0));
        maxY = Math.max(maxY, el.y + (el.height || 0));
      });
      const boundsW = Math.max(10, maxX - minX + 80);
      const boundsH = Math.max(10, maxY - minY + 80);
      const zoom = Math.min(1.5, Math.max(0.2, Math.min(w / boundsW, h / boundsH)));
      const offsetX = (w / 2) - ((minX + maxX) / 2) * zoom;
      const offsetY = (h / 2) - ((minY + maxY) / 2) * zoom;

      ctx.save();
      ctx.translate(offsetX, offsetY);
      ctx.scale(zoom, zoom);

      // Render elements
      elements.forEach(el => {
        ctx.save();
        ctx.lineWidth = el.strokeWidth || 1;
        ctx.strokeStyle = el.strokeColor || "#1e1e1e";
        ctx.fillStyle = el.backgroundColor === "transparent" ? "rgba(0,0,0,0)" : (el.backgroundColor || "rgba(0,0,0,0)");

        if (el.type === "rectangle" || el.type === "frame") {
          if (el.type === "frame") {
            ctx.setLineDash([4, 4]);
            ctx.strokeRect(el.x, el.y, el.width, el.height);
            ctx.fillStyle = "#868e96";
            ctx.font = "12px sans-serif";
            ctx.fillText(el.name || "Frame", el.x + 8, el.y - 6);
          } else {
            ctx.fillRect(el.x, el.y, el.width, el.height);
            ctx.strokeRect(el.x, el.y, el.width, el.height);
          }
        } else if (el.type === "ellipse") {
          ctx.beginPath();
          ctx.ellipse(el.x + el.width / 2, el.y + el.height / 2, el.width / 2, el.height / 2, 0, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        } else if (el.type === "diamond") {
          ctx.beginPath();
          ctx.moveTo(el.x + el.width / 2, el.y);
          ctx.lineTo(el.x + el.width, el.y + el.height / 2);
          ctx.lineTo(el.x + el.width / 2, el.y + el.height);
          ctx.lineTo(el.x, el.y + el.height / 2);
          ctx.closePath();
          ctx.fill();
          ctx.stroke();
        } else if (el.type === "arrow") {
          const points = el.points || [[0, 0], [el.width, el.height]];
          ctx.beginPath();
          ctx.moveTo(el.x + points[0][0], el.y + points[0][1]);
          for (let i = 1; i < points.length; i++) {
            ctx.lineTo(el.x + points[i][0], el.y + points[i][1]);
          }
          ctx.stroke();
        } else if (el.type === "text") {
          ctx.fillStyle = el.strokeColor || "#1e1e1e";
          ctx.font = `${el.fontSize || 16}px sans-serif`;
          ctx.textAlign = "left";
          ctx.textBaseline = "top";
          const lines = (el.text || "").split("\\n");
          lines.forEach((l, idx) => {
            ctx.fillText(l, el.x, el.y + idx * ((el.fontSize || 16) * 1.2));
          });
        }
        ctx.restore();
      });

      ctx.restore();
    }

    function connectWebSocket() {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${protocol}//${window.location.host}/ws`;
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        badge.className = "badge badge-live";
        badge.textContent = "Live Connected";
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "init" || data.type === "scene_updated") {
            currentScene = data.scene;
            currentRevision = data.revision;
            revText.textContent = `Rev: ${currentRevision} | Elements: ${(currentScene.elements || []).length}`;
            renderScene();
          }
        } catch (e) {
          console.error("Failed to parse WS payload:", e);
        }
      };

      ws.onclose = () => {
        badge.className = "badge badge-disconnected";
        badge.textContent = "Disconnected (reconnecting...)";
        setTimeout(connectWebSocket, 1500);
      };

      ws.onerror = () => ws.close();
    }

    async function syncFromBackend() {
      try {
        const res = await fetch("/api/scene");
        if (res.ok) {
          const data = await res.json();
          currentScene = data;
          currentRevision = data.revision || 0;
          revText.textContent = `Rev: ${currentRevision} | Elements: ${(currentScene.elements || []).length}`;
          renderScene();
        }
      } catch (e) {
        console.error("Fetch failed", e);
      }
    }

    resizeCanvas();
    syncFromBackend();
    connectWebSocket();
  </script>
</body>
</html>
"""


class _LiveCanvasUvicornServer(uvicorn.Server):
    """Custom Uvicorn server providing deterministic startup synchronization and clean error propagation."""

    def __init__(self, config: uvicorn.Config, ready_event: threading.Event):
        super().__init__(config)
        self.ready_event = ready_event
        self.startup_error: BaseException | None = None

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await self.lifespan.startup()
        if self.lifespan.should_exit:
            self.should_exit = True
            if getattr(self.lifespan, "startup_failed", False):
                self.startup_error = RuntimeError("ASGI lifespan startup failed")
                raise self.startup_error
            return

        config = self.config

        def create_protocol(
            _loop: asyncio.AbstractEventLoop | None = None,
        ) -> asyncio.Protocol:
            return config.http_protocol_class(
                config=config,
                server_state=self.server_state,
                app_state=self.lifespan.state,
                _loop=_loop,
            )

        loop = asyncio.get_running_loop()

        if sockets is not None:
            self.servers = []
            for sock in sockets:
                server = await loop.create_server(
                    create_protocol,
                    sock=sock,
                    ssl=config.ssl,
                    backlog=config.backlog,
                )
                self.servers.append(server)
            listeners = sockets
        else:
            try:
                server = await loop.create_server(
                    create_protocol,
                    host=config.host,
                    port=config.port,
                    ssl=config.ssl,
                    backlog=config.backlog,
                )
            except OSError as exc:
                self.startup_error = exc
                await self.lifespan.shutdown()
                raise exc

            assert server.sockets is not None
            listeners = server.sockets
            self.servers = [server]

        if sockets is None:
            self._log_started_message(listeners)

        self.started = True
        self.ready_event.set()


_active_servers: set["LiveCanvasServer"] = set()
_active_servers_lock = threading.Lock()
_original_signal_handlers: dict[int, Any] = {}
_signals_installed = False
_atexit_registered = False


def _handle_exit_signal(sig: int, frame: Any) -> None:
    """Process exit signal handler ensuring all active background live servers are cleanly stopped."""
    with _active_servers_lock:
        servers_to_stop = list(_active_servers)
        prev_handler = _original_signal_handlers.get(sig)

    for s in servers_to_stop:
        try:
            s.stop()
        except Exception:
            pass

    _uninstall_signal_handlers()

    if callable(prev_handler):
        prev_handler(sig, frame)
    elif prev_handler == signal.SIG_DFL or prev_handler == 0:
        if sig == signal.SIGINT:
            raise KeyboardInterrupt()
        elif sys.platform != "win32" and sig in (signal.SIGTERM, getattr(signal, "SIGHUP", None)):
            signal.signal(sig, signal.SIG_DFL)
            os.kill(os.getpid(), sig)
        else:
            sys.exit(128 + sig)


def _handle_atexit() -> None:
    """atexit handler ensuring any remaining live canvas servers are stopped on Python exit."""
    with _active_servers_lock:
        servers_to_stop = list(_active_servers)
    for s in servers_to_stop:
        try:
            s.stop()
        except Exception:
            pass


def _install_signal_handlers() -> None:
    """Install process-level signal handlers on the main thread for graceful live server shutdown."""
    global _signals_installed
    if _signals_installed:
        return

    # Signal handlers can only be registered from the main thread
    if threading.current_thread() is not threading.main_thread():
        return

    signals_to_catch = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        signals_to_catch.append(signal.SIGHUP)

    for sig in signals_to_catch:
        try:
            prev = signal.getsignal(sig)
            if prev != _handle_exit_signal:
                _original_signal_handlers[sig] = prev
                signal.signal(sig, _handle_exit_signal)
        except (ValueError, OSError):
            pass

    _signals_installed = True


def _uninstall_signal_handlers() -> None:
    """Restore previous signal handlers when no live servers are active."""
    global _signals_installed
    if not _signals_installed:
        return

    if threading.current_thread() is not threading.main_thread():
        return

    for sig, prev in list(_original_signal_handlers.items()):
        try:
            signal.signal(sig, prev)
        except (ValueError, OSError):
            pass

    _original_signal_handlers.clear()
    _signals_installed = False


def _register_active_server(server: "LiveCanvasServer") -> None:
    """Register an active server and install signal/atexit handlers."""
    global _atexit_registered
    with _active_servers_lock:
        _active_servers.add(server)
        if not _atexit_registered:
            atexit.register(_handle_atexit)
            _atexit_registered = True
        _install_signal_handlers()


def _unregister_active_server(server: "LiveCanvasServer") -> None:
    """Unregister a server and restore signal handlers if no servers remain."""
    with _active_servers_lock:
        _active_servers.discard(server)
        if not _active_servers:
            _uninstall_signal_handlers()


def install_signal_handlers() -> bool:
    """Explicitly install signal handlers on the main thread for live canvas lifecycle management."""
    with _active_servers_lock:
        _install_signal_handlers()
        return _signals_installed


def uninstall_signal_handlers() -> None:
    """Explicitly restore previous signal handlers."""
    with _active_servers_lock:
        _uninstall_signal_handlers()


class LiveCanvasServer:
    """Manages the background Uvicorn live canvas server."""

    def __init__(self, service: Any, host: str = "127.0.0.1", port: int = 8080, auth_token: str | None = None):
        if host in ("0.0.0.0", "::") and not os.environ.get("EXCALIDRAW_ALLOW_REMOTE"):
            raise SceneError("Binding to 0.0.0.0 is disabled by default for security. Use 127.0.0.1 or set EXCALIDRAW_ALLOW_REMOTE=1")
        self.service = service
        self.host = host
        self.port = port
        self.auth_token = auth_token or os.environ.get("EXCALIDRAW_LIVE_TOKEN")
        self.app = self._create_app()
        self.server: _LiveCanvasUvicornServer | None = None
        self.thread: threading.Thread | None = None
        self.active_websockets: set[WebSocket] = set()
        self._ws_lock = threading.Lock()
        self._start_lock = threading.RLock()
        self._unsubscribe_state: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.is_running = False

    def _create_app(self) -> Starlette:
        routes = [
            Route("/", self._handle_index, methods=["GET"]),
            Route("/api/scene", self._handle_get_scene, methods=["GET"]),
            Route("/api/scene", self._handle_post_scene, methods=["POST"]),
            Route("/api/screenshot", self._handle_screenshot, methods=["GET"]),
            Route("/api/health", self._handle_health, methods=["GET"]),
            WebSocketRoute("/ws", self._handle_ws),
        ]
        return Starlette(routes=routes)

    async def _handle_index(self, request):
        page = HTML_PAGE
        if self.auth_token:
            page = page.replace('new WebSocket(`${protocol}//${window.location.host}/ws`)', f'new WebSocket(`${{protocol}}//${{window.location.host}}/ws?token={self.auth_token}`)')
        return HTMLResponse(page)

    async def _handle_get_scene(self, request):
        doc, rev = self.service.state.snapshot()
        return JSONResponse({**doc, "revision": rev})

    async def _handle_post_scene(self, request):
        if self.auth_token:
            token = request.headers.get("x-auth-token") or request.query_params.get("token")
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
            if token != self.auth_token:
                return JSONResponse({"error": "Unauthorized: invalid or missing token"}, status_code=401)

        try:
            payload = await request.json()
        except Exception as err:
            return JSONResponse({"error": f"Invalid JSON: {err}"}, status_code=400)

        try:
            self.service.state.replace(payload)
            doc, rev = self.service.state.snapshot()
            return JSONResponse({"status": "updated", "revision": rev})
        except Exception as err:
            return JSONResponse({"error": str(err)}, status_code=400)

    async def _handle_screenshot(self, request):
        try:
            doc, _ = self.service.state.snapshot()
            scale = float(request.query_params.get("scale", 1.0))
            padding = int(request.query_params.get("padding", 40))
            png_bytes = render_scene_to_png(doc, scale=scale, padding=padding)
            return Response(png_bytes, media_type="image/png")
        except Exception as err:
            return JSONResponse({"error": str(err)}, status_code=500)

    async def _handle_health(self, request):
        doc, rev = self.service.state.snapshot()
        active_els = [el for el in doc.get("elements", []) if not el.get("isDeleted")]
        with self._ws_lock:
            client_count = len(self.active_websockets)
        return JSONResponse(
            {
                "status": "healthy",
                "revision": rev,
                "element_count": len(active_els),
                "active_ws_clients": client_count,
            }
        )

    async def _handle_ws(self, websocket: WebSocket):
        origin = websocket.headers.get("origin")
        if origin:
            import urllib.parse
            parsed = urllib.parse.urlparse(origin)
            allowed = {"localhost", "127.0.0.1", "::1", self.host.lower()}
            if parsed.hostname and parsed.hostname.lower() not in allowed:
                logger.warning("Rejected WebSocket connection from unauthorized origin: %s", origin)
                await websocket.close(code=1008)
                return

        if self.auth_token:
            token = websocket.query_params.get("token") or websocket.headers.get("x-auth-token")
            if token != self.auth_token:
                logger.warning("Rejected WebSocket connection: invalid or missing auth token")
                await websocket.close(code=1008)
                return

        await websocket.accept()
        with self._ws_lock:
            self.active_websockets.add(websocket)
        try:
            # Send initial scene snapshot
            doc, rev = self.service.state.snapshot()
            await websocket.send_text(
                json.dumps({"type": "init", "scene": doc, "revision": rev})
            )

            # Receive client edits if sent over websocket
            while True:
                msg_text = await websocket.receive_text()
                try:
                    data = json.loads(msg_text)
                    if data.get("type") == "update" and "scene" in data:
                        self.service.state.replace(data["scene"])
                except Exception as err:
                    logger.warning("Error processing websocket client update: %s", err)
        except WebSocketDisconnect:
            pass
        finally:
            with self._ws_lock:
                self.active_websockets.discard(websocket)

    def _on_state_change(self, document: dict[str, Any], revision: int):
        """Called by SceneState subscriber whenever state changes."""
        if not self.is_running or not self._loop:
            return

        with self._ws_lock:
            ws_targets = list(self.active_websockets)
        if not ws_targets:
            return

        payload = json.dumps(
            {"type": "scene_updated", "scene": document, "revision": revision}
        )

        async def broadcast():
            for ws in ws_targets:
                try:
                    await ws.send_text(payload)
                except Exception:
                    with self._ws_lock:
                        self.active_websockets.discard(ws)

        try:
            asyncio.run_coroutine_threadsafe(broadcast(), self._loop)
        except Exception:
            pass

    def _cleanup_failed_start(self):
        """Safely cleans up partially initialized server, thread, and state."""
        if self._unsubscribe_state:
            try:
                self._unsubscribe_state()
            except Exception:
                pass
            self._unsubscribe_state = None

        if self.server:
            self.server.should_exit = True

        if self.thread:
            if self.thread.is_alive():
                self.thread.join(timeout=2.0)
            self.thread = None

        self.server = None
        self._loop = None
        self.is_running = False
        with self._ws_lock:
            self.active_websockets.clear()
        _unregister_active_server(self)

    def start(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        """Start the live canvas server in a background thread with deterministic readiness synchronization.

        Args:
            host: Host IP or hostname to bind to.
            port: Port to listen on (0 for dynamic allocation).
            timeout: Maximum seconds to wait for server socket binding and readiness.

        Returns:
            Dict containing status ('started' or 'already_running'), url, host, and port.

        Raises:
            SceneError: If startup fails (e.g. port already bound) or times out.
        """
        with self._start_lock:
            if self.is_running:
                return {
                    "status": "already_running",
                    "url": f"http://{self.host}:{self.port}",
                    "host": self.host,
                    "port": self.port,
                }

            if host is not None:
                self.host = host
            if port is not None:
                self.port = port

            app = self._create_app()
            config = uvicorn.Config(
                app=app,
                host=self.host,
                port=self.port,
                log_level="error",
            )
            ready_event = threading.Event()
            server = _LiveCanvasUvicornServer(config, ready_event=ready_event)
            self.server = server

            server_error: BaseException | None = None

            def run_server():
                nonlocal server_error
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                try:
                    loop.run_until_complete(server.serve())
                except BaseException as exc:
                    server_error = exc
                finally:
                    ready_event.set()
                    try:
                        loop.close()
                    except Exception:
                        pass

            self.thread = threading.Thread(
                target=run_server,
                daemon=True,
                name="ExcalidrawLiveCanvas",
            )
            self.thread.start()

            is_ready = ready_event.wait(timeout=timeout)
            effective_error = server.startup_error or server_error

            if not is_ready:
                self._cleanup_failed_start()
                raise SceneError(
                    f"Live canvas server startup timed out after {timeout:.1f}s on {self.host}:{self.port}"
                )

            if not server.started or effective_error is not None:
                self._cleanup_failed_start()
                err_detail = str(effective_error) if effective_error else "Unknown initialization failure"
                raise SceneError(
                    f"Failed to start live canvas server on {self.host}:{self.port}: {err_detail}"
                ) from effective_error

            # Retrieve actual port if dynamically assigned (port=0)
            if self.port == 0 and server.servers and server.servers[0].sockets:
                self.port = server.servers[0].sockets[0].getsockname()[1]

            self.is_running = True

            # Subscribe to scene mutations
            self._unsubscribe_state = self.service.state.subscribe(self._on_state_change)

            # Register in active servers registry for graceful process signal & atexit shutdown
            _register_active_server(self)

            return {
                "status": "started",
                "url": f"http://{self.host}:{self.port}",
                "host": self.host,
                "port": self.port,
            }

    def stop(self) -> dict[str, Any]:
        """Stop the background live canvas server."""
        with self._start_lock:
            was_running = self.is_running or (self.thread is not None and self.thread.is_alive())
            if not was_running and self.server is None:
                _unregister_active_server(self)
                return {"status": "not_running"}

            self._cleanup_failed_start()
            _unregister_active_server(self)
            return {"status": "stopped"}

    @classmethod
    def install_signal_handlers(cls) -> bool:
        """Class method to explicitly install process signal handlers from the main thread."""
        return install_signal_handlers()

    @classmethod
    def uninstall_signal_handlers(cls) -> None:
        """Class method to restore original process signal handlers."""
        uninstall_signal_handlers()

    def get_status(self) -> dict[str, Any]:
        """Get live canvas server status."""
        with self._ws_lock:
            client_count = len(self.active_websockets)
        return {
            "status": "running" if self.is_running else "stopped",
            "is_running": self.is_running,
            "url": f"http://{self.host}:{self.port}" if self.is_running else None,
            "host": self.host,
            "port": self.port,
            "active_clients": client_count,
        }
