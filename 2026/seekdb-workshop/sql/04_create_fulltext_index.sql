ALTER TABLE movies
ADD FULLTEXT INDEX ft_overview (overview) WITH PARSER ik;
