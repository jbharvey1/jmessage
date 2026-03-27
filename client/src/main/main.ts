import { app, BrowserWindow } from "electron";
import * as path from "path";
import * as fs from "fs";
import * as http from "http";
import WebSocket, { WebSocketServer } from "ws";

let mainWindow: BrowserWindow | null = null;

// --- Load config ---
const configPath = path.join(__dirname, "../../config.json");
const config = JSON.parse(fs.readFileSync(configPath, "utf-8"));
const WS_URL: string = config.relay_url;
const AUTH_TOKEN: string = config.auth_token;

// --- mTLS certs ---
const certsDir = path.join(__dirname, "../../certs");
const tlsOptions: Record<string, any> = { rejectUnauthorized: false };

if (fs.existsSync(path.join(certsDir, "client.pem"))) {
  tlsOptions.cert = fs.readFileSync(path.join(certsDir, "client.pem"));
  tlsOptions.key = fs.readFileSync(path.join(certsDir, "client.key"));
  tlsOptions.ca = fs.readFileSync(path.join(certsDir, "ca.pem"));
}

// --- Local WS proxy: renderer connects here, we forward to Mac with mTLS ---
const LOCAL_PORT = 18765;
let remoteWs: WebSocket | null = null;
let localClients: Set<WebSocket> = new Set();

function connectRemote() {
  remoteWs = new WebSocket(WS_URL, { ...tlsOptions });

  remoteWs.on("open", () => {
    // Auth immediately
    remoteWs!.send(JSON.stringify({ type: "auth", token: AUTH_TOKEN }));
  });

  remoteWs.on("message", (data: Buffer) => {
    const msg = data.toString();
    for (const client of localClients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(msg);
      }
    }
  });

  remoteWs.on("close", () => {
    setTimeout(connectRemote, 3000);
  });

  remoteWs.on("error", () => {
    remoteWs?.close();
  });
}

const localServer = http.createServer();
const wss = new WebSocketServer({ server: localServer });

wss.on("connection", (client) => {
  localClients.add(client);

  client.on("message", (data) => {
    // Forward to remote relay
    if (remoteWs && remoteWs.readyState === WebSocket.OPEN) {
      remoteWs.send(data.toString());
    }
  });

  client.on("close", () => {
    localClients.delete(client);
  });

  // If remote is already connected and authed, request conversations for new client
  if (remoteWs && remoteWs.readyState === WebSocket.OPEN) {
    remoteWs.send(JSON.stringify({ type: "get_conversations" }));
  }
});

// --- Window ---
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 700,
    minWidth: 600,
    minHeight: 400,
    title: "JMessage",
    backgroundColor: "#1C1C1E",
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

app.on("certificate-error", (event, _wc, _url, _err, _cert, cb) => {
  event.preventDefault();
  cb(true);
});

app.whenReady().then(() => {
  // Start local proxy
  localServer.listen(LOCAL_PORT, "127.0.0.1", () => {
    // Connect to remote relay with mTLS
    connectRemote();
    // Create window — renderer connects to ws://127.0.0.1:LOCAL_PORT
    createWindow();
  });
});

app.on("window-all-closed", () => {
  remoteWs?.close();
  localServer.close();
  app.quit();
});
