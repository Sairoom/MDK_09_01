-- MySQL 8.4, UTF-8. Fresh database schema.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTO_INCREMENT, login VARCHAR(30) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL, email VARCHAR(254) NOT NULL UNIQUE,
        phone VARCHAR(16) NOT NULL, role VARCHAR(16) NOT NULL DEFAULT 'participant',
        CHECK (role IN ('participant','admin')));

CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTO_INCREMENT, title VARCHAR(160) NOT NULL,
        starts_at VARCHAR(25) NOT NULL, place VARCHAR(160) NOT NULL,
        description TEXT NOT NULL, capacity INTEGER NOT NULL CHECK (capacity > 0));

CREATE TABLE statuses (id INTEGER PRIMARY KEY, code VARCHAR(16) NOT NULL UNIQUE, name VARCHAR(32) NOT NULL);

INSERT INTO statuses VALUES (1,'new','Новая'),(2,'assigned','Назначено'),(3,'completed','Завершено');

CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTO_INCREMENT, user_id INTEGER NOT NULL,
        event_id INTEGER NOT NULL, status VARCHAR(16) NOT NULL DEFAULT 'new',
        status_id INTEGER NOT NULL DEFAULT 1, FOREIGN KEY (status_id) REFERENCES statuses(id), created_at VARCHAR(25) NOT NULL, payment VARCHAR(16) NOT NULL,
        room VARCHAR(32) NOT NULL, UNIQUE (user_id,event_id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (event_id) REFERENCES events(id));

CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTO_INCREMENT, application_id INTEGER NOT NULL UNIQUE,
        text TEXT NOT NULL, rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
        created_at VARCHAR(25) NOT NULL,
        FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE);

CREATE INDEX idx_applications_status_created ON applications(status_id, created_at);

CREATE INDEX idx_events_starts ON events(starts_at);

CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY);

INSERT INTO schema_migrations VALUES (1),(2);