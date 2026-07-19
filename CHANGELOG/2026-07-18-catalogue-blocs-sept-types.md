# Catalogue de blocs : 19 types → 7, et suppression du groupement implicite / Block catalogue: 19 types → 7, implicit grouping removed

**Date :** 2026-07-18
**Migration :** Oui — `pages` 0004, 0005, 0006 (dont une migration de données)

## Resume / Summary

**Quoi / What :** le catalogue de blocs de l'app `pages` passe de **19 types** a
**7**, organises par INTENTION plutot que par rendu. La variation visuelle est portee
par un nouveau champ `affichage`. Le service `grouper_blocs`, qui recollait des blocs
voisins au rendu, est supprime : chaque bloc se rend seul et la mise en page cote a
cote passe par une grille CSS.
/ The block catalogue drops from **19 types** to **7**, organised by INTENT. Visual
variation moves to a new `affichage` field. The `grouper_blocs` service is gone: each
block renders alone and side-by-side layout comes from a CSS grid.

**Pourquoi / Why :** deux obstacles empechaient un futur front leger de tenir en trois
clics. Un modal a 19 entrees n'est pas « trois clics ». Et `grouper_blocs` decidait la
mise en page dans le dos de la personne : ajouter un bloc changeait l'apparence de deux
autres, sans que l'admin ne le montre. C'est le CHANTIER 07
(`TECH_DOC/SESSIONS/PAGES/CHANTIER-07-moteur-documentaire.md`).

## Le nouveau catalogue

| Type | Intention | Affichages |
|---|---|---|
| `TEXTE` | « j'ecris du texte » (Markdown) | — |
| `SECTION` | « je mets quelque chose en avant » | `BANNIERE` · `TEXTE_IMAGE_GAUCHE` · `TEXTE_IMAGE_DROITE` · `TEXTE_VIDEO` · `MEDIA_ET_CARTES` · `CARTE` · `APPEL_ACTION` · `CITATION` |
| `IMAGES` | « je montre une ou plusieurs images » | `PLEINE_LARGEUR` · `VIGNETTE_TITRE` · `GRILLE` · `BANDE_LOGOS` |
| `INTEGRATION` | « j'integre un truc externe » | `VIDEO` · `WIDGET` · `NEWSLETTER` |
| `LIEU` | « je montre ou c'est » | — |
| `FAQ` | « je reponds a des questions » | — |
| `LISTE` | « je liste des choses automatiquement » | — (champ `source`) |

Regle inscrite dans `blocs_catalogue.py` : **jamais un nouveau TYPE pour une variation
purement visuelle.** Un type dit ce qu'on veut exprimer, un affichage sous quelle forme.

### Points de conception

