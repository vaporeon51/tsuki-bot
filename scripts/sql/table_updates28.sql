-- Add the newly listed individual ping roles only.  Groups and bot roles from
-- the same roster are deliberately excluded.
--
-- Birthday research:
-- Beni / Yihyun: Baby DONT Cry profile data (P Nation group)
-- Elisia: UNIS Japan official fan club profile
-- Kasia / Sasha: ifeye member profiles
-- Nagomi: https://www.madein-official.net/profile/
-- Seowon: UNIS birthday announcements
-- Youngseo: ALLDAY PROJECT birthday announcement

INSERT INTO role_info (role_id, string_tag, member_name, group_name, birthday, member_group_array)
VALUES
    ('1410513297412849775', 'Beni [Baby DONT Cry]', 'Beni', 'Baby DONT Cry', '2008-12-23 00:00:00.000000',
     '{beni,baby,dont,cry}'),
    ('1474353781893234749', 'Elisia [UNIS]', 'Elisia', 'UNIS', '2009-04-18 00:00:00.000000', '{elisia,unis}'),
    ('1410512586180399114', 'Kasia [ifeye]', 'Kasia', 'ifeye', '2008-02-15 00:00:00.000000', '{kasia,ifeye}'),
    ('1410513105779294278', 'Nagomi [MADEIN]', 'Nagomi', 'MADEIN', '2007-07-02 00:00:00.000000',
     '{nagomi,madein}'),
    ('1410512985344049232', 'Sasha [ifeye]', 'Sasha', 'ifeye', '2009-05-20 00:00:00.000000', '{sasha,ifeye}'),
    ('1474353841465065606', 'Seowon [UNIS]', 'Seowon', 'UNIS', '2011-01-27 00:00:00.000000', '{seowon,unis}'),
    ('1410513437930553404', 'Yihyun [Baby DONT Cry]', 'Yihyun', 'Baby DONT Cry', '2006-04-11 00:00:00.000000',
     '{yihyun,baby,dont,cry}'),
    ('1392205915020595381', 'Youngseo [ALLDAY PROJECT]', 'Youngseo', 'ALLDAY PROJECT', '2005-11-13 00:00:00.000000',
     '{youngseo,allday,project}')
ON CONFLICT (role_id) DO UPDATE
SET string_tag = EXCLUDED.string_tag,
    member_name = EXCLUDED.member_name,
    group_name = EXCLUDED.group_name,
    birthday = EXCLUDED.birthday,
    member_group_array = EXCLUDED.member_group_array;
