# Структура базы данных

Физическая схема создаётся версионированным кодом app/migrations.py. Для MySQL используется AUTO_INCREMENT, для SQLite — AUTOINCREMENT; логические типы и ограничения одинаковы. Даты UTC хранятся в ISO 8601 в VARCHAR(25), что сохраняет одинаковую сортировку в обоих движках.

| Таблица | Поля | Ключи и ограничения |
|---|---|---|
| users | id INTEGER; login VARCHAR(30); password_hash VARCHAR(255); email VARCHAR(254); phone VARCHAR(16); role VARCHAR(16) | PK id, UNIQUE login, UNIQUE email; роль participant/admin |
| events | id INTEGER; title VARCHAR(160); starts_at VARCHAR(25); place VARCHAR(160); description TEXT; capacity INTEGER | PK id, capacity > 0, индекс starts_at |
| applications | id INTEGER; user_id INTEGER; event_id INTEGER; status VARCHAR(16); status_id INTEGER; created_at VARCHAR(25); payment VARCHAR(16); room VARCHAR(32) | PK id; FK user_id→users, event_id→events, status_id→statuses; UNIQUE(user_id,event_id) |
| statuses | id INTEGER; code VARCHAR(16); name VARCHAR(32) | PK id; UNIQUE code; 1 new/Новая, 2 assigned/Назначено, 3 completed/Завершено |
| reviews | id INTEGER; application_id INTEGER; text TEXT; rating INTEGER; created_at VARCHAR(25) | PK id; FK application_id→applications с ON DELETE CASCADE; UNIQUE application_id; rating 1–5 |
| schema_migrations | version INTEGER | PK version; техническая таблица миграций |

Все перечисленные бизнес-поля обязательны, кроме отсутствующего отзыва: отсутствие представляется отсутствием строки reviews, а не NULL внутри отзыва. Наличие и корректность разрешённых payment и room проверяет сервис. Старое поле applications.status сохранено для совместимости миграции, синхронно обновляется сервисом; источник текущего статуса — status_id.

users 1:N applications, events 1:N applications, statuses 1:N applications, applications 1:0..1 reviews. Пользователь и мероприятие связаны M:N через applications. Один отзыв относится к одной заявке, а не напрямую к пользователю: это сохраняет связь оценки с фактом участия.

Версия 1 создаёт пользователей, мероприятия и заявки со строковым статусом. Версия 2 добавляет справочник статусов, FK status_id, таблицу отзывов и индексы; переносит существующие значения статусов. Новая БД получает обе версии автоматически. Схемы до и после миграции сохранены в er-v1.svg и er.svg.
