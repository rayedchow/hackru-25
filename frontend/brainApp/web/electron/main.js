const { app, BrowserWindow, ipcMain } = require("electron");
const isDev = require("electron-is-dev");
const path = require("path");
const { spawn } = require("child_process");
const waitOn = require("wait-on");

let mainWindow;
let nextServer;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
    show: false, // Don't show initially
    backgroundColor: "#ffffff",
  });

  // Load Next.js app
  const url = isDev
    ? "http://localhost:3000/chat"
    : `file://${path.join(__dirname, "../out/index.html")}`;

  mainWindow.loadURL(url);

  // Don't show window automatically - wait for screenshot
  mainWindow.once("ready-to-show", () => {
    console.log("Electron window ready (hidden in background)");
    // Window stays hidden until screenshot is taken
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

async function startNextServer() {
  return new Promise((resolve, reject) => {
    console.log("Starting Next.js dev server with WebSocket support...");

    nextServer = spawn("node", ["server.js"], {
      cwd: path.join(__dirname, ".."),
      shell: true,
      stdio: "inherit",
      env: { ...process.env, NODE_ENV: "development" },
    });

    nextServer.on("error", (err) => {
      console.error("Failed to start Next.js server:", err);
      reject(err);
    });

    // Wait for Next.js to be ready
    waitOn({
      resources: ["http://localhost:3000"],
      timeout: 30000,
      interval: 1000,
    })
      .then(() => {
        console.log("Next.js server with WebSocket is ready!");
        resolve();
      })
      .catch((err) => {
        console.error("Next.js server failed to start:", err);
        reject(err);
      });
  });
}

// IPC handlers
ipcMain.on("screenshot-uploaded", () => {
  console.log("Screenshot uploaded, showing window...");
  if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
  } else {
    // If window was closed, recreate it
    createWindow();
    mainWindow.once("ready-to-show", () => {
      mainWindow.show();
      mainWindow.focus();
    });
  }
});

// App lifecycle
app.whenReady().then(async () => {
  if (isDev) {
    await startNextServer();
  }

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("before-quit", () => {
  app.isQuitting = true;
  if (nextServer) {
    nextServer.kill();
  }
});

app.on("window-all-closed", () => {
  // Keep app running in background even when window is closed
  // This allows the window to reopen when a new screenshot arrives
  console.log("Window closed, app remains in background");
});

// API to show window (called from Python via HTTP)
const express = require("express");
const expressApp = express();

expressApp.use(express.json());
expressApp.use((req, res, next) => {
  const origin = req.get("origin");
  if (origin && origin !== "http://127.0.0.1:3000" && origin !== "http://localhost:3000") {
    res.status(403).json({ success: false, error: "untrusted_origin" });
    return;
  }
  next();
});

expressApp.post("/electron/show", (req, res) => {
  console.log("Received request to show window");
  if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
  } else {
    // If window was closed, recreate it
    createWindow();
    mainWindow.once("ready-to-show", () => {
      mainWindow.show();
      mainWindow.focus();
    });
  }
  res.json({ success: true });
});

expressApp.listen(3001, "127.0.0.1", () => {
  console.log("Electron control server listening on 127.0.0.1:3001");
});
