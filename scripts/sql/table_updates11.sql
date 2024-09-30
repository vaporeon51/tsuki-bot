-- Drop foreign key constraint so we can index all roles and update roles table later
ALTER TABLE content_links DROP CONSTRAINT content_links_role_id_fk;
