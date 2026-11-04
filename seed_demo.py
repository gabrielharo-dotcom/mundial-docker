"""Datos ficticios reproducibles, nunca resultados oficiales."""
import app, time
def seed():
    app.init()
    with app.connect() as db:
        if db.execute('SELECT 1 FROM users WHERE email=?',('ana@demo.local',)).fetchone():
            print('Demo ya existe. No se modifican sus datos.');return
        ids=[]
        for name,email in [('Ana Torres','ana'),('Luis Mendoza','luis'),('Sofía Reyes','sofia'),('Diego Pérez','diego')]:
            ids.append(db.execute('INSERT INTO users(name,email,password) VALUES(?,?,?)',(name,email+'@demo.local',app.password_hash('Mundial2026!'))).lastrowid)
        room=db.execute('INSERT INTO rooms(name,code,owner) VALUES(?,?,?)',('Mundial con amigos','MUNDIAL-DEMO',ids[0])).lastrowid
        for uid in ids:db.execute('INSERT INTO members VALUES(?,?)',(room,uid))
        now=time.time()
        fixtures=[('Argentina','Francia',-72,2,1),('Brasil','España',-48,2,0),('Alemania','Japón',-24,1,1),('Perú','Portugal',48,None,None),('México','Uruguay',72,None,None)]
        preds=[[(2,1),(3,1),(0,0)],[(1,0),(2,0),(2,2)],[(0,1),(1,0),(0,0)],[(1,2),(0,2),(1,0)]]
        for i,(home,away,h,rh,ra) in enumerate(fixtures):
            kickoff=now+h*3600
            mid=db.execute('INSERT INTO matches(room_id,home,away,kickoff,home_score,away_score) VALUES(?,?,?,?,?,?)',(room,home,away,kickoff,rh,ra)).lastrowid
            if i<3:
                for j,uid in enumerate(ids):
                    a,b=preds[j][i];db.execute('INSERT INTO predictions VALUES(?,?,?,?,?)',(mid,uid,a,b,kickoff-90000 if j!=3 else kickoff-600))
    print('Demo lista: ana@demo.local / Mundial2026! | invitación MUNDIAL-DEMO')
if __name__=='__main__':seed()
