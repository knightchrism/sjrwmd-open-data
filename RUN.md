# RUN — sjrwmd-open-data
Public repo (origin: github.com/knightchrism/sjrwmd-open-data).
- DB: `cd db && docker compose up -d` (PostGIS on 127.0.0.1:55433; secrets in db/.env, git-ignored). See MIGRATION.md (local, untracked).
- Do not start the root docker-compose.yml as-is (martin :3000 collides with fl-gis-tracker Dagster).
- `wip/` (local only, in .git/info/exclude): sjrwmd-fullmirror-wip.patch, SJRWMD-FROZEN.md.
