const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electron", {
  notifyScreenshot: () => ipcRenderer.send("screenshot-uploaded"),
});
