-- Explicit additive migration for the isolated local preview, not a production importer.
-- Apply to the intended preview database before starting the updated application.
-- No user, visit, identity, training or Canvas cache rows are removed.
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid = 'training_types'::regclass
          AND attname = 'display_order' AND NOT attisdropped
    ) THEN
        ALTER TABLE training_types
            ADD COLUMN display_order integer NOT NULL DEFAULT 100;

        -- Backfill only the six known definitions; custom definitions, including
        -- ones reusing an original icon, retain the append default.
        UPDATE training_types SET display_order = CASE icon_key
            WHEN 'policies' THEN 0
            WHEN 'orientation' THEN 1
            WHEN '3d-printer' THEN 2
            WHEN 'laser-cutter' THEN 3
            WHEN 'resin-printer' THEN 4
            WHEN 'waterjet' THEN 5
            ELSE CASE name
                WHEN 'Policies and Procedures' THEN 0
                WHEN 'Orientation' THEN 1
                WHEN 'FDM Printing' THEN 2
                WHEN 'Laser Cutter' THEN 3
                WHEN 'Resin Printing' THEN 4
                WHEN 'Waterjet' THEN 5
                ELSE 100
            END
        END
        WHERE name IN ('Policies and Procedures', 'Orientation', 'FDM Printing',
                       'Laser Cutter', 'Resin Printing', 'Waterjet');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'training_types'::regclass
          AND conname = 'training_type_display_order_nonnegative'
    ) THEN
        ALTER TABLE training_types ADD CONSTRAINT training_type_display_order_nonnegative
            CHECK (display_order >= 0);
    END IF;
END
$migration$;
COMMIT;

-- Reapplying preserves subsequent custom display_order edits. Reconnect/refresh
-- clients after starting the new application so they take an ordered snapshot.
