#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hmac
import html
import io
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
UPLOAD_DIR = ROOT / "uploads"
PARTS_DIR = ROOT / ".incomplete"
TOKEN_FILE = ROOT / ".access-token"

CHUNK_LIMIT = 32 * 1024 * 1024
JSON_LIMIT = 64 * 1024
COPY_BUFFER = 1024 * 1024
UPLOAD_ID_RE = re.compile(r"^[a-f0-9]{32}$")
WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class ApiError(Exception):
    def __init__(self, status: int, message: str, **details: Any) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details


class OffsetConflict(ApiError):
    def __init__(self, expected_offset: int) -> None:
        super().__init__(
            HTTPStatus.CONFLICT,
            "上传位置不一致",
            code="offset_mismatch",
            expectedOffset=expected_offset,
        )


def load_token() -> str:
    try:
        token = TOKEN_FILE.read_text(encoding="ascii").strip()
        if 20 <= len(token) <= 100:
            return token
    except (FileNotFoundError, OSError, UnicodeError):
        pass

    token = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(token, encoding="ascii")
    return token


def primary_lan_ip() -> str:
    candidates: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            candidates.append(sock.getsockname()[0])
    except OSError:
        pass

    try:
        candidates.extend(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass

    usable: list[ipaddress.IPv4Address] = []
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if (
            isinstance(address, ipaddress.IPv4Address)
            and not address.is_loopback
            and not address.is_link_local
        ):
            usable.append(address)

    def priority(address: ipaddress.IPv4Address) -> int:
        if address in ipaddress.ip_network("192.168.0.0/16"):
            return 0
        if address in ipaddress.ip_network("10.0.0.0/8"):
            return 1
        if address in ipaddress.ip_network("172.16.0.0/12"):
            return 2
        return 3

    if usable:
        return str(min(usable, key=priority))

    return "127.0.0.1"


def safe_filename(raw_name: str) -> str:
    name = (raw_name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(
        character
        for character in name
        if ord(character) >= 32 and character not in '<>:"/\\|?*'
    )
    name = name.strip(" .")
    if not name:
        name = "quest-video.mp4"

    path = Path(name)
    suffix = path.suffix[:20]
    stem = path.stem.strip(" .") or "quest-video"
    if stem.upper() in WINDOWS_RESERVED:
        stem = f"_{stem}"
    if len(stem) > 120:
        stem = stem[:120].rstrip(" .")
    return f"{stem}{suffix}"


@dataclass
class UploadItem:
    upload_id: str
    filename: str
    size: int
    last_modified: int
    created_at: float
    lock: threading.Lock = field(default_factory=threading.Lock)


class UploadStore:
    def __init__(self, upload_dir: Path, parts_dir: Path) -> None:
        self.upload_dir = upload_dir
        self.parts_dir = parts_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.parts_dir.mkdir(parents=True, exist_ok=True)
        self._items: dict[str, UploadItem] = {}
        self._lock = threading.Lock()
        self.cleanup_stale()

    def _part_path(self, upload_id: str) -> Path:
        return self.parts_dir / f"{upload_id}.part"

    def _meta_path(self, upload_id: str) -> Path:
        return self.parts_dir / f"{upload_id}.json"

    def _write_meta(self, item: UploadItem) -> None:
        payload = {
            "uploadId": item.upload_id,
            "filename": item.filename,
            "size": item.size,
            "lastModified": item.last_modified,
            "createdAt": item.created_at,
            "updatedAt": time.time(),
        }
        temporary = self._meta_path(item.upload_id).with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self._meta_path(item.upload_id))

    def _load(self, upload_id: str) -> UploadItem:
        if not UPLOAD_ID_RE.fullmatch(upload_id):
            raise ApiError(HTTPStatus.NOT_FOUND, "上传任务不存在")

        with self._lock:
            existing = self._items.get(upload_id)
            if existing is not None:
                return existing

            meta_path = self._meta_path(upload_id)
            part_path = self._part_path(upload_id)
            if not meta_path.is_file() or not part_path.is_file():
                raise ApiError(HTTPStatus.NOT_FOUND, "上传任务不存在")

            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
                item = UploadItem(
                    upload_id=upload_id,
                    filename=safe_filename(str(payload["filename"])),
                    size=int(payload["size"]),
                    last_modified=int(payload.get("lastModified", 0)),
                    created_at=float(payload.get("createdAt", time.time())),
                )
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                raise ApiError(HTTPStatus.NOT_FOUND, "上传任务已失效") from None

            self._items[upload_id] = item
            return item

    def create(self, raw_name: str, size: int, last_modified: int) -> UploadItem:
        if size <= 0:
            raise ApiError(HTTPStatus.BAD_REQUEST, "文件内容为空")

        upload_id = uuid.uuid4().hex
        item = UploadItem(
            upload_id=upload_id,
            filename=safe_filename(raw_name),
            size=size,
            last_modified=max(0, last_modified),
            created_at=time.time(),
        )

        with self._lock:
            self._part_path(upload_id).touch(exist_ok=False)
            self._write_meta(item)
            self._items[upload_id] = item
        return item

    def status(self, upload_id: str) -> UploadItem:
        item = self._load(upload_id)
        with item.lock:
            part_path = self._part_path(upload_id)
            if not part_path.is_file():
                raise ApiError(HTTPStatus.NOT_FOUND, "上传任务不存在")
            return item

    def offset(self, item: UploadItem) -> int:
        try:
            return self._part_path(item.upload_id).stat().st_size
        except OSError:
            raise ApiError(HTTPStatus.NOT_FOUND, "上传任务不存在") from None

    def write_chunk(
        self,
        upload_id: str,
        offset: int,
        length: int,
        stream: Any,
    ) -> int:
        item = self._load(upload_id)
        if offset < 0 or length <= 0:
            raise ApiError(HTTPStatus.BAD_REQUEST, "分片参数无效")
        if offset + length > item.size:
            raise ApiError(HTTPStatus.BAD_REQUEST, "分片超出文件大小")

        with item.lock:
            part_path = self._part_path(upload_id)
            if not part_path.is_file():
                raise ApiError(HTTPStatus.NOT_FOUND, "上传任务不存在")

            current = part_path.stat().st_size
            if offset > current:
                raise OffsetConflict(current)

            overlap = current - offset
            if overlap >= length:
                self._discard(stream, length)
                return current

            if overlap:
                self._discard(stream, overlap)

            remaining = length - overlap
            written = current
            with part_path.open("r+b") as output:
                output.seek(current)
                while remaining:
                    block = stream.read(min(COPY_BUFFER, remaining))
                    if not block:
                        break
                    output.write(block)
                    written += len(block)
                    remaining -= len(block)
                output.flush()
                os.fsync(output.fileno())

            if remaining:
                raise ApiError(
                    HTTPStatus.BAD_REQUEST,
                    "分片未完整送达",
                    code="incomplete_chunk",
                    expectedOffset=written,
                )

            self._write_meta(item)
            return written

    @staticmethod
    def _discard(stream: Any, length: int) -> None:
        remaining = length
        while remaining:
            block = stream.read(min(COPY_BUFFER, remaining))
            if not block:
                raise ApiError(HTTPStatus.BAD_REQUEST, "请求内容不完整")
            remaining -= len(block)

    def complete(self, upload_id: str) -> dict[str, Any]:
        item = self._load(upload_id)
        with item.lock:
            part_path = self._part_path(upload_id)
            if not part_path.is_file():
                raise ApiError(HTTPStatus.NOT_FOUND, "上传任务不存在")

            actual_size = part_path.stat().st_size
            if actual_size != item.size:
                raise ApiError(
                    HTTPStatus.CONFLICT,
                    "文件尚未传完",
                    code="incomplete_upload",
                    expectedOffset=actual_size,
                )

            with self._lock:
                destination = self._unique_destination(item.filename)
                os.replace(part_path, destination)
                self._meta_path(upload_id).unlink(missing_ok=True)
                self._items.pop(upload_id, None)

            stat = destination.stat()
            return {
                "name": destination.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }

    def abort(self, upload_id: str) -> None:
        item = self._load(upload_id)
        with item.lock:
            self._part_path(upload_id).unlink(missing_ok=True)
            self._meta_path(upload_id).unlink(missing_ok=True)
            with self._lock:
                self._items.pop(upload_id, None)

    def _unique_destination(self, filename: str) -> Path:
        candidate = self.upload_dir / filename
        if not candidate.exists():
            return candidate

        path = Path(filename)
        stem, suffix = path.stem, path.suffix
        index = 1
        while True:
            candidate = self.upload_dir / f"{stem} ({index}){suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    def cleanup_stale(self, days: int = 14) -> None:
        cutoff = time.time() - days * 24 * 60 * 60
        for meta_path in self.parts_dir.glob("*.json"):
            try:
                if meta_path.stat().st_mtime >= cutoff:
                    continue
                upload_id = meta_path.stem
                meta_path.unlink(missing_ok=True)
                self._part_path(upload_id).unlink(missing_ok=True)
            except OSError:
                continue

    def list_files(self) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        with os.scandir(self.upload_dir) as entries:
            for entry in entries:
                if not entry.is_file() or entry.name.startswith("."):
                    continue
                try:
                    stat = entry.stat()
                except OSError:
                    continue
                files.append(
                    {
                        "name": entry.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "url": f"/media/{quote(entry.name)}",
                        "downloadUrl": f"/media/{quote(entry.name)}?download=1",
                    }
                )
        files.sort(key=lambda item: item["modified"], reverse=True)
        return files


@dataclass
class AppContext:
    store: UploadStore
    token: str
    port: int

    @property
    def display_url(self) -> str:
        return f"http://{primary_lan_ip()}:{self.port}"

    @property
    def entry_url(self) -> str:
        return f"{self.display_url}/?k={quote(self.token)}"


class TransferServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        context: AppContext,
    ) -> None:
        super().__init__(server_address, TransferHandler)
        self.app = context

    def handle_error(self, request: Any, client_address: Any) -> None:
        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


