from django.shortcuts import render, get_object_or_404
from . import models as m

def index(request):
    return render(request, 'film_list.html', {'films': m.Film.objects.all()})

def film(request, film_id):
    film_obj = get_object_or_404(m.Film, pk=film_id)
    return render(request, 'film.html', {'film': film_obj})
