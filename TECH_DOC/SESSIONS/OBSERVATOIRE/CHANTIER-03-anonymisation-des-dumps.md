# CHANTIER 03 — Anonymiser les copies de production / Anonymise production dumps

**Date :** 2026-11-12
**Statut :** Spec validée par le mainteneur (2026-11-12), avec les décisions 6 et 7 (§2). Codé.
**Migration :** Non. Le script ne touche à aucun modèle Django.

---

## 1. Le besoin

On veut travailler sur de vraies données de production (pour l'observatoire, et plus
largement en dev), sans y laisser les e-mails des gens ni les clés API.

Trois bases sont concernées :

| Base | Moteur | Ce que donne la sauvegarde de prod |
|---|---|---|
| **Lespass** (ce dépôt) | PostgreSQL, multi-tenant : un schéma `public` + un schéma par lieu (~515 schémas, ~37 000 tables) | `pg_dumpall \| gzip` → `*.sql.gz` (cron `saveDb.sh`). Parfois `pg_dump -Fc` (fiche 05-R). |
| **Fedow** (`../Fedow`) | SQLite, un seul fichier | `backup/snapshot/db.sqlite3` (fichier SQLite brut), archivé ensuite dans borg. Pas de `.gz` produit. |
| **LaBoutik V1** (`../LaBoutik`) | PostgreSQL, une base par lieu | `pg_dumpall \| gzip` → `*.sql.gz` (`cron/dump_and_borg.sh`) |

**Ce qu'on veut :** un script rapide, pas une usine à gaz. Il remplace les e-mails des
gens et les clés API. Tout le reste est gardé : noms des lieux, adresses, événements,
produits, ventes, cartes, montants.

**Ce qu'on ne veut pas :**

- un outil qui charge la prod dans une base vivante pour l'anonymiser ensuite ;
- une commande `manage.py` (elle démarrerait Django, ses signaux et ses réglages) ;
- une liste de règles si large qu'on ne la relit plus.

## 2. Décisions du mainteneur

1. Le script vit dans `seo/`, dans un dossier `scripts_observatoire/`.
2. Il **ne peut pas** être lancé par `manage.py` : ce n'est pas une commande Django.
3. Il prend en argument le chemin de la base : un dump SQL (`.sql` ou `.sql.gz`) ou un
   fichier SQLite (`.sqlite3`, ou `.gz` qui le contient).
4. Il gère PostgreSQL **et** SQLite.
5. On remplace **les e-mails des gens et les clés API** (voir §9 pour ce qui reste en
   clair).
6. **On remplace aussi les noms, prénoms, pseudos et téléphones des personnes**, même
   pour un usage personnel (mainteneur, 2026-11-12 : « c'est important »). Voir §5.5.
7. **On vide toutes les clés RSA**, privées et publiques : elles ne servent pas aux
   analyses (mainteneur, 2026-11-12). Voir §5.4.

## 3. Le principe

Le script ne charge **jamais** la production dans un serveur de base de données. Il lit
le fichier d'entrée et écrit un **nouveau fichier** anonymisé à côté. L'entrée n'est
jamais modifiée.

```
python3 seo/scripts_observatoire/anonymiser_dump.py  lespass.sql.gz  fedow.sqlite3  laboutik.sql.gz
        |
        +-- lespass.sql.gz    --> lespass.anonyme.sql.gz     (lecture en flux, ligne par ligne)
        +-- fedow.sqlite3     --> fedow.anonyme.sqlite3      (copie, puis UPDATE, puis VACUUM)
        +-- laboutik.sql.gz   --> laboutik.anonyme.sql.gz
        |
        +-- un rapport sur la sortie standard : des NOMBRES seulement, jamais une valeur
```

- **Un seul fichier Python**, bibliothèque standard seulement : `argparse`, `gzip`,
  `re`, `hmac`, `hashlib`, `secrets`, `sqlite3`, `shutil`, `os`. Aucune dépendance,
  aucun `import django`. Il tourne avec le `python3` de l'hôte ou du conteneur.
- **Plusieurs fichiers dans une seule commande** : c'est ce qui garde les faux e-mails
  identiques d'une base à l'autre (§4).

### 3.1 Où il vit, pourquoi `manage.py` ne le voit pas

```
seo/scripts_observatoire/
    anonymiser_dump.py      le script (le seul fichier)
    README.md               mode d'emploi court (commande, sorties, limites)
```

`manage.py` ne découvre que `seo/management/commands/`. Le dossier n'a pas de
`__init__.py` : ce n'est pas un paquet, Django ne l'importe jamais.

## 4. Les e-mails

### 4.1 Le faux e-mail

Chaque e-mail trouvé est remplacé par :

```
<16 caractères hexadécimaux>@anonyme.invalid
```

Les 16 caractères sont le début de `HMAC-SHA256(sel, adresse_trouvée)`, sur le texte
**exact** de l'adresse trouvée, sans passer en minuscules.

- **`.invalid`** est un domaine réservé (RFC 2606) : aucun mail ne peut partir vers lui.
- **33 caractères** : ça tient dans la plus petite colonne e-mail des trois bases
  (`APIcashless_membre.email`, 50 caractères). Pour les autres colonnes, voir §6
  (« valeur trop longue »).
- **Toujours le même résultat pour la même adresse**, pendant un lancement. C'est
  indispensable : Fedow retrouve un utilisateur Lespass par son e-mail exact, en
  minuscules (`wallet/get_or_create`, `fedow_connect/fedow_api.py:558-583`). Si Lespass
  et Fedow n'ont pas le même faux e-mail, la création de wallet casse
  (« Wallet and member mismatch »). Les trois systèmes enregistrent déjà les e-mails en
  minuscules (Lespass `AuthBillet/utils.py:113`, Fedow `fedow_core/models.py:1287-1307`,
  LaBoutik `APIcashless/validator.py:256-281`) : le texte exact suffit.
- **Pas de passage en minuscules** : deux adresses différentes donnent toujours deux faux
  e-mails différents. Une colonne unique ne peut donc pas recevoir de doublon
  (voir §4.4).
- **Le sel** est tiré au hasard au démarrage (`secrets.token_bytes(32)`), gardé en
  mémoire, **jamais affiché ni écrit**. Sans lui, on ne peut pas retrouver l'adresse
  d'origine en essayant des adresses connues.
- Conséquence : pour que les trois bases restent cohérentes entre elles, **on les passe
  dans la même commande**. Deux lancements séparés donnent deux faux e-mails différents
  pour la même personne.

### 4.2 Où on les cherche : partout

On ne liste pas les colonnes e-mail. Une expression régulière cherche les e-mails
**dans toutes les valeurs texte de toutes les tables** : colonnes `email`, `username`
(qui vaut l'e-mail dans Lespass, Fedow et LaBoutik), JSON (`metadata`, `custom_form`,
`rapport_emails`…), commentaires, journaux.

Pourquoi : les inventaires ont trouvé des e-mails dans plus de vingt colonnes de texte
libre ou de JSON. Une liste fermée en oublierait. Une recherche partout n'oublie rien de
lisible.

L'expression (à ajuster par le builder, en gardant l'idée) :

