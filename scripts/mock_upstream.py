"""开发用假上游：OpenAI 兼容 /v1/chat/completions（JSON + SSE）+ /models + usage。
用法: python scripts/mock_upstream.py [port]   (默认 11499)
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 11499


def usage_json():
    return {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code: int, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/models", "/v1/models"):
            self._json(200, {"object": "list", "data": [{"id": "mock:7b"}]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self._json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "bad json"})
        if payload.get("stream"):
            return self._stream()
        return self._json(200, {
            "id": "mock-chat", "object": "chat.completion", "created": 0,
            "model": payload.get("model", "mock:7b"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "mock ok"},
                         "finish_reason": "stop"}],
            "usage": usage_json(),
        })

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for piece in ("he", "llo", " stream"):
            chunk = {"id": "mock-1", "object": "chat.completion.chunk", "created": 0,
                     "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()
        final = {"id": "mock-1", "object": "chat.completion.chunk", "created": 0,
                 "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": usage_json()}
        self.wfile.write(f"data: {json.dumps(final)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


if __name__ == "__main__":
    print(f"mock upstream on http://127.0.0.1:{PORT}/v1", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
