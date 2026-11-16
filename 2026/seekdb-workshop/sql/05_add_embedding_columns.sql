ALTER TABLE movies
    ADD COLUMN embedding VECTOR(512),
    ADD COLUMN embedding_model VARCHAR(128),
    ADD COLUMN embedding_text_sha256 CHAR(64);