```python
EXPRESSION_EMAIL = re.compile(r"(?<!\\)[\w.%+-]+@[\w.-]+\.\w{2,}")
```

- `\w` sur du texte Python est Unicode : `rené@exemple.fr` est trouvé.
- **`(?<!\\)`** : dans le texte d'un `COPY`, un retour à la ligne s'écrit `\n`. Sans
  cette règle, `…\nalice@x.fr` donnerait l'adresse `nalice@x.fr`, et donc un autre faux
  e-mail que dans Fedow. Avec elle, la correspondance ne peut pas commencer juste après
  une barre oblique inverse : elle commence à `alice`.

Deux exceptions à l'intérieur de l'expression ou juste après :

- **Les noms d'images « retina »** du type `logo@2x.png` ne sont pas des e-mails. Seul
  `@<chiffres>x.<png|jpg|jpeg|gif|svg|webp>` est épargné. Un nom de fichier comme
  `avatar_alice@gmail.com.png` contient un vrai e-mail : il est remplacé.
- **Les faux e-mails déjà posés** (`@anonyme.invalid`) ne sont pas remplacés à nouveau.
  On peut donc relancer le script sur une sortie sans rien abîmer.

### 4.3 Les colonnes où on ne remplace PAS

| Base | Colonne | Pourquoi |
|---|---|---|
| Fedow | `fedow_core_transaction.comment`, `fedow_core_transaction.metadata` | Elles entrent dans le hash chaîné des transactions (`dict_for_hash`, `Fedow/fedow_core/models.py:533-534`). Les changer casse `verify_hash()`, et chaque nouvelle transaction vérifie la précédente (`models.py:640`) : plus aucune écriture possible sur l'asset. |

Les e-mails trouvés dans ces colonnes sont **comptés** dans le rapport, jamais affichés.
Le chiffre dit au mainteneur ce qui reste en clair.

Ce n'est PAS le cas dans Lespass : la table `fedow_core_transaction` de Lespass (moteur
V2) a un hash individuel, sans chaîne, et vide pour l'instant
(`fedow_core/models.py:418-502`). Ses e-mails sont remplacés.

### 4.4 Les colonnes uniques

Les colonnes uniques (`AuthBillet_tibilletuser.email` et `.username`,
`fedow_core_fedowuser.email` et `.username`, `APIcashless_membre.email`,
`tibiauth_tibiuser.username`) ne reçoivent jamais deux fois le même faux e-mail : le HMAC
porte sur le texte exact (§4.1), donc `Alice@x.fr` et `alice@x.fr` restent distincts.
Le risque de collision des 16 caractères hexadécimaux (64 bits) est négligeable.

