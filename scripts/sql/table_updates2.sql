ALTER TABLE role_info
ADD tsv_member_name tsvector,
ADD tsv_group_name tsvector;

UPDATE role_info
SET tsv_member_name = to_tsvector('english', member_name),
    tsv_group_name = to_tsvector('english', group_name);