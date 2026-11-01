# Примеры запросов

```sh
sqlite3 -header -column data/filmtr.db
```

## Фильмография режиссёра: что из неё в каталоге

```sql
SELECT f.year, coalesce(f.title_ru, f.title) AS title, r.value AS imdb,
       (SELECT group_concat(list_id, ' ') FROM list_entry e WHERE e.film_id = f.id) AS lists
FROM credit c
JOIN film f ON f.id = c.film_id
LEFT JOIN rating r ON r.film_id = f.id AND r.source = 'imdb'
WHERE c.role = 'director'
  AND c.person_id = (SELECT id FROM person WHERE name_ru = 'Андрей Тарковский')
ORDER BY f.year;
```

## Постоянные соавторы режиссёра

Кто чаще всего работал с режиссёром и в каких ролях:

```sql
SELECT coalesce(p.name_ru, p.name) AS person, c2.role, count(*) AS films
FROM credit c1
JOIN credit c2 ON c2.film_id = c1.film_id AND c2.person_id <> c1.person_id
JOIN person p ON p.id = c2.person_id
WHERE c1.role = 'director'
  AND c1.person_id = (SELECT id FROM person WHERE name = 'Ingmar Bergman')
  AND c2.role IN ('cinematographer', 'composer', 'writer', 'editor', 'actor')
GROUP BY c2.person_id, c2.role
HAVING films >= 4
ORDER BY films DESC;
```

## Связки «режиссёр + оператор» в каноне

```sql
SELECT coalesce(d.name_ru, d.name) AS director, coalesce(o.name_ru, o.name) AS cinematographer,
       count(*) AS films, group_concat(coalesce(f.title_ru, f.title), '; ') AS titles
FROM credit cd
JOIN credit co ON co.film_id = cd.film_id AND co.role = 'cinematographer'
JOIN person d ON d.id = cd.person_id
JOIN person o ON o.id = co.person_id
JOIN film f ON f.id = cd.film_id
WHERE cd.role = 'director' AND f.id IN (SELECT id FROM catalog)
GROUP BY cd.person_id, co.person_id
HAVING films >= 4
ORDER BY films DESC
LIMIT 20;
```

## Рейтинг режиссёров по присутствию в каталоге

```sql
SELECT coalesce(p.name_ru, p.name) AS director, count(*) AS films,
       sum(f.id IN (SELECT film_id FROM list_entry WHERE list_id LIKE 'tspdt%')) AS in_tspdt
FROM credit c
JOIN person p ON p.id = c.person_id
JOIN catalog f ON f.id = c.film_id
WHERE c.role = 'director'
GROUP BY c.person_id
ORDER BY films DESC
LIMIT 30;
```

## Фильмы с фильтрами

Советские и российские драмы 1960–1980-х в каталоге, лучшие по IMDb:

```sql
SELECT title, year, imdb_rating, directors, lists
FROM film_card
WHERE id IN (SELECT id FROM catalog)
  AND id IN (SELECT film_id FROM film_country WHERE country IN ('SU', 'RU', 'Q15180'))
  AND id IN (SELECT film_id FROM film_genre WHERE genre = 'Drama')
  AND year BETWEEN 1960 AND 1989
ORDER BY imdb_rating DESC;
```

## Что вошло в каталог только через критиков

Фильмы, которых нет в ядре IMDb, но которые есть в опросах:

```sql
SELECT title, year, imdb_votes, directors, lists
FROM film_card
WHERE id IN (SELECT film_id FROM list_entry WHERE list_id IN ('tspdt-1000', 'sight-and-sound-2022-critics'))
  AND id NOT IN (SELECT film_id FROM list_entry WHERE list_id = 'imdb-core-5000')
ORDER BY imdb_votes DESC;
```