Limite connue : une adresse ancienne enregistrée avec des majuscules dans Lespass
(`Alice@x.fr`) et en minuscules dans Fedow (`alice@x.fr`) recevra deux faux e-mails
différents. Le lien Lespass ↔ Fedow de cette personne casse sur la copie. Les chemins
de création des trois systèmes passent en minuscules : le cas ne devrait concerner que
de vieilles lignes.

## 5. Les clés API et autres secrets

Ici, au contraire des e-mails, **on liste les colonnes une par une**. Une recherche « par
le nom » (`token`, `key`…) toucherait des colonnes qui ne sont pas des secrets : la
table `fedow_core_token` de Fedow contient les soldes des portefeuilles.

### 5.1 Les façons de remplacer

| Mode | Ce qu'on écrit | Pour |
|---|---|---|
| `vide` | `''` (texte vide) | Une clé en clair ou chiffrée. Le code lit « pas de clé configurée ». |
| `null` | `NULL` | Une clé chiffrée dont le code retombe sur une variable d'environnement si la colonne est `NULL`. |
| `hash_inutilisable` | `!anonyme` | Le hash d'une clé API (`hashed_key`). Plus aucune clé ne correspond. La clé primaire `id` (`prefix.hashed_key`) n'est pas touchée : les clés étrangères restent valides, et on ne retrouve pas une clé aléatoire de 32 caractères depuis son hash. |
| `mot_de_passe` | `!anonyme` | Un hash de mot de passe Django. Un mot de passe qui commence par `!` est « inutilisable » pour Django. |
| `jeton_unique` | `anonyme-` + 16 caractères hexadécimaux aléatoires | Un jeton dans une colonne unique (le mode `vide` y créerait des doublons). |
| `nom` | `Anonyme-` + 8 caractères hexadécimaux (HMAC de la valeur, même sel que les e-mails) | Un nom, un prénom, un pseudo. Le même nom donne le même pseudonyme. Deux noms différents peuvent, rarement, donner le même (32 bits) : jamais sur une colonne unique. Une valeur vide reste vide. |
| `identifiant` | l'e-mail remplacé s'il y en a un, sinon `Anonyme-` + 16 caractères hexadécimaux | Un `username`. S'il vaut l'e-mail, il reçoit le même faux e-mail que la colonne `email`. Sinon (« jonas », « admin »), c'est un nom de connexion humain : il devient un pseudonyme long (colonne unique). |

Une valeur `NULL` reste `NULL`, quel que soit le mode.

**À vérifier par le builder, colonne par colonne :** que le code qui lit la colonne
supporte la valeur choisie. Une colonne Fernet que le code déchiffre sans tester d'abord
si elle est vide lèverait `InvalidToken` sur `''`. Dans ce cas, mettre `null` si la
colonne l'accepte, sinon le signaler.

### 5.2 PostgreSQL (Lespass et LaBoutik V1)

Une seule liste pour les deux : leurs noms de tables ne se recouvrent pas, sauf les
tables Django standard, qui se traitent pareil des deux côtés. Une règle s'applique à
une table **quel que soit son schéma** : les tables des lieux existent dans chaque
schéma.

**Lespass, schéma `public` :**

