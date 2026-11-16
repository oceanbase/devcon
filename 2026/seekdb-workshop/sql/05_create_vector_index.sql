CREATE VECTOR INDEX vec_overview ON movies (embedding)
WITH (DISTANCE=cosine, TYPE=hnsw, LIB=vsag);
