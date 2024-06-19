delete from content_links
where role_id = '779823163465793546'
and url in
(
	select iu_urls.url 
    from (
		select url from content_links
		where role_id = '779823163465793546'
		group by 1
	) iu_urls
	join (
		select url, count(*) as counts
		from content_links
		group by url
		having count(*) > 1
	) multi_urls
	on iu_urls.url = multi_urls.url
);
