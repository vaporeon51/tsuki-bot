ALTER TABLE "content_links"
    ADD num_upvotes int NOT NULL DEFAULT 0,
    ADD num_downvotes int NOT NULL DEFAULT 0,
    ADD num_reports int NOT NULL DEFAULT 0;
