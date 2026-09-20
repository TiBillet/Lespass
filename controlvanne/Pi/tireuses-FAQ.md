# Tireuses — FAQ / aide-mémoire

Une question → l'endroit où agir. Pour le détail, suivre les liens.
Chemins sur le Pi : dépôt dans `/home/sysop/tibeer/`, code dans `/home/sysop/tibeer/controlvanne/Pi/`.

## Installation

**L'affichage du kiosk est trop grand / trop petit (écran 10 pouces) — où régler ?**
→ `controlvanne/Pi/config/xinitrc.bash`, option Chromium `--force-device-scale-factor` (`1.0` pour un écran 10 pouces ; `2.0` = tout deux fois plus gros) à adapter en fonction de la taille de l'ecran.
Déployé vers `/home/sysop/.xinitrc` par `make deploy` — ne pas éditer `.xinitrc` à la main, il serait écrasé.
Vérifier la valeur en service : `ps aux | grep -o 'force-device-scale-factor=[0-9.]*'`.
Détail : issue [#448](https://github.com/TiBillet/Lespass/issues/448).

**La vanne s'ouvre au démarrage, ou reste fermée quand on badge — où régler ?**
→ `VALVE_ACTIVE_HIGH` dans `/home/sysop/tibeer/controlvanne/Pi/.env`. C'est une **description du câblage**, à **mesurer** sur chaque Pi (service arrêté, vanne sans pression) :
`sudo systemctl stop tibeer` puis `pigs w 18 1` / `pigs w 18 0` → la vanne s'ouvre à `1` = `True`, à `0` = `False`. Laisser fermée, écrire la valeur, `sudo systemctl start tibeer`.
⚠️ `make claim` régénère le `.env` depuis `config/env_example` (valeur `True`) : re-vérifier après tout ré-appairage.
Détail : [README.md](README.md) § Variables d'environnement.

**Où est la configuration du Pi ?**
→ `/home/sysop/tibeer/controlvanne/Pi/.env` (généré par `make claim`, non versionné). Après modification : `sudo systemctl restart tibeer kiosk`.
Modèle : `config/env_example`. Détail : [README.md](README.md) § Variables d'environnement.
