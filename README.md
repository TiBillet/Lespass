# TiBillet

Réseau événementiel et coopératif.

TiBillet est un système de paiement sans contact Zéro Espèce ( Cashless ), de gestion d'évènements, de gestion de salles
de restauration, d'engagement associatif, de boutique et de reservation en ligne … mais pas uniquement !

C'est aussi un outil de mise en réseau et de gestion d'une carte cashless locale et commune à plusieurs lieux.

L’idée de TiBillet est de se réapproprier des outils qui n’existent tout simplement pas en libre, et de les mutualiser
pour en faire un réseau de musiciens, de lieux et pourquoi pas une monnaie locale dédiée, à la culture, aux associations, aux tiers-lieux, etc...

La richesse de TiBillet, c’est de chercher à créer des zones d’échange, de créer une économie circulaire, sociale et
solidaire, décentralisée et non spéculative à l'échelle d'un territoire.

TiBillet est en période de BETA et en expérimentation sur plusieurs lieux sur l'ile de la Réunion. Venez nous voir au
Bisik, à la Raffinerie, et au Manapany Festival !

Pour en savoir plus : https://wiki.tibillet.re

## Mindmap VF

![](Presentation/carte_heuristique.png)

## Ticketing frontend design.

Open [Front Billetterie.excalidraw](https://github.com/TiBillet/TiBillet/blob/main/Presentation/Front%20Billetterie.excalidraw)
on https://excalidraw.com/

![](Presentation/Design_Front_Ticket.svg)

## Cashless frontend design.

Open [Front Cashless.excalidraw](https://github.com/TiBillet/TiBillet/blob/main/Presentation/Front%20Cashless.excalidraw)
on https://excalidraw.com/

![](Presentation/Design_Front_Cashless_APP.svg)

## Instances de démonstration

TiBillet bouge beaucoup en ce moment !
Si les liens ci-dessous ne sont pas valide, c'est que nous avons les mains dans le cambouis :) 
Revenez plus tard ou passez nous voir sur le discord ! 

### Billetterie démo ( nighty build ) :

https://run.tibillet.org

### Cashless démo ( nighty build ) :

https://democashless.betabillet.tech

- login : adminou
- password : miaoumiaou

Une fois sur la page d'administration, aller sur "Voir le site" pour découvrir l'interface cashless. Ou aller sur :
https://demo.cashless.tibillet.org/wv/

## Introduction.

Le présent dépot ne contient pas encore toutes les sources du projet en cours d'expérimentation :
La billetterie est en cours de publication. Le Cashless est en cours d'audit de sécurité et sera publié sous licence
libre ASAP.

Mais ceci dit, si vous souhaitez l'expérimenter chez vous, n'hésitez pas à nous contacter. Toute aide et retour
d'expérience sont les bienvenus.

TiBillet est originalement construit par l'association des 3Peaks de Manapany : Créateurs du Manapany Surf Festival. 

La société coopérative ( SCIC TiBillet Coop ) a été créé pour porter juridiquement une fédération autour des acteurs de la
solution :
Developpeurs, utilisateurs, organisateurs, tiers-lieux et collectivités locales seront réunis autour d'une coopérative
d'interet commun.

Venez discuter avec nous :

- Discord : https://discord.gg/7FJvtYx

## Install :

### For Production :

You need
- a wildcard ssl certificate. 
It is possible to generate one with letsencrypt and a dns-challenge.
You can use this repo for example :
https://github.com/TiBillet/Traefik-reverse-proxy/tree/main/wildcard

- Docker & docker-compose See https://docs.docker.com/ for installation.

- copy env_example to .env and fill in the necessary variables.

```shell
cd Docker/Production
docker compose pull
docker compose up -d 
docker exec -ti billetterie_django tibinstall
```

### For Contribution :

1. Go talk to us in discord :)
2. Accept the code of conduct.
4. Follow lines below :

#### Dependency

- Traefik. Example here :
  https://github.com/TiBillet/Traefik-reverse-proxy

- Docker & docker-compose See https://docs.docker.com/ for installation.

```shell
cd Docker/Development
# Copy the example environement file 
cp ../env_example .env
# populate .env file with your own variables.
nano .env
# build docker image
docker-compose build
# launch 
docker-compose up
```

#### First time launch

```shell

# Go deeper inside the django container :
docker exec -ti billetterie_django bash

# --> Inside the container :
  # apply the db migration ( tables creations )
  python manage.py migrate
  
  # Populate the database with the public tenant ( the first one : www. )
  python manage.py create_public
  
  # Create the root user on the "public" tenant
  # Use VERY STRONG PASSWORD AND DON'T USE THE SAME EMAIL as .env !
  python manage.py create_tenant_superuser
    ? -> public
    
  # Collect Static :
  python /DjangoFiles/manage.py collectstatic
  
```

#### POP demo data :)

If you want to use the demonstration data, add this to your /etc/hosts :
```
#example /etc/hosts
172.17.0.1       django-local.org
172.17.0.1       www.django-local.org
172.17.0.1       m.django-local.org
172.17.0.1       raffinerie.django-local.org
172.17.0.1       bisik.django-local.org
172.17.0.1       vavangart.django-local.org
172.17.0.1       3peaks.django-local.org
```


```shell
# Go deeper inside the django container :
docker exec -ti billetterie_django bash

# Run the server :
python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
# or
rsp
  
# Pop data inside the TiBillet-Ticket/DjangoFiles/data/domains_and_cards.py
# Change the file if you want !
# --> With a second shell inside the container :
  python manage.py pop_demo_data
```

Test with ```www.$DOMAIN/admin``` and ```raffinerie.$DOMAIN/admin```


# BACKEND API Documentation

### API Postman with example :

https://documenter.getpostman.com/view/17519122/UVeDtTFC

# FRONTEND

Le frontend basé sur le framework Vue.js est en cours de développement. N'hésitez pas à nous contacter pour contribuer.

# Licence :

TiBillet is ( for the moment ) under the Server Side Public Licence ( SSPL ), an AGPL like licence :

https://www.mongodb.com/licensing/server-side-public-license

https://webassets.mongodb.com/_com_assets/legal/SSPL-compared-to-AGPL.pdf


# Crédits and développement :

[AUTHORS.md](https://github.com/TiBillet/TiBillet/blob/main/AUTHORS.md)

# THANKS & SPONSORS

- La Raffinerie

https://www.laraffinerie.re
 
[![logo La Raffinerie](https://documentation.laraffinerie.re/images/thumb/c/c3/LogoRaffinerie.png/300px-LogoRaffinerie.png)](https://www.laraffinerie.re)

- Communnecter.org

https://www.communecter.org

[![logo Communnecter](https://www.communecter.org/assets/94396c20/images/logos/logo-full.png)](https://www.communecter.org)

- JetBrain

https://jb.gg/OpenSourceSupport

![logo JetBrain](https://resources.jetbrains.com/storage/products/company/brand/logos/jb_beam.svg)