class TransferHandler(BaseHTTPRequestHandler):
    server: TransferServer
    protocol_version = "HTTP/1.1"
    server_version = "QuestTransfer/1.0"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.path.startswith("/api/upload") or self.path.startswith("/api/open-folder"):
            print(f"[{self.log_date_time_string()}] {self.client_address[0]} {fmt % args}")

    def do_HEAD(self) -> None:
        self._handle(head_only=True)

    def do_GET(self) -> None:
        self._handle(head_only=False)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        parts = self._path_parts(parsed.path)

        if not self._is_authorized(parsed):
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "访问链接无效"})
            return

        try:
            if parts == ["api", "upload"]:
                self._create_upload()
                return

            if len(parts) == 4 and parts[:2] == ["api", "upload"]:
                upload_id, action = parts[2], parts[3]
                if action == "chunk":
                    self._write_chunk(upload_id, parse_qs(parsed.query))
                    return
                if action == "complete":
                    self._complete_upload(upload_id)
                    return
                if action == "abort":
                    self._abort_upload(upload_id)
                    return

            if parts == ["api", "open-folder"]:
                self._open_folder()
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
        except ApiError as error:
            payload = {"error": error.message, **error.details}
            self._send_json(error.status, payload)
        except Exception as error:
            print(f"请求处理失败: {error}", file=sys.stderr)
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "电脑端处理失败"})

    def _handle(self, head_only: bool) -> None:
        parsed = urlparse(self.path)
        parts = self._path_parts(parsed.path)
        query = parse_qs(parsed.query)

        if parts == []:
            supplied_token = query.get("k", [""])[0]
            if supplied_token and hmac.compare_digest(supplied_token, self.server.app.token):
                self._redirect_with_cookie()
                return

        if not self._is_authorized(parsed):
            if parts and parts[0] == "api":
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "访问链接无效"})
            else:
                self._send_auth_page(head_only)
            return

        try:
            if parts == []:
                self._serve_static("index.html", head_only)
                return
            if parts == ["app.js"]:
                self._serve_static("app.js", head_only)
                return
            if parts == ["style.css"]:
                self._serve_static("style.css", head_only)
                return
            if parts == ["favicon.ico"]:
                self.send_response(HTTPStatus.NO_CONTENT)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if parts == ["api", "info"]:
                self._send_info()
                return
            if parts == ["api", "files"]:
                self._send_json(
                    HTTPStatus.OK,
                    {"files": self.server.app.store.list_files()},
                )
                return
            if parts == ["api", "qr.svg"]:
                self._send_qr(query, head_only)
                return
            if len(parts) == 3 and parts[:2] == ["api", "upload"]:
                item = self.server.app.store.status(parts[2])
                offset = self.server.app.store.offset(item)
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "uploadId": item.upload_id,
                        "name": item.filename,
                        "size": item.size,
                        "offset": offset,
                    },
                )
                return
            if len(parts) == 2 and parts[0] == "media":
                self._serve_media(parts[1], query, head_only)
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "页面不存在"})
        except ApiError as error:
            self._send_json(error.status, {"error": error.message, **error.details})
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as error:
            print(f"请求处理失败: {error}", file=sys.stderr)
            if not self.wfile.closed:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "电脑端处理失败"})

    @staticmethod
    def _path_parts(path: str) -> list[str]:
        return [unquote(part) for part in path.split("/") if part]

    def _is_authorized(self, parsed: Any) -> bool:
        supplied_token = parse_qs(parsed.query).get("k", [""])[0]
        if supplied_token and hmac.compare_digest(supplied_token, self.server.app.token):
            return True

        for cookie in self.headers.get("Cookie", "").split(";"):
            name, separator, value = cookie.strip().partition("=")
            if (
                separator
                and name == "quest_transfer"
                and hmac.compare_digest(value, self.server.app.token)
            ):
                return True
        return False

    def _redirect_with_cookie(self) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self._security_headers()
        self.send_header(
            "Set-Cookie",
            f"quest_transfer={self.server.app.token}; Path=/; HttpOnly; SameSite=Strict",
        )
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _is_local_client(self) -> bool:
        try:
            address = ipaddress.ip_address(self.client_address[0])
            return address.is_loopback or str(address) == primary_lan_ip()
        except ValueError:
            return False

    def _create_upload(self) -> None:
        payload = self._read_json()
        try:
            filename = str(payload["name"])
            size = int(payload["size"])
            last_modified = int(payload.get("lastModified", 0))
        except (KeyError, TypeError, ValueError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "文件信息不完整") from None

        item = self.server.app.store.create(filename, size, last_modified)
        self._send_json(
            HTTPStatus.CREATED,
            {"uploadId": item.upload_id, "name": item.filename, "size": item.size},
        )

    def _write_chunk(self, upload_id: str, query: dict[str, list[str]]) -> None:
        try:
            offset = int(query.get("offset", ["-1"])[0])
        except ValueError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "上传位置无效") from None

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "分片长度无效") from None

        if length <= 0:
            raise ApiError(HTTPStatus.LENGTH_REQUIRED, "缺少分片内容")
        if length > CHUNK_LIMIT:
            self.close_connection = True
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "分片过大")

        try:
            new_offset = self.server.app.store.write_chunk(
                upload_id,
                offset,
                length,
                self.rfile,
            )
        except OffsetConflict:
            self.close_connection = True
            raise
        self._send_json(
            HTTPStatus.OK,
            {"uploadId": upload_id, "offset": new_offset},
        )

    def _complete_upload(self, upload_id: str) -> None:
        file_info = self.server.app.store.complete(upload_id)
        self._send_json(HTTPStatus.OK, {"ok": True, "file": file_info})

    def _abort_upload(self, upload_id: str) -> None:
        self.server.app.store.abort(upload_id)
        self._send_json(HTTPStatus.OK, {"ok": True})

    def _open_folder(self) -> None:
        if not self._is_local_client():
            raise ApiError(HTTPStatus.FORBIDDEN, "只能在电脑上打开文件夹")

        if sys.platform == "win32":
            os.startfile(str(self.server.app.store.upload_dir))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(self.server.app.store.upload_dir)])
        else:
            subprocess.Popen(["xdg-open", str(self.server.app.store.upload_dir)])
        self._send_json(HTTPStatus.OK, {"ok": True})

    def _send_info(self) -> None:
        self._send_json(
            HTTPStatus.OK,
            {
                "displayUrl": self.server.app.display_url,
                "entryUrl": self.server.app.entry_url,
                "uploadDir": str(self.server.app.store.upload_dir),
                "canOpenFolder": self._is_local_client(),
            },
        )

    def _send_qr(self, query: dict[str, list[str]], head_only: bool) -> None:
        data = query.get("data", [""])[0]
        if not data or len(data) > 500:
            raise ApiError(HTTPStatus.BAD_REQUEST, "二维码内容无效")

        try:
            import qrcode
            import qrcode.image.svg
        except ImportError:
            raise ApiError(HTTPStatus.SERVICE_UNAVAILABLE, "未安装二维码组件") from None

        image = qrcode.make(
            data,
            image_factory=qrcode.image.svg.SvgPathImage,
            box_size=10,
            border=2,
        )
        output = io.BytesIO()
        image.save(output)
        self._send_bytes(
            HTTPStatus.OK,
            output.getvalue(),
            "image/svg+xml; charset=utf-8",
            head_only,
        )

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "请求长度无效") from None
        if length <= 0 or length > JSON_LIMIT:
            raise ApiError(HTTPStatus.BAD_REQUEST, "请求内容无效")
        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "请求格式无效") from None
        if not isinstance(payload, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "请求格式无效")
        return payload

    def _serve_static(self, filename: str, head_only: bool) -> None:
        path = (STATIC_DIR / filename).resolve()
        try:
            path.relative_to(STATIC_DIR.resolve())
        except ValueError:
            raise ApiError(HTTPStatus.NOT_FOUND, "页面不存在") from None
        if not path.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "页面不存在")

        content_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
        }.get(path.suffix, "application/octet-stream")
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        if not head_only:
            with path.open("rb") as source:
                self._copy_stream(source, path.stat().st_size)

    def _serve_media(
        self,
        filename: str,
        query: dict[str, list[str]],
        head_only: bool,
    ) -> None:
        upload_dir = self.server.app.store.upload_dir.resolve()
        path = (upload_dir / filename).resolve()
        try:
            path.relative_to(upload_dir)
        except ValueError:
            raise ApiError(HTTPStatus.NOT_FOUND, "文件不存在") from None
        if not path.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "文件不存在")

        size = path.stat().st_size
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        start = 0
        end = size - 1
        status = HTTPStatus.OK

        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            requested = range_header[6:].split(",", 1)[0].strip()
            try:
                first, _, last = requested.partition("-")
                if first:
                    start = int(first)
                    end = int(last) if last else size - 1
                elif last:
                    suffix_length = int(last)
                    start = max(0, size - suffix_length)
                if start < 0 or end < start or start >= size:
                    raise ValueError
                end = min(end, size - 1)
                status = HTTPStatus.PARTIAL_CONTENT
            except ValueError:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

        length = end - start + 1
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")

        disposition = "attachment" if query.get("download") else "inline"
        ascii_name = path.name.encode("ascii", "replace").decode("ascii").replace('"', "_")
        self.send_header(
            "Content-Disposition",
            f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(path.name)}",
        )
        self.end_headers()

        if head_only:
            return
        with path.open("rb") as source:
            source.seek(start)
            self._copy_stream(source, length)

    def _copy_stream(self, source: Any, length: int) -> None:
        remaining = length
        while remaining:
            block = source.read(min(COPY_BUFFER, remaining))
            if not block:
                break
            self.wfile.write(block)
            remaining -= len(block)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, data, "application/json; charset=utf-8", False)

    def _send_bytes(
        self,
        status: int,
        data: bytes,
        content_type: str,
        head_only: bool,
    ) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
            "media-src 'self'; object-src 'none'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'",
        )

    def _send_auth_page(self, head_only: bool) -> None:
        body = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>需要访问链接</title>
