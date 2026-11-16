CREATE TABLE IF NOT EXISTS movies (
    id                VARCHAR(32) PRIMARY KEY,
    tmdb_id           BIGINT NOT NULL,
    title             VARCHAR(255) NOT NULL,
    original_title    VARCHAR(255) NOT NULL,
    overview          TEXT NOT NULL,
    `year`            SMALLINT NOT NULL,
    release_date      DATE NOT NULL,
    genres            JSON NOT NULL,
    countries         JSON NOT NULL,
    original_language VARCHAR(16) NOT NULL,
    runtime_minutes   SMALLINT NOT NULL,
    rating            DECIMAL(5, 3),
    vote_count        INT NOT NULL,
    poster_url        VARCHAR(1024),
    source            VARCHAR(32) NOT NULL,
    source_url        VARCHAR(512) NOT NULL,
    data_language     VARCHAR(16) NOT NULL
) DEFAULT CHARSET = utf8mb4 ORGANIZATION = HEAP;
