import sqlite3, os

def get_conn(path:str):
 os.makedirs(os.path.dirname(path), exist_ok=True)
 c=sqlite3.connect(path, check_same_thread=False)
 c.execute('CREATE TABLE IF NOT EXISTS user_prefs(user_id TEXT PRIMARY KEY, mode TEXT, home_address TEXT, work_address TEXT, home_lat REAL, home_lon REAL, work_lat REAL, work_lon REAL)')
 c.commit(); return c

def upsert_prefs(conn,user_id,**kw):
 cur=conn.cursor(); cur.execute('SELECT 1 FROM user_prefs WHERE user_id=?',(user_id,)); ex=cur.fetchone() is not None
 keys=list(kw.keys()); vals=[kw[k] for k in keys]
 if ex:
  setc=','.join([f"{k}=?" for k in keys]); cur.execute(f"UPDATE user_prefs SET {setc} WHERE user_id=?",(*vals,user_id))
 else:
  allk=['user_id']+keys; qm=','.join(['?']*len(allk)); cur.execute(f"INSERT INTO user_prefs({','.join(allk)}) VALUES({qm})",(user_id,*vals))
 conn.commit()

def get_prefs(conn,user_id):
 cur=conn.cursor(); cur.execute('SELECT user_id,mode,home_address,work_address,home_lat,home_lon,work_lat,work_lon FROM user_prefs WHERE user_id=?',(user_id,))
 r=cur.fetchone()
 if not r: return {'user_id':user_id,'mode':'balanced'}
 cols=[d[0] for d in cur.description]; return {k:v for k,v in zip(cols,r)}
