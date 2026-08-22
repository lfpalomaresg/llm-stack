# probe-harness.py — báscula del harness de opencode (v5.4.2, 2026-08-23).
# Uso: python3 probe-harness.py &  → añadir provider "measure" en opencode.json
#   (baseURL http://127.0.0.1:4999/v1, modelo "probe", tool_call true)
#   → `opencode run "di hola" -m measure/probe` → tamaños en probe-sizes.jsonl.
# Con esto se midió el adelgazamiento 79KB→37KB (skills inyectadas: 41KB).

import json, http.server
LOG = "/private/tmp/claude-501/-Users-pifanmac/5be85b4e-a20c-4734-837c-737e14f1b024/scratchpad/probe-sizes.jsonl"
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        body = json.dumps({"object":"list","data":[{"id":"probe","object":"model"}]}).encode()
        self.send_response(200); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        n = int(self.headers.get("Content-Length",0)); raw = self.rfile.read(n)
        try:
            d = json.loads(raw); msgs = d.get("messages",[])
            rec = {"bytes": n, "n_messages": len(msgs), "n_tools": len(d.get("tools",[]) or []),
                   "sys_bytes": sum(len(json.dumps(m)) for m in msgs if m.get("role")=="system"),
                   "tools_bytes": len(json.dumps(d.get("tools",[]) or []))}
        except Exception as e: rec = {"bytes": n, "err": str(e)}
        open(LOG,"a").write(json.dumps(rec)+"\n")
        try:
            if rec.get("bytes",0)>20000:
                d2=json.loads(raw)
                open(LOG.replace("probe-sizes.jsonl","probe-dump.json"),"w").write(json.dumps(d2,ensure_ascii=False,indent=1))
        except Exception: pass
        stream = False
        try: stream = bool(json.loads(raw).get("stream"))
        except Exception: pass
        if stream:
            self.send_response(200); self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache"); self.end_headers()
            for chunk in [{"choices":[{"index":0,"delta":{"role":"assistant","content":"OK"},"finish_reason":None}]},
                          {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],
                           "usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}]:
                chunk.update({"id":"probe1","object":"chat.completion.chunk","created":1,"model":"probe"})
                self.wfile.write(("data: "+json.dumps(chunk)+"\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            resp = json.dumps({"id":"probe1","object":"chat.completion","created":1,"model":"probe",
              "choices":[{"index":0,"finish_reason":"stop","message":{"role":"assistant","content":"OK"}}],
              "usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}).encode()
            self.send_response(200); self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(resp))); self.end_headers(); self.wfile.write(resp)
http.server.HTTPServer(("127.0.0.1",4999),H).serve_forever()