| Table | Colonne | Mode |
|---|---|---|
| `AuthBillet_tibilletuser` | `password` | `mot_de_passe` |
| `AuthBillet_tibilletuser` | `username` | `identifiant` |
| `MetaBillet_waitingconfiguration` | `otp_hash` (hash d'un code à 6 chiffres : retrouvable en essayant le million de codes) | `vide` |
| `root_billet_rootconfiguration` | `stripe_api_key` (Fernet) | `vide` |
| `root_billet_rootconfiguration` | `stripe_test_api_key` | `vide` |
| `root_billet_rootconfiguration` | `fedow_create_place_apikey` (Fernet) | `vide` |
| `onboard_onboardinvitation` | `code` (unique : un lien d'invitation valide) | `jeton_unique` |

**Lespass, schémas des lieux :**

| Table | Colonne | Mode |
|---|---|---|
| `BaseBillet_configuration` | `key_cashless`, `key_fedow`, `stripe_api_key`, `stripe_test_api_key` (en clair) | `vide` |
| `BaseBillet_ghostconfig` | `ghost_key` (Fernet) | `vide` |
| `BaseBillet_formbricksconfig` | `api_key` (Fernet) | `vide` |
| `BaseBillet_brevoconfig` | `api_key` (Fernet) | `vide` |
| `BaseBillet_webhook` | `url` (une URL de webhook porte souvent un jeton) | `vide` |
| `fedow_connect_fedowconfig` | `fedow_place_admin_apikey` (Fernet) | `vide` |
| `laboutik_laboutikconfiguration` | `sunmi_app_id`, `sunmi_app_key`, `hmac_key` (Fernet) | `vide` |
| `laboutik_tpebancaire` | `registration_code` | `vide` |
| `discovery_pairingdevice` (schéma `public`) | `pin_code` (entier, unique, nullable : un PIN non réclamé crée une clé `LaBoutikAPIKey` sur la prod, `discovery/views.py:231-239`) | `null` |
| `BaseBillet_scannerapikey`, `BaseBillet_laboutikapikey`, `controlvanne_tireuseapikey`, `rest_framework_api_key_apikey` | `hashed_key` | `hash_inutilisable` |

**LaBoutik V1 (schéma `public` de chaque base) :**

| Table | Colonne | Mode |
|---|---|---|
| `tibiauth_tibiuser` | `password` | `mot_de_passe` |
| `tibiauth_tibiuser` | `username` | `identifiant` |
| `APIcashless_configuration` | `odoo_login` (identifiant Odoo, souvent un e-mail) | `vide` |
| `APIcashless_configuration` | `odoo_api_key`, `dokos_key`, `lespass_api_key`, `fedow_place_admin_apikey` (en clair) | `vide` |
| `APIcashless_configuration` | `string_connect` (base64 qui contient une clé temporaire Fedow), `onboard_url` (lien Stripe avec jeton) | `vide` |
| `APIcashless_configuration` | `stripe_api_key`, `sunmi_app_id`, `sunmi_app_key`, `discovery_key` (Fernet) | `vide` |
| `APIcashless_configurationstripe` | `stripe_api_key` (Fernet) | `vide` |
| `APIcashless_terminal` | `registration_code` | `vide` |
| `APIcashless_appareil` | `pin_code` (entier, nullable, PIN d'appairage) | `null` |
| `epsonprinter_printer` | `api_serveur_impression` (en clair) | `vide` |
| `rest_framework_api_key_apikey` | `hashed_key` | `hash_inutilisable` |

Une règle dont la colonne n'existe pas dans le dump est ignorée sans erreur. Exemple :
`APIcashless_configuration.lespass_api_key` n'existe qu'à partir de la migration 0267 de
LaBoutik ; un dump plus ancien ne l'a pas.

**Tables vidées** (toutes les lignes retirées, la structure reste) :

| Table | Pourquoi |
|---|---|
| `django_session` | Contient l'e-mail OTP, le hash d'authentification, signés avec la clé de prod. Inutilisable en dev de toute façon. |
| `authtoken_token` | Jetons DRF en clair. |
| `token_blacklist_outstandingtoken`, `token_blacklist_blacklistedtoken` | Jetons JWT. |
| `AuthBillet_terminalpairingtoken` | Jetons d'appairage de terminal, éphémères. La colonne `token` est un entier `NOT NULL` : on ne peut pas la mettre à `NULL`. |
| `django_admin_log` | Les représentations d'objets contiennent e-mails et noms. Aucune valeur pour l'observatoire. |

**Les rôles PostgreSQL** (`pg_dumpall` seulement) : la ligne
`ALTER ROLE … PASSWORD '…'` porte le hash du mot de passe du rôle. On retire la clause
`PASSWORD '…'` et on garde le reste de la ligne.

### 5.3 SQLite (Fedow)

Le script choisit cette liste quand l'entrée est un fichier SQLite. Fedow est la seule
des trois bases en SQLite.

| Table | Colonne | Mode |
|---|---|---|
| `fedow_core_fedowuser` | `password` | `mot_de_passe` |
| `fedow_core_fedowuser` | `username` | `identifiant` |
| `fedow_core_configuration` | `stripe_api_key`, `stripe_endpoint_secret_enc` (Fernet ; si `NULL`, le code relit l'environnement) | `null` |
| `fedow_core_place` | `cashless_admin_apikey` (Fernet) | `vide` |
| `fedow_core_createplaceapikey`, `fedow_core_organizationapikey`, `rest_framework_api_key_apikey` | `hashed_key` | `hash_inutilisable` |

Tables vidées : `django_session`, `django_admin_log`.

Les e-mails contenus dans `fedow_core_organizationapikey.name` (`"{lieu}:{email}"`) sont
remplacés par la recherche générale (§4.2).

### 5.4 Les clés RSA : toutes vidées (décision 7)

Les clés privées sont chiffrées avec le `SECRET_KEY` de prod, absent du dump. On les vide
quand même : si ce `SECRET_KEY` fuyait un jour, la clé du wallet primaire de Fedow
deviendrait utilisable. Les clés publiques sont vidées aussi : elles ne servent pas aux
analyses.

| Base | Table | Colonnes | Mode |
|---|---|---|---|
| Lespass | `AuthBillet_rsakey` | `private_pem`, `public_pem` (`NOT NULL`) | `vide` |
| Lespass | `AuthBillet_wallet` | `public_pem` | `vide` |
| Lespass | `root_billet_rootconfiguration` | `fedow_primary_pub_pem` | `vide` |
| Lespass | `BaseBillet_configuration` | `laboutik_public_pem` | `vide` |
| LaBoutik | `APIcashless_configuration` | `private_pem`, `public_pem` (`NOT NULL` ; le code régénère la paire quand elle est vide, `APIcashless/models.py:2390-2410`) | `vide` |
| LaBoutik | `tibiauth_tibiuser` | `public_pem` | `vide` |
| Fedow | `fedow_core_wallet` | `private_pem`, `public_pem` | `vide` |
| Fedow | `fedow_core_place` | `cashless_rsa_pub_key` | `vide` |

Conséquences sur la copie : la vérification des QR codes des billets, la poignée de main
LaBoutik ↔ Fedow et les signatures des wallets ne marchent plus. Ce n'est pas utile pour
les analyses.

### 5.5 Les noms, prénoms, pseudos et téléphones (décision 6)

| Base | Table | Colonnes | Mode |
|---|---|---|---|
| Lespass | `AuthBillet_tibilletuser` | `first_name`, `last_name` | `nom` |
| Lespass | `AuthBillet_tibilletuser` | `phone` | `vide` |
| Lespass | `BaseBillet_membership` | `first_name`, `last_name`, `pseudo` | `nom` |
| Lespass | `BaseBillet_membership` | `phone` | `vide` |
| Lespass | `BaseBillet_commande` | `first_name`, `last_name` | `nom` |
| Lespass | `BaseBillet_ticket` | `first_name`, `last_name` | `nom` |
| Lespass | `booking_booking` | `first_name`, `last_name` | `nom` |
| Lespass | `crowds_contribution` | `contributor_name` | `nom` |
| Lespass | `crowds_globalfunding` | `contributor_name` | `nom` |
| Lespass | `MetaBillet_waitingconfiguration` | `first_name`, `last_name` | `nom` |
| Lespass | `MetaBillet_waitingconfiguration` | `phone` (`NOT NULL`) | `vide` |
| Lespass | `BaseBillet_configuration` | `phone` (souvent le portable d'un organisateur) | `vide` |
| LaBoutik | `APIcashless_membre` | `name` (`NOT NULL`), `prenom`, `pseudo` | `nom` |
| LaBoutik | `APIcashless_membre` | `tel` | `vide` |
| LaBoutik | `APIcashless_configuration` | `telephone` | `vide` |
| LaBoutik | `tibiauth_tibiuser` | `first_name`, `last_name` | `nom` |
| Fedow | `fedow_core_fedowuser` | `first_name`, `last_name` | `nom` |

`Anonyme-xxxxxxxx` fait 16 caractères. Dans une colonne plus courte, la règle « valeur trop
longue » (§6) s'applique.

## 6. Le traitement d'un dump PostgreSQL (texte)

Lecture **en flux**, ligne par ligne, avec `gzip.open(..., "rt")` si l'entrée est
compressée. La mémoire reste constante, quelle que soit la taille du dump.

```
pour chaque ligne :
    hors d'un bloc COPY :
        ligne "ALTER ROLE ... PASSWORD '...'"  -> retirer la clause PASSWORD
        ligne "COPY <schéma>.<table> (<colonnes>) FROM stdin;"
            -> retenir la table et la position de chaque colonne
            -> entrer dans le bloc COPY
        toute autre ligne                      -> recopiée telle quelle
    dans un bloc COPY :
        ligne "\."                             -> sortir du bloc
        table à vider                          -> ligne non recopiée
        sinon :
            couper la ligne sur les tabulations
            pour chaque colonne qui a une règle de secret -> appliquer le mode
            pour chaque autre valeur                      -> remplacer les e-mails
            recoller avec des tabulations, écrire
```

Points précis :

- L'en-tête `COPY` met parfois les noms entre guillemets (`public."APIcashless_membre"`,
  `"ticketZ"`, `"end"`, `"order"`). On retire les guillemets pour comparer aux règles.
- Dans le format texte de `COPY`, une tabulation ou un retour à la ligne **à
  l'intérieur** d'une valeur est échappé (`\t`, `\n`). Couper sur les vraies tabulations
  est donc sûr, et une ligne est toujours une ligne de la table. `NULL` s'écrit `\N`.
- Le faux e-mail ne contient ni tabulation, ni barre oblique inverse : il ne casse pas
  l'échappement.
- **Valeur trop longue.** Le faux e-mail (33 caractères) peut être plus long que
  l'adresse d'origine (`a@b.fr`, 6 caractères). Dans une colonne `varchar(30)`,
  PostgreSQL refuserait la ligne au chargement, **tout le `COPY` de la table serait
  annulé**, et `psql` continuerait : une table vide, sans erreur visible. Pour l'éviter :
  - le script lit les longueurs dans les `CREATE TABLE` du dump. Ils arrivent toujours
    **avant** les `COPY` dans un dump texte. On retient, par table et par colonne, le
    `N` de `character varying(N)` ;
  - si la valeur réécrite dépasse `N`, on la remplace en entier par l'empreinte (HMAC) de
    la valeur d'origine, coupée à `N` caractères. La donnée est perdue, mais rien ne
    fuit, le chargement passe, et deux valeurs différentes restent différentes : une
    colonne unique comme `BaseBillet_externalapikey.name` (`varchar(30)`) ne reçoit pas
    de doublon ;
  - le rapport compte ces cas (« valeurs trop longues ») par table et colonne.

  SQLite ne vérifie pas les longueurs : la question ne s'y pose pas.
- Un dump au **format custom** (`pg_dump -Fc`, il commence par `PGDMP`) est refusé avec
  un message qui donne la conversion :
  `pg_restore -f - fichier.dump | gzip > fichier.sql.gz`.
- Les données `INSERT` (`pg_dump --inserts`) ne sont pas gérées : les dumps de prod
  utilisent `COPY`. Si le script croise une ligne `INSERT INTO`, il s'arrête avec un
  message clair, plutôt que de laisser passer des données non anonymisées.
- La sortie est compressée en `.sql.gz` (niveau 6, pour aller vite).

## 7. Le traitement d'une base SQLite

1. Copier l'entrée vers le fichier de sortie « en cours » (décompressée si elle est en
   `.gz`). Si un fichier `-wal` est à côté de l'entrée, il est copié aussi : SQLite y lit
   les dernières écritures.
2. **L'entrée n'est jamais ouverte par SQLite.** Ouvrir une base en mode WAL, même en
   lecture seule, crée des fichiers `-wal` et `-shm` à côté d'elle (constaté par les
   tests). L'entrée doit être une copie au repos (snapshot de `save.sh`, archive borg
   extraite), pas la base vivante.
3. Sur la copie, dans une transaction :
   - appliquer les règles de secrets (§5.3) par `UPDATE` ;
   - vider les tables de la liste par `DELETE` ;
   - remplacer les e-mails : une fonction Python enregistrée avec
     `create_function("anonymiser_emails", 1, ...)`, puis pour chaque table et chaque
     colonne : `UPDATE t SET c = anonymiser_emails(c) WHERE typeof(c) = 'text' AND c LIKE '%@%'`,
     sauf les colonnes protégées (§4.3).
4. `PRAGMA journal_mode = DELETE`, puis **`VACUUM`**. Après la fermeture, aucun fichier
   annexe (`-wal`, `-shm`, `-journal`) ne doit rester : s'il en reste un, le script
   s'arrête et supprime tout.

**Le `VACUUM` est obligatoire.** Sans lui, les anciennes valeurs (vrais e-mails, clés)
restent lisibles dans les pages libres du fichier SQLite, même après les `UPDATE`.

## 8. Le rapport et le contrôle final

### 8.1 Le rapport

Affiché à la fin de chaque fichier. **Que des nombres et des noms de tables ou de
colonnes, jamais une valeur.**

Chaque compteur donne son total, puis le détail par `table.colonne` :

```
lespass.sql.gz -> lespass.anonyme.sql.gz
  e-mails remplaces                 : 264
      AuthBillet_tibilletuser.email : 65
      ...
  valeurs remplacees (regles)       : 204
  valeurs trop longues              : 0
  lignes retirees (tables videes)   : 8
  e-mails laisses (colonnes protegees): 0
  clauses PASSWORD retirees         : 1
  colonnes suspectes NON traitees   : 0
  controle final                    : OK
```

**Les colonnes suspectes** : toute colonne dont le nom contient `key`, `secret`,
`token`, `password`, `pem`, `pin`, `api`, `apikey` ou `otp` (mot entier, entre `_`) et qui n'a pas de règle (ni dans §5, ni dans une
courte liste « vue et laissée exprès », par exemple `public_pem`, `fedow_core_token`,
`stripe_connect_account`). Le script **ne les touche pas** ; il les nomme. C'est ce qui
tient la liste à jour quand un modèle gagne un champ.

