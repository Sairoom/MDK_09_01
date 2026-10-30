"""Versioned, additive migration preserving existing applications."""
V1 = [
    '''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, login VARCHAR(30) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL, email VARCHAR(254) NOT NULL UNIQUE,
        phone VARCHAR(16) NOT NULL, role VARCHAR(16) NOT NULL DEFAULT 'participant',
        CHECK (role IN ('participant','admin')))''',
    '''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title VARCHAR(160) NOT NULL,
        starts_at VARCHAR(25) NOT NULL, place VARCHAR(160) NOT NULL,
        description TEXT NOT NULL, capacity INTEGER NOT NULL CHECK (capacity > 0))''',
    '''CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        event_id INTEGER NOT NULL, status VARCHAR(16) NOT NULL DEFAULT 'new',
        created_at VARCHAR(25) NOT NULL, payment VARCHAR(16) NOT NULL,
        room VARCHAR(32) NOT NULL, UNIQUE (user_id,event_id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (event_id) REFERENCES events(id))''',
]
V2 = [
    '''CREATE TABLE IF NOT EXISTS statuses (
        id INTEGER PRIMARY KEY, code VARCHAR(16) NOT NULL UNIQUE,
        name VARCHAR(32) NOT NULL)''',
    'ALTER TABLE applications ADD COLUMN status_id INTEGER NOT NULL DEFAULT 1 REFERENCES statuses(id)',
    '''CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT, application_id INTEGER NOT NULL UNIQUE,
        text TEXT NOT NULL, rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
        created_at VARCHAR(25) NOT NULL,
        FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE)''',
    'CREATE INDEX idx_applications_status_created ON applications(status_id, created_at)',
    'CREATE INDEX idx_events_starts ON events(starts_at)',
]


def ddl(sql, mysql):
    if mysql:
        sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'INTEGER PRIMARY KEY AUTO_INCREMENT')
    return sql


def migrate(db, target=2):
    db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)')
    done = {row['version'] for row in db.all('SELECT version FROM schema_migrations')}
    if 1 not in done:
        for sql in V1:
            db.execute(ddl(sql, db.mysql))
        db.execute('INSERT INTO schema_migrations(version) VALUES (1)')
    if target >= 2 and 2 not in done:
        db.execute(ddl(V2[0], db.mysql))
        for item in [(1, 'new', 'Новая'), (2, 'assigned', 'Назначено'), (3, 'completed', 'Завершено')]:
            db.execute('INSERT INTO statuses(id,code,name) VALUES (?,?,?)', item)
        if db.mysql:
            db.execute('ALTER TABLE applications ADD COLUMN status_id INTEGER NOT NULL DEFAULT 1')
            db.execute('ALTER TABLE applications ADD CONSTRAINT fk_application_status FOREIGN KEY (status_id) REFERENCES statuses(id)')
        else:
            # SQLite cannot add a non-null REFERENCES column to a populated table.
            # Rebuild inside the surrounding transaction, preserving primary keys.
            sql = V1[2].replace('applications (', 'applications_v2 (').replace(
                'created_at VARCHAR(25)',
                'status_id INTEGER NOT NULL DEFAULT 1 REFERENCES statuses(id), created_at VARCHAR(25)')
            db.execute(sql)
            db.execute('''INSERT INTO applications_v2
                (id,user_id,event_id,status,created_at,payment,room,status_id)
                SELECT id,user_id,event_id,status,created_at,payment,room,
                CASE status WHEN 'assigned' THEN 2 WHEN 'completed' THEN 3 ELSE 1 END
                FROM applications''')
            db.execute('DROP TABLE applications')
            db.execute('ALTER TABLE applications_v2 RENAME TO applications')
        db.execute('UPDATE applications SET status_id = CASE status WHEN \'assigned\' THEN 2 WHEN \'completed\' THEN 3 ELSE 1 END')
        for sql in V2[2:]:
            db.execute(ddl(sql, db.mysql))
        db.execute('INSERT INTO schema_migrations(version) VALUES (2)')
