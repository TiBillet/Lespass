# Chantier 05-R — Charger une copie de la production sans que rien ne sorte

> **Statut** : procédure proposée (2026-10-04), issue d'un audit en lecture seule du code.
> Pour la session R-0 (comptage des cas réels) et la répétition chronométrée de la nuit
> de bascule. **Rien n'est chargé tant que le mainteneur n'a pas validé.**

## 1. Pourquoi des précautions

La base de production contient, **par lieu**, des adresses et des clés en clair. Une
tâche Celery ou un simple enregistrement d'une ligne (signal) sur la copie peut appeler
le vrai serveur :

| Sortie | Stockée | Déclencheur sans action humaine |
|---|---|---|
| Ancien LaBoutik (V1) | `BaseBillet_configuration.server_cashless`, `key_cashless` **en clair** | ré-enregistrer une `LigneArticle` payée (machine à états `BaseBillet/signals.py` ~l.491) → `send_sale_to_laboutik` ; enregistrer un produit adhésion ; **ouvrir le tableau de bord de l'admin** (appel synchrone, `Administration/admin/dashboard.py` ~l.2585) |
| Webhooks des lieux | `BaseBillet_webhook.url` en clair | réservation / adhésion payée (signaux) |
| Ancien Fedow | `RootConfiguration.fedow_domain` (base, schéma public) | produits adhésion / badge, recharges — bloqué tant que la `FERNET_KEY` de dev ≠ prod (clé chiffrée) |
| Stripe live, Ghost, Brevo, Formbricks, Sunmi | clés **chiffrées** (Fernet) | bloqués par la `FERNET_KEY` de dev (erreur `InvalidToken`) |
| Imprimantes LAN | `laboutik_printer.ip_address` | une IP privée de la prod peut exister sur le réseau local |
| Mails | `.env` → Mailpit | relances d'adhésion (cron 5 h), mails de clôture, billets / factures (signaux) — partent dans Mailpit, visible du réseau local via Traefik |

Tâches automatiques (beat dans le worker `lespass_celery -B`, `TiBillet/celery.py`) :
`cron_morning` (crée des lieux d'attente, **relance les adhérents de tous les lieux**),
`cron_clotures_automatiques` (**écrit des clôtures** sur la copie), purge des brouillons
d'onboarding, cache SEO.

**Le `.env` de production ne doit PAS être copié** : il rendrait déchiffrables la clé
Stripe live, les clés Fedow / Ghost / Brevo / Sunmi, et donnerait le vrai serveur mail et
Sentry. La reprise n'a besoin d'aucune de ces clés.

## 2. Déjà fait

- `db-prod/` dans `.gitignore` (jamais dans un commit) et dans `.dockerignore` (jamais
  dans une image : `docker_push_update.sh` pousse l'image sur Docker Hub).

## 2 bis. Décisions du mainteneur (2026-10-04)

- **Même pile Docker que le dev** (pas de pile à part) : la base de dev est remplacée par
  la copie ; un flush remet le dev en place ensuite. La procédure ci-dessous s'adapte :
  `lespass_celery` (worker + beat) **arrêté** avant le chargement et tant que la copie est
  en place ; `stripe listen` arrêté ; neutralisation SQL (étape 4) **juste après le
  chargement, avant tout `manage.py`, avant d'ouvrir l'admin** ; jamais de `make test`,
  `make e2e` ni pytest sur la copie. Le réseau n'est pas coupé : la neutralisation est le
  seul garde-fou pour les adresses en clair (LaBoutik, webhooks).
- **Pas d'anonymisation.** 100 % local. **Claude ne lit aucune donnée personnelle** :
  seulement des comptages agrégés (`COUNT`, `GROUP BY` sur statuts, moyens, origines,
  dates, montants), jamais de `SELECT` qui ramène des mails, noms, adresses, numéros de
  carte, tags NFC ; règle écrite en tête de chaque brief d'ouvrier qui touche la copie.

**Script de neutralisation** (ignoré par git) : `bash db-prod/neutraliser_copie_prod.sh`
— refuse si `lespass_celery` ou `stripe listen` tournent, puis lance
`db-prod/neutraliser_copie_prod.sql` en une transaction (clés Stripe et Fedow du schéma
public ; par lieu : LaBoutik, Fedow, mails de clôture, webhooks, Ghost, Brevo,
Formbricks, clé Fedow du lieu) et vérifie qu'il ne reste rien, sinon annule tout.
Testé le 2026-10-04 sur la base de dev en transaction annulée (70 lieux, vérification
OK, rien écrit). Ordre : charger le dump → script → seulement ensuite `migrate_schemas`.

## 3. Procédure (variante pile à part, gardée pour mémoire)

0. **Avant** : arrêter `stripe listen` ; le mainteneur vérifie dans le `.env`, sans
   afficher les secrets, que `FERNET_KEY` est **différente** de celle de la production
   (déjà vérifié : `EMAIL_HOST="mailpit"`, `DEBUG=1`, `STRIPE_TEST=1`).
1. **Une pile Docker à part**, sur un réseau **interne** (aucune sortie internet), **sans
   Celery ni beat, sans Traefik** : postgres (`max_locks_per_transaction=512`), redis,
   memcached, mailpit, django (`sleep infinity`, image existante, **pas de build**).
   La base de dev n'est jamais touchée. Fichier `db-prod/docker-compose.copie-prod.yml`
   (ignoré par git).
2. **Vérifier la coupure** avant tout chargement : depuis le conteneur django de la
   copie, `requests.get("https://example.org", timeout=5)` doit **échouer**.
3. **Charger le dump** (`psql` ou `pg_restore --no-owner --no-acl`). Vérifier la version
   de PostgreSQL de la production (le dev est en 13).
4. **Neutraliser en SQL, avant tout `manage.py`** (noms de tables à vérifier sur le
   dump) : clés Stripe et `fedow_domain` du schéma public ; dans chaque schéma de lieu :
   `server_cashless`, `key_cashless`, webhooks désactivés, Ghost, Brevo, Formbricks, clé
   Fedow du lieu. **Ne pas vider les comptes Stripe Connect** (un identifiant vide
   déclenche une création de compte). Anonymisation des mails : facultative (le réseau
   est coupé), à décider.
5. **Migrer** (`migrate_schemas --executor=multiprocessing`) ; puis vider les
   `rapport_emails` et `sunmi_*` ajoutés par la branche.
6. **Travailler** : comptage (R-0), répétition chronométrée. Jamais de `make test` /
   pytest (ils utilisent la base partagée), jamais de worker ni de beat, pas de domaine
   navigable.
7. **Fin** : `docker compose -f db-prod/docker-compose.copie-prod.yml down -v`, supprimer
   le dump, vider `logs/` si des données de la copie y sont.