### 8.2 Le contrôle final

Une fois la sortie écrite, le script **la relit en entier** et compte les e-mails qui ne
finissent pas par `@anonyme.invalid`, hors colonnes protégées (§4.3) et hors noms
d'images retina. Pour un dump PostgreSQL, les lignes hors des blocs `COPY` (un
`COMMENT ON`, une valeur par défaut) sont lues aussi, et comptées sous
« (hors des blocs COPY) ». La fin du domaine doit être faite de lettres : `django@4.2`
n'est pas un e-mail.

Le contrôle utilise une expression **plus large** que celle du remplacement. Sinon, il ne
prouverait que l'accord du script avec lui-même. Elle attrape aussi les formes que le
remplacement ne voit pas : l'arobase encodée dans une URL (`%40`) et tout texte de la
forme `quelque-chose@domaine.xx` qui ne serait pas reconnu par `\w`. Ce qu'elle trouve
n'est pas remplacé : c'est signalé.

- 0 → `contrôle final : OK`.
- Plus de 0 → le script le dit, donne les tables concernées (pas les valeurs) et sort
  avec le code 1. La sortie n'est pas supprimée : le mainteneur décide.

### 8.3 Codes de sortie

| Code | Sens |
|---|---|
| 0 | Tout est anonymisé, contrôle OK. |
| 1 | Sortie écrite, mais le contrôle final a trouvé des e-mails réels. |
| 2 | Entrée refusée (format custom, `INSERT`, fichier binaire ou format inconnu, dump tronqué, sortie déjà présente, fichier absent). Rien n'est gardé pour ce fichier. |
| 3 | Erreur pendant le traitement (gzip corrompu, erreur SQLite…). Seul le **type** de l'erreur est affiché : son message peut contenir un morceau de donnée de prod. Le fichier de travail est supprimé ; les fichiers suivants sont traités quand même. |

