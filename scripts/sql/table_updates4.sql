DELETE FROM content_links
WHERE role_id = '779823163465793546'
AND url IN
(
	SELECT iu_urls.url 
    FROM (
		SELECT url FROM content_links
		WHERE role_id = '779823163465793546'
		GROUP BY url
	) iu_urls
	JOIN (
		SELECT url, count(*) AS counts
		FROM content_links
		GROUP BY url
		HAVING count(*) > 1
	) multi_urls
	ON iu_urls.url = multi_urls.url
);
