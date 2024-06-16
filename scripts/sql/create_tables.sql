CREATE TABLE IF NOT EXISTS role_info
(
    role_id                    VARCHAR NOT NULL PRIMARY KEY,
    string_tag                 VARCHAR(1000),
    member_name                VARCHAR(1000),
    group_name                 VARCHAR(1000)
);


CREATE TABLE IF NOT EXISTS content_links
(
    role_id                     VARCHAR
        CONSTRAINT content_links_role_id_fk REFERENCES role_info ON UPDATE CASCADE ON DELETE CASCADE,
    author_id                   VARCHAR(1000),
    author                      VARCHAR(1000),
    uploaded_date               TIMESTAMP,
    url                         VARCHAR NOT NULL,
    initial_reaction_count      INT,
    is_broken                   BOOLEAN
);

CREATE INDEX IF NOT EXISTS content_links_role_id
    ON content_links (role_id);