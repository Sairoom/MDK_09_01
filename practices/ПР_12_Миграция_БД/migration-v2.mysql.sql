-- Apply once to version 1. Back up the database before schema changes.
CREATE TABLE IF NOT EXISTS statuses (
        id INTEGER PRIMARY KEY, code VARCHAR(16) NOT NULL UNIQUE,
        name VARCHAR(32) NOT NULL);
INSERT INTO statuses VALUES (1,'new','Новая'),(2,'assigned','Назначено'),(3,'completed','Завершено');
ALTER TABLE applications ADD COLUMN status_id INTEGER NOT NULL DEFAULT 1;
UPDATE applications SET status_id=CASE status WHEN 'assigned' THEN 2 WHEN 'completed' THEN 3 ELSE 1 END;
ALTER TABLE applications ADD CONSTRAINT fk_application_status FOREIGN KEY(status_id) REFERENCES statuses(id);
CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTO_INCREMENT, application_id INTEGER NOT NULL UNIQUE,
        text TEXT NOT NULL, rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
        created_at VARCHAR(25) NOT NULL,
        FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE);
CREATE INDEX idx_applications_status_created ON applications(status_id, created_at);
CREATE INDEX idx_events_starts ON events(starts_at);
INSERT INTO schema_migrations VALUES (2);
