# TiBillet-Ticket
Vente de billet et gestion évènementielle.

## Installation pour dev' :

```shell
cd Docker/Development
docker-compose --build up -d

# une fois buildé et lancé, on rentre dans le conteneur :
docker exec -ti tibillet_django bash

# --> dans le conteneur :
  # on crée la DB :
  python manage.py migrate
  # On lance le serveur avec un alias ( cf bashrc dans root )  
  # python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
  rsp 
```

# Credits :

## Développement :

Jonas TURBEAUX & Nicolas DIJOUX
pour Peaks2Prod & 3Peaks Production.

Free for personal and commercial use under the MIT 3.0 license

## Graphisme : 

Massively by HTML5 UP
html5up.net | @ajlkn
Free for personal and commercial use under the CCA 3.0 license (html5up.net/license)


This is Massively, a text-heavy, article-oriented design built around a huge background
image (with a new parallax implementation I'm testing) and scroll effects (powered by
Scrollex). A *slight* departure from all the one-pagers I've been doing lately, but one
that fulfills a few user requests and makes use of some new techniques I've been wanting
to try out. Enjoy it :)

Demo images* courtesy of Unsplash, a radtastic collection of CC0 (public domain) images
you can use for pretty much whatever.

(* = not included)

AJ
aj@lkn.io | @ajlkn


Credits:

	Demo Images:
		Unsplash (unsplash.com)

	Icons:
		Font Awesome (fontawesome.io)

	Other:
		jQuery (jquery.com)
		Scrollex (github.com/ajlkn/jquery.scrollex)
		Responsive Tools (github.com/ajlkn/responsive-tools)