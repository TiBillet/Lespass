# Guide Développeur - LaBoutik Client

## Déploiement sur Raspberry Pi

### Copie du projet via SSH

#### Prérequis
- Avoir les droits SSH sur le Pi
- Connaître l'IP du Pi et le nom d'utilisateur

#### Méthode 1 : scp (simple)

```bash
# Depuis ton PC vers le Pi
scp -r /chemin/vers/laboutik_client_pi_desktop_v2/ sysop@IP_DU_PI:/home/sysop/
```

Remplace :
- `sysop` par le nom d'utilisateur sur le Pi
- `IP_DU_PI` par l'adresse IP du Pi (ex: 192.168.1.100)

#### Méthode 2 : rsync (recommandé pour les mises à jour)

```bash
# Première copie
rsync -avz /chemin/vers/laboutik_client_pi_desktop_v2/ sysop@IP_DU_PI:/home/sysop/laboutik_client_pi_desktop_v2/

# Mise à jour (ne copie que les fichiers modifiés)
rsync -avz --update /chemin/vers/laboutik_client_pi_desktop_v2/ sysop@IP_DU_PI:/home/sysop/laboutik_client_pi_desktop_v2/
```

#### Méthode 3 : Clé SSH (sans mot de passe)

Si tu as configuré une clé SSH :

```bash
# Copier la clé publique sur le Pi (à faire une fois)
ssh-copy-id sysop@IP_DU_PI

# Puis copier sans mot de passe
scp -r /chemin/vers/laboutik_client_pi_desktop_v2/ sysop@IP_DU_PI:/home/sysop/
```

#### Exemple concret

```bash
# Si ton Pi a l'IP 192.168.1.50
scp -r /home/dIcon/laboutik_client_pi_desktop_v2/ sysop@192.168.1.50:/home/sysop/

# Ou avec rsync
rsync -avz /home/dIcon/laboutik_client_pi_desktop_v2/ sysop@192.168.1.50:/home/sysop/laboutik_client_pi_desktop_v2/
```

### Lancement sur le Pi

Après la copie, connecte-toi au Pi et lance le serveur :

```bash
ssh sysop@IP_DU_PI
cd laboutik_client_pi_desktop_v2
npm install
node nfcServer.js
```

## Partage de terminal avec tmate

`tmate` permet de partager un terminal SSH en temps réel, utile pour le débogage à distance ou l'assistance.

### Installation sur le Pi

```bash
sudo apt-get install tmate
```

### Utilisation

```bash
# Lancer tmate
tmate

# Afficher les informations de connexion
tmate display -p '#{tmate_ssh}'
```

### Partager la session

Une fois lancé, `tmate` affiche une URL SSH du type :

```
ssh session@nyc1.tmate.io
```

Tu peux partager cette URL avec un collaborateur pour lui donner accès à ton terminal.

### Commandes utiles

```bash
# Voir les connexions actives
tmate list-sessions

# Fermer la session
tmate kill-server
```

### Sécurité

- L'URL est temporaire et unique
- La session se termine quand tu quittes tmate
- Ne partage jamais l'URL publiquement

## Architecture du projet

```
laboutik_client_pi_desktop_v2/
├── install_pi/           # Scripts d'installation pour Raspberry Pi
│   ├── setup-laboutik-pi  # Script d'installation principal (X11)
│   ├── uninstall-x11.sh   # Désinstallation de X11/Openbox
│   └── src/               # Fichiers de configuration
├── modules/              # Modules Node.js
│   ├── devices/          # Pilotes NFC et imprimantes
│   └── commun.js         # Fonctions utilitaires
├── httpServer/           # Serveur HTTP personnalisé
├── www/                  # Frontend statique
├── env.js                # Configuration runtime
├── nfcServer.js          # Point d'entrée principal
└── readme_dev.md         # Ce fichier
```

## Développement

### Prérequis
- Node.js 24+
- npm

### Installation locale
```bash
npm install
```

### Lancement en mode développement
```bash
node nfcServer.js
```

Le serveur démarre sur http://localhost:3000

### Tests
```bash
# Test du module NFC (desktop)
node modules/devices/acr122u-u9.js

# Test du module NFC (Pi)
node modules/devices/vma405-rfid-rc522.js
```

## Notes

- Le projet utilise les modules ES (`"type": "module"` dans package.json)
- Le fichier `env.js` est requis au runtime
- Le dossier `pi/` contient l'ancienne version pour référence
- l'installation des modules pour le pi et desktop :
   .