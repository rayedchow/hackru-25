const { createServer } = require("http");
const { parse } = require("url");
const next = require("next");
const { WebSocketServer } = require("ws");

const dev = process.env.NODE_ENV !== "production";
const hostname = process.env.SYNAPSE_WEB_BIND_HOST || "127.0.0.1";
const port = 3000;
const allowedOrigins = new Set(
  (process.env.SYNAPSE_WEB_ALLOWED_ORIGINS || "http://127.0.0.1:3000,http://localhost:3000")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean),
);

// Create Next.js app
const app = next({ dev, hostname, port });
const handle = app.getRequestHandler();

// Store WebSocket clients
let wss;

// Broadcast to all WebSocket clients
function broadcastScreenshotUpdate() {
  if (!wss) return;
  
  const message = JSON.stringify({
    type: "screenshot_update",
    timestamp: Date.now(),
  });

  wss.clients.forEach((client) => {
    if (client.readyState === 1) { // WebSocket.OPEN
      client.send(message);
    }
  });
}

// Export for use in API routes
global.broadcastScreenshotUpdate = broadcastScreenshotUpdate;

app.prepare().then(() => {
  const server = createServer(async (req, res) => {
    try {
      const parsedUrl = parse(req.url, true);
      await handle(req, res, parsedUrl);
    } catch (err) {
      console.error("Error occurred handling", req.url, err);
      res.statusCode = 500;
      res.end("internal server error");
    }
  });

  // Create WebSocket server
  wss = new WebSocketServer({ noServer: true });

  wss.on("connection", (ws) => {
    console.log("WebSocket client connected");

    ws.on("close", () => {
      console.log("WebSocket client disconnected");
    });

    ws.on("error", (error) => {
      console.error("WebSocket error:", error);
    });
  });

  // Handle WebSocket upgrade
  server.on("upgrade", (request, socket, head) => {
    const { pathname } = parse(request.url);
    const origin = request.headers.origin;

    if (pathname === "/ws/screenshot" && origin && allowedOrigins.has(origin)) {
      wss.handleUpgrade(request, socket, head, (ws) => {
        wss.emit("connection", ws, request);
      });
    } else {
      socket.destroy();
    }
  });

  server.listen(port, hostname, (err) => {
    if (err) throw err;
    console.log(`> Ready on http://${hostname}:${port}`);
    console.log(`> WebSocket server ready on ws://${hostname}:${port}/ws/screenshot`);
  });
});
