const { app, BrowserWindow, ipcMain, Menu, globalShortcut } = require("electron");
const path = require("path");
const fs = require("fs");

const DEV_SERVER = `http://localhost:5173`;
const CONFIG_PATH = path.join(app.getPath("userData"), "window-state.json");

function loadWindowState() {
  try { if (fs.existsSync(CONFIG_PATH)) return JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8")); }
  catch {}
  return { width: 1400, height: 900, maximized: true };
}
function saveWindowState(win) {
  const m = win.isMaximized();
  const b = m ? win.getNormalBounds() : win.getBounds();
  fs.writeFileSync(CONFIG_PATH, JSON.stringify({ width: b.width, height: b.height, x: b.x, y: b.y, maximized: m }));
}

let mainWindow;

async function createWindow() {
  const st = loadWindowState();
  mainWindow = new BrowserWindow({
    width: st.width, height: st.height,
    minWidth: 800, minHeight: 500,
    frame: false,
    titleBarStyle: "hidden",
    backgroundColor: "#0B0E14",
    webPreferences: { nodeIntegration: false, contextIsolation: true, preload: path.join(__dirname, "preload.js") },
  });
  if (st.maximized) mainWindow.maximize();

  try { await mainWindow.loadURL(DEV_SERVER); }
  catch { mainWindow.loadFile(path.join(__dirname, "..", "hagoku_web", "dist", "index.html")); }
  mainWindow.webContents.focus();

  ["resize","move","maximize","unmaximize"].forEach(e => mainWindow.on(e, () => saveWindowState(mainWindow)));
  mainWindow.on("maximize", () => mainWindow?.webContents.send("win:stateChanged", true));
  mainWindow.on("unmaximize", () => mainWindow?.webContents.send("win:stateChanged", false));

  // 快捷键
  mainWindow.webContents.on("before-input-event", (_, input) => {
    const ctrl = input.control || input.meta;
    if (ctrl && (input.key === "=" || input.key === "+" || input.code === "Equal" || input.code === "NumpadAdd")) {
      mainWindow.webContents.setZoomLevel(mainWindow.webContents.getZoomLevel() + 0.5);
    }
    if (ctrl && (input.key === "-" || input.code === "Minus" || input.code === "NumpadSubtract")) {
      mainWindow.webContents.setZoomLevel(mainWindow.webContents.getZoomLevel() - 0.5);
    }
    if (ctrl && input.key === "0") {
      mainWindow.webContents.setZoomLevel(0);
    }
    if (input.key === "F11") { mainWindow.setFullScreen(!mainWindow.isFullScreen()); }
    if (ctrl && input.shift && input.key === "I") { mainWindow.webContents.toggleDevTools(); }
  });
}

// ── IPC：窗口控制 ──
ipcMain.on("win:minimize", () => mainWindow?.minimize());
ipcMain.on("win:maximize", () => { mainWindow?.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize(); });
ipcMain.on("win:close", () => mainWindow?.close());
ipcMain.handle("win:isMaximized", () => mainWindow?.isMaximized() ?? false);
ipcMain.handle("print:url", async (_, url) => {
  const fullUrl = url.startsWith("http") ? url : `http://localhost:8000${url}`;
  const pw = new BrowserWindow({ show: false, webPreferences: { nodeIntegration: false, contextIsolation: true } });
  await pw.loadURL(fullUrl);
  const data = await pw.webContents.printToPDF({ printBackground: true, preferCSSPageSize: true });
  const { writeFileSync } = require("fs");
  const tmpPath = require("path").join(require("os").tmpdir(), `hagoku_report_${Date.now()}.pdf`);
  writeFileSync(tmpPath, data);
  pw.close();
  require("electron").shell.openPath(tmpPath);
});

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  createWindow();
});
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
