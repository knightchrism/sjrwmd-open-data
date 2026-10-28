-- QC over every harvested layer; one batch of rows per layer in qc.results.
SET client_min_messages = warning;
DO $$
DECLARE r record; n bigint; bad bigint; nulls bigint; rep bigint; srids text; batch timestamptz := clock_timestamp();
BEGIN
  FOR r IN SELECT * FROM meta.layer_registry ORDER BY name LOOP
    IF r.geometry_type IS NULL OR r.geometry_type = '' THEN
      EXECUTE format('SELECT count(*) FROM sjrwmd.%I', r.name) INTO n;
      INSERT INTO qc.results(checked_at, layer, check_name, expected, actual, passed, detail)
        VALUES (batch, r.name, 'count_vs_server', r.server_count, n, n = r.server_count, 'table (no geometry)');
      CONTINUE;
    END IF;
    EXECUTE format($q$SELECT count(*),
                    count(*) FILTER (WHERE geom IS NOT NULL AND NOT ST_IsValid(geom)),
                    count(*) FILTER (WHERE geom IS NULL OR ST_IsEmpty(geom)),
                    count(*) FILTER (WHERE _geom_repaired),
                    coalesce(string_agg(DISTINCT ST_SRID(geom)::text, ',') FILTER (WHERE geom IS NOT NULL), '')
                    FROM sjrwmd.%I$q$, r.name) INTO n, bad, nulls, rep, srids;
    INSERT INTO qc.results(checked_at, layer, check_name, expected, actual, passed, detail) VALUES
      (batch, r.name, 'count_vs_server', r.server_count, n, n = r.server_count, 'returnCountOnly at harvest'),
      (batch, r.name, 'invalid_geometry', 0, bad, bad = 0, 'ST_IsValid after loader repair'),
      (batch, r.name, 'repaired_geometry', NULL, rep, true, 'source rings repaired with ST_MakeValid (informational)'),
      (batch, r.name, 'null_or_empty_geometry', 0, nulls, nulls = 0, 'null/empty geometry in source'),
      (batch, r.name, 'srid', 3086, NULLIF(srids, '')::bigint, srids IN ('3086', ''), 'distinct SRIDs: ' || srids);
  END LOOP;
END$$;
SELECT check_name, count(*) AS layers, count(*) FILTER (WHERE passed) AS passed, sum(actual) AS total_actual
FROM qc.results WHERE checked_at = (SELECT max(checked_at) FROM qc.results) GROUP BY 1 ORDER BY 1;
