Voici une liste des petits trucs utiles à savoir pour développer sur ce projet.

# Stack :

- Django
- Docker
- Posgres
- Poetry
- Django rest framework

# Guidelines :

## FALC

SUPER IMPORTANT :
Fabriquer du code facile à lire et à comprendre : FALC !
Le but est de faire un commun numérique facile à manipuler : on préfère faire des for que des compli complique. Le verbeux n'est pas un problème.

On commente toujours en Français et en Anglais !

## Exectution dans l'environnement django de docker :

Pour lancer une commande django depuis le terminal : docker exec lespass_django poetry run

## Viewset et Serializer

On utilise au maximum les vues ViewSet de Django rest framework.
On utilise pas les form django : Chaque input doit être vérifié par un serializer.


# TEST playright

on peut lancer les test E2E directement depuis l'hote :
cd test/playwright && yarn playwright test --project=chromium --headed --workers=1 17-membership-free-price-multi.spec.ts

Ne jamais lancer tous les tests, les lancer un par un.