"""Prueba de distribución, caída y recuperación en procesos aislados."""
import os, sys, subprocess, tempfile, time, collections, json
from pathlib import Path
from stress import request
ROOT=Path(__file__).parent
def wait(port):
    for _ in range(100):
        try:return request(f'http://127.0.0.1:{port}','/health')
        except OSError:time.sleep(.1)
    raise RuntimeError('No inició '+str(port))
def main():
    results={}; processes=[]
    with tempfile.TemporaryDirectory() as tmp:
        env=dict(os.environ,DB_PATH=str(Path(tmp)/'cluster.db'))
        subprocess.run([sys.executable,str(ROOT/'seed_demo.py')],env=env,check=True,stdout=subprocess.DEVNULL)
        def start(i):
            p=subprocess.Popen([sys.executable,str(ROOT/'app.py')],env=dict(env,PORT=str(8100+i),INSTANCE_ID='cluster-'+str(i)),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(p);wait(8100+i);return p
        try:
            replicas=[start(i) for i in (1,2,3)]
            p=subprocess.Popen([sys.executable,str(ROOT/'proxy.py')],env=dict(env,BACKENDS='8101,8102,8103',PROXY_PORT='8180'),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(p);wait(8180)
            base='http://127.0.0.1:8180';login,_=request(base,'/api/login',dict(email='ana@demo.local',password='Mundial2026!'));token=login['token']
            def sample():
                counts=collections.Counter()
                for _ in range(60):
                    rooms,instance=request(base,'/api/rooms',token=token);counts[instance]+=1
                return dict(counts)
            results['normal_60']=sample()
            replicas[1].terminate();replicas[1].wait();results['replica_2_stopped_60']=sample()
            replicas[1]=start(2);results['recovered_60']=sample()
            rooms,_=request(base,'/api/rooms',token=token);room=rooms[0]['id'];s,_=request(base,'/api/state?room='+str(room),token=token);mid=s['matches'][-1]['id']
            request(base,'/api/predict',dict(room=room,match=mid,home=4,away=2),token)
            for r in replicas:r.terminate();r.wait()
            replicas=[start(i) for i in (1,2,3)]
            s,_=request(base,'/api/state?room='+str(room),token=token)
            m=next(m for m in s['matches'] if m['id']==mid)
            results['session_after_full_restart']=s['user']['name']=='Ana Torres'
            results['prediction_after_full_restart']=[m['prediction_home'],m['prediction_away']]
            assert results['normal_60']=={'cluster-1':20,'cluster-2':20,'cluster-3':20}
            assert 'cluster-2' not in results['replica_2_stopped_60']
            assert results['session_after_full_restart'] and results['prediction_after_full_restart']==[4,2]
            results['status']='PASS'
        finally:
            for p in processes:
                if p.poll() is None:p.terminate()
            for p in processes:p.wait()
    out=ROOT/'evidence'/'cluster.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results,indent=2))
if __name__=='__main__':main()
