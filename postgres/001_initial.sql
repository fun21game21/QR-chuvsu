CREATE TABLE sessions (
    id uuid PRIMARY KEY,
    title varchar(160) NOT NULL,
    group_name varchar(80) NOT NULL,
    session_code char(6) NOT NULL UNIQUE CHECK (session_code ~ '^[0-9]{6}$'),
    qr_path text NOT NULL,
    latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    radius integer NOT NULL CHECK (radius BETWEEN 10 AND 5000),
    teacher_name varchar(160) NOT NULL,
    location_name varchar(200) NOT NULL,
    owner_hash char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    active boolean NOT NULL DEFAULT true,
    CHECK (expires_at > created_at)
);
CREATE INDEX sessions_owner ON sessions(owner_hash, created_at DESC);

CREATE TABLE attendance (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id uuid REFERENCES sessions(id) ON DELETE CASCADE,
    student_name varchar(160) NOT NULL,
    group_name varchar(80) NOT NULL,
    name_key text NOT NULL,
    group_key text NOT NULL,
    device_token uuid,
    fingerprint char(64),
    latitude double precision CHECK (latitude BETWEEN -90 AND 90),
    longitude double precision CHECK (longitude BETWEEN -180 AND 180),
    ip_address inet NOT NULL,
    status text NOT NULL CHECK (status IN ('accepted', 'rejected', 'manual')),
    reason text NOT NULL,
    distance_m double precision,
    attempted_code varchar(6) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX attendance_session ON attendance(session_id, created_at);
CREATE UNIQUE INDEX attendance_unique_student
    ON attendance(session_id, name_key, group_key) WHERE status IN ('accepted', 'manual');
CREATE UNIQUE INDEX attendance_unique_device
    ON attendance(session_id, device_token) WHERE status = 'accepted';
CREATE UNIQUE INDEX attendance_unique_fingerprint
    ON attendance(session_id, fingerprint) WHERE status = 'accepted';

-- Shared across workers; one window per IP (not one attendance per IP).
CREATE TABLE ip_rate_limits (
    ip_address inet PRIMARY KEY,
    window_start timestamptz NOT NULL,
    hits integer NOT NULL
);