**Arrêt en cours de route.** Le fichier de travail s'appelle
`<sortie>.travail-PAS-ENCORE-ANONYME` : pour SQLite, c'est d'abord une copie brute de la
prod. Un `kill`, un terminal fermé ou un `docker stop` (SIGTERM, SIGHUP) sont transformés
en sortie propre : le fichier de travail est supprimé (code 143 ou 129). Un `kill -9` ne
peut pas être intercepté : supprimer ce fichier à la main s'il reste.

## 9. Ce qui reste en clair

Les inventaires ont trouvé d'autres données personnelles. Elles **ne sont pas
touchées** :

- dates de naissance, codes postaux (adhésions, `APIcashless_membre`) ;
- noms et téléphones **écrits dans du texte libre ou du JSON** : réponses aux formulaires
  (`custom_form` des réservations, adhésions et bookings), commentaires. Seuls les
  e-mails y sont remplacés ;
- adresses IP et user agents (`AuthBillet_tibilletuser`, `fedow_core_wallet.ip`,
  `fedow_core_transaction.ip`, `APIcashless_appareil`, `APIcashless_ipuser`) ;
- commentaires libres (`APIcashless_membre.commentaire`, `BaseBillet_membership.commentaire`…),
  sauf les e-mails qu'ils contiennent ;
