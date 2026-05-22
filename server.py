"""
Файлообменник: загрузка/скачивание + cloudflared (trycloudflare.com).
  pip install -r requirements.txt
  python server.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT / "uploads"
PUBLIC_DIR = ROOT / "public"
PORT = int(os.environ.get("PORT", "3847"))
API_VERSION = "1.0"

app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = None
app.config["MAX_FORM_MEMORY_SIZE"] = None


@app.after_request
def cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Filename, X-Api-Key"
    return response


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def api_options(_any: str):
    return "", 204


def ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def safe_name(name: str) -> str:
    base = Path(name).name
    for ch in '<>:"|?*\\':
        base = base.replace(ch, "_")
    return base


def public_base_url() -> str:
    override = request.headers.get("X-Base-Url") or request.args.get("base")
    if override:
        return override.rstrip("/")
    return request.host_url.rstrip("/")


def file_entry(path: Path) -> dict:
    stat = path.stat()
    name = path.name
    return {
        "name": name,
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "downloadUrl": f"{public_base_url()}/download/{name}",
        "apiDownloadUrl": f"{public_base_url()}/api/download/{name}",
    }


def list_files() -> list[dict]:
    items = [file_entry(path) for path in UPLOAD_DIR.iterdir() if path.is_file()]
    return sorted(items, key=lambda x: x["mtime"], reverse=True)


def save_uploaded_file(original: str, data: bytes) -> dict:
    original = safe_name(original or "file.bin")
    dest_name = f"{int(time.time() * 1000)}-{original}"
    dest = UPLOAD_DIR / dest_name
    dest.write_bytes(data)
    entry = file_entry(dest)
    return {
        "name": dest_name,
        "originalName": original,
        "size": entry["size"],
        "url": f"/download/{dest_name}",
        "downloadUrl": entry["downloadUrl"],
    }


@app.get("/")
def index():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.get("/api")
@app.get("/api/info")
def api_info():
    base = public_base_url()
    return jsonify(
        version=API_VERSION,
        baseUrl=base,
        endpoints={
            "health": f"{base}/api/health",
            "list": f"{base}/api/files",
            "uploadMultipart": f"{base}/api/upload",
            "uploadBinary": f"{base}/api/upload/binary",
            "download": f"{base}/api/download/{{name}}",
            "delete": f"{base}/api/files/{{name}}",
        },
        uploadFields=["files", "file"],
        uploadHeaders={"binary": ["Content-Type: application/octet-stream", "X-Filename: name.ext"]},
    )


@app.get("/api/health")
def api_health():
    return jsonify(ok=True, version=API_VERSION, uploads=str(UPLOAD_DIR))


@app.get("/api/files")
def api_files():
    return jsonify(ok=True, count=len(list_files()), files=list_files())


def _collect_multipart_uploads() -> list[dict]:
    saved: list[dict] = []
    if not request.files:
        return saved
    for key in request.files:
        for storage in request.files.getlist(key):
            if not storage:
                continue
            original = storage.filename or "file.bin"
            saved.append(save_uploaded_file(original, storage.read()))
    return saved


@app.post("/api/upload")
@app.post("/api/upload/multipart")
def api_upload():
    saved = _collect_multipart_uploads()
    if not saved:
        return jsonify(
            ok=False,
            error="No files. Use multipart field 'files' or 'file'.",
        ), 400
    return jsonify(ok=True, files=saved)


@app.put("/api/upload/binary")
@app.post("/api/upload/binary")
def api_upload_binary():
    """Сырой body + заголовок X-Filename (удобно для HttpClient из C#)."""
    raw = request.get_data()
    if not raw:
        return jsonify(ok=False, error="Empty body"), 400
    filename = request.headers.get("X-Filename") or request.args.get("name") or "file.bin"
    saved = save_uploaded_file(filename, raw)
    return jsonify(ok=True, files=[saved])


@app.get("/api/download/<path:name>")
@app.get("/download/<path:name>")
def download(name: str):
    # Flask уже декодирует %XX в path
    safe = safe_name(name)
    full = UPLOAD_DIR / safe
    if not full.is_file():
        return jsonify(ok=False, error="File not found", name=safe), 404
    return send_from_directory(
        UPLOAD_DIR,
        safe,
        as_attachment=True,
        download_name=safe.split("-", 1)[-1] if "-" in safe else safe,
    )


@app.delete("/api/files/<path:name>")
def delete_file(name: str):
    safe = safe_name(name)
    full = UPLOAD_DIR / safe
    if not full.is_file():
        return jsonify(error="Not found"), 404
    full.unlink()
    return jsonify(ok=True, deleted=safe)


def _watch_tunnel_output(proc: subprocess.Popen[str], label: str) -> None:
    assert proc.stdout is not None

    def reader() -> None:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            print(f"[{label}] {line}")
            if "trycloudflare.com" in line or "loca.lt" in line:
                for token in line.replace("|", " ").replace("(", " ").replace(")", " ").split():
                    if token.startswith("https://"):
                        print("\n=== Public URL (cloudflared) ===")
                        print(token)
                        print("Upload page:", token + "/\n")
                        break

    threading.Thread(target=reader, daemon=True).start()


def _resolve_cloudflared() -> str | None:
    found = shutil.which("cloudflared")
    if found and Path(found).is_file():
        return found
    if sys.platform != "win32":
        return None
    candidates: list[Path] = []
    for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(key)
        if not base:
            continue
        root = Path(base)
        candidates.extend(
            [
                root / "cloudflared" / "cloudflared.exe",
                root / "Cloudflare" / "cloudflared" / "cloudflared.exe",
                root / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe",
            ]
        )
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _spawn_tunnel(cmd: list[str], label: str) -> bool:
    try:
        if sys.platform == "win32" and cmd and str(cmd[0]).lower().endswith((".cmd", ".bat")):
            cmd = ["cmd.exe", "/c", *cmd]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (FileNotFoundError, OSError) as ex:
        print(f"[{label}] start failed: {ex}")
        return False
    _watch_tunnel_output(proc, label)
    return True


def start_public_tunnel(port: int) -> None:
    local_url = f"http://127.0.0.1:{port}"
    cloudflared = _resolve_cloudflared()
    if cloudflared:
        print(f"[cloudflared] Using: {cloudflared}")
        if _spawn_tunnel(
            [
                cloudflared,
                "tunnel",
                "--url",
                local_url,
                "--no-autoupdate",
                "--protocol",
                "http2",
            ],
            "cloudflared",
        ):
            return

    print("\n[WARN] Public tunnel not started — cloudflared not found.")
    print(f"  Local:  {local_url}/")
    print("  Install:  winget install Cloudflare.cloudflared")
    print(f"  Manual:   cloudflared tunnel --url {local_url} --protocol http2\n")


def main() -> None:
    ensure_dirs()
    if not (PUBLIC_DIR / "index.html").is_file():
        print("[ERROR] public/index.html missing")
        sys.exit(1)
    print(f"Local: http://127.0.0.1:{PORT}/")
    print(f"Uploads: {UPLOAD_DIR}")
    print("Tunnel: cloudflared (trycloudflare.com)")
    threading.Thread(target=start_public_tunnel, args=(PORT,), daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, threaded=True, debug=False)


if __name__ == "__main__":
    main()
