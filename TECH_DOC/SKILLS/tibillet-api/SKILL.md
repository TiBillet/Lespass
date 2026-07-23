---
name: tibillet-api
description: >
  Créer, éditer et peupler des ressources TiBillet/Lespass via l'API v2 REST
  sémantique (schema.org/JSON-LD) : pages & blocs (sites web), events, products,
  memberships, reservations, crowds, wallet-refills, adresses postales. Utilise ce
  skill dès qu'il faut fabriquer un site par blocs, créer un événement/produit/adhésion,
  peupler ou seeder un tenant, importer du contenu, scripter des créations, ou obtenir
  une clé API de test. Déclenche aussi quand l'utilisateur mentionne « l'API v2 »,
  « l'API TiBillet », « créer une page/un event via l'API », « peupler un tenant »,
  « une clé API », un endpoint `/api/v2/...`, ou le catalogue `block-types`. Ne pas
  attendre le mot « API » : tout ce qui consiste à créer des ressources TiBillet
  programmatiquement (plutôt que via l'admin Unfold) passe par ce skill.
---

# TiBillet API v2 — créer et peupler des ressources par l'API sémantique

L'API v2 est une API REST **sémantique** (vocabulaire schema.org, corps JSON-LD),
authentifiée par clé, multi-tenant. Elle couvre : **pages & blocs** (constructeur de
site), **events**, **products/prices**, **memberships**, **reservations**, **sales**,
**crowds/initiatives**, **wallet-refills**, **postal-addresses**.

Ce skill donne l'**auth, le modèle mental, les réflexes et les pièges**. Il ne recopie
PAS la liste des champs : celle-ci vit dans les sources de vérité ci-dessous, qui
restent à jour quand l'API évolue.

## Sources de vérité — toujours s'y référer, ne pas deviner

1. **`api_v2/openapi-schema.yaml`** — le contrat complet : tous les endpoints, schémas,
   exemples de requête. C'est LA référence des champs. Lis-la (ou la section concernée)
   avant de construire un corps de requête non trivial.
2. **`api_v2/GUIDELINES.md`** — le guide sémantique : mapping schema.org ↔ modèle,
   images (URL vs multipart), pièges, permissions.
3. **`GET /api/v2/pages/block-types/`** — le **catalogue LIVE** des types de blocs et
   de leurs champs autorisés. Pour tout travail sur les pages : **interroge-le d'abord**.
   Il reflète le code réel (`pages/blocs_catalogue.py`), donc les nouveaux blocs y
   apparaissent automatiquement — ne code jamais la liste des types en dur.

Règle d'or : **si tu hésites sur un champ ou un endpoint, lis l'OpenAPI ou interroge
l'API — ne devine pas.**

## 1. Authentification & environnement

- **Header** : `Authorization: Api-Key <clé>` sur chaque requête.
- **URL par tenant** (multi-tenant) : `https://<tenant>.tibillet.localhost/api/v2/…`
  en dev (Traefik, certificat auto-signé → `curl -k`). En prod : le domaine réel du
  tenant. **L'hôte détermine le tenant** ; une clé n'est valable que sur son tenant.
- **Permissions granulaires** : une `ExternalApiKey` ouvre des domaines précis —
  `event` (+ `postaladdress`), `product` (+ `price`), `page` (= pages **ET** blocs),
  `membership`, `reservation`, `ticket`, `wallet`, `sale`, `crowd`, et `walletrefill`
  (si un `gift_asset` est défini). Une requête hors permission renvoie **403**.
- **Obtenir une clé de test** : `scripts/creer_cle_api.py` (voir la fin de ce fichier).

## 2. Le modèle mental sémantique (schema.org)

Les ressources ne portent pas les noms du modèle Django mais leur équivalent schema.org.
Pour les **blocs** de page (`WebPageElement`), le mapping est :

| Clé JSON (entrée/sortie) | Champ modèle | Note |
|---|---|---|
| `additionalType` | `type_bloc` | **pivot** : HERO, PARAGRAPHE, IFRAME, PARTENAIRES, NEWSLETTER… |
| `headline` | `titre` | |
| `alternativeHeadline` | `sous_titre` | |
| `text` | `texte` | HTML nettoyé par nh3 côté serveur |
| `image` | `image` | URL (string) **ou** `ImageObject[]` pour GALERIE / PARTENAIRES |
| `position` | `position` | ordre dans la page |
| `additionalProperty` | *tout le reste* | `PropertyValue[]` (voir ci-dessous) |

**`additionalProperty`** transporte tous les autres champs, au format
`{"@type":"PropertyValue","name":"<champ>","value":<valeur>}`. Exemples de `name` :
`embed_url`, `hauteur_px`, `bouton_url`, `points_gps`, `nombre_max`, `repliable`…
La liste exacte par type vient de `block-types/`. `value` accepte string, nombre,
booléen, liste ou objet JSON.

Deux points qui évitent de deviner :
- **`@type":"PropertyValue"` est facultatif** — le serveur ne lit que `name` et `value`.
  On peut écrire simplement `{"name":"embed_url","value":"…"}`. (Les exemples de ce skill
  l'omettent parfois pour la lisibilité : les deux formes marchent.)
- **Seul `additionalType` est requis** pour créer un bloc ; tout le reste (dont `headline`)
  est optionnel. Un bloc sans titre est valide — ne pas inventer un titre « pour faire joli ».

Les **pages** (`WebPage`) suivent la même logique : `name` = titre, `hasPart` = la liste
ordonnée de blocs (création imbriquée en un seul POST), `additionalProperty` pour
`slug`, `publie`, `est_accueil`, `est_blog`, `noindex`, `meta_title`, `meta_description`.

**Hiérarchie & navbar** : pour ranger une page **sous une page parente** (menu déroulant),
utilise le champ **`isPartOf`** (au niveau haut du corps, PAS dans additionalProperty) =
l'uuid **ou** le slug de la parente. Une page **d'accueil** (`est_accueil`) ne peut pas
être parente. Une page **blog** (`est_blog=true`) type ses sous-pages en **articles** (JSON-LD Article +
signature date, et elles sortent du menu déroulant). Pour lister les articles en cartes,
ajoute un bloc `LISTE_SOUS_PAGES` à la page blog (c'est lui qui rend les cartes ; `est_blog`
ne les crée pas). Le corps d'un article : un bloc `MARKDOWN` (les images `![](url)` du
markdown sont **importées** et servies depuis le tenant, via `galerie:N`).

## 3. Réflexes par domaine

- **Pages/blocs** : (1) `GET block-types/` pour connaître types + champs à jour ;
  (2) `POST /api/v2/pages/` avec `hasPart` pour créer la page **et** ses blocs d'un
  coup, OU `POST /api/v2/pages/{uuid}/blocs/` pour ajouter un bloc à une page existante.
- **Images** : par **URL** (le serveur télécharge, valide Pillow, ≤ 10 Mo, refuse le
  SSRF interne/loopback) — pratique pour scripter. Ou par **upload multipart** sur les
  endpoints `blocs`. La **vidéo** n'est pas settable par l'API (utiliser un bloc EMBED).
- **Autres domaines** (events, products, memberships, crowds, wallet-refills) : consulter
  la section correspondante de l'OpenAPI. Les recettes curl canoniques sont dans
  `references/recettes.md`.

## 4. Composer une page qui rend bien (l'API ne juge pas la mise en page)

Un `201` prouve que le bloc existe, **pas** que la page est belle. Deux règles issues
de vraies corrections en review :

- **Quinconce (`IMAGE_TEXTE`) : le texte ne doit pas être plus haut que l'image.**
  Le template pose le texte *à côté* de l'image, et l'image **garde son ratio** (pas de
  crop : ce sont souvent des illustrations). Si tu colles 6 paragraphes à côté d'une
  illustration, le texte déborde sous elle et le bloc devient bancal.
  → Garde **~400 caractères max** à côté de l'image (un chapô), et renvoie **le reste
  dans un bloc `PARAGRAPHE` pleine largeur** juste après. Alterne
  `image_position` GAUCHE/DROITE d'un `IMAGE_TEXTE` au suivant pour l'effet quinconce.
  Ne « corrige » pas ça en CSS avec un `object-fit: cover` : ça croperait les
  illustrations de tous les tenants (la skin `classic` est partagée).
- **Un bloc = une idée.** Une section longue = `IMAGE_TEXTE` (image + chapô) puis
  `PARAGRAPHE`(s). Pas un bloc géant par section.

## 5. Peupler un site entier : figer la source, scripter, vérifier

Pour **1 à 3 pages** : `curl` direct, c'est suffisant. **Au-delà** (import d'une doc, seed
d'un tenant, refonte), scripter est nettement meilleur — et c'est ce qui a servi à
construire le site `la-maison-des-communs` (21 pages) :

1. **Figer la source** dans des fichiers locaux (`docs-raw/*.json`) : la source (MCP Docs,
   scraping, CSV) est lente, rate-limitée et non déterministe. On la lit **une fois**.
2. **Un script de mapping + POST** qui lit ces fichiers, construit les corps JSON-LD et
   boucle les `POST /pages/` (`hasPart` imbriqué = 1 requête par page). Itérer sur la
   mise en page devient gratuit : on relance le script, pas la lecture de la source.
3. **Rendre le script rejouable.** C'est le point qu'on rate : un 2ᵉ run se plante en
   collisions de slug. Fais commencer le script par une **suppression fiable** de ce
   qu'il va recréer, et **vérifie que la suppression a marché** avant de recréer (un
   parsing bancal de `GET /pages/` qui « supprime 0 page » en silence coûte une heure).
