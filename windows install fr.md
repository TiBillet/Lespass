# Installation Windows et contribuer avec VSC :

### Installer VSC
https://code.visualstudio.com

### Intaller Git
https://git-scm.com/download/win

### Installer Docker
https://docs.docker.com/desktop/windows/install/

### Mettre a jour le kernel WSL
https://docs.microsoft.com/fr-fr/windows/wsl/install-manual#step-4---download-the-linux-kernel-update-package

### dans power shell ( touche windows + x -> powershell admin) :
```
wsl --set-default-version 2
```

### modifier le etc/hosts
Avec les droits admin, modifier le fichier suivant :
```C:\Windows\System32\drivers\etc\hosts```

rajoutez à la fin :
```
# TiBillet Dev
127.0.0.1       tibillet-local.me
127.0.0.1       www.tibillet-local.me
127.0.0.1       demo.tibillet-local.me
```

## Récuperer le projet 

Créer un compte github
Lancer VSC
Clonez un dépot avec l'adresse : ```https://github.com/Nasjoe/TiBillet-Ticket```

Autorisez VSC a se connecter avec son compte github

Dans VSC, icone extension, installer :
```
Docker - Par microsoft
Django - Par Baptiste Darthenay
```

## Configurer docker
ouvrir un terminal dans VSC :


```
docker network create frontend
docker login registry.3peaks.re
docker pull registry.3peaks.re/billetterie_django:2.8-bullyeses_python38_prelog4s
```
Demandez à Jonas en privé pour pull l'image :)


Toujours dans le même terminal, notifiez à Git qui vous êtes :
```
git config --global user.email "moi@moi.me"
git config --global user.name "Moi Windows VSC"
```


### Copier les variables d'environement utiles au projet
Dans l'explorateur de gauche, ouvrir Docker/Development.

Copier / coller env_example.

renommer env_example copy en .env

### Construire et lancer les conteneurs 
clic droit sur docker-compose.yml -> Compose Up

Une fois terminé, si le parefeu windows se lance, cocher et accepter tout.

### Entrer dans le conteneur qui fait tourner l'application
Allez sur l'onglet docker de VSC

Dans la partie CONTAINERS, clic droit sur billetterie_django -> attach shel

### Créer la base de donnée et le super utilisateur
Dans le terminal qui s'ouvre:
```
python manage.py migrate
python manage.py createdemo
python manage.py create_tenant_superuser
    -> public
```
Bien entrer nom, email et mot de passe.

### lancer l'application
Toujours dans le conteneur :
```
python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
```

### 
Sur votre navigateur, aller sur :
http://demo.tibillet-local.me:8002

Pour l'admin :
http://demo.tibillet-local.me:8002/admin

avec email / password créé plus haut 