- identifiants Stripe (`cus_…`, `acct_…`, `cs_…`, `pi_…`) : ce ne sont pas des secrets,
  mais ils désignent de vrais clients chez Stripe ;
- identifiants de cartes NFC (`tag_id`, `number`, `qrcode_uuid`) : clés de jointure entre
  les trois systèmes ;
- e-mails **cachés dans du base64 ou des données signées** : `fedow_core_checkoutstripe.metadata`,
  `fedow_core_transaction.metadata` (LaBoutik y envoie `signing.dumps(...)` de la requête
  de caisse). L'expression régulière ne les voit pas.

**Le résultat est donc pseudonymisé, pas « anonyme » au sens du RGPD.** Les noms, e-mails,
téléphones et clés sont remplacés, mais une personne peut encore être retrouvée par
recoupement (texte libre, date de naissance et code postal, identifiants Stripe).

## 10. Conséquences connues sur la copie anonymisée

Elles sont attendues et ne sont pas des bugs :

- Aucun lieu ne peut parler à Stripe, Ghost, Brevo, Formbricks, Sunmi, Odoo, Dokos,
  ni à LaBoutik V1 ou à Fedow : les clés sont vides.
- `laboutik_laboutikconfiguration.hmac_key` vide : une nouvelle clé est créée au premier
  usage (`get_or_create_hmac_key`, `laboutik/models.py:260`). La vérification
  d'intégrité des anciennes lignes de caisse échoue en dev. (Avec la clé de prod
  chiffrée, elle échouait déjà : le `FERNET_KEY` du dev ne la déchiffre pas.)
- Personne ne peut se connecter avec un mot de passe. En dev, on se connecte par OTP (le
  mail part vers Mailpit) après avoir remis son propre e-mail sur son compte :
  `manage.py shell`, une ligne. Le mode d'emploi (`README.md`) donne la commande.
- Le dump ne sert qu'à lire. Le charger, c'est la procédure de la pile à part
  (`TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-copie-prod.md`) ou un Postgres jetable.
  Ce chantier ne la change pas.
- **Toujours charger avec `psql -v ON_ERROR_STOP=1`.** Sans cette option, `psql` continue
  après une erreur : un `COPY` refusé laisse une table vide, une contrainte d'unicité
  refusée laisse une table sans contrainte, et rien ne le signale. Le `README.md` donne
  la commande complète.

## 11. Questions ouvertes pour le mainteneur

Les deux questions de la première version sont tranchées (§2, décisions 6 et 7).

## 12. Ce qui reste au builder

- Le découpage interne du fichier (fonctions, noms), en FALC, commentaires bilingues.
- Le réglage fin de l'expression e-mail (§4.2), en gardant les deux exceptions.
- La vérification colonne par colonne du mode `vide` / `null` (§5.1).
- La courte liste « colonnes vues et laissées exprès » du rapport (§8.1).

