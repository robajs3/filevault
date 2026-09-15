-- Migracja: udostępnianie głównego folderu pokoju (rooms) i podfolderów (room_folders).
-- db.create_all() NIE doda tych kolumn do już istniejących tabel w Postgresie —
-- trzeba uruchomić to ręcznie jednorazowo, np.:
--   psql "$DATABASE_URL" -f migration_add_room_sharing.sql

ALTER TABLE rooms
    ADD COLUMN IF NOT EXISTS share_token VARCHAR(64) UNIQUE,
    ADD COLUMN IF NOT EXISTS share_expires_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS share_password_hash VARCHAR(255);

ALTER TABLE room_folders
    ADD COLUMN IF NOT EXISTS share_token VARCHAR(64) UNIQUE,
    ADD COLUMN IF NOT EXISTS share_expires_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS share_password_hash VARCHAR(255);
