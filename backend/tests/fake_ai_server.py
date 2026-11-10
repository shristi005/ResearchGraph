"""Stand-in for the Groq + Gemini HTTP APIs, ONLY for automated tests/demos (stdlib only).
It returns schema-valid canned answers for the synthetic sample papers, so it proves the plumbing (HTTP, parsing, routing,
fallback) works - NOT that a real model writes good answers. Real-model verification is in docs/LIVE_TESTS.md.

Modes (per provider, switchable at runtime via POST /_mode {"groq": "ok|429|500|401|badjson", "gemini": ...}):"""
import hashlib
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STOP = set("a an the of and or for in on to with by from at as is are was were this that it its using".split())
CANNED = {
    "node_explain": {"about": "This paper studies a detection problem.", "problem": "Spotting false information automatically.",
                     "importance": "False information spreads fast.", "approach": "Trains a classifier.",
                     "findings": "The approach reached high accuracy on the dataset used.", "limitations": "Small datasets.",
                     "student_takeaways": ["Models need good data", "Compare methods fairly"], "connections": "Related to other uploaded papers."},
    "edge_explain": {"connected": "Both papers study related detection methods.", "in_common": ["Same application area", "Similar datasets"],
                     "differences": ["Different model families", "Different scope"], "why_read_both": "Together they show how methods compare."},
    "graph_overview": {"research_area": "Automatic detection of misinformation.", "common_themes": ["Detection accuracy", "Dataset limits"],
                       "differences": ["Text models vs graph models"], "common_methods": ["BERT"], "key_limitations": ["Computational cost"],
                       "what_to_learn": "How different method families compare."},
    "gap_details": {"title": "A grounded research direction", "problem": "A problem explained simply.", "why_matters": "It could improve practice.",
                    "research_question": "Can this be improved under realistic conditions?", "possible_methodology": "Compare two baselines on one public dataset.",
                    "datasets_resources": ["Not stated in the papers; verify manually"], "student_direction": "Reproduce, then change one factor.",
                    "feasibility_considerations": ["Needs a GPU for large models"]},
    "feasibility": {"complexity": "Medium: needs model training.", "technical_knowledge": ["Python", "ML basics"],
                    "dataset_availability": "Not stated in the papers; must be verified manually", "computing_requirements": "A laptop GPU helps.",
                    "tools": ["scikit-learn", "PyTorch"], "implementation_approach": ["Reproduce baseline", "Change one factor", "Compare"],
                    "challenges": ["Reproducibility"], "evaluation_metrics": ["Accuracy", "F1"], "undergraduate_suitability": "Maybe: scope it small."},
}
MODES = {"groq": "ok", "gemini": "ok", "ollama": "ok"}
CALLS = {"groq": 0, "gemini": 0, "embed": 0, "ollama": 0, "ollama_embed": 0}
# last (system, prompt) each provider received - lets tests prove fallback sends the identical task
LAST = {}
LOCK = threading.Lock()


def vec(text: str, dim: int = 768):
    v = [0.0] * dim
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w not in STOP:
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dim] += 1.0
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


