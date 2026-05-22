const express = require("express");
const fs = require("fs");
const path = require("path");
const multer = require("multer");
const { spawn } = require("child_process");

const PORT = Number(process.env.PORT) || 3847;
const UPLOAD_DIR = path.join(__dirname, "uploads");
const PUBLIC_DIR = path.join(__dirname, "public");

fs.mkdirSync(UPLOAD_DIR, { recursive: true });

/** Практически без лимита (≈1 ТБ на файл). */
const MAX_FILE_BYTES = 1024 * 1024 * 1024 * 1024;

const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, UPLOAD_DIR),
  filename: (_req, file, cb) => {
    const safe = path.basename(file.originalname || "file.bin").replace(/[<>:"|?*\\]/g, "_");
    cb(null, `${Date.now()}-${safe}`);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: MAX_FILE_BYTES, files: 50 },
});

const app = express();
app.use(express.json({ limit: "1mb" }));
app.use((req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, X-Filename, X-Base-Url");
  if (req.method === "OPTIONS") return res.sendStatus(204);
  next();
});
app.use(express.static(PUBLIC_DIR));

function publicBaseUrl(req) {
  const override = req.get("X-Base-Url") || req.query.base;
  if (override) return String(override).replace(/\/$/, "");
  return `${req.protocol}://${req.get("host")}`;
}

function fileEntry(req, name, stat) {
  const base = publicBaseUrl(req);
  return {
    name,
    size: stat.size,
    mtime: stat.mtime.toISOString(),
    downloadUrl: `${base}/download/${encodeURIComponent(name)}`,
    apiDownloadUrl: `${base}/api/download/${encodeURIComponent(name)}`,
  };
}

function listStoredFiles(req) {
  if (!fs.existsSync(UPLOAD_DIR)) {
    return [];
  }
  return fs
    .readdirSync(UPLOAD_DIR, { withFileTypes: true })
    .filter((e) => e.isFile())
    .map((e) => {
      const full = path.join(UPLOAD_DIR, e.name);
      const stat = fs.statSync(full);
      return fileEntry(req, e.name, stat);
    })
    .sort((a, b) => b.mtime.localeCompare(a.mtime));
}

app.get(["/api", "/api/info"], (req, res) => {
  const base = publicBaseUrl(req);
  res.json({
    version: "1.0",
    baseUrl: base,
    endpoints: {
      uploadMultipart: `${base}/api/upload`,
      uploadBinary: `${base}/api/upload/binary`,
      list: `${base}/api/files`,
      download: `${base}/api/download/{name}`,
    },
    uploadFields: ["files", "file"],
  });
});

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, version: "1.0" });
});

app.get("/api/files", (req, res) => {
  const files = listStoredFiles(req);
  res.json({ ok: true, count: files.length, files });
});

const uploadAny = upload.fields([
  { name: "files", maxCount: 50 },
  { name: "file", maxCount: 50 },
]);

app.post(["/api/upload", "/api/upload/multipart"], uploadAny, (req, res) => {
  const list = [...(req.files?.files || []), ...(req.files?.file || [])];
  const base = publicBaseUrl(req);
  const saved = list.map((f) => ({
    name: f.filename,
    originalName: f.originalname,
    size: f.size,
    url: `/download/${encodeURIComponent(f.filename)}`,
    downloadUrl: `${base}/download/${encodeURIComponent(f.filename)}`,
  }));
  if (!saved.length) {
    return res.status(400).json({ ok: false, error: "Use multipart field 'files' or 'file'." });
  }
  res.json({ ok: true, files: saved });
});

app.put("/api/upload/binary", express.raw({ limit: "1024gb", type: "*/*" }), (req, res) => {
  if (!req.body || !req.body.length) {
    return res.status(400).json({ ok: false, error: "Empty body" });
  }
  const original = path.basename(req.get("X-Filename") || req.query.name || "file.bin").replace(/[<>:"|?*\\]/g, "_");
  const destName = `${Date.now()}-${original}`;
  const full = path.join(UPLOAD_DIR, destName);
  fs.writeFileSync(full, req.body);
  const stat = fs.statSync(full);
  const base = publicBaseUrl(req);
  res.json({
    ok: true,
    files: [
      {
        name: destName,
        originalName: original,
        size: stat.size,
        url: `/download/${encodeURIComponent(destName)}`,
        downloadUrl: `${base}/download/${encodeURIComponent(destName)}`,
      },
    ],
  });
});

app.get(["/api/download/:name", "/download/:name"], (req, res) => {
  const name = path.basename(req.params.name);
  const full = path.join(UPLOAD_DIR, name);
  if (!fs.existsSync(full) || !fs.statSync(full).isFile()) {
    return res.status(404).send("File not found");
  }
  res.download(full, name);
});

app.delete("/api/files/:name", (req, res) => {
  const name = path.basename(req.params.name);
  const full = path.join(UPLOAD_DIR, name);
  if (!fs.existsSync(full)) {
    return res.status(404).json({ error: "Not found" });
  }
  fs.unlinkSync(full);
  res.json({ ok: true, deleted: name });
});

app.use((err, _req, res, _next) => {
  console.error(err);
  if (err && err.code === "LIMIT_FILE_SIZE") {
    return res.status(413).json({ error: "File too large for server limit" });
  }
  res.status(500).json({ error: err?.message || "Server error" });
});

function startCloudflared(port) {
  const localUrl = `http://127.0.0.1:${port}`;
  const bin = process.platform === "win32" ? "cloudflared.exe" : "cloudflared";
  const proc = spawn(bin, ["tunnel", "--url", localUrl, "--no-autoupdate", "--protocol", "http2"], {
    stdio: ["ignore", "pipe", "pipe"],
    shell: process.platform === "win32",
  });
  const onLine = (chunk) => {
    const text = chunk.toString();
    process.stdout.write(`[cloudflared] ${text}`);
    const match = text.match(/https:\/\/[^\s]+trycloudflare\.com[^\s]*/);
    if (match) {
      const url = match[0].replace(/[^\w:/.-]+$/, "");
      console.log("\n=== Public URL (cloudflared) ===");
      console.log(url);
      console.log("Upload page:", `${url}/\n`);
    }
  };
  proc.stdout.on("data", onLine);
  proc.stderr.on("data", onLine);
  proc.on("error", (err) => {
    console.error("[cloudflared] failed:", err.message);
    console.error("Install: winget install Cloudflare.cloudflared");
  });
}

app.listen(PORT, "0.0.0.0", () => {
  console.log(`Local server: http://127.0.0.1:${PORT}/`);
  console.log(`Upload folder: ${UPLOAD_DIR}`);
  startCloudflared(PORT);
});
