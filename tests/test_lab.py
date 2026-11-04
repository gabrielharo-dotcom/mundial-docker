import unittest, tempfile, os, sys, time, threading, json, urllib.request, urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from http.server import ThreadingHTTPServer

class ScoreTests(unittest.TestCase):
    def score(self,a,b,c,d,lead=90000):return app.points(a,b,c,d,0,lead)
    def test_exact(self):self.assertEqual(self.score(2,1,2,1)['base'],5)
    def test_winner_only(self):self.assertEqual(self.score(1,0,3,1)['base'],3)
    def test_difference(self):self.assertEqual(self.score(3,1,2,0)['base'],5)
    def test_wrong(self):self.assertEqual(self.score(0,2,1,0)['base'],0)
    def test_draw(self):self.assertEqual(self.score(2,2,1,1)['base'],5)
    def test_exact_draw(self):self.assertEqual(self.score(0,0,0,0)['base'],5)
    def test_wrong_direction(self):self.assertEqual(self.score(2,0,0,2)['base'],0)
    def test_more_24(self):self.assertEqual(self.score(1,0,0,2,86401)['early'],1)
    def test_exactly_24(self):self.assertEqual(self.score(1,0,1,0,86400)['early'],0)
    def test_ten_minutes(self):self.assertEqual(self.score(1,0,1,0,600)['early'],0)

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();app.DB=str(Path(cls.tmp.name)/'test.db');app.init()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.tmp.cleanup()
    def req(self,path,data=None,token=''):
        req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as r:
            with r:return r.code,json.load(r)
    def setUp(self):
        suffix=str(time.time_ns());_,self.a=self.req('/api/register',dict(name='Ana',email=suffix+'@a.local',password='Password123!'))
        _,self.b=self.req('/api/register',dict(name='Luis',email=suffix+'@b.local',password='Password123!'))
        self.ta=self.a['token'];self.tb=self.b['token'];_,r=self.req('/api/rooms',{'name':'Test'},self.ta);self.room=r['id']
        _,s=self.req('/api/state?room='+str(self.room),token=self.ta);self.code=s['room']['code']
        _,m=self.req('/api/matches',dict(room=self.room,home='A',away='B',kickoff=time.time()+172800),self.ta);self.mid=m['id']
    def join(self):return self.req('/api/join',{'code':self.code},self.tb)
    def predict(self,a=2,b=1,token=None):return self.req('/api/predict',dict(room=self.room,match=self.mid,home=a,away=b),token or self.ta)
    def result(self,a=2,b=1,token=None):return self.req('/api/result',dict(room=self.room,match=self.mid,home=a,away=b),token or self.ta)
    def past(self):
        with app.connect() as db:db.execute('UPDATE matches SET kickoff=? WHERE id=?',(time.time()-10,self.mid))
    def test_auth_required(self):self.assertEqual(self.req('/api/rooms')[0],401)
    def test_room_isolation(self):self.assertEqual(self.req('/api/state?room='+str(self.room),token=self.tb)[0],403)
    def test_invitation(self):self.assertEqual(self.join()[0],200);self.assertEqual(self.join()[0],200)
    def test_bad_invite(self):self.assertEqual(self.req('/api/join',{'code':'bad'},self.tb)[0],404)
    def test_predict_and_update(self):
        self.predict();self.predict(3,0)
        with app.connect() as db:
            rows=db.execute('SELECT * FROM predictions WHERE match_id=?',(self.mid,)).fetchall();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['home'],3)
    def test_negative_goals(self):self.assertEqual(self.predict(-1,0)[0],400)
    def test_decimal_goals(self):self.assertEqual(self.predict(1.5,0)[0],400)
    def test_boolean_goals(self):self.assertEqual(self.predict(True,0)[0],400)
    def test_closed_prediction(self):self.past();self.assertEqual(self.predict()[0],409)
    def test_early_result_blocked(self):self.assertEqual(self.result()[0],409)
    def test_result_owner(self):self.join();self.past();self.assertEqual(self.result(token=self.tb)[0],403)
    def test_match_owner(self):self.join();self.assertEqual(self.req('/api/matches',dict(room=self.room,home='X',away='Y',kickoff=time.time()+1000),self.tb)[0],403)
    def test_result_and_correction(self):
        self.predict();self.past();self.result();self.result(0,2)
        _,s=self.req('/api/state?room='+str(self.room),token=self.ta);self.assertEqual(s['ranking'][0]['points'],0)
    def test_logout(self):self.req('/api/logout',{},self.ta);self.assertEqual(self.req('/api/rooms',token=self.ta)[0],401)
    def test_expired_session(self):
        with app.connect() as db:db.execute('UPDATE sessions SET expires=0 WHERE token=?',(self.ta,))
        self.assertEqual(self.req('/api/rooms',token=self.ta)[0],401)
    def test_updated_time(self):
        self.predict()
        with app.connect() as db:db.execute('UPDATE predictions SET created=1 WHERE match_id=?',(self.mid,))
        self.predict(3,2)
        with app.connect() as db:self.assertGreater(db.execute('SELECT created FROM predictions WHERE match_id=?',(self.mid,)).fetchone()[0],time.time()-10)
    def test_streak_six_and_reset_missing(self):
        with app.connect() as db:
            db.execute('DELETE FROM matches WHERE id=?',(self.mid,))
            for i in range(7):
                k=time.time()-1000+i*10
                mid=db.execute('INSERT INTO matches(room_id,home,away,kickoff,home_score,away_score) VALUES(?,?,?,?,2,1)',(self.room,'A','B',k)).lastrowid
                if i<6:db.execute('INSERT INTO predictions VALUES(?,?,?,?,?)',(mid,self.a['user']['id'],2,1,k-600))
            rank=app.ranking(db,self.room)[0]
            self.assertEqual(rank['points'],34);self.assertEqual(rank['streak'],0)
            self.assertEqual([d['streak_bonus'] for d in rank['detail']],[0,0,2,0,0,2,0])
    def test_pending_holds_later_scores(self):
        self.predict()
        with app.connect() as db:
            k=time.time()+200000
            mid=db.execute('INSERT INTO matches(room_id,home,away,kickoff,home_score,away_score) VALUES(?,?,?,?,2,1)',(self.room,'C','D',k)).lastrowid
            db.execute('INSERT INTO predictions VALUES(?,?,?,?,?)',(mid,self.a['user']['id'],2,1,k-600))
            self.assertEqual(app.ranking(db,self.room)[0]['points'],0)
    def test_bad_password(self):self.assertEqual(self.req('/api/login',dict(email='unknown@local',password='Password123!'))[0],401)

if __name__=='__main__':unittest.main(verbosity=2)
