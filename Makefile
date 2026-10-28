-include .env
export
up:        ; docker compose up -d
down:      ; docker compose down
venv:      ; python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
harvest:   ; .venv/bin/python harvest.py
force:     ; .venv/bin/python harvest.py --force
qc:        ; psql -v ON_ERROR_STOP=1 -f qc/qc.sql
runs:      ; psql -c "select run_id,name,status,server_count,fetched,inserted,updated,deleted,seconds from meta.harvest_run order by run_id desc limit 30"
smoke:     ; curl -s localhost:9000/collections.json | head -c 400; echo; curl -s localhost:3000/catalog | head -c 400
.PHONY: up down venv harvest force qc runs smoke