<style>
body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background: #f4f1ea;
color: #1d2433; }}
main {{ max-width: 34rem; padding: 2rem; text-align: center; }}
h1 {{ font-size: clamp(2rem, 8vw, 3rem); margin: 0 0 1rem; }}
p {{ color: #697386; line-height: 1.7; margin: 0; }}
</style>
</head>
<body><main><h1>访问链接已失效</h1>
<p>请在电脑上重新打开启动窗口中的地址，或扫描电脑页面上的二维码。</p>
</main></body></html>"""
        self._send_bytes(
            HTTPStatus.FORBIDDEN,
            body.encode("utf-8"),
            "text/html; charset=utf-8",
            head_only,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quest 3 视频局域网传输")
    parser.add_argument("--port", type=int, default=8780, help="监听端口，默认 8780")
    parser.add_argument("--open", action="store_true", help="启动后打开电脑端页面")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.port <= 65535:
        print("端口必须在 1-65535 之间。", file=sys.stderr)
        return 2

    token = load_token()
    store = UploadStore(UPLOAD_DIR, PARTS_DIR)
    context = AppContext(store=store, token=token, port=args.port)

    try:
        server = TransferServer(("0.0.0.0", args.port), context)
    except OSError as error:
        print(f"无法启动服务：{error}", file=sys.stderr)
        print(f"请确认端口 {args.port} 没有被其他程序占用。", file=sys.stderr)
        return 1

    print()
    print("Quest 视频传输已启动")
    print(f"电脑端 / Quest 3 打开：{context.display_url}")
    print(f"保存目录：{store.upload_dir}")
    print("保持 Quest 3 与电脑连接同一 Wi-Fi。按 Ctrl+C 停止。")
    print()

    if args.open:
        threading.Timer(0.8, lambda: webbrowser.open(context.entry_url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
