from django.contrib import admin

from . import models as m


class PersonAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
    )


class PartAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'film',
        'profession',
        'person',
    )


admin.site.register(m.Person, PersonAdmin)
admin.site.register(m.Film)
admin.site.register(m.Part, PartAdmin)
admin.site.register(m.Profession)
