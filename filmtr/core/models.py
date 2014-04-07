from django.db import models


class Person(models.Model):
    name = models.CharField(max_length=200)
    def __unicode__(self):
        return self.name


class Film(models.Model):
    name = models.CharField(max_length=200)
    year = models.IntegerField()
    country = models.ManyToManyField('Country')
    kinopoisk_link = models.URLField(max_length=200)

    @models.permalink
    def get_absolute_url(self):
        return ('film', [self.pk])

    def __unicode__(self):
        return self.name


class Profession(models.Model):
    name = models.CharField(max_length=20)
    slug = models.SlugField(max_length=20)
    def __unicode__(self):
        return self.slug


class Part(models.Model):
    film = models.ForeignKey(Film)
    person = models.ForeignKey(Person)
    profession = models.ForeignKey(Profession)
    description = models.TextField()
    def __unicode__(self):
        return self.description


class Country(models.Model):
    name = models.CharField(max_length=200)
    def __unicode__(self):
        return self.name
