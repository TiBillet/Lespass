# Déploiement — Traefik lit les domaines personnalisés dans Lespass

> **Statut** : idée, spec à écrire. Demande du mainteneur (2026-10-12), après la nuit de bascule du
> chantier 05.
> Pré-requis : Traefik v3 en production (fait le 2026-10-12).

## Le problème
Un lieu peut avoir son propre domaine (`fairefestival.fr`, `guichet.latendresse.fr`…). Traefik ne le
route, et Let's Encrypt ne lui délivre un certificat, que s'il est écrit dans la règle du routeur
`custom_dns` (`docker-compose.prod.yml`). Depuis le 2026-10-12, cette règle est dans le `.env`
(`CUSTOM_DOMAINS_RULE`, voir `env_example`) au lieu d'être en dur dans le compose. Mais il reste
**un geste manuel** à chaque nouveau domaine : éditer le `.env` du serveur, puis
`docker compose up -d lespass_nginx` (le site coupé une seconde). Un lieu qui ajoute son domaine dans
l'admin n'a rien tant que le mainteneur ne l'a pas fait.

Une règle « attrape-tout » (`HostRegexp`) ne suffit pas : Traefik ne demande un certificat que pour
les noms écrits en `Host()` (ou dans `tls.domains`).

## Aujourd'hui : la marche manuelle (rodée le 2026-10-12 avec `codecommun.coop`)
Sur le serveur, dans `~/main-lespass` :
1. Le DNS du domaine pointe sur le serveur : `getent ahostsv4 <domaine>` (sinon attendre : 5 échecs
   Let's Encrypt par heure bloquent le nom une heure).
2. `.env` : ajouter `|| Host(\`<domaine>\`)` à `CUSTOM_DOMAINS_RULE` (Traefik) ET `,<domaine>` à
   `ADDITIONAL_DOMAINS` (Django : `ALLOWED_HOSTS`, `TiBillet/settings.py`). Sans la seconde, le
   domaine a son certificat mais Django répond **404**.
3. `docker compose up -d --no-deps lespass_nginx` (nouveau label → certificat ; une seconde de
   coupure). Attendre `Verify return code: 0 (ok)` (`openssl s_client -verify_hostname`).
4. `docker compose up -d --no-deps lespass_django` (le `.env` n'est relu qu'à la création du
   conteneur : **~1 min 30 de coupure**, le temps de `start.sh`). **Toujours `--no-deps`** : sans
   lui, postgres est recréé aussi (vécu le même jour).
5. Le domaine dans Lespass, APRÈS le certificat : `Customers.Domain` lié au lieu, `is_primary`
   si c'est le nouveau principal (l'ancien passe à False), puis
   `cache.delete(f"canonical_primary_domain:<schéma>")` (le middleware de redirection garde le
   principal 1 h en cache). Dès qu'il est principal, les anciens domaines du lieu redirigent (302).
6. Contrôle : le nouveau domaine répond 200, l'ancien 302 vers lui.

**Défaut constaté** : `ADDITIONAL_DOMAINS` sert aussi aux suffixes proposés à la création d'un lieu
(`onboard/services.py`, `dns_suffixes_disponibles`) : chaque domaine personnalisé y apparaît
(`monlieu.fairefestival.fr`, `monlieu.codecommun.coop`…). Séparer les deux listes (une variable pour
`ALLOWED_HOSTS`, une pour les suffixes d'onboarding) — ou faire lire `ALLOWED_HOSTS` dans
`Customers_domain`, avec le provider HTTP ci-dessous.

## L'idée : le provider HTTP de Traefik
Lespass connaît déjà la liste : les lignes de `Customers_domain` qui ne finissent ni par
`tibillet.re` ni par `tibillet.coop` (les deux wildcards).
Traefik v3 sait lire sa configuration dynamique sur une adresse HTTP, à intervalle régulier
(`providers.http.endpoint`, `pollInterval`).

1. Lespass expose une route interne qui rend, en JSON, un routeur par domaine personnalisé
   (`rule: Host(...)`, `tls.certResolver: myresolver`, service = `lespass_nginx`).
2. La route n'est joignable que depuis le réseau Docker de Traefik (jamais depuis Internet), et ne
   rend que des noms de domaine.
3. La conf statique de Traefik (`~/TraefikV3/wildcard_conf`) déclare ce provider.
4. Un domaine ajouté dans l'admin : routé et certifié au tour suivant, sans toucher au compose ni
   couper le site. Un domaine retiré : son routeur disparaît.

## Points à trancher dans la spec
1. Le service cible : déclaré par le provider HTTP (adresse de `lespass_nginx`), ou référence au
   service du provider Docker (`lespass_nginx@docker`) ?
2. La protection de la route : réseau seulement, ou réseau + clé ?
3. Le DNS d'un domaine pas encore pointé sur le serveur : Let's Encrypt échouera, et 5 échecs par
   heure bloquent le nom une heure (vécu la nuit de bascule avec `tibillet.coop`). Ne rendre que les
   domaines dont le DNS pointe déjà sur le serveur ?
4. Que devient `CUSTOM_DOMAINS_RULE` : supprimé, ou gardé comme secours si Lespass ne répond pas
   (Traefik garde la dernière conf lue) ?
5. Le pas de temps (`pollInterval`) : 30 s ? 1 min ?
