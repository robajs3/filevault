-- Migracja: limit rozmiaru pliku per użytkownik (users.max_upload_mb).
-- Tabela `settings` (limit domyślny) powstanie sama przez db.create_all(),
-- ale db.create_all() NIE dodaje kolumn do istniejących tabel — uruchom jednorazowo:
--   psql "$DATABASE_URL" -f migration_add_max_upload.sql

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS max_upload_mb INTEGER;
