"""Live canvas server providing real-time bidirectional synchronization between Python backend and browser UI."""

import asyncio
import json
import logging
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


class LiveCanvasServer:
    """Manages the background Uvicorn live canvas server."""

    def __init__(self, service: Any, host: str = "127.0.0.1", port: int = 8080):
        self.service = service
        self.host = host
        self.port = port
        self.app = self._create_app()
        self.server: uvicorn.Server | None = None
        self.thread: threading.Thread | None = None
        self.active_websockets: set[WebSocket] = set()
        self._ws_lock = threading.Lock()
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
        return HTMLResponse(HTML_PAGE)

    async def _handle_get_scene(self, request):
        doc, rev = self.service.state.snapshot()
        return JSONResponse({**doc, "revision": rev})

    async def _handle_post_scene(self, request):
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

    def start(self, host: str | None = None, port: int | None = None) -> dict[str, Any]:
        """Start the live canvas server in a background thread."""
        if self.is_running:
            return {
                "status": "already_running",
                "url": f"http://{self.host}:{self.port}",
                "host": self.host,
                "port": self.port,
            }

        if host:
            self.host = host
        if port:
            self.port = port

        app = self._create_app()
        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            log_level="error",
        )
        self.server = uvicorn.Server(config)

        # Event loop capture
        started_event = threading.Event()
        server_error = None

        def run_server():
            nonlocal server_error
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            started_event.set()
            try:
                loop.run_until_complete(self.server.serve())
            except BaseException as exc:
                server_error = exc
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

        self.thread = threading.Thread(target=run_server, daemon=True, name="ExcalidrawLiveCanvas")
        self.thread.start()
        started_event.wait(timeout=3.0)

        # Wait briefly for socket binding
        time.sleep(0.3)
        if not self.thread.is_alive():
            self.thread = None
            self.server = None
            self._loop = None
            err_msg = str(server_error) if server_error else f"Could not bind to port {self.port}"
            return {
                "status": "failed",
                "error": err_msg,
                "host": self.host,
                "port": self.port,
            }

        self.is_running = True

        # Subscribe to scene mutations
        self._unsubscribe_state = self.service.state.subscribe(self._on_state_change)

        return {
            "status": "started",
            "url": f"http://{self.host}:{self.port}",
            "host": self.host,
            "port": self.port,
        }

    def stop(self) -> dict[str, Any]:
        """Stop the background live canvas server."""
        was_running = self.is_running or (self.thread is not None and self.thread.is_alive())
        if not was_running and self.server is None:
            return {"status": "not_running"}

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

        self.is_running = False
        self.server = None
        self._loop = None
        with self._ws_lock:
            self.active_websockets.clear()

        return {"status": "stopped"}

    def get_status(self) -> dict[str, Any]:
        """Get live canvas server status."""
        with self._ws_lock:
            client_count = len(self.active_websockets)
        return {
            "is_running": self.is_running,
            "url": f"http://{self.host}:{self.port}" if self.is_running else None,
            "host": self.host,
            "port": self.port,
            "active_clients": client_count,
        }
