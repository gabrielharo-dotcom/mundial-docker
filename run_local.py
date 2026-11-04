import subprocess, sys, os, time, urllib.request
from pathlib import Path
ROOT=Path(__file__).parent
if __name__=='__main__':
    if '--demo' in sys.argv:
        subprocess.run([sys.executable,str(ROOT/'seed_demo.py')],check=True)
    children=[]
    try:
        for i in range(1,4):
            env=dict(os.environ,PORT=str(8000+i),INSTANCE_ID=f'app-{i}')
            children.append(subprocess.Popen([sys.executable,str(ROOT/'app.py')],env=env))
        for port in (8001,8002,8003):
            for attempt in range(50):
                try:
                    urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1);break
                except OSError: time.sleep(.2)
            else: raise RuntimeError(f'No inicia el puerto {port}')
        children.append(subprocess.Popen([sys.executable,str(ROOT/'proxy.py')]))
        print('Abrir http://127.0.0.1:8080 | Ctrl+C para detener',flush=True)
        while all(c.poll() is None for c in children): time.sleep(1)
    except KeyboardInterrupt: pass
    finally:
        for c in children:
            if c.poll() is None:c.terminate()
        for c in children:c.wait()
