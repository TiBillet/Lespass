# Stack :

- Django
- Docker
- Posgres
- Poetry
- Django rest framework

# Guidelines :

SUPER IMPORTANT :
Fabriquer du code facile a lire et a comprendre : FALC !
Le but est de faire un commun numérique facile à manipuler : on préfère faire des for que des compli complique. Le verbeux n'est pas un problème.

On commente toujours en Français et en Anglais !

Pour lancer une commande django depuis le terminal : docker exec lespass_django poetry run

# TEST playright

on peut lancer les test E2E directement depuis l'hote :
yarn playwright test --project=chromium --headed --workers=1 17-membership-free-price-multi.spec.ts

Ne jamais lancer tout les tests, les lancer un par un.