def answer(system: str, prompt: str, json_mode: bool) -> str:
    if '"ok": true' in prompt:
        return '{"ok": true, "n": 3}'
    m = re.match(r"TASK:(\w+)", system)
    task = m.group(1) if m else "analysis"
    if task == "mentor":
        tags = re.findall(r"\[(S\d+)\]", prompt)
        cite = f" [{tags[0]}]" if tags else ""
        return f"From your papers: the retrieved passage discusses the topic{cite}. My inference: this suggests a small comparison project."
    if task in CANNED:
        return json.dumps(CANNED[task])
    try:
        from sample_data.samples import SAMPLES, analysis_for
        hits = [(prompt.find(s["title"]), s)
                for s in SAMPLES if s["title"] in prompt]
        if hits:
            return json.dumps(analysis_for(min(hits, key=lambda h: h[0])[1]))
    except Exception:
        pass
    return json.dumps({"topics": ["federated learning"], "limitations": ["This heterogeneity remains challenging for current aggregation methods"],
                       "future_work": ["Future work should evaluate aggregation strategies on realistic multi-hospital benchmarks"]})


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, headers=None):
        raw = json.dumps(body).encode() if not isinstance(
            body, bytes) else body
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _fail(self, mode):
        if mode == "429":
            self._send(429, {"error": "rate limited"}, {"Retry-After": "7"})
        elif mode == "500":
            self._send(500, {"error": "boom"})
        elif mode == "401":
            self._send(401, {"error": "bad key"})
        elif mode == "400":
            self._send(400, {"error": "bad request"})
        elif mode == "404":
            self._send(404, {"error": "no such model"})
        elif mode == "badjson":
            return False
        return True

    def do_GET(self):
        if self.path.endswith("/openai/v1/models"):
            return self._send(200, {"data": [{"id": "openai/gpt-oss-120b"}, {"id": "openai/gpt-oss-20b"}]})
        if "/v1beta/models" in self.path:
            return self._send(200, {"models": [{"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                                               {"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent", "batchEmbedContents"]}]})
        self._send(404, {"error": "unknown path"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/_mode":
            with LOCK:
                MODES.update(body)
            return self._send(200, MODES)
        if self.path == "/_calls":
            return self._send(200, CALLS)
        # Ollama (streams NDJSON)
        if self.path == "/api/chat":
            with LOCK:
                CALLS["ollama"] += 1
            LAST["ollama_auth"] = self.headers.get("Authorization", "")
            mode = MODES["ollama"]
            if mode == "404":
                return self._send(404, {"error": "model 'x' not found"})
            if mode == "500":
                return self._send(500, {"error": "boom"})
            text = "not json" if mode == "badjson" else answer(
                body["messages"][0]["content"], body["messages"][-1]["content"], True)
            LAST["ollama"] = (body["messages"][0]["content"],
                              body["messages"][-1]["content"], body.get("format"))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            third = max(1, len(text) // 3)
            for part in (text[:third], text[third:2 * third], text[2 * third:]):
                self.wfile.write((json.dumps(
                    {"message": {"role": "assistant", "content": part}, "done": False}) + "\n").encode())
                self.wfile.flush()
            self.wfile.write((json.dumps({"message": {
                             "content": ""}, "done": True, "prompt_eval_count": 11, "eval_count": 7}) + "\n").encode())
            return
        if self.path == "/api/embed":
            with LOCK:
                CALLS["ollama_embed"] += 1
            LAST["ollama_embed_auth"] = self.headers.get("Authorization", "")
            if MODES["ollama"] == "404":
                return self._send(404, {"error": "model not found"})
            inp = body["input"]
            return self._send(200, {"embeddings": [vec(t.split(": ", 1)[-1], 768) for t in (inp if isinstance(inp, list) else [inp])]})
        # Groq (OpenAI-compatible)
        if self.path.endswith("/chat/completions"):
            with LOCK:
                CALLS["groq"] += 1
            mode = MODES["groq"]
            if mode not in ("ok", "badjson") and self._fail(mode):
                return
            if not self.headers.get("Authorization", "").startswith("Bearer ") or "invalid-key" in self.headers.get("Authorization", ""):
                return self._send(401, {"error": "no key"})
            if "definitely-not" in body.get("model", ""):
                return self._send(404, {"error": "model not found"})
            LAST["groq"] = (body["messages"][0]["content"], body["messages"]
                            [-1]["content"], body.get("response_format"))
            text = "this is not json" if mode == "badjson" else answer(
                body["messages"][0]["content"], body["messages"][-1]["content"], True)
            return self._send(200, {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 100, "completion_tokens": 50}})
        if ":generateContent" in self.path:                               # Gemini
            with LOCK:
                CALLS["gemini"] += 1
            mode = MODES["gemini"]
            if mode not in ("ok", "badjson") and self._fail(mode):
                return
            if not self.headers.get("x-goog-api-key") or "invalid-key" in self.headers.get("x-goog-api-key", ""):
                return self._send(403, {"error": "no key"})
            if "definitely-not" in self.path:
                return self._send(404, {"error": "model not found"})
            sysm = body["systemInstruction"]["parts"][0]["text"]
            prompt = body["contents"][-1]["parts"][0]["text"]
            LAST["gemini"] = (
                sysm, prompt, body["generationConfig"].get("responseMimeType"))
            text = "this is not json" if mode == "badjson" else answer(
                sysm, prompt, True)
            return self._send(200, {"candidates": [{"content": {"parts": [{"text": text}]}}],
                                    "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 40}})
        if ":batchEmbedContents" in self.path:
            with LOCK:
                CALLS["embed"] += 1
            if MODES["gemini"] in ("429", "500", "401"):
                return self._fail(MODES["gemini"])
            dim = body["requests"][0].get("outputDimensionality", 768)
            return self._send(200, {"embeddings": [{"values": vec(r["content"]["parts"][0]["text"], dim)} for r in body["requests"]]})
        self._send(404, {"error": "unknown path"})


def serve(port: int = 0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    s = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"fake Groq/Gemini on :{port}", flush=True)
    s.serve_forever()
