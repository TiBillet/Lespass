---
slug: sysadmin-mon-chaton-part1
title: Linux, Docker, Compose, Traefik, Crowdsec, SSH, et c'est parti mon chaton !
authors: jonas
keywords: [ ubuntu, linux, wallet, traefik, crowsec, administration systeme, sysadmin, charte ]
tags: [ ubuntu, linux, wallet, traefik, crowsec, administration systeme, sysadmin ]
image: /img/federons/decollage.jpg
description: Installation et sécurisation d'un serveur linux "from scratch" pour acceuillir nos outils.
draft: False
---

![/img/federons/decollage.jpg](/img/federons/decollage.jpg)

<!-- truncate -->

Nous allons détailler ici la préparation d'un serveur sous distribution Debian (ou Ubuntu) pour acceuillir toutes nos
solutions libres que nous proposons dans la coopérative.

## Préparation du système

### Mises à jour du système

```shell
sudo apt update
sudo apt upgrade -y
sudo reboot
```

### Sécuriser le serveur

#### Connexion SHH par clé

```shell
# Depuis votre ordinateur client
ssh-copy-id <user>@<ip>
# ou ajouter votre cle id_rsa.pub directement sur le serveur 
nano .ssh/authorized_keys 
````

#### Changer le port d'écoute du service SSH et obliger la connexion via clé ssh

```shell
sudo nano /etc/ssh/sshd_config
# Port 22
Port 2252 # choisissez un port entre 1024 et 65535

# On en profite pour autoriser l'agent forwarding
# Cela sera trés utile pour pull/push des dépots git avec sa propre identité
# plutôt que celle du serveur.
AllowAgentForwarding yes

# Pour encore plus d'efficacité, on force la clé ssh.
# L'user n'en sera que plus reconnaissable, avec sa clé et son agent
# Attention à bien backuper votre clé. Si vous la perdez, vous perdez la main sur le serveur.

# To disable tunneled clear text passwords, change to no here!
PasswordAuthentication no
#PermitEmptyPasswords no


```

Attention, sur les serveurs VPS Ovh, un fichier de conf' ssh se cache dans le dossier /etc/ssh/sshd_config.d/ et permet
la connexion via mot de passe.
C'est utile pour la première connexion, mais ^ensez à le supprimer si vous voulez forcer la connexion par clé.

On recharge le daemon ssh :

```shell
sudo service sshd reload
```

#### Installer Crowdsec

Crowdsec est une solution open source très utile pour gérer la sécurité de votre serveur.
Il utilise une liste de banissement d'ip géré par la communauté, surveille les iptables, et peut même s'interfacer avec
un reverse proxy pour surveiller les requetes http. Plus d'info ici :

- https://www.crowdsec.net/
- https://plugins.traefik.io/plugins/6335346ca4caa9ddeffda116/crowdsec-bouncer-traefik-plugin

Avant d'installer la solution, il est nécéssaire de créer un compte gratuit sur leur site.

```shell
curl -s https://packagecloud.io/install/repositories/crowdsec/crowdsec/script.deb.sh | sudo bash
sudo apt-get install crowdsec
sudo apt install crowdsec-firewall-bouncer-iptables
```

Allez sur l'interface Crowdsec et générez votre token d'invitation :

- https://app.crowdsec.net/security-engines

Une commande du type suivant vous sera proposé :

```sudo cscli console enroll ****```

Lancez la, puis accepter l'invitation sur l'interface web.

Rebootez le serveur.

### Installation des dépendances

Mes ptits softs que j'aime utiliser :

```shell
sudo apt update
sudo apt install git byobu htop borgbackup

```

#### Docker :

- https://docs.docker.com/engine/install/ubuntu/

```shell
# Un script d'installation est disponible, si vous ne voulez pas le faire a la main.
curl -fsSL https://get.docker.com -o get-docker.sh
# Attention ! Vérifiez toujours le contenus des scripts téléchargé avant de les lancer en sudo ! 
sudo sh get-docker.sh
# Ajoutez votre utilisteur au groupe docker
sudo usermod -aG docker $USER
```

Relancez une nouvelle session utilisateur pour prendre en compte les changements de groupes et vérifiez que vous avez
bien les droits :

```shell
docker ps
```

#### Traefik

Traefik est un service de reverse proxy. C'est lui qui gère la redirection du conteneur depuis votre DNS et qui s'occupe
du chiffrement HTTPS grâce à la formidable initiative de lets'encrypt.

Pour le faire tourner, vous devez avoir un nom de domaine qui pointe vers l'ip de votre serveur. Ajoutez un champ A sur
votre admin DNS.

```shell
#clonez le dépot
git clone git@github.com:TiBillet/Traefik-reverse-proxy.git
cd Traefik-reverse-proxy
# Creez le sous réseau "frontend" commun
docker network create frontend
# Lancez les conteneur en mode daemon
docker compose up -d
# Vérifiez que le conteneur tourne et qu'il écoute bien les ports 80 et 443 :
docker ps
```

```shell
CONTAINER ID   IMAGE               COMMAND                  CREATED         STATUS         PORTS                                                                    NAMES
7f27255b935a   traefik:chevrotin   "/entrypoint.sh --lo…"   5 seconds ago   Up 4 seconds   0.0.0.0:80->80/tcp, :::80->80/tcp, 0.0.0.0:443->443/tcp, :::443->443/tcp traefik
```

#### Testons Traefik :

Lançons un conteneur de test pour savoir si tout tourne bien :

```shell
cd Traefik-reverse-proxy/test_conteneur
cat "DOMAIN=localhost" > .env # créons un fichier .env qui sera lu par compose
docker compose up
```

Si vous allez dans https://test.localhost, vous devriez voir une page whoami !

Si vous avez un DNS qui pointe vers l'ip de votre serveur, changez le .env en conséquence pour avoir une connexion
chiffrée en TLS !

# Conclusion

Et Hop ! Notre serveur est prêt pour acceuillir tous nos services futurs.
Dans un prochain article, nous allons voir comment installer Traefik en mode Wildcard pour le moteur TiBillet d'adhésion, de reservation et d'agenda
fédéré !
