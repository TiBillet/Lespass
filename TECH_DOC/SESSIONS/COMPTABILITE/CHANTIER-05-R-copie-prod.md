# Chantier 05-R — Charger une copie de la production sans que rien ne sorte

> **Statut** : procédure arrêtée le 2026-10-05 (demande du mainteneur : « Prépare le
> compose avec les sécurités et les bretelles ! Pas d'envoi de mail, débranche Celery »).
> La **pile à part** devient LA procédure ; la variante « même pile que le dev » du
> 2026-10-04 est abandonnée (§2 bis, gardée pour mémoire). Fichiers prêts, **rien n'est
> démarré ni chargé**. Pour la session R-0 (comptage des cas réels) et la répétition
> chronométrée de la nuit de bascule.
>
> **2026-10-06** (décision du mainteneur : « ça ne me gêne pas si ça part sur
> Mailpit ») : un **Mailpit capteur** entre dans la pile (`copie_prod_mailpit`). Il est
> le seul serveur de mail que Django joint ; tout mail tenté y reste, et son total est
> surveillé (`compter`). Voir §4, ligne « Mails ».
>
> **2026-10-06, session 15-4** (spec `FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md` §8) :
> nouvelle sous-commande **`compter_avant`**, en lecture seule, entre `charger` et
> `neutraliser`. Elle compte les lieux qui ont un drapeau de module V2 à vrai **avant** que la
> neutralisation vide `server_cashless`. Voir §3.3 et la nouvelle §3.5 (cases à cocher du
> moteur de monnaie et du réseau CLAF).

## 1. Pourquoi des précautions

La base de production contient, **par lieu**, des adresses et des clés en clair. Une
tâche Celery ou un simple enregistrement d'une ligne (signal) sur la copie peut appeler
le vrai serveur :

| Sortie | Stockée | Déclencheur sans action humaine |
|---|---|---|
| Ancien LaBoutik (V1) | `BaseBillet_configuration.server_cashless`, `key_cashless` **en clair** | ré-enregistrer une `LigneArticle` payée (machine à états `BaseBillet/signals.py` ~l.491) → `send_sale_to_laboutik` ; enregistrer un produit adhésion ; **ouvrir le tableau de bord de l'admin** (appel synchrone, `Administration/admin/dashboard.py` ~l.2571) |
| Webhooks des lieux | `BaseBillet_webhook.url` en clair | réservation / adhésion payée (signaux) |
| Ancien Fedow | `RootConfiguration.fedow_domain` (schéma public), `Configuration.server_fedow` | produits adhésion / badge (signal **synchrone** `send_membership_and_badge_product_to_fedow`), recharges |
| Stripe live, Ghost, Brevo, Formbricks, Sunmi | clés **chiffrées** (Fernet) | paiements, newsletters, impressions |
| Imprimantes LAN | `laboutik_printer.ip_address` (table **ajoutée par la branche** : vide sur la copie) | ticket de commande / de vente |
| Mails | réglages `EMAIL_*` | relances d'adhésion (cron 5 h), mails de clôture, billets / factures (signaux) |
| Tâches automatiques | beat Celery (`TiBillet/celery.py`) | `cron_morning` (crée des lieux d'attente, **relance les adhérents de tous les lieux**), `cron_clotures_automatiques` (**écrit des clôtures**), purge des brouillons d'onboarding, cache SEO |
| Sentry | `SENTRY_DNS` | toute erreur |

**Le `.env` de production ne doit PAS être copié** : il rendrait déchiffrables la clé
Stripe live, les clés Fedow / Ghost / Brevo / Sunmi, et donnerait le vrai serveur mail et
Sentry. La reprise n'a besoin d'aucune de ces clés.

## 2. Déjà fait

- `db-prod/` dans `.gitignore` (l.268, jamais dans un commit) et dans `.dockerignore`
  (l.55, jamais dans une image : `docker_push_update.sh` pousse l'image sur Docker Hub).
- **Pas d'anonymisation.** 100 % local. **Claude ne lit aucune donnée personnelle** :
  seulement des comptages agrégés (`COUNT`, `GROUP BY` sur statuts, moyens, origines,
  dates, montants), jamais de `SELECT` qui ramène des mails, noms, adresses, numéros de
  carte, tags NFC ; règle écrite en tête de chaque brief d'ouvrier qui touche la copie.

## 2 bis. Ancienne décision (2026-10-04), remplacée

« Même pile Docker que le dev » : la base de dev remplacée par la copie, `lespass_celery`
arrêté, réseau non coupé (la neutralisation SQL seul garde-fou pour les adresses en
clair). **Remplacée le 2026-10-05 par la pile à part (§3)** : la base de dev n'est plus
touchée, le réseau est coupé, Celery n'existe pas dans la pile. Le script de cette
variante, `db-prod/neutraliser_copie_prod.sh`, reste en place (il vise
`lespass_postgres`) ; son SQL est réutilisé tel quel par la pile à part.

## 3. LA procédure : la pile à part

### 3.1 Les fichiers (tous dans `db-prod/`, ignorés par git et par docker)

| Fichier | Rôle |
|---|---|
| `docker-compose.copie-prod.yml` | projet Docker `lespass_copie_prod` : `copie_prod_postgres` (postgres 13, comme la prod — le dump dit 13.23), `copie_prod_redis`, `copie_prod_memcached`, `copie_prod_django` (image du dev déjà construite, `sleep infinity`), `copie_prod_mailpit` (le capteur des mails, image du dev `axllent/mailpit:latest`, aucun relais). Le réseau de travail est `internal: true`. Un second réseau, `lespass_copie_prod_ecran_mailpit`, porte **Mailpit seul**, **sans NAT** (`enable_ip_masquerade: false`) : il publie l'écran web sur **`127.0.0.1:18025`** seulement (Docker ne publie aucun port d'un conteneur branché seulement sur un réseau interne : vérifié le 2026-10-06 sur Docker 29.8.1). Le SMTP de Mailpit n'est pas publié. Aucun autre port, aucun Traefik, **aucun Celery**. `pull_policy: never`, `restart: "no"`. Code monté en **lecture seule** ; `logs/` et `www/media/` en tmpfs (effacés à l'arrêt) |
| `env.copie-prod` | l'environnement de la copie : `FERNET_KEY`, `DJANGO_SECRET` et mot de passe Postgres **neufs** (générés le 2026-10-05), `DEBUG=1`, `TEST=0`, domaines en `.invalid`, mails vers le capteur (`EMAIL_HOST=copie_prod_mailpit`, port 1025, sans TLS ni authentification, expéditeur factice `copie-prod@expediteur.invalid`), Stripe et Sentry vides. Ni le `.env` du dev ni celui de la prod |
| `copie_prod.sh` | **le seul point d'entrée** : `demarrer`, `verifier`, `charger`, `compter_avant`, `neutraliser`, `migrer`, `compter`, `detruire` ; refus net à chaque garde |
| `neutraliser_copie_prod.sql` | la neutralisation SQL (inchangée), une transaction, tout ou rien |

### 3.2 Avant

1. Arrêter `stripe listen` (le script refuse sinon).
2. Faire le dump **de la base Lespass** sur la prod, au format custom :
   `pg_dump -Fc -d <base> > tibillet-prod-AAAA-MM-JJ.dump` (ou texte :
   `pg_dump --no-owner --no-acl -d <base> | gzip`). **Pas `pg_dumpall`** : il porte les
   rôles (et leurs mots de passe) et crée sa propre base ; le script le refuse.
   Client `pg_dump` 13 de préférence (le `pg_restore` de la pile est en 13 : il ne lit
   pas un dump fait par un `pg_dump` plus récent).
3. Copier le dump dans `db-prod/` (le script refuse un dump ailleurs).

### 3.3 L'ordre exact des commandes (depuis la racine du dépôt)

```bash
bash db-prod/copie_prod.sh demarrer        # crée la pile à part, puis toutes les vérifications
bash db-prod/copie_prod.sh charger db-prod/<dump>   # base VIDE exigée ; chronométré
bash db-prod/copie_prod.sh compter_avant   # LECTURE SEULE, psql seul : drapeaux V2 et server_cashless
                                           # par lieu (comptages) ; refuse après la neutralisation
bash db-prod/copie_prod.sh neutraliser     # AVANT tout manage.py ; pose le témoin « neutralisee »
# (R-4) docker exec copie_prod_django poetry run python /DjangoFiles/manage.py supprimer_lieux_inactifs ...
#                                         # comme la nuit : sur la base de main, avant migrer (fiche R §12 étape 2 bis)
bash db-prod/copie_prod.sh migrer          # refuse sans le témoin ; migrate_schemas chronométré ;
                                           # neutralise ce que la branche ajoute ; témoin « migree »
bash db-prod/copie_prod.sh compter         # total des mails captés par Mailpit, puis comptage agrégé
# ... travail : comptages R-0, passage à blanc de la reprise, chronométrage ...
bash db-prod/copie_prod.sh detruire        # down -v de la pile à part SEULE, confirmation tapée
```

`bash db-prod/copie_prod.sh verifier` se relance à tout moment, sans rien changer.

Ce que contrôle `verifier` (et chaque étape avant d'agir) :

- `env.copie-prod` porte la marque `COPIE_PROD=1`, aucun secret à générer, pas de
  `CELERY_TASK_ALWAYS_EAGER`, et sa `FERNET_KEY` est **différente de toutes** celles du
  `.env` du dev (comparaison par empreinte SHA-256, jamais affichée) ;
- aucun `stripe listen` sur le poste ;
- le projet `lespass_copie_prod` contient **exactement** les 5 conteneurs attendus,
  aucun nom en celery / beat / worker / traefik / nginx ;
- chaque conteneur : en marche, du bon projet, branché sur le **seul** réseau
  `lespass_copie_prod_interne`, **aucun port** publié ; le réseau est `internal` et
  personne d'autre n'y est branché. Seule exception, `copie_prod_mailpit` : aussi sur
  `lespass_copie_prod_ecran_mailpit` (sans NAT, lui seul dessus), et un seul port
  publié, exactement `8025/tcp -> 127.0.0.1:18025` ;
- **Mailpit n'a pas de sortie**, éprouvé depuis son conteneur : `nc` vers `1.1.1.1:443`,
  `1.1.1.1:25`, `8.8.8.8:587` et `172.17.0.1:443` doivent échouer (la résolution DNS
  peut marcher depuis Mailpit, le DNS de Docker répondant depuis l'hôte : on ne s'y fie
  pas, seul le TCP compte) ;
- aucun processus `celery` ni `supervisord` dans `copie_prod_django` ;
- le conteneur a bien `COPIE_PROD=1` et la `FERNET_KEY` du fichier (sinon : pile à
  recréer) ;
- **la coupure, éprouvée depuis `copie_prod_django`** : résolution DNS de `example.org`,
  requête `https://example.org`, connexion à `1.1.1.1:443`, à l'hôte par `172.17.0.1:443`
  (Traefik du dev) et à la passerelle du réseau interne (ports 80, 443, 1025, 5432)
  doivent **toutes échouer** ; contrôle positif : `postgres` se résout ;
- **les mails, depuis `copie_prod_django`** : contrôle positif, le capteur
  `copie_prod_mailpit:1025` répond ; **aucun autre serveur de mail** n'est joignable
  (résolution de `mailpit`, `lespass_mailpit`, `smtp.gmail.com`, `smtp-relay.brevo.com` ;
  SMTP direct vers `1.1.1.1:25`, `8.8.8.8:465`, `8.8.8.8:587` ; Mailpit du dev par
  `172.17.0.1:1025` : tout doit échouer) ;
- les réglages **effectifs** de Django (`manage.py shell -c`, n'affiche que des noms et
  des vrai/faux) : backend mail, `EMAIL_HOST` = `copie_prod_mailpit`, `EMAIL_PORT` =
  1025, ni TLS ni SSL, adresse d'expédition en `.invalid`, `task_always_eager` faux, `DEBUG` vrai, `SENTRY_DNS` vide, `DOMAIN` en `.invalid`.
  Ce contrôle est **sauté** tant que la base est chargée mais pas neutralisée (aucun
  `manage.py` avant la neutralisation).

`compter_avant` (lecture seule, **psql seul**, aucun `manage.py`) se lance **juste après
`charger` et avant `neutraliser`** : la neutralisation vide `server_cashless`, il serait trop
tard. Gardes : la pile est la bonne (mêmes contrôles que `verifier`, sans Django), un dump est
chargé, la neutralisation n'est **pas** faite (témoin « neutralisee » absent, et adresse Fedow
de la configuration racine pas encore en `.invalid`) ; sinon : refus « trop tard,
`server_cashless` est vidé ». Toutes ses requêtes tournent dans une transaction
`READ ONLY`. Elle affiche, **sans aucune donnée personnelle** :

- les colonnes de configuration absentes de la production, et dans combien de lieux
  (`module_kiosk` n'existe pas sur `main` : il est compté « faux ») ;
- par catégorie de lieu, puis au total : nombre de lieux, lieux avec une configuration,
  lieux avec `module_caisse`, `module_monnaie_locale`, `module_kiosk`, `module_tireuse` à
  vrai, lieux avec **au moins un** de ces quatre drapeaux (`un_drapeau_v2`), lieux avec
  `server_cashless` renseigné (compté, **jamais affiché**), lieux avec `module_federation` ;
- le chiffre qui décide : **lieux de production (hors pool `W`) avec un drapeau V2**.
  `OK` s'il vaut 0, `STOP` sinon (voir §3.5).

**Le SQL de `compter_avant`, copié ici** (le script `db-prod/copie_prod.sh` est hors git ;
copie du 2026-10-06). Tout tourne entre `BEGIN TRANSACTION READ ONLY;` et `COMMIT;`, par
`psql` seul. Seuls des agrégats sortent (des nombres de lieux) : aucune ligne d'un lieu,
aucun nom, `server_cashless` réduit à « renseigné ou non ».

1. Les colonnes lues (une colonne absente d'un lieu compte « faux » pour ce lieu) :

```sql
-- COLONNES_LUES
(VALUES
    (1, 'module_caisse',         'module_caisse',             'coalesce(module_caisse, false)'),
    (2, 'module_monnaie_locale', 'module_monnaie_locale',     'coalesce(module_monnaie_locale, false)'),
    (3, 'module_kiosk',          'module_kiosk',              'coalesce(module_kiosk, false)'),
    (4, 'module_tireuse',        'module_tireuse',            'coalesce(module_tireuse, false)'),
    (5, 'module_federation',     'module_federation',         'coalesce(module_federation, false)'),
    (6, 'server_cashless',       'server_cashless_renseigne', 'coalesce(server_cashless, '''') <> ''''')
) AS colonne_lue(rang, colonne_en_base, nom_affiche, expression)
```

2. La fabrique de la requête « une ligne par lieu » (elle ne lit que le catalogue ; son
   résultat, un texte `SELECT … UNION ALL …`, est la `REQUETE_PAR_LIEU` des agrégats) :

```sql
WITH lieux AS (
    SELECT schema_name,
           categorie,
           to_regclass(format('%I."BaseBillet_configuration"', schema_name)) IS NOT NULL AS a_la_table
    FROM public."Customers_client"
    WHERE schema_name <> 'public'
),
colonnes_par_lieu AS (
    SELECT lieux.schema_name,
           lieux.categorie,
           lieux.a_la_table,
           (SELECT string_agg(
                CASE
                    WHEN lieux.a_la_table AND EXISTS (
                        SELECT 1 FROM information_schema.columns AS colonne_du_catalogue
                        WHERE colonne_du_catalogue.table_schema = lieux.schema_name
                          AND colonne_du_catalogue.table_name = 'BaseBillet_configuration'
                          AND colonne_du_catalogue.column_name = colonne_lue.colonne_en_base)
                    THEN format('coalesce(bool_or(%s), false) AS %I',
                                colonne_lue.expression, colonne_lue.nom_affiche)
                    ELSE format('false AS %I', colonne_lue.nom_affiche)
                END,
                ', ' ORDER BY colonne_lue.rang)
            FROM COLONNES_LUES) AS colonnes
    FROM lieux
)
SELECT string_agg(
    CASE
        WHEN a_la_table THEN format(
            'SELECT %L::text AS categorie, count(*) > 0 AS a_une_configuration, %s FROM %I."BaseBillet_configuration"',
            categorie, colonnes, schema_name)
        ELSE format(
            'SELECT %L::text AS categorie, false AS a_une_configuration, %s',
            categorie, colonnes)
    END,
    ' UNION ALL ')
FROM colonnes_par_lieu;
```

3. Les trois agrégats affichés :

```sql
-- a) Colonnes absentes de la configuration, et dans combien de lieux
SELECT colonne_lue.colonne_en_base AS colonne,
       count(*) FILTER (WHERE NOT EXISTS (
           SELECT 1 FROM information_schema.columns AS colonne_du_catalogue
           WHERE colonne_du_catalogue.table_schema = lieu.schema_name
             AND colonne_du_catalogue.table_name = 'BaseBillet_configuration'
             AND colonne_du_catalogue.column_name = colonne_lue.colonne_en_base)) AS lieux_sans_cette_colonne
FROM public."Customers_client" AS lieu
CROSS JOIN COLONNES_LUES
WHERE lieu.schema_name <> 'public'
  AND to_regclass(format('%I."BaseBillet_configuration"', lieu.schema_name)) IS NOT NULL
GROUP BY colonne_lue.rang, colonne_lue.colonne_en_base
ORDER BY colonne_lue.rang;

-- b) Lieux par catégorie, puis le total
SELECT coalesce(categorie, 'TOTAL') AS categorie,
       count(*) AS lieux,
       count(*) FILTER (WHERE a_une_configuration) AS avec_configuration,
       count(*) FILTER (WHERE module_caisse) AS module_caisse,
       count(*) FILTER (WHERE module_monnaie_locale) AS module_monnaie_locale,
       count(*) FILTER (WHERE module_kiosk) AS module_kiosk,
       count(*) FILTER (WHERE module_tireuse) AS module_tireuse,
       count(*) FILTER (WHERE module_caisse OR module_monnaie_locale
                           OR module_kiosk OR module_tireuse) AS un_drapeau_v2,
       count(*) FILTER (WHERE server_cashless_renseigne) AS server_cashless_renseigne,
       count(*) FILTER (WHERE module_federation) AS module_federation
FROM (REQUETE_PAR_LIEU) AS par_lieu
GROUP BY ROLLUP (par_lieu.categorie)
ORDER BY grouping(par_lieu.categorie), par_lieu.categorie;

-- c) Le chiffre qui décide : lieux de production (hors pool W) avec un drapeau V2
--    (0 = OK ; sinon STOP, voir §3.5)
SELECT count(*) FROM (REQUETE_PAR_LIEU) AS par_lieu
WHERE categorie <> 'W'
  AND (module_caisse OR module_monnaie_locale OR module_kiosk OR module_tireuse);
```

`COLONNES_LUES` et `REQUETE_PAR_LIEU` sont remplacés par le script avant l'envoi à `psql`
(le premier est le bloc 1, le second le texte rendu par le bloc 2).

`compter` affiche d'abord le **nombre** de messages reçus par Mailpit (API
`/api/v1/messages`, lue depuis `copie_prod_django` par le réseau interne : seulement le
total, jamais un sujet, un contenu ni un destinataire). Un total non nul dit qu'une
opération a tenté d'envoyer des mails : ils sont restés dans le capteur.

`charger` refuse : une base non vide, un dump hors de `db-prod/`, un dump de grappe
(`pg_dumpall`), un dump sans table, un dump texte avec propriétaires / droits. Les
erreurs de `psql` / `pg_restore` vont dans `db-prod/journal_chargement.txt` (elles
peuvent citer une ligne de données : jamais dans le terminal, jamais partagé ;
supprimé par `detruire`).

### 3.4 Pendant le travail

- Jamais de `make test`, `make e2e` ni pytest **sur la copie** (ils visent la pile du
  dev : la copie n'y est pas, mais l'habitude doit rester).
- Jamais de worker ni de beat ; ne pas lancer `cron_morning`,
  `generer_les_clotures_automatiques`, `refresh_seo_cache` à la main.
- Pas de `runserver` : rien n'est navigable (aucun port, aucun Traefik), et ce n'est pas
  le but. Seul l'écran de Mailpit est ouvert, sur `http://127.0.0.1:18025`, pour le
  mainteneur. Les messages captés peuvent contenir des données personnelles de la prod
  (adresses, noms) : **Claude ne l'ouvre jamais** et ne lit que le total (`compter`).
- Les commandes Django passent par
  `docker exec -it copie_prod_django poetry run python /DjangoFiles/manage.py ...`
  (code en lecture seule : aucune écriture dans le dépôt).

### 3.5 Vérifications du moteur de monnaie et du réseau CLAF

Spec `TECH_DOC/SESSIONS/FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md` §4.2 et §8. Deux
migrations de la branche posent le moteur de monnaie de chaque lieu : `Customers
0006_moteur_de_monnaie` met **tous** les lieux existants en `legacy` (ancien Fedow), sauf les
emplacements vides du pool (`WAITING_CONFIG`, catégorie `W`), mis en `v2` ; puis `BaseBillet
0227_moteur_v2_si_un_module_v2_est_actif` passe en `v2` un lieu dont la configuration a un
drapeau de module V2 à vrai. Décision du mainteneur : **tous les lieux de production restent
`legacy`**. Ces cases le vérifient. Comptages agrégés seulement, en lecture seule.

- [ ] **Avant `neutraliser`** — `bash db-prod/copie_prod.sh compter_avant`.
      **Attendu : `OK     0 lieu de production avec un drapeau V2`.**
      **Si le chiffre n'est pas 0 : STOP.** Ne pas lancer `migrer` pour la bascule. Le
      signaler au mainteneur, avec le tableau par catégorie : `0227` passerait ces lieux en
      `v2` (modules V2 et admin `fedow_core` ouverts, alors que tout le reste de la production
      est `legacy`). **Décision du mainteneur avant la bascule** : éteindre ces drapeaux en
      production avant la nuit, ou accepter ces lieux en `v2`. La répétition sur la copie peut
      continuer (la copie n'est pas la production) ; noter le chiffre.
      Noter aussi `server_cashless_renseigne` (lieux LaBoutik V1) : ce nombre ne se relit plus
      après la neutralisation.
- [ ] **Après `migrer`** — le journal de `migrate_schemas` liste chaque lieu passé en `v2` par
      `0227` (ligne `-> [<schéma>] moteur v2 (module V2 actif)`). **Attendu : aucune ligne**
      (cf. case précédente). Puis, en lecture seule :
      `docker exec -i copie_prod_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT moteur_monnaie, categorie, count(*) FROM public.\"Customers_client\" GROUP BY 1, 2 ORDER BY 1, 2"'`.
      Attendu : tout en `legacy`, sauf la catégorie `W` en `v2`.
- [ ] **Avant / après `migrer`** : empreinte du miroir `public.fedow_public_assetfedowpublic`
      et de ses tables M2M `federated_with` et `pending_invitations`
      (`md5(string_agg(… ORDER BY …))`). Empreintes identiques.
- [ ] **CLAF** : pour les assets dont le nom commence par « CLAF », même nombre de lieux dans
      `federated_with` avant et après `migrer`, `archive` faux.
- [ ] **Après `migrer`** : tables `fedow_core_*` (asset, token, transaction, federation) à 0
      ligne.
- [ ] **Hors copie, la nuit de la bascule** : capture de la fiche de l'asset CLAF
      (ventilation par lieu) et de `/fedow/asset/<uuid>/retrieve_bank_deposits/` avant la
      bascule, même page après, mêmes chiffres. Aucun POST de remise en banque (irréversible).

## 4. Chaque sortie : ceinture ET bretelles

Quatre protections communes : **réseau interne** (aucune sortie, ni internet, ni réseau
local, ni hôte : éprouvé par `verifier` ; Mailpit a en plus le réseau de son écran, sans
NAT, sans sortie éprouvée), **pas de Celery** (aucun worker ni beat dans
la pile ; un `.delay()` reste dans le redis de la copie, effacé par `detruire`), **clé
Fernet neuve** (toute clé chiffrée de la prod est illisible : `InvalidToken`),
**neutralisation SQL** avant tout `manage.py`.

| Sortie | Protections |
|---|---|
| Ancien LaBoutik (V1) | SQL (`server_cashless`, `key_cashless` vidés) + réseau + pas de Celery pour `send_sale_to_laboutik` / `send_refund_to_laboutik`. L'appel synchrone du tableau de bord ne part pas : pas de serveur en base, pas d'admin navigable, pas de réseau. **3 protections** |
| Webhooks des lieux | SQL (désactivés, adresse `.invalid`, revérifié après `migrer`) + réseau + pas de Celery (`webhook_reservation`, `webhook_membership`). **3** |
| Ancien Fedow | SQL (`fedow_domain` en `.invalid`, clé de création vidée ; par lieu `server_fedow`, `key_fedow`, clé du lieu vidés) + clé Fernet neuve (clés illisibles) + réseau. Le signal produit adhésion est **synchrone** (pas de Celery en jeu) : il échoue sans bloquer (`try/except`). **3** |
| Stripe live | SQL (clés live et test vidées, `stripe_mode_test=false` → `fernet_decrypt(None)` échoue) + clé Fernet neuve + `STRIPE_KEY` / `STRIPE_KEY_TEST` vides + réseau. Les identifiants Stripe Connect sont **gardés** (un vide déclencherait une création de compte) : sans clé ni réseau, rien ne part. **4** |
| Ghost | SQL (`ghost_url`, `ghost_key` vidés) + clé Fernet neuve + réseau + pas de Celery. **4** |
| Brevo | SQL (`api_key` vidée) + clé Fernet neuve + réseau + pas de Celery. **4** |
| Formbricks | SQL (`api_key`, `api_host` vidés) + clé Fernet neuve + réseau. **3** |
| Sunmi (impression cloud) | tables ajoutées par la branche, vides à la création ; `migrer` vide `sunmi_app_id` / `sunmi_app_key` et revérifie + clé Fernet neuve + réseau + pas de Celery. **4** |
| Imprimantes LAN | table ajoutée par la branche (vide) ; `migrer` désactive et vide `ip_address` / numéro de série + réseau (aucune route vers le réseau local). **2** |
| Mails | **pas de worker** (les tâches d'envoi restent dans redis) + **réseau interne** (le seul serveur de mail joignable est le capteur, éprouvé par `verifier`) + **Mailpit capteur** (`EMAIL_HOST=copie_prod_mailpit` : un mail tenté y reste, aucun relais configuré, et Mailpit lui-même n'a pas de sortie) + **total surveillé** (`compter` affiche le nombre de messages captés : un envoi tenté se voit) + destinataires des clôtures vidés (SQL, `rapport_emails` des deux modèles). L'expéditeur est factice, en `.invalid` (`copie-prod@expediteur.invalid`) : `CeleryMailerClass.config_valid()` est vrai, les mails tentés arrivent dans le capteur et servent de détecteur. **4 à 5** |
| Tâches automatiques | aucun beat ni worker dans la pile (vérifié : conteneurs ET processus) + `django` en `sleep infinity` (pas de `supervisord`, qui lancerait Celery en prod) + réseau (une clôture écrite n'irait nulle part). Si un humain lance une commande `cron_*` à la main, elle s'exécute : **une seule vraie protection (pas de beat) pour les écritures en base**, la consigne §3.4 fait le reste |
| Sentry | `DEBUG=1` (`settings.py` n'initialise Sentry que si `not DEBUG`) + `SENTRY_DNS` vide + réseau. **3** |

**Ce que `EMAIL_BACKEND` ne peut pas faire ici** : `settings.py` ne lit pas
`EMAIL_BACKEND` dans l'environnement (backend SMTP de Django, fixe). Un backend `dummy`
demanderait une ligne dans `settings.py`
(`EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')`)
— hors du périmètre de cette préparation, à décider par le mainteneur. Les verrous
ci-dessus suffisent : le serveur SMTP est le capteur.

## 5. Ce que la pile ne couvre pas

- **Une commande lancée à la main** dans `copie_prod_django` (ex. `cron_morning`,
  `generer_les_clotures_automatiques`) écrit en base de la copie. Rien ne sort, mais la
  copie n'est plus la prod : refaire `detruire` / `demarrer` / `charger`.
- **Les tâches en file** : un signal qui fait `.delay()` (ex. une ligne repassée en
  payée pendant la reprise) remplit le redis de la copie. Rien ne les lit ;
  `detruire` les efface. Ne jamais brancher un worker sur cette pile.
- **Quelques valeurs de la prod restent** dans des colonnes que la neutralisation ne
  vide pas, parce que le code ne s'en sert plus pour appeler : `Configuration.stripe_api_key`
  / `stripe_test_api_key` des lieux (champ « à dégager », `get_stripe_api()` lit la
  configuration racine), `RootConfiguration.fedow_ip`. Une seule protection effective :
  le réseau.
- **Les dépendances Python** : l'image `lespass-lespass_django:latest` date du
  2026-09-07 ; depuis, seul `pytest-cov` (outil de test) a été ajouté au `poetry.lock`.
  Si une dépendance manque, `verifier` le dit (Django ne démarre pas) ; **pas de
  `poetry install` dans la copie** (pas de réseau) : reconstruire l'image du dev à
  part, puis `detruire` / `demarrer`.
- **Le fuseau par défaut** : `TIME_ZONE=UTC` (gabarit). Chaque lieu a le sien en base ;
  aligner sur la prod si la répétition en dépend.
- **Le volume de la base** reste sur le disque du poste tant que `detruire` n'est pas
  lancé (données personnelles) ; le dump aussi, jusqu'à sa suppression à la main.

## 6. État du dump au 2026-10-05

`db-prod/tibillet.re-M0221-2026-10-04-20-00.sql.gz` : 740 octets (2 066 décompressés).
C'est un **dump de grappe** (`pg_dumpall`, PostgreSQL 13.23) qui ne contient **que des
rôles** et les bases système : 0 `CREATE TABLE`, 0 `COPY`. **Aucune donnée de Lespass.**
Il faut un nouveau dump (§3.2) ; `charger` refuserait celui-ci.

## 7. Fin

`bash db-prod/copie_prod.sh detruire` (conteneurs, les deux réseaux, volume de la base,
journal de chargement ; logs, media et messages de Mailpit étaient dans les conteneurs),
puis supprimer le dump de `db-prod/`.
