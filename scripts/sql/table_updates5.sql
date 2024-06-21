ALTER TABLE role_info
ADD COLUMN member_group_array TEXT[],
DROP COLUMN tsv_string_tag;

-- Populate the new columns
UPDATE role_info
SET member_group_array = array_cat(
    string_to_array(regexp_replace(regexp_replace(LOWER(TRIM(member_name)), '[^a-zA-Z0-9\s]', '', 'g'), '\s+', ' ', 'g'), ' '),
    string_to_array(regexp_replace(regexp_replace(LOWER(TRIM(group_name)), '[^a-zA-Z0-9\s]', '', 'g'), '\s+', ' ', 'g'), ' ')
);