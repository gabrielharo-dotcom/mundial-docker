"""Laboratorio local. Python 3.12+ y biblioteca estándar."""
import os, json, sqlite3, secrets, hashlib, hmac, time, socket
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from contextlib import contextmanager

ROOT = Path(__file__).parent
DB = os.environ.get('DB_PATH', str(ROOT / 'data' / 'mundial.db'))
INSTANCE = os.environ.get('INSTANCE_ID', socket.gethostname())

@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY,name TEXT NOT NULL,code TEXT UNIQUE NOT NULL,owner INTEGER REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS members(room_id INTEGER REFERENCES rooms(id),user_id INTEGER REFERENCES users(id),PRIMARY KEY(room_id,user_id));
        CREATE TABLE IF NOT EXISTS matches(id INTEGER PRIMARY KEY,room_id INTEGER REFERENCES rooms(id),home TEXT NOT NULL,away TEXT NOT NULL,kickoff REAL NOT NULL,home_score INTEGER,away_score INTEGER);
        CREATE TABLE IF NOT EXISTS predictions(match_id INTEGER REFERENCES matches(id),user_id INTEGER REFERENCES users(id),home INTEGER NOT NULL,away INTEGER NOT NULL,created REAL NOT NULL,PRIMARY KEY(match_id,user_id));
        CREATE INDEX IF NOT EXISTS idx_matches_room ON matches(room_id,kickoff,id);
        ''')

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),180000).hex()

def points(ph,pa,rh,ra,created,kickoff):
    exact = (ph,pa)==(rh,ra)
    winner = (ph>pa)-(ph<pa)==(rh>ra)-(rh<ra)
    difference = ph-pa==rh-ra
    base = 5 if exact else (3 if winner else 0)+(2 if difference else 0)
    early = int(kickoff-created > 86400)
    return {'base':base,'early':early,'correct':winner,'exact':exact,'difference':difference}

def ranking(db, room):
    matches=db.execute('SELECT * FROM matches WHERE room_id=? ORDER BY kickoff,id',(room,)).fetchall()
    result=[]
    for u in db.execute('SELECT u.id,u.name FROM users u JOIN members m ON m.user_id=u.id WHERE m.room_id=?',(room,)):
        total=streak=hits=exacts=0; detail=[]
        for m in matches:
            # Un partido pendiente interrumpe el cálculo hasta que se publique su resultado.
            if m['home_score'] is None: break
            p=db.execute('SELECT * FROM predictions WHERE match_id=? AND user_id=?',(m['id'],u['id'])).fetchone()
            s=points(p['home'],p['away'],m['home_score'],m['away_score'],p['created'],m['kickoff']) if p else dict(base=0,early=0,correct=False,exact=False,difference=False)
            streak=streak+1 if s['correct'] else 0
            bonus=2 if streak and streak%3==0 else 0
            total+=s['base']+s['early']+bonus; hits+=int(s['correct']); exacts+=int(s['exact'])
            detail.append(dict(match=m['id'],fixture=m['home']+' vs '+m['away'],prediction=f"{p['home']}-{p['away']}" if p else 'Sin pronóstico',result=f"{m['home_score']}-{m['away_score']}",**s,streak_bonus=bonus,total=s['base']+s['early']+bonus))
        result.append(dict(id=u['id'],name=u['name'],points=total,hits=hits,exacts=exacts,streak=streak,detail=detail))
    return sorted(result,key=lambda u:(-u['points'],-u['exacts'],-u['hits'],u['id']))

class Error(Exception):
    def __init__(self,status,message): self.status,self.message=status,message

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,status,data,ctype='application/json; charset=utf-8'):
        if 200 <= status < 300 and getattr(self,'db',None) is not None:
            self.db.commit()
        raw=json.dumps(data,ensure_ascii=False).encode() if not isinstance(data,bytes) else data
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(raw)))
        self.send_header('X-Instance-ID',INSTANCE); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(raw)
    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def handle_request(self):
        try:
            self.route()
        except Error as e: self.send(e.status,{'error':e.message})
        except (ValueError,TypeError,KeyError,json.JSONDecodeError): self.send(400,{'error':'Datos inválidos o campos incompletos'})
        except sqlite3.IntegrityError: self.send(409,{'error':'El registro ya existe o viola una restricción'})
        except sqlite3.OperationalError: self.send(503,{'error':'Base de datos ocupada. Reintenta.'})
        except Exception as e:
            print(type(e).__name__,str(e),flush=True); self.send(500,{'error':'Error interno'})
    def route(self):
        path=urlparse(self.path).path; query=parse_qs(urlparse(self.path).query)
        if self.command=='GET' and path in ('/','/app.js','/style.css'):
            file={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]
            return self.send(200,(ROOT/'static'/file).read_bytes(),{'/':'text/html; charset=utf-8','/app.js':'text/javascript; charset=utf-8','/style.css':'text/css; charset=utf-8'}[path])
        if path=='/health':
            with connect() as db: db.execute('SELECT 1').fetchone()
            return self.send(200,{'status':'ok','instance':INSTANCE})
        data={}
        if self.command=='POST':
            length=int(self.headers.get('Content-Length','0'))
            if length>16384: raise Error(413,'Petición demasiado grande')
            data=json.loads(self.rfile.read(length) or '{}')
        with connect() as db:
            self.db=db
            if path in ('/api/register','/api/login') and self.command=='POST':
                email=str(data['email']).strip().lower(); password=str(data['password'])
                if '@' not in email or len(email)>160 or not 8<=len(password)<=128: raise Error(400,'Correo válido y contraseña de 8 a 128 caracteres requeridos')
                if path.endswith('register'):
                    name=str(data['name']).strip()
                    if not 1<=len(name)<=60: raise Error(400,'Nombre requerido de hasta 60 caracteres')
                    db.execute('INSERT INTO users(name,email,password) VALUES(?,?,?)',(name,email,password_hash(password)))
                u=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
                if not u or not hmac.compare_digest(password_hash(password,u['password'].split(':')[0]),u['password']): raise Error(401,'Credenciales incorrectas')
                token=secrets.token_urlsafe(32)
                db.execute('INSERT INTO sessions VALUES(?,?,?)',(token,u['id'],time.time()+86400))
                return self.send(200,dict(token=token,user=dict(id=u['id'],name=u['name'])))
            token=self.headers.get('Authorization','').removeprefix('Bearer ')
            u=db.execute('SELECT u.id,u.name FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires>?',(token,time.time())).fetchone()
            if not u: raise Error(401,'Inicia sesión para continuar')
            uid=u['id']
            if path=='/api/logout' and self.command=='POST':
                db.execute('DELETE FROM sessions WHERE token=?',(token,)); return self.send(200,{'ok':True})
            if path=='/api/rooms':
                if self.command=='POST':
                    name=str(data['name']).strip()
                    if not 1<=len(name)<=80: raise Error(400,'Nombre de sala requerido de hasta 80 caracteres')
                    cur=db.execute('INSERT INTO rooms(name,code,owner) VALUES(?,?,?)',(name,secrets.token_urlsafe(9),uid))
                    db.execute('INSERT INTO members VALUES(?,?)',(cur.lastrowid,uid))
                    return self.send(201,{'id':cur.lastrowid})
                return self.send(200,[dict(r) for r in db.execute('SELECT r.* FROM rooms r JOIN members m ON m.room_id=r.id WHERE m.user_id=?',(uid,))])
            if path=='/api/join' and self.command=='POST':
                r=db.execute('SELECT * FROM rooms WHERE code=?',(data['code'],)).fetchone()
                if not r: raise Error(404,'Invitación no encontrada')
                db.execute('INSERT OR IGNORE INTO members VALUES(?,?)',(r['id'],uid)); return self.send(200,{'id':r['id']})
            room=int(data.get('room',query.get('room',[0])[0]))
            r=db.execute('SELECT r.* FROM rooms r JOIN members m ON m.room_id=r.id WHERE r.id=? AND m.user_id=?',(room,uid)).fetchone()
            if not r: raise Error(403,'No perteneces a esta sala')
            if path=='/api/state' and self.command=='GET':
                matches=[dict(m) for m in db.execute('SELECT m.*,p.home AS prediction_home,p.away AS prediction_away,p.created AS predicted_at FROM matches m LEFT JOIN predictions p ON p.match_id=m.id AND p.user_id=? WHERE m.room_id=? ORDER BY kickoff,m.id',(uid,room))]
                return self.send(200,dict(room=dict(r),user=dict(u),matches=matches,ranking=ranking(db,room),instance=INSTANCE,now=time.time()))
            if path=='/api/matches' and self.command=='POST':
                if r['owner']!=uid: raise Error(403,'Solo el creador administra partidos')
                home=str(data['home']).strip(); away=str(data['away']).strip(); kickoff=float(data['kickoff'])
                if not home or not away or home==away or max(len(home),len(away))>60 or not time.time()+60<kickoff<time.time()+315360000: raise Error(400,'Equipos distintos y fecha futura válida requeridos')
                c=db.execute('INSERT INTO matches(room_id,home,away,kickoff) VALUES(?,?,?,?)',(room,home,away,kickoff)); return self.send(201,{'id':c.lastrowid})
            if path in ('/api/predict','/api/result') and self.command=='POST':
                # Reservar el escritor antes de leer evita carreras resultado/pronóstico.
                db.execute('BEGIN IMMEDIATE')
                m=db.execute('SELECT * FROM matches WHERE id=? AND room_id=?',(int(data['match']),room)).fetchone()
                if not m: raise Error(404,'Partido no encontrado')
                a,b=data['home'],data['away']
                if type(a) is not int or type(b) is not int or not (0<=a<=30 and 0<=b<=30): raise Error(400,'Goles enteros entre 0 y 30')
                now=time.time()
                if path=='/api/predict':
                    if now>=m['kickoff'] or m['home_score'] is not None: raise Error(409,'Pronósticos cerrados')
                    db.execute('INSERT INTO predictions VALUES(?,?,?,?,?) ON CONFLICT(match_id,user_id) DO UPDATE SET home=excluded.home,away=excluded.away,created=excluded.created',(m['id'],uid,a,b,now))
                else:
                    if r['owner']!=uid: raise Error(403,'Solo el creador publica resultados')
                    if now<m['kickoff']: raise Error(409,'El partido todavía no inicia')
                    db.execute('UPDATE matches SET home_score=?,away_score=? WHERE id=?',(a,b,m['id']))
                return self.send(200,{'ok':True})
            raise Error(404,'Ruta no encontrada')

class LabHTTPServer(ThreadingHTTPServer):
    request_queue_size=256

if __name__=='__main__':
    init()
    port=int(os.environ.get('PORT','8001'))
    print(f'Mundial Lab {INSTANCE} en {port}',flush=True)
    LabHTTPServer((os.environ.get('HOST','127.0.0.1'),port),Handler).serve_forever()