4. **Relire le résultat dans le navigateur**, pas seulement les codes HTTP.

Ce script de build est **jetable** : garde-le hors du dépôt (scratchpad), pas dans le
dossier du skill. Et **jamais de clé API en dur** — ce dossier est versionné : lis la clé
depuis l'environnement (`os.environ["TIBILLET_API_KEY"]`).

## 6. Pièges à connaître (avant de perdre du temps)

- **Slugs réservés** : une page ne peut pas prendre un slug de route existante
  (`event`, `memberships`, `admin`…). Pas besoin de connaître la liste à l'avance : si le
  slug est réservé, le POST renvoie un **400 explicite** — lis le message et choisis un
  autre slug. (Référence exhaustive : `pages/models.py:SLUGS_RESERVES`.)
- **La réponse expose les défauts de TOUS les champs** : à la relecture (`GET`), chaque
  bloc renvoie `additionalProperty` avec les valeurs par défaut de tous les champs du
  modèle (`image_position`, `nombre_max`, `hauteur_px`…), pas seulement ceux de son type.
  C'est normal — ne cherche que les champs que tu as posés, ignore les autres.
- **URLs dangereuses neutralisées** : les champs lien (`bouton_url`, `embed_url`, et la
  clé `url` d'un logo PARTENAIRES) à schéma `javascript:`/`data:`/`vbscript:` sont
  **vidés** côté serveur, pas rejetés. Ne compte pas dessus pour valider — envoie du https.
- **`embed_url` d'un IFRAME** n'est **rendu** que si son hôte est autorisé par le
  superadmin ROOT (whitelist globale). L'API accepte la création ; le rendu, lui, dépend
  de la whitelist.
- **403 ≠ 404** : un 403 signale une clé sans la bonne permission, pas une ressource
  absente. Vérifie les droits de la clé.
- **Isolation tenant** : tester avec le bon hôte. Une clé d'un tenant ne voit pas les
  ressources d'un autre.
- **Tout n'est pas settable par l'API** : la **vidéo** d'un bloc, et l'**image de la page**
  (og:image) ne le sont pas. Si le besoin est là, c'est un manque à combler dans
  `api_v2/serializers.py`, pas un champ à deviner.

## 7. Boucle de travail recommandée

1. Identifier le tenant et la permission nécessaire ; obtenir/valider une clé.
2. Pour les pages : `GET block-types/`. Sinon : lire la section OpenAPI du domaine.
3. Construire le corps JSON-LD (sémantique du §2) ; pour un site entier, préférer le
   POST `hasPart` imbriqué.
4. `curl -k` (dev) le POST, **vérifier le code HTTP** (201 = créé, 400 = corps invalide,
   403 = permission).
5. Relire la ressource (`GET`) pour confirmer le mapping.
6. **Ouvrir la page dans le navigateur** (`https://<tenant>.tibillet.localhost/…`) : le
   mapping peut être juste et la mise en page cassée (cf. §4). C'est l'étape qu'on saute
   et qui coûte un aller-retour de review.

## Helper — obtenir une clé API de test

```bash
python TECH_DOC/SKILLS/tibillet-api/scripts/creer_cle_api.py \
  --tenant lespass --perms page,event,product
```

Le script crée une `ExternalApiKey` sur le tenant et imprime la clé en clair (elle
n'est visible qu'à la création). Options : `--tenant`, `--perms` (liste séparée par
virgules parmi event, product, page, membership, reservation, ticket, wallet, sale,
crowd), `--name`, `--container` (défaut `lespass_django`). Voir `--help`.

⚠️ **Helper de DEV uniquement** : il passe par `docker exec` et **supprime d'abord toute
clé existante portant le même nom**. Ne le lance pas contre une base de production.
La clé imprimée est un secret : ne la recopie **jamais** dans un fichier du dépôt.

> En dev, le serveur tourne dans byobu et Traefik sert le HTTPS ; utilise
> `https://<tenant>.tibillet.localhost/` et `curl -k`. Ne lance pas de serveur toi-même.
