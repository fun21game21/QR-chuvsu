-- Existing sessions retain their original location and coordinates.
-- New sessions get their location from the server's verified campus catalogue.
ALTER TABLE sessions ADD COLUMN campus_id text;
