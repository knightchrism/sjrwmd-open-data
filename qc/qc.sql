-- Load check: rows loaded vs. the server's returnCountOnly count, per selected layer.
-- (The harvester records server_count in meta.layer_registry at fetch time.)
DO $$
DECLARE r record; n bigint;
BEGIN
  FOR r IN SELECT name, alias, server_count FROM meta.layer_registry WHERE alias IS NOT NULL ORDER BY alias LOOP
    EXECUTE format('SELECT count(*) FROM sjrwmd.%I', r.name) INTO n;
    RAISE NOTICE '% loaded % of % %', rpad(r.alias, 26), n, r.server_count, CASE WHEN n = r.server_count THEN 'OK' ELSE 'MISMATCH' END;
  END LOOP;
END $$;
