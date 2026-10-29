-- Roles are created without a password; 02_role_passwords.sh sets them from LOADER_PASSWORD / READER_PASSWORD.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS sjrwmd;
CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS qc;

DO $$BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='sjrwmd_loader') THEN
    CREATE ROLE sjrwmd_loader LOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='sjrwmd_reader') THEN
    CREATE ROLE sjrwmd_reader LOGIN; END IF;
END$$;
GRANT USAGE, CREATE ON SCHEMA sjrwmd, meta, qc TO sjrwmd_loader;
GRANT USAGE ON SCHEMA sjrwmd TO sjrwmd_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE sjrwmd_loader IN SCHEMA sjrwmd GRANT SELECT ON TABLES TO sjrwmd_reader;

CREATE TABLE IF NOT EXISTS meta.layer_registry (
  name text PRIMARY KEY, service text NOT NULL, layer_id int NOT NULL, source_url text NOT NULL,
  hub_item_id text, geometry_type text, max_record_count int, last_edit_date timestamptz,
  server_count int, last_harvested_at timestamptz, last_status text,
  schema_sig text, alias text, layer_title text);
CREATE TABLE IF NOT EXISTS meta.harvest_run (
  run_id bigserial PRIMARY KEY, name text NOT NULL, started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz, status text, server_count int, fetched int, inserted int, updated int,
  deleted int, unchanged int, last_edit_date timestamptz, seconds numeric, message text);
CREATE TABLE IF NOT EXISTS qc.results (
  id bigserial PRIMARY KEY, checked_at timestamptz NOT NULL DEFAULT now(), layer text NOT NULL,
  check_name text NOT NULL, expected bigint, actual bigint, passed boolean, detail text);
ALTER TABLE meta.layer_registry OWNER TO sjrwmd_loader;
ALTER TABLE meta.harvest_run OWNER TO sjrwmd_loader;
ALTER TABLE qc.results OWNER TO sjrwmd_loader;
