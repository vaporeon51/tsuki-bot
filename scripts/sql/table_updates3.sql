CREATE TABLE IF NOT EXISTS temp_birthdays
(
    role_id                    VARCHAR NOT NULL PRIMARY KEY,
    string_tag                 VARCHAR(1000),
    birthday                   TIMESTAMP NOT NULL DEFAULT '1900-01-01 00:00'
);

INSERT INTO "temp_birthdays" ("role_id", "string_tag", "birthday") VALUES
    ('779826919863615488', 'Chaeyeon [IZONE]', '2000-01-11 00:00'),
    ('1000867801420009502', 'Chaeyeon [tripleS]', '2004-12-04 00:00'),
    ('779847857078272092', 'Chaeyoung [fromis_9]', '2000-05-14 00:00'),
    ('779825045413429259', 'Chaeyoung [TWICE]', '1999-04-23 00:00'),
    ('779844961612464129', 'Cheng Xiao [WJSN]', '1998-07-15 00:00'),
    ('1058790681939804221', 'Chiquita [BABYMONSTER]', '2009-02-17 00:00'),
    ('779827829633843223', 'Choerry [Loona]', '2001-06-04 00:00'),
    ('842613426760056877', 'Chowon [LIGHTSUM]', '2002-09-16 00:00'),
    ('779869669275598848', 'Chungha', '1996-02-09 00:00'),
    ('779828161319534595', 'Chuu [LOONA]', '1999-10-20 00:00'),
    ('779866230524739584', 'Cignature', '1900-01-01 00:00'),
    ('1051926448589512864', 'CSR', '1900-01-01 00:00'),
    ('779816698965655583', 'Dahyun [RcPc]', '2005-04-29 00:00'),
    ('779824927611682836', 'Dahyun [TWICE]', '1998-05-28 00:00'),
    ('809565815476060211', 'Dami [Dreamcatcher]', '1997-03-07 00:00'),
    ('1000865551020740629', 'Danielle [NewJeans]', '2005-04-11 00:00'),
    ('825604064720977931', 'Dawon [WJSN]', '1997-03-16 00:00'),
    ('906300209565417542', 'Dayeon [Kep1er]', '2003-03-02 00:00'),
    ('780147579391836160', 'Dayoung [WJSN]', '1999-05-14 00:00'),
    ('1003189261857738843', 'Dosie [Purple Kiss]', '2000-02-11 00:00'),
    ('779873422503051264', 'Dreamnote', '1900-01-01 00:00'),
    ('779818840074092614', 'EU [EVERGLOW]', '1998-05-19 00:00'),
    ('779826915627761686', 'Eunbi [IZONE]', '1995-09-27 00:00'),
    ('961353302921068614', 'Eunchae [LE SSERAFIM]', '2006-11-10 00:00'),
    ('779834000327180319', 'Eunha [VIVIZ]', '1997-05-30 00:00'),
    ('779844835061923901', 'Eunseo [WJSN]', '1998-05-27 00:00'),
    ('779844261683789845', 'Exy [WJSN]', '1995-11-06 00:00'),
    ('916036962694090792', 'Gaeul [IVE]', '2002-09-24 00:00'),
    ('779849462499508254', 'Gahyeon [Dreamcatcher]', '1999-02-03 00:00'),
    ('779818212233576510', 'Giselle [Aespa]', '2000-10-30 00:00'),
    ('779828668125020180', 'Gowon [Loona]', '2000-11-19 00:00'),
    ('779847395076341800', 'Gyuri [fromis_9]', '1997-12-27 00:00'),
    ('1000867359914991718', 'H1-KEY', '1900-01-01 00:00'),
    ('1000866108028493954', 'Haerin [NewJeans]', '2006-05-15 00:00'),
    ('945905738285469757', 'Haewon [NMIXX]', '2003-02-25 00:00'),
    ('779874187908743178', 'Handong [Dreamcatcher]', '1996-03-26 00:00'),
    ('1000863360776147054', 'Hanni [NewJeans]', '2004-10-06 00:00'),
    ('779827239729496076', 'Haseul [Loona]', '1997-08-18 00:00'),
    ('779847039017943101', 'Hayoung [fromis_9]', '1997-09-29 00:00'),
    ('779826601905881088', 'Heejin [Loona]', '2000-10-19 00:00'),
    ('906301530481762324', 'Hikaru [Kep1er]', '2004-03-12 00:00'),
    ('779850312239808542', 'Hwasa [MAMAMOO]', '1995-07-23 00:00'),
    ('1000866639727829103', 'Hyein [NewJeans]', '2008-04-21 00:00'),
    ('1000860126724493444', 'Hyeju [CLASS:y]', '2003-12-09 00:00'),
    ('779828876351111218', 'Hyeju [Loona]', '1900-01-01 00:00'),
    ('779830005642821634', 'Hyewon [IZONE]', '1999-07-05 00:00'),
    ('868170363899625482', 'Hyunbin [TRI.BE]', '2004-05-26 00:00'),
    ('1000862576055427173', 'Hyungseo [CLASS:y]', '2001-06-25 00:00'),
    ('779826921613426708', 'Hyunjin [Loona]', '2000-11-15 00:00'),
    ('779833011196788736', 'Irene [Red Velvet]', '1991-03-29 00:00'),
    ('1147390265166930001', 'Iroha [ILLIT]', '1900-01-01 00:00'),
    ('779822396831301643', 'Isa [StayC]', '2002-01-23 00:00'),
    ('779823163465793546', 'IU', '1993-05-16 00:00'),
    ('779822389647114271', 'J [StayC]', '2004-12-09 00:00'),
    ('779823018968219651', 'Jaehee [Weeekly]', '2004-03-18 00:00'),
    ('970868690402816011', 'Jeewon [CIGNATURE]', '1999-04-01 00:00'),
    ('779830218889625622', 'Jennie [BLACKPINK]', '1996-01-16 00:00'),
    ('779823848451211275', 'Jeongyeon [TWICE]', '1996-11-01 00:00'),
    ('868170522649841694', 'Jia [TRI.BE]', '2005-07-30 00:00'),
    ('779823020326912010', 'Jihan [Weeekly]', '2004-07-12 00:00'),
    ('779848199434797097', 'Jiheon [fromis_9]', '2003-04-17 00:00'),
    ('779824234007494656', 'Jihyo [TWICE]', '1997-02-01 00:00'),
    ('1000861170552541297', 'Jimin [CLASS:y]', '2007-11-25 00:00'),
    ('945906614341349416', 'Jini [NMIXX]', '2004-04-16 00:00'),
    ('779829455219851302', 'Jinsoul [Loona]', '1997-06-13 00:00'),
    ('779832209187274764', 'Jisoo [BLACKPINK]', '1995-01-03 00:00'),
    ('779847665109434369', 'Jisun [fromis_9]', '1998-11-23 00:00'),
    ('779877813679030303', 'Jiu [Dreamcatcher]', '1994-05-17 00:00'),
    ('779847575711776809', 'Jiwon [fromis_9]', '1998-03-20 00:00'),
    ('945907571464757298', 'Jiwoo [NMIXX]', '2005-04-13 00:00'),
    ('1090716716939628559', 'Jiwoo [tripleS]', '2005-10-24 00:00'),
    ('1222628857304322239', 'Joonie [ICHILLIN]', '1900-01-01 00:00'),
    ('779833362134073364', 'Joy [Red Velvet]', '1996-09-03 00:00'),
    ('1234943239556169789', 'Julie [KISS OF LIFE]', '1900-01-01 00:00'),
    ('779816675667214357', 'Juri [RcPc]', '1997-10-03 00:00'),
    ('1193016480795721829', 'Kaede [tripleS]', '2005-12-20 00:00'),
    ('779818210375106610', 'Karina [Aespa]', '2000-04-11 00:00'),
    ('961642896224837722', 'Kazuha [LE SSERAFIM]', '2003-08-09 00:00'),
    ('818404437919793183', 'Kelly [TRI.BE]', '2002-01-16 00:00'),
    ('779827650725675018', 'Kim Lip [Loona]', '1999-02-10 00:00'),
    ('1128074420360065166', 'KISS OF LIFE', '1900-01-01 00:00'),
    ('945907846434922566', 'Kyujin [NMIXX]', '2006-05-26 00:00'),
    ('988290184812585011', 'LAPILLUS', '1900-01-01 00:00'),
    ('916036671412273283', 'Leeseo [IVE]', '2007-02-21 00:00'),
    ('779825044984823860', 'Lia [ITZY]', '2000-07-21 00:00'),
    ('842614831269806120', 'LIGHTSUM', '1900-01-01 00:00'),
    ('945906099696042006', 'Lily [NMIXX]', '2002-10-17 00:00'),
    ('1074792475912327169', 'LIMELIGHT', '1900-01-01 00:00'),
    ('779832401655889940', 'Lisa [BLACKPINK]', '1997-03-27 00:00'),
    ('916036552327594005', 'Liz [IVE]', '2004-11-21 00:00'),
    ('798064388161536070', 'Lucy [woo!ah!]', '2004-04-09 00:00'),
    ('779844645156683846', 'Luda [WJSN]', '1997-03-06 00:00'),
    ('906302029301944321', 'Mashiro [Kep1er]', '1999-12-16 00:00'),
    ('779819834174734336', 'Mia [EVERGLOW]', '2000-01-13 00:00'),
    ('779843020115804232', 'Mijoo [Lovelyz]', '1994-09-23 00:00'),
    ('797538701789626378', 'Mimi [OMG]', '1995-05-01 00:00'),
    ('779824359057522698', 'Mina [TWICE]', '1997-03-24 00:00'),
    ('1000863945084653628', 'Minji [NewJeans]', '2004-05-07 00:00'),
    ('1147390015341596712', 'Minju [ILLIT]', '1900-01-01 00:00'),
    ('779826918568361984', 'Minju [IZONE]', '1900-01-01 00:00'),
    ('779856689943281694', 'Minnie [G-IDLE]', '1997-10-23 00:00'),
    ('798064761929072651', 'Minseo [woo!ah!]', '2004-08-12 00:00'),
    ('868170582779367475', 'Mire [TRI.BE]', '2006-03-26 00:00'),
    ('779856224618938438', 'Miyeon [G-IDLE]', '1997-01-31 00:00'),
    ('1147390143980908584', 'Moka [ILLIT]', '1900-01-01 00:00'),
    ('779823413513814027', 'Momo [TWICE]', '1996-11-09 00:00'),
    ('779823016581791774', 'Monday [Weeekly]', '2002-05-10 00:00'),
    ('1221925113029464094', 'Nakyoung [tripleS]', '1900-01-01 00:00'),
    ('779848040235794443', 'Nakyung [fromis_9]', '2000-06-01 00:00'),
    ('785670300171894844', 'Nana [woo!ah!]', '2001-03-09 00:00'),
    ('779808180514586635', 'Nancy [MOMOLAND]', '2000-04-13 00:00'),
    ('1120221524029349890', 'Natty [KISS OF LIFE]', '1900-01-01 00:00'),
    ('779824162382282784', 'Nayeon [TWICE]', '1995-09-22 00:00'),
    ('1000858915921215648', 'Nayoung [LIGHTSUM]', '2002-11-30 00:00'),
    ('779818215735033878', 'NingNing [Aespa]', '2002-10-23 00:00'),
    ('779823847582859294', 'Onda [EVERGLOW]', '2000-05-18 00:00'),
    ('1058790432206766080', 'Pharita [BABYMONSTER]', '2005-08-26 00:00'),
    ('815450910519459852', 'PIXY', '1900-01-01 00:00'),
    ('842614764962447370', 'Purple Kiss', '1900-01-01 00:00'),
    ('1195411393143386204', 'QWER', '1900-01-01 00:00'),
    ('1058790158406795324', 'Rami [BABYMONSTER]', '2007-10-17 00:00'),
    ('916037195649929216', 'Rei [IVE]', '2004-02-03 00:00'),
    ('1234020371355795507', 'RESCENE', '1900-01-01 00:00'),
    ('1000859597759856680', 'Riwon [CLASS:y]', '2007-01-11 00:00'),
    ('1058790584241881238', 'Rora [BABYMONSTER]', '2008-08-05 00:00'),
    ('779830417112432680', 'Rose [BLACKPINK]', '1997-02-11 00:00'),
    ('1058791512818847814', 'Ruka [BABYMONSTER]', '2002-03-20 00:00'),
    ('779820176127557632', 'Ryujin [ITZY]', '2001-04-17 00:00'),
    ('779847277455081533', 'Saerom [fromis_9]', '1997-01-07 00:00'),
    ('779823846815039488', 'Sakura [LE SSERAFIM]', '1998-03-19 00:00'),
    ('779823328889536512', 'Sana [TWICE]', '1996-12-29 00:00'),
    ('1000858352139653282', 'Sangah [LIGHTSUM]', '2002-09-04 00:00'),
    ('779874407098613841', 'Secret Number', '1900-01-01 00:00'),
    ('779822398719000607', 'Seeun [StayC]', '2003-06-14 00:00'),
    ('779846589510058044', 'Sejeong [Gugudan]', '1996-08-28 00:00'),
    ('820183171693412352', 'Seola [WJSN]', '1994-12-24 00:00'),
    ('1000863010442723418', 'Seonyou [CLASS:y]', '2008-03-20 00:00'),
    ('779847756138807298', 'Seoyeon [fromis_9]', '2000-01-22 00:00'),
    ('1141805269978980452', 'Seoyeon [tripleS]', '2003-08-06 00:00'),
    ('779833124821270548', 'Seulgi [Red Velvet]', '1994-02-10 00:00'),
    ('941894587830661161', 'Sheon [Billlie]', '2003-01-28 00:00'),
    ('779857250381987860', 'Shuhua [G-IDLE]', '2000-01-06 00:00'),
    ('779822395547844659', 'Sieun [StayC]', '2001-08-01 00:00'),
    ('779839197262643221', 'Ahin [MOMOLAND]', '1999-09-27 00:00'),
    ('1058790666467033088', 'Ahyeon [BABYMONSTER]', '2007-04-11 00:00'),
    ('779823575707680799', 'Aisha [EVERGLOW]', '2000-07-21 00:00'),
    ('779835514534494208', 'Arin [OMG]', '1999-06-18 00:00'),
    ('1058790840836825118', 'Asa [BABYMONSTER]', '2006-04-17 00:00'),
    ('945907369043447829', 'BAE [NMIXX]', '2004-12-28 00:00'),
    ('906298254675816558', 'Bahiyyih [Kep1er]', '2004-07-27 00:00'),
    ('906302907614367774', 'Billlie', '1900-01-01 00:00'),
    ('1000862052602093568', 'Boeun [CLASS:y]', '2008-02-11 00:00'),
    ('779844178963071007', 'Bona [WJSN]', '1995-08-19 00:00'),
    ('906297933039812608', 'Chaehyun [Kep1er]', '2002-04-26 00:00'),
    ('779825044066271262', 'Chaeryeong [ITZY]', '2001-06-05 00:00'),
    ('1000860647560581240', 'Chaewon [CLASS:y]', '2003-06-04 00:00'),
    ('779826916328472627', 'Chaewon [LE SSERAFIM]', '2000-08-01 00:00'),
    ('1005395368843956304', 'ICHILLIN', '1900-01-01 00:00'),
    ('1169832169364013137', 'NiziU', '1900-01-01 00:00'),
    ('779824630202368011', 'Sihyeon [EVERGLOW]', '1999-08-05 00:00'),
    ('779834908859695124', 'SinB [VIVIZ]', '1998-06-03 00:00'),
    ('779849307750793218', 'Siyeon [Dreamcatcher]', '1995-10-01 00:00'),
    ('868170429821513769', 'Soeun [TRI.BE]', '2005-12-10 00:00'),
    ('779823018070376488', 'Soeun [Weeekly]', '2002-10-26 00:00'),
    ('1099099767402934272', 'Sohyun [tripleS]', '2002-10-13 00:00'),
    ('779849921545109544', 'Solar [MAMAMOO]', '1991-02-21 00:00'),
    ('779823021812613141', 'Somi', '2001-03-09 00:00'),
    ('809565207449174036', 'Songsun [TRI.BE]', '1997-03-22 00:00'),
    ('825604227316449290', 'Soobin [WJSN]', '1996-09-14 00:00'),
    ('779823009485553664', 'Soojin [Weeekly]', '2001-12-12 00:00'),
    ('798063947974049812', 'Sora [woo!ah!]', '2003-08-30 00:00'),
    ('779857001697771520', 'Soyeon [G-IDLE]', '1998-08-26 00:00'),
    ('779848835190620171', 'SuA [Dreamcatcher]', '1994-08-10 00:00'),
    ('945906385596588042', 'Sullyoon [NMIXX]', '2004-01-26 00:00'),
    ('779822392359911425', 'Sumin [StayC]', '2001-03-13 00:00'),
    ('779851132985933875', 'Sunmi', '1992-05-02 00:00'),
    ('779816690380832768', 'Suyun [RcPc]', '2001-03-17 00:00'),
    ('1003188612109713408', 'Swan [Purple Kiss]', '2003-07-11 00:00'),
    ('779839820339085322', 'Taeyeon [SNSD]', '1989-03-09 00:00'),
    ('1090309281691226112', 'Takara [Busters]', '2005-01-19 00:00'),
    ('1000868080911646861', 'tripleS', '1900-01-01 00:00'),
    ('970867695090282558', 'Tsuki [Billlie]', '2002-09-21 00:00'),
    ('779825531977728017', 'Tzuyu [TWICE]', '1999-06-14 00:00'),
    ('779834986361520138', 'Umji [VIVIZ]', '1998-08-19 00:00'),
    ('1224066003651133682', 'UNIS', '1900-01-01 00:00'),
    ('779827501475561472', 'Vivi [Loona]', '1996-12-09 00:00'),
    ('779833268203028490', 'Wendy [Red Velvet]', '1994-02-21 00:00'),
    ('779818213936332811', 'Winter [Aespa]', '2001-01-01 00:00'),
    ('1147389678413168720', 'Wonhee [ILLIT]', '2007-06-26 00:00'),
    ('779808234239557662', 'Wonyoung [IVE]', '2004-08-31 00:00'),
    ('798063140298293298', 'Wooyeon [woo!ah!]', '2003-02-11 00:00'),
    ('906302191852200057', 'Xiaoting [Kep1er]', '1999-11-12 00:00'),
    ('1144754742661226556', 'Xinyu [tripleS]', '2002-05-25 00:00'),
    ('779825042695520288', 'Yeji [ITZY]', '2000-05-26 00:00'),
    ('1234942385897734245', 'Yeju [ICHILLIN]', '2004-09-01 00:00'),
    ('1074613959266664479', 'Yel [H1-KEY]', '2004-12-25 00:00'),
    ('779828194340634625', 'Yena [IZONE]', '1999-09-29 00:00'),
    ('779827362815672431', 'Yeojin [Loona]', '2002-11-11 00:00'),
    ('779808449251770378', 'Yeonhee [RcPc]', '2000-12-06 00:00'),
    ('1234942669751455846', 'Yeonji [tripleS]', '2008-01-08 00:00'),
    ('779845071574794251', 'Yeoreum [WJSN]', '1999-01-10 00:00'),
    ('779833497438388234', 'Yeri [Red Velvet]', '1999-03-05 00:00'),
    ('906301154407907358', 'Yeseo [Kep1er]', '2005-08-22 00:00'),
    ('779812170472095764', 'Yiren [EVERGLOW]', '2000-12-29 00:00'),
    ('779835650902851634', 'Yooa [OMG]', '1995-09-17 00:00'),
    ('779870866862243840', 'Yoohyeon [Dreamcatcher]', '1997-01-07 00:00'),
    ('779822399758532608', 'Yoon [StayC]', '2004-04-14 00:00'),
    ('1079677939878219826', 'Yooyeon [tripleS]', '2001-02-09 00:00'),
    ('906300722956611624', 'Youngeun [Kep1er]', '2004-12-27 00:00'),
    ('779836549772345375', 'Yubin [OMG]', '1997-09-09 00:00'),
    ('1141805462996664351', 'Yubin [tripleS]', '2005-02-03 00:00'),
    ('779826918480281631', 'Yujin [IVE]', '2003-09-01 00:00'),
    ('779840775277641779', 'Yujin [Kep1er]', '1996-08-12 00:00'),
    ('779834837418770492', 'Yuju [GFRIEND]', '1997-10-04 00:00'),
    ('842613003908153414', 'Yuki [Purple Kiss]', '2002-11-06 00:00'),
    ('779824620404473866', 'Yuna [ITZY]', '2003-12-09 00:00'),
    ('1147390366417436683', 'Yunah [ILLIT]', '2004-01-15 00:00'),
    ('962006315935338606', 'Yunjin [LE SSERAFIM]', '2001-10-08 00:00'),
    ('779816692309950516', 'Yunkyoung [RcPc]', '2001-11-01 00:00'),
    ('779857131893030932', 'Yuqi [G-IDLE]', '1999-09-23 00:00'),
    ('779826917166940162', 'Yuri [IZONE]', '2001-10-22 00:00'),
    ('779827944658567189', 'Yves [LOONA]', '1997-05-24 00:00'),
    ('779823021279150111', 'Zoa [Weeekly]', '2005-05-31 00:00');



ALTER TABLE role_info
ADD COLUMN birthday TIMESTAMP NOT NULL DEFAULT '1900-01-01 00:00';

UPDATE role_info 
   SET birthday=(SELECT birthday FROM temp_birthdays WHERE role_info.role_id=temp_birthdays.role_id);

DROP TABLE temp_birthdays;