---
slug: codensamb-preambule
title: Codons le logiciel de caisse enregistreuse "LaBoutik" depuis zero
authors: [ jonas, glen, mike ]
description: Ça sert a rien de faire du logiciel libre si on explique pas pourquoi et comment.Venez contribuer quelque que soit votre domaine de connaissance .
tags: [ cod-ensamb, code-with-me, blog, python, poetry, django, jetbrains, pycharm, tibillet, cashless, caisse-enregistreuse, tuto, ]
keywords: [ cod-ensamb, code-with-me, blog, python, poetry, django, jetbrains, pycharm, tibillet, cashless, caisse-enregistreuse, tuto, ]
draft: false
image: /img/blog/cod-ensamb/2023-10-26/congratulations.png
---


## Préambule

Dans la Coop', on pense que ça ne sert à rien de faire du logiciel libre si on explique pas pourquoi et comment. Donc premier effort à fournir : de la documentation et de la vulgarisation.

On commence par un chantier participatif ? Tous les lundi : cod' ensamb !

L'idée : Recoder tout le projet LaBoutik (Caisse enregistreuse, cashless, monnaie locale, etc... pour en savoir plus : https://tibillet.org).

Étape par étape, comme un grand tutoriel géant, nous allons détailler pourquoi et comment nous le construisons.

Le but avoué est d'encourager les contributions aux projets de la coopérative, de réduire le flou technologique, de vulgariser le code, mais surtout de s'engager dans une démarche de partage de savoir.

<!-- truncate -->

## Koi fé ? (TLDR;)

Dans ce tuto, nous allons voir comment : 

- Préparer son environnement de développement python avec Poetry 
- Configurer l'IDE de Jetbrain, Pycharm, pour qu'il nous facilite la vie 
- Installer Django 4.2
- Créer ses premiers objets en base de donnée
- Créer une interface d'admin pour les créer et les manipuler

# Codons le logiciel de caisse enregistreuse "LaBoutik" depuis zero

### La "stack" : 

Autrement dit, l'ensemble des librairies, framework (cadriciel) et outils divers pour construire notre solution.

