from __future__ import annotations

import email
import io
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "vendor"))
from app.law_db import init_db, search_laws, stats, import_json

HOST = "127.0.0.1"
PORT = 8000
STATIC = ROOT / "static"
UPLOADS = {}
MAX_UPLOAD = 12 * 1024 * 1024


def load_env(path=ROOT / ".env"):
    out = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def cfg():
    e = load_env()
    return {
        "key": e.get("DEEPSEEK_API_KEY", os.environ.get("DEEPSEEK_API_KEY", "")),
        "base": e.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        "fast": e.get("DEEPSEEK_FAST_MODEL", "deepseek-v4-flash"),
        "strong": e.get("DEEPSEEK_STRONG_MODEL", "deepseek-v4-pro"),
    }


def deepseek_chat(messages, strong=False):
    c = cfg()
    key = c["key"].strip()
    if not key or key in {"your_key_here", "sk-..."}:
        raise RuntimeError("کلید DeepSeek تنظیم نشده است. فایل .env را باز کنید و DEEPSEEK_API_KEY را وارد کنید.")
    model = c["strong"] if strong else c["fast"]
    payload = json.dumps({"model": model, "messages": messages, "temperature": 0.15, "stream": False}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(c["base"].rstrip("/") + "/chat/completions", data=payload, method="POST", headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            obj = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"DeepSeek API error {exc.code}: {body}") from exc
    except Exception as exc:
        raise RuntimeError(f"خطا در اتصال به DeepSeek: {exc}") from exc
    text = obj["choices"][0]["message"].get("content") or ""
    return text.strip(), {"model": model, "usage": obj.get("usage", {})}


def build_sources(query):
    hits = search_laws(query, limit=10)
    citations, chunks = [], []
    validity_warning = False
    for i, h in enumerate(hits, 1):
        cid = f"L{i}"
        citations.append({"id": f"[{cid}]", "law_title": h.get("law_title", ""), "article": h.get("article", ""), "source_url": h.get("source_url", ""), "status": h.get("status", "unknown")})
        if h.get("status") != "valid":
            validity_warning = True
        chunks.append(f"[{cid}]\nعنوان: {h.get('law_title','')}\nماده/بخش: {h.get('article','')}\nنوع: {h.get('doc_type','')}\nوضعیت اعتبار: {h.get('status','unknown')}\nمنبع: {h.get('source_url','')}\nمتن رسمی بازیابی‌شده:\n{h.get('text','')[:6000]}")
    return citations, "\n\n".join(chunks), not bool(hits), validity_warning


def answer_legal(message, mode, document_text, history):
    query = message + (" " + document_text[:7000] if document_text else "")
    citations, sources, coverage_warning, validity_warning = build_sources(query)
    mode_text = {
        "simple": "پاسخ را برای فرد غیرحقوق‌دان، روشن و مرحله‌ای بده.",
        "deep": "تحلیل حقوقی عمیق ارائه کن: مسائل، قواعد، استدلال موافق/مخالف، ریسک‌ها، اقدام بعدی و مهلت‌های احتمالی.",
        "draft": "یک پیش‌نویس حقوقی یا لایحه منظم تولید کن؛ هرجا واقعیت پرونده ناقص است با [نیاز به تکمیل] مشخص کن.",
    }.get(mode, "پاسخ روشن و دقیق بده.")
    system = f"""تو «دادبان»، دستیار تخصصی حقوق ایران هستی.
{mode_text}
قواعد سخت:
1) هیچ شماره ماده، رأی، مهلت یا عنوان قانونی را از حافظه به عنوان استناد قطعی نساز.
2) فقط منابعی را که در بخش منابع بازیابی‌شده با شناسه [L1] و ... آمده‌اند به عنوان استناد قطعی ذکر کن.
3) اگر منبع مرتبط کافی نیست، صریح بگو «برای استناد قطعی، منبع کافی در مخزن بازیابی نشد» و سپس فقط تحلیل عمومی یا مشروط ارائه کن.
4) اگر وضعیت اعتبار منبع unknown است، آن را «معتبر فعلی» اعلام نکن و نیاز به کنترل تنقیحی را بگو.
5) متن رسمی، ادعای کاربر، واقعیت استخراج‌شده از سند و استنباط خودت را با هم مخلوط نکن.
6) نتیجه پرونده را تضمین نکن.
7) پاسخ فارسی و منظم باشد.
"""
    user = f"""درخواست کاربر:
{message}

متن سند کاربر (ممکن است ناقص باشد):
{document_text[:22000] if document_text else '(سندی بارگذاری نشده)'}

منابع بازیابی‌شده از مخزن حقوقی دادبان:
{sources or '(هیچ منبع مرتبطی پیدا نشد)'}
"""
    safe_hist = []
    for item in (history or [])[-6:]:
        role = item.get("role")
        content = str(item.get("content", ""))[:5000]
        if role in {"user", "assistant"} and content:
            safe_hist.append({"role": role, "content": content})
    text, meta = deepseek_chat([{"role": "system", "content": system}, *safe_hist, {"role": "user", "content": user}], strong=mode in {"deep", "draft"})
    return {"answer": text, "citations": citations, "coverage_warning": coverage_warning, "validity_warning": validity_warning, "model": meta.get("model"), "usage": meta.get("usage", {})}


def extract_docx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        raw = z.read("word/document.xml")
    root = ET.fromstring(raw)
    texts = []
    for el in root.iter():
        if el.tag.endswith("}t") and el.text:
            texts.append(el.text)
        elif el.tag.endswith("}p"):
            texts.append("\n")
    return re.sub(r"\n\s*\n+", "\n", " ".join(texts)).strip()


def extract_uploaded(filename, data):
    ext = Path(filename).suffix.lower()
    if ext in {".txt", ".md", ".csv", ".log"}:
        for enc in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
            try:
                return data.decode(enc), "text"
            except UnicodeDecodeError:
                pass
    if ext == ".docx":
        return extract_docx(data), "docx"
    if ext == ".pdf":
        txt = data.decode("latin-1", "ignore")
        pieces = []
        for m in re.finditer(r"\(([^()]|\\.){3,}\)\s*T[Jj]", txt):
            s = re.sub(r"\)\s*T[Jj]$", "", m.group(0))[1:]
            s = s.replace("\\n", "\n").replace("\\r", "").replace("\\(", "(").replace("\\)", ")")
            pieces.append(s)
        out = "\n".join(pieces).strip()
        if len(out) < 40:
            raise ValueError("این PDF متن قابل استخراج نداشت. PDF اسکن‌شده به OCR نیاز دارد؛ فعلاً متن را کپی کنید.")
        return out, "pdf-basic"
    raise ValueError("در نسخه Portable فعلاً TXT/MD/CSV/DOCX و PDF متنی ساده پشتیبانی می‌شود.")


def parse_multipart(headers, body):
    ctype = headers.get("Content-Type", "")
    msg = email.message_from_bytes((f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n").encode() + body)
    for part in msg.walk():
        if part.get_content_disposition() == "form-data" and part.get_param("name", header="content-disposition") == "file":
            return part.get_filename() or "upload.bin", part.get_payload(decode=True) or b""
    raise ValueError("فایل در درخواست پیدا نشد.")


class Handler(BaseHTTPRequestHandler):
    server_version = "DadbanPortable/3.0"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def send_json(self, obj, status=200):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def send_file(self, path):
        path = Path(path)
        if not path.exists():
            self.send_error(404)
            return
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        n = int(self.headers.get("Content-Length", "0") or "0")
        if n > MAX_UPLOAD:
            raise ValueError("حجم درخواست بیش از حد مجاز است.")
        return self.rfile.read(n)

    def do_GET(self):
        if self.path in {"/", "/index.html"}:
            return self.send_file(STATIC / "index.html")
        if self.path == "/api/health":
            c = cfg()
            return self.send_json({"ok": True, "portable": True, "deepseek_configured": bool(c["key"] and c["key"] not in {"your_key_here", "sk-..."}), "law_db": stats()})
        if self.path == "/api/laws/stats":
            return self.send_json(stats())
        self.send_error(404)

    def do_POST(self):
        try:
            if self.path == "/api/chat":
                data = json.loads(self.read_body().decode("utf-8"))
                msg = str(data.get("message", "")).strip()
                if not msg:
                    return self.send_json({"detail": "متن سؤال خالی است."}, 400)
                did = data.get("document_id")
                doc_text = UPLOADS.get(str(did), {}).get("text", "") if did else ""
                return self.send_json(answer_legal(msg, str(data.get("mode", "simple")), doc_text, data.get("history") or []))
            if self.path == "/api/upload":
                filename, content = parse_multipart(self.headers, self.read_body())
                text, kind = extract_uploaded(filename, content)
                did = uuid.uuid4().hex
                UPLOADS[did] = {"filename": filename, "text": text[:120000], "created": time.time()}
                return self.send_json({"document_id": did, "filename": filename, "kind": kind, "characters": len(text)})
            self.send_error(404)
        except json.JSONDecodeError:
            self.send_json({"detail": "JSON نامعتبر است."}, 400)
        except Exception as exc:
            self.send_json({"detail": str(exc)}, 500)


def seed_json_if_present():
    init_db()
    seed = ROOT / "data" / "laws.json"
    if seed.exists():
        try:
            raw = json.loads(seed.read_text(encoding="utf-8-sig"))
            records = raw.get("laws", []) if isinstance(raw, dict) else raw
            if records and stats().get("articles", 0) == 0:
                import_json(str(seed))
        except Exception as exc:
            print("Seed import warning:", exc)


def main():
    seed_json_if_present()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 64)
    print("Dadban Portable Legal AI")
    print(f"Open: http://{HOST}:{PORT}")
    print("No Python/pip/winget installation is required.")
    print("Press Ctrl+C to stop.")
    print("=" * 64)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
