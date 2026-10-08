"""Authenticated loopback IPC to a running GUI. This HTTP endpoint is NOT MCP.

Agent --stdio MCP--> adapter --local JSON IPC--> GUI main-thread work functions.
"""
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


class GuiBridge:
    def __init__(self,runtime_path,dispatch):
        self.path=Path(runtime_path)
        self.dispatch=dispatch
        self.token=secrets.token_urlsafe(32)

    def start(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                if self.path!='/call' or not secrets.compare_digest(self.headers.get('Authorization',''),f'Bearer {owner.token}'):
                    self.send_error(403); return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0 < size <= 65536: raise ValueError('Invalid request size')
                    data=json.loads(self.rfile.read(size))
                    value=owner.dispatch(data['action'],data.get('args',{}))
                    response={'ok':True,'result':value}
                except Exception as error:
                    response={'ok':False,'error':str(error)}
                payload=json.dumps(response,ensure_ascii=False,allow_nan=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Content-Length',str(len(payload)))
                self.end_headers(); self.wfile.write(payload)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.info={'url':f'http://127.0.0.1:{self.server.server_port}/call','token':self.token}
        temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.info),encoding='utf-8'); temp.replace(self.path)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown(); self.server.server_close()
        if self.path.exists() and json.loads(self.path.read_text(encoding='utf-8')).get('token')==self.token:
            self.path.unlink()


def call_gui(runtime_path,action,args=None):
    path=Path(runtime_path)
    try:
        info=json.loads(path.read_text(encoding='utf-8'))
        if not info['url'].startswith('http://127.0.0.1:'):
            raise ValueError('Only local GUI endpoints are supported')
        req=Request(info['url'],data=json.dumps({'action':action,'args':args or {}},allow_nan=False).encode(),
                    headers={'Content-Type':'application/json','Authorization':f"Bearer {info['token']}"})
        with urlopen(req,timeout=15) as response: result=json.load(response)
    except (OSError,URLError,ValueError,KeyError) as error:
        raise RuntimeError('FIR GUI is unavailable. Open the GUI and press MCP Connect / 연결 준비 first.') from error
    if not result['ok']: raise ValueError(result['error'])
    return result['result']
