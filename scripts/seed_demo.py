"""Explicit, repeatable demo fixtures. Never run against a production database."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.services import now

app=create_app()
service=app.extensions['portal']
dbase=app.extensions['database']
with dbase.connection() as db:
    user=db.one("SELECT id FROM users WHERE login='demo'")
if user:
    uid=user['id']
else:
    uid=service.register(dict(login='demo',password='Demo_User_2026!',email='demo@example.test',phone='+79991234567'))
with dbase.connection() as db:
    for eid,status in [(1,1),(2,2),(4,3)]:
        if not db.one('SELECT id FROM applications WHERE user_id=? AND event_id=?',(uid,eid)):
            db.execute('INSERT INTO applications(user_id,event_id,status,status_id,created_at,payment,room) VALUES (?,?,?,?,?,?,?)',
                (uid,eid,{1:'new',2:'assigned',3:'completed'}[status],status,now(),'card','online' if eid==4 else 'main'))
print('Demo participant: demo / Demo_User_2026! (synthetic data)')
