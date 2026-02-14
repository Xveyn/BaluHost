-- Universal script to fix all PostgreSQL sequences after SQLite migration
-- This dynamically finds all sequences and resets them to MAX(id) + 1

DO $$
DECLARE
    r RECORD;
    v_max_id BIGINT;
    v_seq_name TEXT;
BEGIN
    -- Loop through all tables with serial columns
    FOR r IN
        SELECT
            c.relname AS table_name,
            a.attname AS column_name,
            pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname) AS sequence_name
        FROM
            pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            JOIN pg_attrdef ad ON ad.adrelid = c.oid AND ad.adnum = a.attnum
        WHERE
            c.relkind = 'r'
            AND n.nspname = 'public'
            AND a.attnum > 0
            AND NOT a.attisdropped
            AND pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname) IS NOT NULL
        ORDER BY c.relname
    LOOP
        -- Get max ID from table
        EXECUTE format('SELECT COALESCE(MAX(%I), 0) FROM %I', r.column_name, r.table_name) INTO v_max_id;

        -- Set sequence to max_id
        IF v_max_id > 0 THEN
            EXECUTE format('SELECT setval(%L, %s, true)', r.sequence_name, v_max_id);
            RAISE NOTICE 'Fixed sequence for %.%: set to %', r.table_name, r.column_name, v_max_id;
        ELSE
            EXECUTE format('SELECT setval(%L, 1, false)', r.sequence_name);
            RAISE NOTICE 'Reset sequence for %.% to 1 (empty table)', r.table_name, r.column_name;
        END IF;
    END LOOP;
END $$;

-- Verify: Show current sequence values
SELECT
    c.relname AS table_name,
    a.attname AS column_name,
    pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname) AS sequence_name,
    (SELECT last_value FROM pg_sequences WHERE schemaname = 'public' AND sequencename = substring(pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname) from '"public"."(.+)"')) AS current_value
FROM
    pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid
WHERE
    c.relkind = 'r'
    AND n.nspname = 'public'
    AND a.attnum > 0
    AND NOT a.attisdropped
    AND pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname) IS NOT NULL
ORDER BY c.relname;
