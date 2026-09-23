from __future__ import annotations
import json, mimetypes, os, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from engine.pipeline import TroubleshootingEngine

ROOT=Path(__file__).parent
ENGINE=TroubleshootingEngine(ROOT / 'data')

class Handler(BaseHTTPRequestHandler):
    server_version='SGTE/1.0'
    def _json(self, status, payload):
        raw=json.dumps(payload, ensure_ascii=False, separators=(',',':')).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store')
        self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/health': return self._json(200, ENGINE.health())
        if path=='/v1/metrics': return self._json(200, ENGINE.metrics())
        if path=='/v1/catalog/status': return self._json(200, ENGINE.asset_status())
        target=ROOT/('web/index.html' if path=='/' else path.lstrip('/'))
        if ROOT not in target.resolve().parents or not target.is_file(): return self._json(404,{'error':'not_found'})
        raw=target.read_bytes(); self.send_response(200)
        self.send_header('Content-Type',mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_POST(self):
        if urlparse(self.path).path!='/v1/troubleshoot': return self._json(404,{'error':'not_found'})
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n>200000: raise ValueError('body_too_large')
            body=json.loads(self.rfile.read(n) or b'{}')
            query=body.get('query',''); siis=body.get('siis_response')
            if not isinstance(query,str) or not query.strip(): raise ValueError('query_required')
            if siis is not None and not isinstance(siis,str): raise ValueError('siis_response_must_be_string')
            return self._json(200,ENGINE.troubleshoot(query,siis))
        except (ValueError,json.JSONDecodeError) as e: return self._json(400,{'error':str(e)})
        except Exception: return self._json(500,{'error':'internal_error'})
    def log_message(self, fmt, *args): pass

if __name__=='__main__':
    host=os.getenv('HOST','0.0.0.0'); port=int(os.getenv('PORT','8000'))
    print(f'Smart Guided Troubleshooting Engine: http://{host}:{port} (AI {"on" if ENGINE.ai.enabled else "off"})',flush=True)
    import threading; threading.Thread(target=ENGINE._ensure_embeddings,daemon=True).start()  # warm catalog embeddings
    ThreadingHTTPServer((host,port),Handler).serve_forever()
