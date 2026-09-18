-- Разовая починка справочника вузов, 18 сентября 2026 года.
--
-- За наплыв 13–14 сентября в справочник уехало шесть двойников уже
-- существующих вузов: заявку на новый вуз одобряли, не видя, что такой вуз
-- заведён (карточка похожих записей не показывала). Двойник дальше сам
-- находился в поиске и собирал людей: запись «РГПУ им. Герцена» за пять дней
-- собрала десять человек. Всего в вузах-двойниках оказалось 23 человека.
--
-- Что делает скрипт, одной транзакцией:
--   1. переносит названия двойников и их варианты поиска к настоящим записям
--      (чтобы люди впредь находили настоящую запись по тем же словам);
--   2. переводит на настоящие записи людей, незакрытые анкеты и сами заявки;
--   3. удаляет семь строк-двойников;
--   4. убирает мусорный вариант поиска «Готово» — это текст кнопки, попавший
--      в справочник.
--
-- Порядок важен: удаление строки справочника обнуляет вуз у тех, кто на ней
-- записан (ON DELETE SET NULL), поэтому люди переезжают раньше удаления.
-- Любая ошибка внутри — откат целиком (ON_ERROR_STOP + транзакция).
--
-- Перед запуском снимается дамп базы. Как запускать — в PROJECT.md, запись
-- за 18.09.2026.
--
-- Было на 18.09.2026: 44 вуза в справочнике, 7 человек без вуза (это «не
-- студенты СПб» — так и должно остаться). Ожидается после склейки:
--   вузов 37; людей без вуза по-прежнему 7;
--   id 1  СПбГУ           28 -> 32
--   id 10 СПбГАСУ          8 -> 14
--   id 11 Герцена         13 -> 23
--   id 13 СПбГУПТД        12 -> 14
--   id 16 Педиатрический   7 -> 8

begin;

create temp table merge_map(dup int, keep int) on commit drop;
insert into merge_map values
    (38, 1),   -- «Федеральное государственное бюджетное... СПбГУ» -> Санкт-Петербургский государственный университет
    (39, 11),  -- «РГПУ им. Герцена»                               -> РГПУ им. А. И. Герцена
    (40, 10),  -- «Санкт Петербургский... архитектурной-строительный» -> СПбГАСУ
    (43, 10),  -- «Санкт-Петербургский Архитектурно-Строительный Университет» -> СПбГАСУ
    (41, 13),  -- «Высшая школа печати и медиатехнологий» (институт внутри) -> СПбГУПТД
    (42, 13),  -- «Санкт-Петербургского государственного университета... .» -> СПбГУПТД
    (44, 16);  -- «СПбГПМУ»                                        -> Педиатрический университет

-- 1. Названия двойников становятся вариантами поиска настоящей записи.
insert into university_aliases (university_id, alias_text)
select distinct m.keep, u.canonical_name
from merge_map m
join universities u on u.university_id = m.dup
where not exists (
    select 1 from university_aliases a
    where a.university_id = m.keep and lower(a.alias_text) = lower(u.canonical_name)
);

-- Варианты поиска двойников переезжают туда же.
insert into university_aliases (university_id, alias_text)
select distinct m.keep, a.alias_text
from merge_map m
join university_aliases a on a.university_id = m.dup
where not exists (
    select 1 from university_aliases b
    where b.university_id = m.keep and lower(b.alias_text) = lower(a.alias_text)
);

-- Чистая аббревиатура педиатрического: в заявке три слова слиплись в одну строку.
insert into university_aliases (university_id, alias_text)
select 16, 'СПбГПМУ'
where not exists (
    select 1 from university_aliases a
    where a.university_id = 16 and lower(a.alias_text) = 'спбгпму'
);

-- 2. Люди, незакрытые анкеты и заявки переезжают на настоящие записи.
update users u set university_id = m.keep
from merge_map m where u.university_id = m.dup;

update registration_requests r set university_id = m.keep
from merge_map m where r.university_id = m.dup;

update university_requests q set created_university_id = m.keep
from merge_map m where q.created_university_id = m.dup;

-- 3. Двойников в справочнике больше нет.
delete from universities where university_id in (select dup from merge_map);

-- 4. Текст кнопки, попавший в варианты поиска.
delete from university_aliases where lower(alias_text) = 'готово';

commit;

-- Проверка глазами: у настоящих записей прибавилось людей и вариантов поиска,
-- людей без вуза — столько же, сколько было (это «не студенты СПб»).
select un.university_id as id,
       left(un.canonical_name, 45) as вуз,
       (select count(*) from users u where u.university_id = un.university_id) as людей,
       (select count(*) from university_aliases a where a.university_id = un.university_id) as вариантов
from universities un
where un.university_id in (1, 10, 11, 13, 16)
order by un.university_id;

select count(*) as вузов_в_справочнике from universities;
select count(*) as людей_без_вуза from users where university_id is null;
