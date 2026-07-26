"""Live HTTP server: run FieldGuard on a document and stream every stage.

    python3 -m fieldguard.server                      # http://localhost:8000
    python3 -m fieldguard.server --model qwen2.5:1.5b --port 8080

Stdlib only, same as the rest of the package. Streaming is Server-Sent Events:
one `data: {...}` frame per stage, flushed as the stage completes, so the page
shows the model actually thinking rather than a spinner and a final blob.

# ponytail: ThreadingHTTPServer, no auth, no rate limit — this binds to
# localhost for demos and development. Put it behind a real server before
# exposing it to a network.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .adapter import load_jsonl, schema_from_json
from .backends import MockBackend, OpenAICompatBackend
from .live import analyze
from .schemas import Schema

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DATASETS = ROOT / "datasets"

# dataset id -> (jsonl, schema json, human label)
CORPORA = {
    "sroie": ("sroie_50.jsonl", "sroie.schema.json",
              "SROIE receipts (ICDAR 2019) — scanned-receipt OCR text"),
    "kleister_nda": ("kleister_nda_party.jsonl", "kleister_nda_party.schema.json",
                     "Kleister-NDA contracts — 30% of gold fields legitimately absent"),
}
SAMPLES_PER_CORPUS = 6


def _load_samples() -> tuple[dict, dict[str, Schema]]:
    """Read a few documents + gold from each shipped corpus. Missing files skip."""
    payload, schemas = {}, {}
    for key, (data_file, schema_file, label) in CORPORA.items():
        data_path, schema_path = DATASETS / data_file, DATASETS / schema_file
        if not (data_path.exists() and schema_path.exists()):
            continue
        schema = schema_from_json(schema_path)
        examples, _ = load_jsonl(data_path, schema)
        schemas[key] = schema
        payload[key] = {
            "label": label,
            "fields": [{"name": f.name, "type": f.type, "required": f.required,
                        "multi": f.multi, "description": f.description}
                       for f in schema.fields],
            "samples": [{"id": f"{key}-{i}", "document": ex.document, "gold": ex.gold}
                        for i, ex in enumerate(examples[:SAMPLES_PER_CORPUS])],
        }
    return payload, schemas


def _ollama_models(base_url: str) -> list[str]:
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=3) as r:
            return sorted(m["id"] for m in json.load(r).get("data", []))
    except Exception:
        return []


def make_handler(base_url: str, default_model: str):
    corpora, schemas = _load_samples()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # quiet: one line per request is noise
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                page = WEB / "live.html"
                if not page.exists():
                    self._send(500, b"web/live.html missing", "text/plain")
                    return
                self._send(200, page.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/config":
                models = _ollama_models(base_url)
                self._json({"corpora": corpora, "models": models,
                            "default_model": default_model,
                            "base_url": base_url,
                            "backend_ready": bool(models)})
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if self.path != "/api/analyze":
                self._send(404, b"not found", "text/plain")
                return
            try:
                n = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(n) or b"{}")
            except (ValueError, json.JSONDecodeError) as exc:
                self._json({"error": f"bad request: {exc}"}, 400)
                return

            corpus = req.get("corpus", "sroie")
            if corpus not in schemas:
                self._json({"error": f"unknown corpus {corpus!r}"}, 400)
                return
            document = (req.get("document") or "").strip()
            if not document:
                self._json({"error": "empty document"}, 400)
                return

            model = req.get("model") or default_model
            backend = (MockBackend() if model == "mock"
                       else OpenAICompatBackend(base_url=base_url, model=model))

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            def emit(obj) -> None:
                self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
                self.wfile.flush()

            try:
                for event in analyze(
                    backend, document, schemas[corpus],
                    threshold=float(req.get("threshold", 0.5)),
                    ground_threshold=float(req.get("ground_threshold", 0.5)),
                    ground_repair=bool(req.get("ground_repair", False)),
                    gold=req.get("gold") or None,
                ):
                    emit(event)
            except BrokenPipeError:
                return  # client navigated away mid-run
            except Exception as exc:
                traceback.print_exc()
                emit({"stage": "error", "message": f"{type(exc).__name__}: {exc}"})

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--base-url", default="http://localhost:11434/v1",
                    help="OpenAI-compatible endpoint (default: local Ollama)")
    ap.add_argument("--model", default="qwen2.5:3b")
    args = ap.parse_args()

    handler = make_handler(args.base_url, args.model)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    models = _ollama_models(args.base_url)
    print(f"FieldGuard live  ->  http://{args.host}:{args.port}")
    print(f"  backend {args.base_url}: "
          + (f"{len(models)} model(s), default {args.model}" if models
             else "UNREACHABLE (start Ollama, or pick the 'mock' model)"))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
