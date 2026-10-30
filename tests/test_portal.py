import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.db import Database
from app.migrations import migrate
from app.services import ValidationError


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        url = os.environ.get('TEST_DATABASE_URL', 'sqlite:///' + str(Path(self.temp.name) / 'test.db'))
        if url.startswith('mysql://'):
            with Database(url).connection() as db:
                db.execute('SET FOREIGN_KEY_CHECKS=0')
                for table in ('reviews', 'applications', 'statuses', 'events', 'users', 'schema_migrations'):
                    db.execute('DROP TABLE IF EXISTS ' + table)
                db.execute('SET FOREIGN_KEY_CHECKS=1')
        self.app = create_app(dict(TESTING=True, SECRET_KEY='test-only', DATABASE_URL=url, ADMIN_PASSWORD='Test_Admin_2026'))
        self.client = self.app.test_client()
        self.db = self.app.extensions['database']
        self.service = self.app.extensions['portal']
        self.user_id = self.service.register(dict(login='participant', password='Test_User_2026', email='user@example.test', phone='+79991234567'))

    def tearDown(self):
        self.temp.cleanup()

    def post(self, url, data=None, client=None):
        client = client or self.client
        client.get('/login')
        with client.session_transaction() as session:
            token = session['csrf']
        return client.post(url, data={**(data or {}), 'csrf':token})

    def login(self, admin=False, client=None):
        return self.post('/login', dict(login='admin' if admin else 'participant', password='Test_Admin_2026' if admin else 'Test_User_2026'), client)

    def apply(self):
        return self.service.apply(self.user_id, dict(event_id='1', payment='card', room='main'))

    def complete(self, application_id):
        self.service.transition(application_id, 2)
        with self.db.connection() as db:
            db.execute("UPDATE events SET starts_at='2025-01-01T00:00:00Z' WHERE id=1")
        self.service.transition(application_id, 3)

    def test_registration_and_password_hash(self):
        with self.db.connection() as db:
            user = db.one('SELECT * FROM users WHERE id=?', (self.user_id,))
        self.assertNotIn('Test_User_2026', user['password_hash'])
        self.assertTrue(user['password_hash'].startswith('scrypt:'))
        self.assertIsNotNone(self.service.authenticate('participant', 'Test_User_2026'))

    def test_invalid_fields(self):
        valid = dict(login='validuser', password='Password_2026', email='v@example.test', phone='+79991234567')
        for key, value in [('login', "x' OR 1=1--"), ('password', 'short'), ('email','bad'), ('phone','123')]:
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.service.register({**valid, key:value})

    def test_duplicate_registration(self):
        with self.assertRaises(ValidationError):
            self.service.register(dict(login='participant',password='Password_2026',email='another@example.test',phone='+79991234567'))

    def test_login_csrf_rotation(self):
        self.client.get('/login')
        with self.client.session_transaction() as s:
            old = s['csrf']
        self.assertEqual(self.login().status_code, 303)
        with self.client.session_transaction() as s:
            self.assertNotEqual(old, s['csrf'])
        self.assertEqual(self.client.post('/logout',data={'csrf':old}).status_code, 400)

    def test_wrong_password(self):
        self.assertEqual(self.post('/login',dict(login='participant',password='incorrect')).status_code,422)

    def test_sql_injection_is_data(self):
        self.assertIsNone(self.service.authenticate("' OR 1=1--", 'anything'))
        self.assertEqual(len(self.service.applications()), 0)

    def test_csrf_required(self):
        self.assertEqual(self.client.post('/login',data={'login':'admin'}).status_code,400)

    def test_guest_and_participant_permissions(self):
        self.assertEqual(self.client.get('/applications').status_code,302)
        self.login()
        self.assertEqual(self.client.get('/admin').status_code,403)
        self.assertEqual(self.post('/admin/1/status',dict(status_id=2)).status_code,403)

    def test_create_read_delete(self):
        self.login()
        response = self.post('/applications/new',dict(event_id=1,payment='card',room='main'))
        self.assertEqual(response.status_code,303)
        rows=self.service.applications(self.user_id)
        self.assertEqual(len(rows),1)
        self.assertEqual(self.post(f'/applications/{rows[0]["id"]}/delete').status_code,303)
        self.assertEqual(len(self.service.applications(self.user_id)),0)

    def test_duplicate_application(self):
        self.apply()
        with self.assertRaises(ValidationError): self.apply()

    def test_payment_room_allowlist(self):
        for values in [dict(payment='cash',room='main'),dict(payment='card',room='invalid')]:
            with self.assertRaises(ValidationError):
                self.service.apply(self.user_id,dict(event_id=1,**values))

    def test_closed_and_full_events(self):
        with self.assertRaises(ValidationError):
            self.service.apply(self.user_id,dict(event_id=4,payment='card',room='main'))
        with self.db.connection() as db:
            db.execute('UPDATE events SET capacity=1 WHERE id=1')
        self.apply()
        other=self.service.register(dict(login='other',password='Password_2026',email='o@example.test',phone='+79991234567'))
        with self.assertRaises(ValidationError):
            self.service.apply(other,dict(event_id=1,payment='card',room='main'))

    def test_ownership(self):
        application_id=self.apply()
        other=self.app.test_client()
        self.service.register(dict(login='other',password='Password_2026',email='o@example.test',phone='+79991234567'))
        self.post('/login',dict(login='other',password='Password_2026'),other)
        self.assertEqual(other.get(f'/applications/{application_id}/review').status_code,404)
        self.assertEqual(self.post(f'/applications/{application_id}/delete',client=other).status_code,404)
        self.assertNotIn('Веб без границ'.encode(),other.get('/applications').data)

    def test_ordered_statuses(self):
        aid=self.apply()
        with self.assertRaises(ValidationError): self.service.transition(aid,3)
        self.service.transition(aid,2)
        with self.assertRaises(ValidationError): self.service.transition(aid,1)
        with self.assertRaises(ValidationError): self.service.transition(aid,3)

    def test_admin_filter(self):
        aid=self.apply()
        self.login(admin=True)
        self.assertEqual(self.post(f'/admin/{aid}/status',dict(status_id=2)).status_code,303)
        self.assertEqual(len(self.service.applications(status_id=1)),0)
        self.assertEqual(len(self.service.applications(status_id=2)),1)
        self.assertIn('Назначено'.encode(),self.client.get('/admin?status=2').data)

    def test_review_after_completion_and_no_duplicates(self):
        aid=self.apply()
        review=dict(text='Очень полезная конференция',rating='5')
        with self.assertRaises(ValidationError): self.service.review(self.user_id,aid,review)
        self.complete(aid)
        self.service.review(self.user_id,aid,review)
        with self.assertRaises(ValidationError): self.service.review(self.user_id,aid,review)
        self.assertEqual(self.service.applications(self.user_id)[0]['rating'],5)

    def test_review_validation(self):
        aid=self.apply(); self.complete(aid)
        for data in [dict(text='short',rating=5),dict(text='Достаточно длинный отзыв',rating=6)]:
            with self.assertRaises(ValidationError): self.service.review(self.user_id,aid,data)

    def test_xss_escaped(self):
        aid=self.apply(); self.complete(aid)
        self.service.review(self.user_id,aid,dict(text='<script>alert(1)</script>',rating=5))
        self.login()
        content=self.client.get('/applications').data
        self.assertNotIn(b'<script>alert(1)</script>',content)
        self.assertIn(b'&lt;script&gt;',content)

    def test_cookie_and_security_headers(self):
        response=self.client.get('/login')
        cookie=response.headers['Set-Cookie']
        self.assertIn('HttpOnly',cookie); self.assertIn('SameSite=Lax',cookie)
        self.assertEqual(response.headers['X-Frame-Options'],'DENY')
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        self.assertIn("object-src 'none'",response.headers['Content-Security-Policy'])

    def test_all_pages_render(self):
        for url in ['/','/register','/login','/not-found']:
            response=self.client.get(url)
            self.assertEqual(response.status_code,404 if url=='/not-found' else 200)
        self.login()
        for url in ['/applications','/applications/new','/account']:
            self.assertEqual(self.client.get(url).status_code,200)

    def test_migration_preserves_legacy_status(self):
        if self.db.mysql:
            legacy=self.db
            with legacy.connection() as db:
                db.execute('SET FOREIGN_KEY_CHECKS=0')
                for table in ('reviews','applications','statuses','events','users','schema_migrations'):
                    db.execute('DROP TABLE IF EXISTS '+table)
                db.execute('SET FOREIGN_KEY_CHECKS=1')
        else:
            legacy=Database('sqlite:///'+str(Path(self.temp.name)/'legacy.db'))
        with legacy.connection() as db:
            migrate(db,target=1)
            uid=db.insert("INSERT INTO users(login,password_hash,email,phone) VALUES ('legacy','hash','l@example.test','+79991234567')")
            eid=db.insert("INSERT INTO events(title,starts_at,place,description,capacity) VALUES ('Legacy','2025-01-01','Moscow','test',10)")
            db.execute("INSERT INTO applications(user_id,event_id,status,created_at,payment,room) VALUES (?,?,'completed','2025-01-01','card','main')",(uid,eid))
        legacy.migrate(); legacy.migrate()
        with legacy.connection() as db:
            self.assertEqual(db.one('SELECT status_id FROM applications')['status_id'],3)
            self.assertEqual(db.one('SELECT COUNT(*) AS n FROM schema_migrations')['n'],2)
            self.assertEqual(db.one('''SELECT COUNT(*) AS n FROM applications a
                LEFT JOIN users u ON u.id=a.user_id LEFT JOIN events e ON e.id=a.event_id
                LEFT JOIN statuses s ON s.id=a.status_id
                WHERE u.id IS NULL OR e.id IS NULL OR s.id IS NULL''')['n'],0)
            if not db.mysql:
                self.assertEqual(db.all('PRAGMA foreign_key_check'),[])

    def test_foreign_keys(self):
        with self.assertRaises(Exception):
            with self.db.connection() as db:
                db.execute("INSERT INTO applications(user_id,event_id,created_at,payment,room) VALUES (999,999,'2025','card','main')")


if __name__=='__main__': unittest.main(verbosity=2)
