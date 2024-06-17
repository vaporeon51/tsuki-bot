ALTER TABLE role_info
ADD tsv_string_tag tsvector;

UPDATE role_info
SET tsv_string_tag = to_tsvector('english', regexp_replace(string_tag, '[^a-zA-Z0-9\s]', '', 'g'));