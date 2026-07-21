const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hagokuDesktop", {
  minimize: () => ipcRenderer.send("win:minimize"),
  maximize: () => ipcRenderer.send("win:maximize"),
  close: () => ipcRenderer.send("win:close"),
  isMaximized: () => ipcRenderer.invoke("win:isMaximized"),
  onStateChanged: (cb) => ipcRenderer.on("win:stateChanged", (_, m) => cb(m)),
  printUrl: (url) => ipcRenderer.invoke("print:url", url),
});