- Linux (ubuntu/debian) quoique, on pourrait installer la stack sur windows et mac, mais on va le faire paske faut bien choisir.
- Python 3.10
- Poetry (outil de gestion d'environement python qui sert à maintenir nos versions à jour et nous assurer que les librairies n'aient pas d'incompatibilité entre elles )
- Django 4.2

Et bien sur notre IDE préféré qui nous facilite grandement la tache : Pycharm (https://www.jetbrains.com/fr-fr/pycharm/)

### Le dépot GIT

Travaillons sur le dépot : https://github.com/CoopCodeCommun/LaBoutik-CodEnsamb

## Installons Poetry

- [https://python-poetry.org/docs/](https://python-poetry.org/docs/)


```shell=
curl -sSL https://install.python-poetry.org | python3 -
git clone git@github.com:CoopCodeCommun/LaBoutik-CodEnsamb.git
```
 
```shell=
### Sur Mac :
brew install poetry
```


Une fois le poetry installé et le repos git crée. On peut initialiser le poetry.
A La racine du projet : 
```shell=
poetry init
```
Répondez aux questions en vérifiant  
*Compatible Python versions [^3.10] :* laissez par defaut .
*Pour les question concernant les dépendances , répondez* No ( nous les installerons nous meme )

Vous avez maintenant un fichier **pyproject.toml** dans  votre projet qui reprend tous les paramétres saisis .
Ouvrez ce fichier , vous pouvez ici entrer les dépendances que vous sohaitez dans la section *[tool.poetry.dependencies]*: 
![](https://codimd.communecter.org/uploads/upload_b663a13e2226de8c483a1b4e9b747fef.png)

Le *^* indique version minimun
Nous allons ajouter Django en ligne de commande en figeant la version à l'aide de *@* ( à ce jour Octobre 2023 la version stable est : 4.2) : 

```shell=
poetry add django@4.2
```
Ce qui à pour effet d'installer aussi les dépendances necessaires pour le projet et de créer le fichier *poetry.lock* qui est l'état actuel de notre projet .

>Si vous avez cloné le projet , les 2 premières étapes ``` poetry init ``` et ```poetry add django@4.2```ne seront pas necessaire .( elles le sont uniquement si vous partez de zéro * ) 

Maintenant entrons et travaillons dans l'environement virtuel qui nous permet d'avoir le meme environement de travail quelque soit l' OS utilisé : 
```shell=
poetry shell
```


## Installons et configurons Django 


Créons le projet (l'application)
```shell=
    django-admin startproject laboutik .
    // le point '.' est utilisé pour que la racine du project soit dans le dossier dont on est situé
    ./manage.py startapp labutik_core
    
```
idem( * ) les 2 premières commande ci dessus ne sont plus necessaires si vous avez cloné le projet .

Dans laboutik/settings.py on ajoute:
```shell=
    INSTALLED_APPS = [
    ...,
    'laboutik_core',
    ]
    
    AUTH_USER_MODEL = 'laboutik_core.CustomUser'
```
Dajngo à besoin d'une BD, nous allons la créer : 
```shell=
./manage.py migrate
```
on voit une nouvelle base de données dans notre projet : 
![](https://codimd.communecter.org/uploads/upload_1bd46a93d9d713f32601e0efc53f7873.png)

et dans le fichier settings : 
![](https://codimd.communecter.org/uploads/upload_3df05cceccef8245a1467116db77411c.png)


Pour le moment nous laissons sqlite3, nous changerons plus tard en Production vers une DB plus adaptée .

Lançons le serveur : 
```shell=
./manage.py runserver
```

Maintenant en vous connectant à l'adresse : http://127.0.0.1:8000/ vous devriez avoir la page ci dessous : 

![](https://codimd.communecter.org/uploads/upload_3095d9553a558ca4f5024567eeb12c7f.png)

Vous avez maintenant dans votre projet 2 nouveaux répertoires *laboutik* et *laboutik_core* et le fichier racine *manage.py* : 


### Configurons Pycharm
Pour l'instant nous n'avons pas indiqué à Pycharm notre environement . Il faut lui indiquer que nous travaillons avec Python3.10 , Poetry et Django .
Configurons l'interpreteur , dans settings de Pycharm : 
![](https://codimd.communecter.org/uploads/upload_c47a858894d9007d560bf34272948d6f.png)




Add interpreter/Local/Poetry environement : 
![](https://codimd.communecter.org/uploads/upload_ca5d21bf2d08a1646387fd63c7625a5e.png)

Dans "Poetry executable" indiquez le chemin d'installation de poetry installé precedemment .

Vérifions la configuration pour Django : 
![](https://codimd.communecter.org/uploads/upload_5f9d1348c6b8fc49c2f197b05110e3d2.png)


Du coup maintenant Pycharm va nous alerter en cas d'erreur de syntaxe , proposer de l'auto-complétion ... trop top :+1: 

Merci à JetBrains de nous supporter pour nos projets .
Pour tester si notre IDE a bien compris notre environement de travail , allez dans le fichier urls.py placer le curseur sur "path" et faites F12 .
![](https://codimd.communecter.org/uploads/upload_62aa41db1310966ee8ab869fd0b63766.png)
Vous devriez etre redirigé vers le fichier conf.py .
>Remarque pour Mac : 
>le raccourcis clavier est "fn + F12" si cela ne fonctionne pas modifiez le model Keymap sur " sublime Text Copy" 
>![](https://codimd.communecter.org/uploads/upload_6648e596509e95743c39491e099b7e68.png)


### Modele user

La création d'un model user custom est fortement conseillé dès le début du projet.
Dans le futur il devient très compliqué de modifier le modele user une fois nos modeles sont lancés.

Dans le fichier models.py : 

```python=
from django.db import models
from django.contrib.auth.models import AbstractUser
from uuid import uuid4

class CustomUser(AbstractUser):
    """
    Modèle de base pour les utilisateurs
    On utilise des uuid4 plutôt que des pk auto-incrementés
    """
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, db_index=False)
```

Dans le fichier settings.py : 

```python
# Model user custom
AUTH_USER_MODEL = 'laboutik_core.CustomUser'
```

On applique les modifications en faisant une migration : 
```shell
./manage.py makemigrations
./manage.py migrate
```





## Architecture rapide du projet

Listons les "objects" dont nous allons avoir besoin.

- Configuration
- Point de vente
- Catégories
    - Produit
        - TVAs
    - Prix
- Users
    - droits
- Moyens de paiement
- Ventes

### Codons nos objets : 

Dans le fichier models.py : 

TODO: Vidéo sur https://peertube.communecter.org

Le detail du codage en Live [ici](https://2023-10-16-CodeWithMe-CodagePremiersObjets.mp4)


## Création du modèle de base de donnée et d'administration


### Routage url

le fichier urls.py

il existe déja l'url de l'admin: 

```python
urlpatterns = [
    path('admin/', admin.site.urls),
]
```
Lancement du serveur : 

```shell
./manage.py runserver
-> Starting development server at http://127.0.0.1:8000/
```


Du coup, si je vais dans http://127.0.0.1:8000/admin/

![](https://codimd.communecter.org/uploads/upload_16d13cc013a4cf7610ebcf2f5a794e3f.png)


### Administration Django

Créons notre utilisateur admin.

```
# Création du super user "root"
./manage.py createsuperuser
```

Attention, createsuperuser fabrique des users avec is_staff = True ET is_superuser = True
Seul is_staff est nécéssaire pour acceder à l'admin. is_superuser est comparable à un utilisateur "ROOT" qui a tout les droits sur l'admin.

![](https://codimd.communecter.org/uploads/upload_f20bd7ef2d8895d60fba43854d39e6ba.png)

Enregistrer les modèles dans l'admin : 

```python=
# laboutik_core/admin.py
from django.contrib import admin
from laboutik_core.models import Product, Price, VAT, Category, PointOfSale

# Register your models here.

admin.site.register(Product)
admin.site.register(Price)
admin.site.register(VAT)
admin.site.register(Category)
admin.site.register(PointOfSale)

```

![](https://codimd.communecter.org/uploads/upload_203c37f9e1c3d369fc36423d5458e115.png)

TODO: Uploader dans peertube
La vidéo complete en detail [ici](https://2023-10-16-CodeWithMe-PremierAdmin.mp4)


## Conclusion

Nous avons maintenant notre environnement installé et nous pouvons créer des objets en base de donnée. 

Dans les prochaines sessions, nous verrons comment créer notre "frontend" avec les templates Jinja, et comment rendre cette stack "MVT" moderne avec HTMX.