"""Carga de bucle cerrado: lecturas autenticadas y escrituras de pronósticos."""
import argparse, concurrent.futures, time, json, urllib.request, urllib.error, statistics, collections
from pathlib import Path
def request(base,path,data=None,token=''):
    req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
    with urllib.request.urlopen(req,timeout=35) as r:return json.load(r),r.headers.get('X-Instance-ID')
def run(base,users,n,token,room,mid,mode):
    def one(i):
        start=time.perf_counter()
        try:
            _,instance=request(base,'/api/state?room='+str(room),token=token) if mode=='read' else request(base,'/api/predict',dict(room=room,match=mid,home=i%4,away=i%3),token)
            return (time.perf_counter()-start)*1000,True,instance
        except Exception as e:return (time.perf_counter()-start)*1000,False,type(e).__name__
    start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=users) as pool:results=list(pool.map(one,range(n)))
    elapsed=time.perf_counter()-start;lat=sorted(r[0] for r in results)
    return dict(base=base,mode=mode,concurrency=users,requests=n,seconds=round(elapsed,3),rps=round(n/elapsed,2),p50_ms=round(statistics.median(lat),2),p95_ms=round(lat[min(n-1,int(.95*n))],2),max_ms=round(max(lat),2),errors=sum(not r[1] for r in results),instances=dict(collections.Counter(r[2] for r in results)))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8080');p.add_argument('--out',default='evidence/stress.json');a=p.parse_args()
    login,_=request(a.base,'/api/login',dict(email='ana@demo.local',password='Mundial2026!'));token=login['token']
    rooms,_=request(a.base,'/api/rooms',token=token);room=rooms[0]['id'];state,_=request(a.base,'/api/state?room='+str(room),token=token);mid=next(m['id'] for m in state['matches'] if m['kickoff']>time.time() and m['home_score'] is None)
    results=[]
    # Calentamiento excluido de las métricas.
    for _ in range(10):request(a.base,'/api/state?room='+str(room),token=token)
    for mode in ('read','write'):
        for users,n in ((1,100),(10,300),(50,600),(100,1000)):
            result=run(a.base,users,n,token,room,mid,mode);results.append(result);print(json.dumps(result),flush=True)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(results,indent=2),encoding='utf-8')