## 13. Livrables

| Fichier | Contenu |
|---|---|
| `seo/scripts_observatoire/anonymiser_dump.py` | Le script. Neuf : `ruff check --fix` et `ruff format` permis. |
| `seo/scripts_observatoire/README.md` | Mode d'emploi : commande, sorties, codes, limites (§9, §10). |
| `tests/pytest/test_anonymiser_dump.py` | Les tests (§14). |
| `CHANGELOG/2026-11-12-anonymiser-dumps-observatoire.md` | Fiche du chantier. |
| `TECH_DOC/SESSIONS/OBSERVATOIRE/INDEX.md` | Ligne du chantier 03. |

## 14. Tests

Le script s'importe dans les tests par son chemin
(`importlib.util.spec_from_file_location`). Les données de test sont **fabriquées** dans
le test : un petit dump texte et une petite base SQLite, écrits dans `tmp_path`. Aucun
dump de prod dans le dépôt.

Tests attendus (un test = une chose) :

1. Un e-mail dans une colonne `COPY` est remplacé par un `…@anonyme.invalid`.
2. Le même e-mail, dans un fichier SQL et dans un fichier SQLite **passés dans la même
   commande**, donne le même faux e-mail.
3. Un e-mail dans du JSON (`metadata`) est remplacé.
4. `logo@2x.png` n'est pas touché, mais `avatar_dave@gmail.com.png` est remplacé.
4 bis. `…\nalice@x.fr` dans une valeur `COPY` donne le même faux e-mail que `alice@x.fr`.
4 ter. `rené@exemple.fr` est remplacé.
4 quater. `Alice@x.fr` et `alice@x.fr` donnent deux faux e-mails différents.
4 quinquies. Un e-mail court dans une colonne `character varying(10)` devient `anonyme`
   (10 caractères au plus), et le rapport le compte.
5. Une colonne de secret reçoit son mode (`vide`, `null`, `hash_inutilisable`,
   `mot_de_passe`, `jeton_unique`), et `\N` reste `\N`.
6. Une table de la liste « à vider » n'a plus de lignes, et le bloc `COPY` reste valide.
7. La clause `PASSWORD '…'` disparaît d'une ligne `ALTER ROLE`.
8. Un en-tête `COPY` avec noms entre guillemets et schéma de lieu est reconnu.
9. Fedow : `fedow_core_transaction.comment` garde son e-mail, et le rapport le compte.
10. SQLite : après le traitement, la recherche de l'ancien e-mail dans les **octets** du
    fichier de sortie ne trouve rien (preuve du `VACUUM`).
11. Un dump au format custom (`PGDMP`) est refusé, code 2, rien n'est écrit.
12. Une sortie déjà présente est refusée, code 2.
13. Le contrôle final sort en code 1 quand un e-mail réel reste (test qui force le cas,
    par exemple une adresse en `%40`).
14. Le rapport ne contient aucune des valeurs d'origine (ni e-mail, ni clé).

Règle du projet : chaque test est vu **échouer** sur une mutation volontaire du script
avant d'être livré.

**Essai sur un vrai dump** (à la main, hors tests) : le dump LaBoutik de dev
`../LaBoutik/Backup/dumps/laboutik.tibillet.localhost-M0263-2025-07-18-14-01.sql.gz`.
On l'anonymise, puis on le charge dans un Postgres jetable avec
`psql -v ON_ERROR_STOP=1` : il doit se charger sans erreur, contraintes d'unicité
comprises.

**Liste à jour des tests :** voir `tests/pytest/test_anonymiser_dump.py` (33 tests). Deux
séries de mutations volontaires du script (23 au total) ont chacune fait échouer au moins
un test. L'arrêt par signal est vérifié à la main (`kill -TERM` en cours de traitement :
fichier de travail supprimé, code 143).

**Relecture du code :** agent Fable (2026-11-12). Retenus : `crowds_globalfunding`,
exception d'image resserrée, signaux, empreinte distincte pour les valeurs trop longues,
test du `VACUUM` par `freelist_count` et `secure_delete`, contrôle de tout le dump, refus
des fichiers binaires, code 3, mode `identifiant` pour les `username`, `odoo_login`,
pseudonymes sur 32 bits, tests manquants. Écartés : apostrophe dans la partie locale
(`o'brien@…` : l'ajouter casserait les valeurs entre guillemets), colonnes tableau
(`varchar(N)[]` : aucune dans les modèles).

**Relecture de la spec :** builder check par un agent Fable (2026-11-12). Retenus : valeurs trop
longues (§6), HMAC sur le texte exact (§4.1, §4.4), PIN d'appairage (§5.2), expression
avec `(?<!\\)` et Unicode (§4.2), contrôle final plus large (§8.2), `ON_ERROR_STOP` (§10).
