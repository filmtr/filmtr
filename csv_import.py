# -*- coding:utf-8 -*-

import sys
import csv

from upprint import upprint as pprint

from filmtr.core import models as m


#Русское название, Профиль на Кинопоиске, Год, Страна, Продюсер, Режиссёр, Сценарист, Композитор, Актёр


PROFESSIONS = [
    'producer',
    'director',
    'screenwriter',
    'composer',
    'actor',
]

FIELDNAMES = [
    'name',
    'link',
    'year',
    'country',
] + PROFESSIONS


def add_persons(film, profession_slug, persons_raw):
    profession, created = m.Profession.objects.get_or_create(slug=profession_slug)
    person_names = [p.strip() for p in persons_raw.split(',')]
    for person_name in person_names:
        person, created = m.Person.objects.get_or_create(name=person_name)
        part = m.Part(
            person=person,
            film=film,
            profession=profession,
        )
        part.save()


def csv_import(filename):
    #m.Film.objects.all().delete()

    csvfile = open(filename, 'r')
    reader = csv.DictReader(csvfile, fieldnames=FIELDNAMES)

    for i, film_dict in enumerate(reader):
        #pprint((i, film_dict))
        if i == 0:
            continue

        print '=' * 50
        print film_dict['name']
        film = m.Film()
        film.name = film_dict['name']
        film.year = film_dict['year']
        film.kinopoisk_link = film_dict['link']
        film.save()

        for profession_slug in PROFESSIONS:
            persons_raw = film_dict[profession_slug]
            add_persons(film, profession_slug, persons_raw)


if __name__ == '__main__':
    try:
        filename = sys.argv[1]
        print filename
        csv_import(filename)
    except:
        print 'No args'
        raise