- **`TEXTE` = Markdown, un seul pipeline de securite.** Les deux anciens types de texte
  avaient deux traitements differents (`clean_html` au save d'un cote, sanitize `nh3`
  au rendu de l'autre). Faire dependre ce choix d'un select ferait varier la securite
  selon une valeur d'affichage.
- **Les trois affichages d'`INTEGRATION` choisissent trois pipelines de securite**
  distincts (whitelist video codee / whitelist ROOT + sandbox / script Ghost). Le
  pipeline se lit dans `affichage`, jamais dans l'URL.
- **`source` de `LISTE` n'est pas un affichage** : il choisit une requete, pas un rendu.
- **`Bloc.clean()` valide le couple (type, affichage)** — Django ne sait pas conditionner
  des choices par la valeur d'un autre champ, le modele porte l'union.
- **`page_source` est hors de `CHAMPS_BLOC_AUTORISES`** (nouveau `CHAMPS_RELATION`) :
  un `setattr` d'uuid en texte leverait un `ValueError` (500 au lieu de 400) et un
  `getattr` renverrait une instance non serialisable, cassant la lecture de toute page.

### `MEDIA_ET_CARTES` — la section composee

Un affichage de `SECTION` qui porte ses **sous-cartes** dans le JSONField `contenu`
(items TEXTE : `titre`, `texte`, `badge`). Une sous-carte n'est pas un bloc : elle vit
a l'interieur de la colonne de sa section, la ou une liste plate de blocs ne saurait la
placer. Le skin `faire_festival` la rend en deux colonnes (media a gauche, titre + texte
+ sous-cartes + bouton a droite) ; le socle `classic` empile.

## Ce qui disparait

- **`VIDEO_TEXTE`** en tant que type (devient `SECTION`/`TEXTE_VIDEO`).
- **`grouper_blocs`** (`pages/services.py`) et `context["groupes_blocs"]`.
- **Champs de `Bloc`** : `surtitre` (→ `sous_titre`), `image_position` (→ deux
  affichages), `affichage_image` (→ `affichage`), `repliable` (la FAQ est toujours un
  accordeon).
- **`Page.est_blog`**, le JSON-LD `Article` et la signature date/auteur : le blog sort
  du moteur (decision mainteneur, un outil externe est a l'etude).

## Migrations

| # | Role | Note |
|---|---|---|
| 0004 | `AddField` + `AlterField` + **conversion des donnees** | `atomic = False` : melange DDL/DML que Postgres refuse en une transaction |
| 0005 | Les 4 `RemoveField` | **Separee** : Postgres refuse un `ALTER TABLE` sur une table qui vient de recevoir des `UPDATE`/`DELETE` |
| 0006 | `AlterField` (ajout de `MEDIA_ET_CARTES`) | |

La conversion 0004 traite deux cas non triviaux : **`INFOS` + `CARTE_LEAFLET` adjacents
fusionnent en un seul `LIEU`** (2:1), et `source` est pose AVANT que la conversion
generique n'efface l'ancien type (sinon `EVENEMENTS` et `LISTE_SOUS_PAGES` deviennent
indiscernables).

Verification apres migration, au bloc pres : 128 blocs avant, 126 apres (les 2 `INFOS`
absorbes). Chaque ancien type retombe sur le bon couple.

## Mise en page

- `.tb-flux` : grille **12 colonnes** qui porte le cadrage (zone de contenu centree sur
  `--tb-largeur-max`), le `column-gap` et l'etirement des rangees. Les blocs pleine
  largeur s'en echappent par marges negatives (`.tb-pleine-largeur`).
- Classes **structurelles** `tb-colonnes-4` / `tb-colonnes-6`, separees des classes
  d'habillage : un skin declare sa largeur sans heriter du style du socle.
- Alignement des cartes : zone d'image a hauteur constante, texte elastique, bouton
  colle en bas — images, textes et boutons alignes entre cartes voisines.

## Comment tester (a la main) / Manual test

### Test 1 — les deux skins rendent

1. `https://festival.tibillet.localhost/` — banniere « Faire », section « c'est quoi ? »
   avec le media a gauche et les cartes JOUR **a droite**, cartes tuto 1/2/3 dont les
   images, textes et boutons sont alignes.
2. `https://la-maison-des-communs.tibillet.localhost/` et
   `https://lespass.tibillet.localhost/` — skin classic, cartes en rangees de trois.

### Test 2 — la fusion LIEU

`https://festival.tibillet.localhost/infos-pratiques/` : les infos pratiques a gauche et
la carte Leaflet a droite forment **un seul bloc** dans l'admin.

### Test 3 — aucun bloc n'influence son voisin

Dans l'admin, deplacer un bloc `SECTION`/`CARTE` au milieu d'une suite de cartes :
l'apparence des blocs voisins ne change pas.

### Test 4 — la validation type x affichage

Creer un bloc `SECTION` et tenter de lui poser l'affichage `BANDE_LOGOS` (via l'API ou
un `full_clean()`) : `ValidationError`.

### Verifs automatiques / Automated checks

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/ -q
```

## Reste a faire / Still to do

- L'admin (`conditional_fields` sur le couple type x affichage) et l'API v2
  (`block-types/`, resolution de `page_source`).
- Les commandes de seed : `charger_demo_faire_festival.py` doit produire un bloc
  `MEDIA_ET_CARTES` — sinon un rechargement de la demo recree l'ancienne structure.
- Les tests : plusieurs s'accrochent aux anciens `data-testid` et aux anciens types.
