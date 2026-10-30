"""Small DB adapter: SQLite for a zero-setup demo, MySQL for Compose/CI."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote, urlparse


class Database:
    def __init__(self, url):
        self.url = url
        self.mysql = url.startswith('mysql://')

    @contextmanager
    def connection(self):
        if self.mysql:
            import pymysql
            u = urlparse(self.url)
            conn = pymysql.connect(host=u.hostname, port=u.port or 3306,
                user=unquote(u.username or ''), password=unquote(u.password or ''),
                database=u.path.lstrip('/'), charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor, autocommit=False)
        else:
            path = self.url.removeprefix('sqlite:///')
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, timeout=15)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA foreign_keys=ON')
        try:
            yield Session(conn, self.mysql)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self):
        from .migrations import migrate
        with self.connection() as db:
            migrate(db)


class Session:
    def __init__(self, conn, mysql):
        self.conn, self.mysql = conn, mysql

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql.replace('?', '%s') if self.mysql else sql, params)
        return cur

    def all(self, sql, params=()):
        cur = self.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def one(self, sql, params=()):
        cur = self.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row is not None else None

    def insert(self, sql, params=()):
        return self.execute(sql, params).lastrowid
