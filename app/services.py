import re
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class ValidationError(Exception):
    pass


class PortalService:
    def __init__(self, database):
        self.database = database

    def register(self, data):
        login = data.get('login', '').strip()
        password = data.get('password', '')
        email = data.get('email', '').strip().lower()
        phone = re.sub(r'[\s()\-]', '', data.get('phone', ''))
        if not re.fullmatch(r'[A-Za-z0-9_]{3,30}', login):
            raise ValidationError('Логин: 3–30 латинских букв, цифр или знак подчёркивания.')
        if not 8 <= len(password) <= 128:
            raise ValidationError('Пароль должен содержать от 8 до 128 символов.')
        if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise ValidationError('Укажите корректный email.')
        if not re.fullmatch(r'\+7\d{10}', phone):
            raise ValidationError('Телефон должен иметь формат +7 999 123-45-67.')
        with self.database.connection() as db:
            if db.one('SELECT id FROM users WHERE login=? OR email=?', (login, email)):
                raise ValidationError('Логин или email уже используется.')
            try:
                return db.insert('INSERT INTO users(login,password_hash,email,phone,role) VALUES (?,?,?,?,?)',
                    (login, generate_password_hash(password), email, phone, 'participant'))
            except Exception as error:
                # A concurrent registration may race the pre-check; constraints remain authoritative.
                if 'unique' in str(error).lower() or 'duplicate' in str(error).lower():
                    raise ValidationError('Логин или email уже используется.') from error
                raise

    def authenticate(self, login, password):
        with self.database.connection() as db:
            user = db.one('SELECT * FROM users WHERE login=?', (login.strip(),))
        if user and check_password_hash(user['password_hash'], password):
            return user
        return None

    def apply(self, user_id, data):
        if data.get('payment') not in ('card', 'invoice'):
            raise ValidationError('Выберите способ оплаты.')
        if data.get('room') not in ('main', 'workshop', 'online'):
            raise ValidationError('Выберите помещение.')
        try:
            event_id = int(data.get('event_id', ''))
        except (TypeError, ValueError):
            raise ValidationError('Выберите мероприятие.')
        with self.database.connection() as db:
            suffix = ' FOR UPDATE' if db.mysql else ''
            if not db.mysql:
                db.execute('BEGIN IMMEDIATE')
            event = db.one('SELECT * FROM events WHERE id=?' + suffix, (event_id,))
            if not event or event['starts_at'] <= now():
                raise ValidationError('Регистрация на это мероприятие закрыта.')
            if db.one('SELECT id FROM applications WHERE user_id=? AND event_id=?', (user_id, event_id)):
                raise ValidationError('Вы уже подали заявку на это мероприятие.')
            count = db.one('SELECT COUNT(*) AS n FROM applications WHERE event_id=?', (event_id,))['n']
            if count >= event['capacity']:
                raise ValidationError('Свободных мест больше нет.')
            return db.insert('INSERT INTO applications(user_id,event_id,created_at,payment,room) VALUES (?,?,?,?,?)',
                (user_id, event_id, now(), data['payment'], data['room']))

    def applications(self, user_id=None, status_id=None):
        sql = '''SELECT a.*, u.login, e.title, e.starts_at, e.place, s.name AS status_name,
                 r.rating, r.text AS review_text FROM applications a
                 JOIN users u ON u.id=a.user_id JOIN events e ON e.id=a.event_id
                 JOIN statuses s ON s.id=a.status_id LEFT JOIN reviews r ON r.application_id=a.id'''
        clauses, params = [], []
        if user_id is not None:
            clauses.append('a.user_id=?'); params.append(user_id)
        if status_id is not None:
            clauses.append('a.status_id=?'); params.append(status_id)
        if clauses:
            sql += ' WHERE ' + ' AND '.join(clauses)
        with self.database.connection() as db:
            return db.all(sql + ' ORDER BY a.created_at DESC, a.id DESC LIMIT 200', params)

    def transition(self, application_id, next_id):
        try:
            next_id = int(next_id)
        except (ValueError, TypeError):
            raise ValidationError('Недопустимый статус.')
        with self.database.connection() as db:
            row = db.one('SELECT a.status_id,e.starts_at FROM applications a JOIN events e ON e.id=a.event_id WHERE a.id=?', (application_id,))
            if not row or next_id != row['status_id'] + 1 or next_id not in (2, 3):
                raise ValidationError('Разрешены переходы Новая → Назначено → Завершено.')
            if next_id == 3 and row['starts_at'] > now():
                raise ValidationError('Мероприятие ещё не завершилось.')
            result = db.execute('UPDATE applications SET status_id=?,status=? WHERE id=? AND status_id=?',
                (next_id, {2:'assigned',3:'completed'}[next_id], application_id, row['status_id']))
            if result.rowcount != 1:
                raise ValidationError('Заявка уже изменена. Обновите страницу.')

    def review(self, user_id, application_id, data):
        text = data.get('text', '').strip()
        try:
            rating = int(data.get('rating', ''))
        except (ValueError, TypeError):
            raise ValidationError('Выберите оценку от 1 до 5.')
        if not 1 <= rating <= 5 or not 10 <= len(text) <= 2000:
            raise ValidationError('Оценка: 1–5. Текст отзыва: 10–2000 символов.')
        with self.database.connection() as db:
            row = db.one('''SELECT a.status_id,e.starts_at FROM applications a
                JOIN events e ON e.id=a.event_id WHERE a.id=? AND a.user_id=?''', (application_id, user_id))
            if not row or row['status_id'] != 3 or row['starts_at'] > now():
                raise ValidationError('Отзыв доступен только после завершения вашего мероприятия.')
            if db.one('SELECT id FROM reviews WHERE application_id=?', (application_id,)):
                raise ValidationError('Отзыв уже сохранён.')
            db.execute('INSERT INTO reviews(application_id,text,rating,created_at) VALUES (?,?,?,?)',
                (application_id, text, rating, now()))
