import os
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta
from functools import wraps
from pathlib import Path
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash
from .db import Database
from .services import PortalService, ValidationError, now


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
        DATABASE_URL=os.environ.get('DATABASE_URL', 'sqlite:///' + str(Path(app.instance_path) / 'portal.db')),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30), MAX_CONTENT_LENGTH=32768)
    if config:
        app.config.update(config)
    database = Database(app.config['DATABASE_URL'])
    database.migrate()
    service = PortalService(database)
    app.extensions.update(database=database, portal=service)
    attempts = defaultdict(deque)

    with database.connection() as db:
        if not db.one('SELECT id FROM events LIMIT 1'):
            for values in [
                ('Веб без границ', '2027-04-16T10:00:00Z', 'Москва · Технопарк', 'Архитектура, интерфейсы и доступность современных веб-приложений.', 120),
                ('Дизайн в деталях', '2027-05-21T11:00:00Z', 'Москва · Дизайн-центр', 'Практикум о типографике, визуальных системах и пользовательском опыте.', 80),
                ('Данные и решения', '2027-06-11T09:00:00Z', 'Онлайн', 'Базы данных, производительность и инженерные решения.', 200),
                ('Frontend встреча', '2025-09-20T10:00:00Z', 'Москва · Технопарк', 'Архивная конференция для демонстрации завершённых заявок и отзывов.', 100)]:
                db.execute('INSERT INTO events(title,starts_at,place,description,capacity) VALUES (?,?,?,?,?)', values)
        admin_password = app.config.get('ADMIN_PASSWORD') or os.environ.get('ADMIN_PASSWORD')
        if admin_password and not db.one('SELECT id FROM users WHERE login=?', ('admin',)):
            if len(admin_password) < 8:
                raise ValueError('ADMIN_PASSWORD must contain at least 8 characters')
            db.execute('INSERT INTO users(login,password_hash,email,phone,role) VALUES (?,?,?,?,?)',
                ('admin', generate_password_hash(admin_password), 'admin@example.test', '+79990000000', 'admin'))

    def protected(admin=False):
        def decorator(view):
            @wraps(view)
            def wrapper(*args, **kwargs):
                if g.user is None:
                    return redirect(url_for('login'))
                if admin and g.user['role'] != 'admin':
                    abort(403)
                return view(*args, **kwargs)
            return wrapper
        return decorator

    @app.before_request
    def guard():
        g.user = None
        if session.get('user_id'):
            with database.connection() as db:
                g.user = db.one('SELECT id,login,email,phone,role FROM users WHERE id=?', (session['user_id'],))
        session.setdefault('csrf', secrets.token_urlsafe(32))
        if request.method == 'POST':
            token = request.form.get('csrf', '')
            if not token or not secrets.compare_digest(token, session['csrf']):
                abort(400, description='Срок действия формы истёк. Обновите страницу.')

    @app.after_request
    def security(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.context_processor
    def common():
        return dict(current_time=now(), payment_names={'card':'Банковская карта','invoice':'Счёт для организации'},
            room_names={'main':'Большой зал','workshop':'Мастерская','online':'Онлайн'})

    @app.get('/')
    def index():
        with database.connection() as db:
            events = db.all('SELECT * FROM events ORDER BY starts_at')
        return render_template('index.html', events=events)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            try:
                service.register(request.form)
                flash('Аккаунт создан. Войдите, чтобы подать заявку.', 'success')
                return redirect(url_for('login'), code=303)
            except ValidationError as error:
                flash(str(error), 'error')
                return render_template('register.html'), 422
        return render_template('register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            key = request.remote_addr or 'local'
            q = attempts[key]
            while q and q[0] < time.monotonic() - 60:
                q.popleft()
            if len(q) >= 10 and not app.testing:
                flash('Слишком много попыток. Повторите через минуту.', 'error')
                return render_template('login.html'), 429
            user = service.authenticate(request.form.get('login', ''), request.form.get('password', ''))
            if user:
                attempts.pop(key, None)
                session.clear()
                session.update(user_id=user['id'], csrf=secrets.token_urlsafe(32))
                session.permanent = True
                return redirect(url_for('admin' if user['role'] == 'admin' else 'applications'), code=303)
            q.append(time.monotonic())
            flash('Неверный логин или пароль.', 'error')
            return render_template('login.html'), 422
        return render_template('login.html')

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('index'), code=303)

    @app.get('/account')
    @protected()
    def account():
        return render_template('account.html')

    @app.get('/applications')
    @protected()
    def applications():
        return render_template('applications.html', applications=service.applications(g.user['id']))

    @app.route('/applications/new', methods=['GET', 'POST'])
    @protected()
    def apply():
        status = 200
        if request.method == 'POST':
            try:
                service.apply(g.user['id'], request.form)
                flash('Заявка отправлена. Следите за её статусом в личном кабинете.', 'success')
                return redirect(url_for('applications'), code=303)
            except ValidationError as error:
                flash(str(error), 'error'); status = 422
        with database.connection() as db:
            events = db.all('SELECT * FROM events WHERE starts_at>? ORDER BY starts_at', (now(),))
        return render_template('apply.html', events=events), status

    @app.post('/applications/<int:application_id>/delete')
    @protected()
    def delete(application_id):
        with database.connection() as db:
            result = db.execute('DELETE FROM applications WHERE id=? AND user_id=? AND status_id=1', (application_id, g.user['id']))
            if result.rowcount != 1:
                abort(404)
        flash('Заявка отменена.', 'success')
        return redirect(url_for('applications'), code=303)

    @app.route('/applications/<int:application_id>/review', methods=['GET', 'POST'])
    @protected()
    def review(application_id):
        rows = [a for a in service.applications(g.user['id']) if a['id'] == application_id]
        if not rows:
            abort(404)
        row = rows[0]
        if row['status_id'] != 3 or row['starts_at'] > now() or row['rating'] is not None:
            abort(403)
        if request.method == 'POST':
            try:
                service.review(g.user['id'], application_id, request.form)
                flash('Спасибо! Ваш отзыв сохранён.', 'success')
                return redirect(url_for('applications'), code=303)
            except ValidationError as error:
                flash(str(error), 'error')
                return render_template('review.html', application=row), 422
        return render_template('review.html', application=row)

    @app.get('/admin')
    @protected(admin=True)
    def admin():
        status_id = request.args.get('status', type=int)
        if status_id not in (1, 2, 3):
            status_id = None
        rows = service.applications(status_id=status_id)
        with database.connection() as db:
            counts = db.all('SELECT s.id,s.name,COUNT(a.id) AS n FROM statuses s LEFT JOIN applications a ON a.status_id=s.id GROUP BY s.id,s.name ORDER BY s.id')
        return render_template('admin.html', applications=rows, counts=counts, selected=status_id)

    @app.post('/admin/<int:application_id>/status')
    @protected(admin=True)
    def status(application_id):
        try:
            service.transition(application_id, request.form.get('status_id'))
            flash('Статус заявки обновлён.', 'success')
        except ValidationError as error:
            flash(str(error), 'error')
        return redirect(url_for('admin'), code=303)

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def error_page(error):
        return render_template('error.html', code=error.code, message=error.description), error.code

    return app
