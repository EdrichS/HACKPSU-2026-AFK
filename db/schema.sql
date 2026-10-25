-- Nametags schema. Applied at every backend startup, so every statement is idempotent.
-- CREATE TABLE IF NOT EXISTS never changes an existing table: after editing this file, stop the
-- backend and reset with `docker compose down -v && find data -type f -delete` (deletes everything).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS people (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          text NOT NULL CHECK (name ~ '\S' AND char_length(name) <= 80),
    relationship  text NOT NULL CHECK (relationship ~ '\S' AND char_length(relationship) <= 40),
    small_context text NOT NULL DEFAULT '' CHECK (char_length(small_context) <= 300),
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS people_name_relationship_key
    ON people (lower(btrim(name)), lower(btrim(relationship)));

CREATE TABLE IF NOT EXISTS photos (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_path   text NOT NULL UNIQUE,
    width       integer NOT NULL CHECK (width > 0),
    height      integer NOT NULL CHECK (height > 0),
    uploaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS face_samples (
    id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    photo_id   integer NOT NULL REFERENCES photos (id) ON DELETE CASCADE,
    person_id  integer REFERENCES people (id) ON DELETE SET NULL,  -- NULL = unlabelled
    box_x      integer NOT NULL CHECK (box_x >= 0),
    box_y      integer NOT NULL CHECK (box_y >= 0),
    box_width  integer NOT NULL CHECK (box_width > 0),
    box_height integer NOT NULL CHECK (box_height > 0),
    model      text NOT NULL CHECK (model ~ '\S'),
    embedding  vector(128) NOT NULL CHECK (vector_norm(embedding) > 0),
    UNIQUE (photo_id, person_id)       -- one face per person per photo; NULLs never clash
);

CREATE TABLE IF NOT EXISTS voice_samples (
    id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    person_id  integer NOT NULL REFERENCES people (id) ON DELETE CASCADE,
    audio_path text NOT NULL UNIQUE,
    model      text NOT NULL CHECK (model ~ '\S'),
    embedding  vector(192) NOT NULL CHECK (vector_norm(embedding) > 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS facts (
    id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    person_id  integer NOT NULL REFERENCES people (id) ON DELETE CASCADE,
    text       text NOT NULL CHECK (text ~ '\S' AND char_length(text) <= 300),
    source     text NOT NULL CHECK (source IN ('conversation', 'notes')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS facts_person_text_key ON facts (person_id, lower(btrim(text)));
