"""Balanceador local round robin con failover; Docker utiliza Nginx."""
import os, threading, itertools, http.client, json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
BACKENDS=os.environ.get('BACKENDS','8001,8002,8003').split(',')
counter=itertools.count(); lock=threading.Lock()
class Proxy(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self): self.forward()
    def do_POST(self): self.forward()
    def forward(self):
        body=self.rfile.read(int(self.headers.get('Content-Length','0')))
        with lock: start=next(counter)%len(BACKENDS)
        for i in range(len(BACKENDS)):
            conn=http.client.HTTPConnection('127.0.0.1',int(BACKENDS[(start+i)%len(BACKENDS)]),timeout=30)
            try:
                conn.connect()
            except OSError:
                conn.close(); continue
            try:
                conn.request(self.command,self.path,body,{k:v for k,v in self.headers.items() if k.lower() not in ('host','connection')})
                response=conn.getresponse(); content=response.read()
                self.send_response(response.status)
                for k,v in response.getheaders():
                    if k.lower() not in ('server','date','connection','transfer-encoding'): self.send_header(k,v)
                self.end_headers(); self.wfile.write(content); return
            except Exception:
                # Una escritura enviada no se reintenta: podría haberse confirmado.
                self.send_error(502,'Backend interrumpido'); return
            finally: conn.close()
        self.send_error(503,'No hay replicas disponibles')
if __name__=='__main__':
    print('Balanceador http://127.0.0.1:8080 -> '+','.join(BACKENDS),flush=True)
    ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('PROXY_PORT','8080'))),Proxy).serve_forever()
