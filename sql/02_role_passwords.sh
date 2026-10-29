#!/usr/bin/env bash
# Runs once from /docker-entrypoint-initdb.d after 01_init.sql. Sets role passwords from the environment
# (no defaults: initialization aborts if either is missing). Values are passed as psql variables, never interpolated.
set -eo pipefail   # (no -u: the postgres entrypoint may source this file)
: "${LOADER_PASSWORD:?LOADER_PASSWORD is required}"
: "${READER_PASSWORD:?READER_PASSWORD is required}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v loader_pw="$LOADER_PASSWORD" -v reader_pw="$READER_PASSWORD" <<'SQL'
ALTER ROLE sjrwmd_loader PASSWORD :'loader_pw';
ALTER ROLE sjrwmd_reader PASSWORD :'reader_pw';
SQL
