# Page évènement : description longue lisible et sous la galerie / Event page: readable long description, below the gallery

**Date :** 2026-11-27
**Migration :** Non
**Chantier :** `TECH_DOC/SESSIONS/TEXTE_RICHE/SPEC.md`, partie A (session 1 sur 5)

## Resume / Summary

**Quoi / What :** Sur la page publique d'un évènement (skin V2), l'en-tête suit
maintenant l'ordre : titre, description courte, galerie d'images, description
longue, fiches pratiques. La description longue est rendue dans un
`<div class="event-prose">` : tout le texte a la même couleur et la même largeur,
les listes ont leurs puces, les titres restent petits. Dans le skin classic,
l'accordéon « Schedule » rend aussi la description longue dans un `<div>`.
/ V2 event page order: title, short description, gallery, long description,
practical info. The long description is rendered in a `<div class="event-prose">`.

**Pourquoi / Why :** La description longue (HTML de l'admin : paragraphes, listes)
était placée dans un `<p class="page-intro">`. Le navigateur ferme un `<p>` au
premier bloc qu'il contient : le début du texte était gris sur une colonne étroite,
la suite noire sur toute la largeur. Les deux descriptions se suivaient aussi sans
espace, et la galerie coupait le titre de son résumé.
/ The long description was inside a `<p>`, which the browser closes at the first
block: half the text lost its style.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/vues/evenement.html` | Galerie déplacée dans le bloc `evenement_description`, entre les deux descriptions ; longue dans `<div class="event-prose">` ; `data-testid` `evenement-description-courte` et `evenement-description-longue` |
| `pages/templates/pages/V2/partials/evenement_galerie.html` | Commentaire d'en-tête : nouvelle place de la galerie |
| `pages/templates/pages/classic/partials/evenement_accordeon.html` | `<p>` → `<div>` autour de la description longue |
| `pages/static/V2/css/V2.css` | Descriptions courte et longue en pleine largeur dans l'en-tête (plus de `max-width` 62ch / 70ch) ; `.event-prose` : titres h1 à h6 à 18 px, citation avec filet à gauche, pas de marge sous le dernier bloc |
| `tests/pytest/test_evenement_rendu_descriptions.py` | Nouveau : ordre courte → galerie → longue, longue entière dans son `<div>`, cas sans galerie, skin classic |

Aucun nom de bloc du contrat de skin n'a changé.

---

## Comment tester (a la main) / Manual test

### Test 1 — pytest
`docker exec lespass_django poetry run pytest tests/pytest/test_evenement_rendu_descriptions.py -q`
→ 4 passed.

Vérification par mutation (faite le 2026-11-27) : chaque test échoue quand on
remet la galerie avant la courte, la longue dans un `<p>`, ou le `<p>` dans
l'accordéon classic.

### Test 2 — dans le navigateur (fait le 2026-11-27, skin V2)
Ouvrir un évènement avec une description courte, une galerie et une description
longue contenant une liste. Attendu :
- la description courte est juste sous le titre ;
- la galerie vient ensuite, puis la description longue ;
- tous les paragraphes de la longue ont la même couleur (noir) et la même largeur ;
- la liste a ses puces.

Écarts mesurés : titre → courte 12 px, courte → galerie 16 px, galerie → longue
24 px, courte → longue sans galerie 16 px, longue → fiches pratiques 24 px.

### Test 3 — sur la prod, après déploiement
https://la-filature.tibillet.coop/event/la-bande-a-balk-270109-2020-d2f19c17/ :
le texte n'est plus moitié gris, moitié noir. Les listes déjà éclatées et les
`<br>` en trop restent visibles : ils seront réparés par les parties C et E du
chantier.

---

# Session 2 — Texte riche : garder les blocs et ranger le HTML / Rich text: keep blocks and tidy HTML

**Chantier :** `TECH_DOC/SESSIONS/TEXTE_RICHE/SPEC.md`, partie C
**Migration :** Non

## Resume / Summary

**Quoi / What :** Le nettoyage des textes riches garde maintenant les `<div>` de
l'éditeur de l'admin (Trix). Une nouvelle fonction, `normaliser_html_editeur`,
range le HTML après le nettoyage : elle retire les lignes vides du début et de
la fin, les blocs vides, et recolle les listes coupées en listes d'un seul point.
Elle est appelée par l'admin (tous les champs texte), l'API v2 (description des
évènements) et le wizard public.
/ Sanitizing keeps Trix `<div>`. `normaliser_html_editeur` removes leading and
trailing blank lines, empty blocks, and merges split lists.

**Pourquoi / Why :** nh3 retirait les `<div>` de Trix : le texte perdait ses
paragraphes, et chaque enregistrement ajoutait un `<br>` en fin de texte. Un
collage depuis un mail coupait aussi chaque point de liste dans sa propre liste.
Un texte abîmé se répare maintenant au premier enregistrement dans l'admin.
/ nh3 stripped Trix blocks; each save added a `<br>`; pasted lists were split.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/utils.py` | `"div"` dans `ALLOWED_TAGS` ; nouvelle fonction `normaliser_html_editeur` |
| `Administration/admin/site.py` | `sanitize_textfields` : `clean_html` puis `normaliser_html_editeur` |
| `api_v2/serializers.py` | `validate_description` (création et modification d'event) : idem |
| `BaseBillet/views.py` | `_creer_event_depuis_brouillon` (wizard) : idem |
| `BaseBillet/templates/commun/adhesion/form.html` | `<p>` → `<div>` autour de `product.long_description` |
| `pages/templates/pages/classic/vues/accueil.html` | `<p class="lead">` → `<div class="lead">` |
| `pages/templates/pages/classic/vues/adhesions.html` | `<p class="card-text">` → `<div class="card-text">` |
| `pages/templates/pages/classic/vues/compte/membership/membership_card.html` | idem |
| `crowds/templates/crowds/views/detail.html` | `<p class="lead">` → `<div class="lead">` |
| `crowds/templates/crowds/views/list.html` | `<p class="text-muted mb-2">` → `<div …>` |
| `tests/pytest/test_texte_riche_normalisation.py` | Nouveau : 25 tests (cas retirés, cas gardés, stabilité, branchements) |
| `tests/e2e/test_admin_texte_riche_enregistrements.py` | Nouveau : ancien format enregistré trois fois dans l'admin |

Les six templates passent en `<div>` parce que les textes riches gardent
maintenant leurs `<div>` : dans un `<p>`, ils casseraient la mise en page (même
défaut que la page évènement, corrigé en session 1).
/ The six templates now use `<div>`: kept `<div>` blocks would break a `<p>`.

---

## Comment tester (a la main) / Manual test

### Test 1 — pytest et E2E
- `docker exec lespass_django poetry run pytest tests/pytest/test_texte_riche_normalisation.py -q` → 25 passed.
- `make e2e ARGS="tests/e2e/test_admin_texte_riche_enregistrements.py -q"` → 1 passed.

Vérification par mutation (faite le 2026-11-27) : les tests échouent si on retire
`div` des balises autorisées, si la fonction ne fait rien, si elle oublie
`&nbsp;`, si elle ne fait qu'une passe, ou si l'un des trois branchements
(admin, API v2, wizard) l'oublie. Le test E2E échoue si l'admin ne range plus.

### Test 2 — dans l'admin
1. Ouvrir un évènement dont la description commence ou finit par des lignes vides.
2. Cliquer sur « Enregistrer et continuer » sans rien changer.
3. Attendu : les lignes vides du début et de la fin ont disparu, les listes
   d'un seul point sont recollées en une seule liste.
4. Enregistrer encore deux fois : le texte ne change plus.

### Test 3 — mesure sur les données de La Filature (faite le 2026-11-27)
Sur les 84 descriptions non vides (copie de la prod), 19 sont modifiées par le
rangement, toutes de façon stable. La Bande à Balk : 6 listes → 1 liste, les
`<br>` du début sont retirés.

---

# Session 3 — Éditeur de l'admin : les paragraphes ne fusionnent plus / Admin editor: paragraphs no longer merge

**Chantier :** `TECH_DOC/SESSIONS/TEXTE_RICHE/SPEC.md`, partie B (simplifiée)
**Migration :** Non

## Resume / Summary

**Quoi / What :** Un script d'une ligne, chargé sur toute l'admin, corrige la
config de l'éditeur (Trix) ajoutée par Unfold. Les paragraphes `<p>` qui se
suivent restent séparés à l'ouverture d'une fiche.
/ A one-line admin script fixes Unfold's Trix config: neighbouring `<p>` stay separate.

**Pourquoi / Why :** Unfold déclare le bloc « paragraphe » sans `group: false`.
Trix fusionnait alors `<p>Un.</p><p>Deux.</p>` en `<p>Un.Deux.</p>` dès
l'ouverture de la fiche, et l'enregistrement gardait le texte collé.
/ Without `group: false`, Trix merged neighbouring paragraphs on load.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `static/js/trix_paragraphes.js` | Nouveau : `Trix.config.blockAttributes.p.group = false` sur `trix-before-initialize` |
| `TiBillet/settings.py` | `UNFOLD["SCRIPTS"]` charge ce script |
| `tests/e2e/test_admin_texte_riche_enregistrements.py` | Nouveau test : trois `<p>` restent trois `<p>` après un enregistrement |

---

## Comment tester (a la main) / Manual test

### Test 1 — E2E
`make e2e ARGS="tests/e2e/test_admin_texte_riche_enregistrements.py -q"` → 2 passed.
Vérification par mutation (faite le 2026-11-27) : sans la ligne du script, le test
des paragraphes échoue (`<p>Un.Deux.Trois.</p>`).

### Test 2 — collage d'un mail dans l'admin
1. Copier un mail avec plusieurs paragraphes, une liste à puces, du gras et un lien.
2. Le coller dans la description longue d'un évènement.
3. La liste peut apparaître coupée dans l'éditeur : c'est normal avant l'enregistrement.
4. Cliquer sur « Enregistrer et continuer ».
5. Attendu : paragraphes séparés, une seule liste, gras et lien conservés.

---

# Sessions 4 et 5 — Texte brut converti, réparation des events en base / Plain text converted, repair of stored events

**Chantier :** `TECH_DOC/SESSIONS/TEXTE_RICHE/SPEC.md`, parties D et E
**Migration :** Non

## Resume / Summary

**Quoi / What :**
- Le wizard public et l'API v2 convertissent un texte sans balise en HTML :
  sauts de ligne en `<br>`, URL et adresses mail cliquables (`texte_brut_vers_html`).
- Nouvelle commande `normaliser_textes_riches [--dry-run]` : applique aux
  descriptions longues déjà en base, dans tous les lieux, le traitement d'un
  nouvel enregistrement (conversion, nettoyage, rangement).
/ Wizard and API v2 convert plain text to HTML. New command repairs stored descriptions.

**Pourquoi / Why :** Le textarea du wizard envoie du texte brut. Affiché en HTML,
il perdait ses sauts de ligne : tout le texte tenait sur une ligne. Les events
déjà en base gardaient leurs lignes vides et leurs listes coupées jusqu'au
prochain enregistrement dans l'admin.
/ Wizard plain text lost its line breaks; stored events kept their defects.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/utils.py` | Nouvelle fonction `texte_brut_vers_html` |
| `api_v2/serializers.py` | `validate_description` : conversion avant le nettoyage |
| `BaseBillet/views.py` | `_creer_event_depuis_brouillon` : idem |
| `Administration/management/commands/normaliser_textes_riches.py` | Nouvelle commande |
| `api_v2/openapi-schema.yaml` | `description` d'Event et d'EventPatch : conversion et rangement documentés |
| `TECH_DOC/SKILLS/tibillet-api/references/recettes.md` | idem |
| `tests/pytest/test_texte_riche_normalisation.py` | 9 tests ajoutés (conversion, API, wizard, commande) |

---

## Comment tester (a la main) / Manual test

### Test 1 — pytest
`docker exec lespass_django poetry run pytest tests/pytest/test_texte_riche_normalisation.py -q` → 34 passed.
Vérification par mutation (faite le 2026-11-27) : conversion inerte, `urlize` après
les `<br>`, API ou wizard sans conversion, passe à blanc qui écrit, commande qui
n'écrit pas : chaque cas fait échouer au moins un test.

### Test 2 — wizard public
Proposer un évènement avec une description sur plusieurs lignes et un lien.
Attendu sur la page publique : les sauts de ligne sont gardés, le lien est cliquable.

### Test 3 — réparation en production (mainteneur)
**Après le déploiement de tout le chantier**, dans cet ordre :
1. Faire un dump de la base.
2. `python manage.py normaliser_textes_riches --dry-run` : lire les chiffres par
   lieu et les exemples « avant / après ».
3. `python manage.py normaliser_textes_riches` : la vraie passe.
4. Relancer `--dry-run` : il doit annoncer 0 event à changer.

En dev (2026-11-27), la passe à blanc annonce 22 events. Un texte brut d'une
seule ligne est lui aussi changé : il est entouré d'un `<div>`, sans effet visible.

---

# Corrections après la relecture Fable (2026-11-27)

| Fichier / File | Changement / Change |
|---|---|
| `Administration/utils.py` | `texte_brut_vers_html` décode les entités avant de convertir : la commande de réparation ne transforme plus `Tom &amp; Jerry` en `Tom &amp;amp; Jerry` |
| `Administration/utils.py` | Une balise exige un nom suivi d'une espace, d'un `/` ou d'un `>` : « Jean <jean@exemple.org> » est du texte brut, ses sauts de ligne sont gardés |
| `Administration/utils.py` | Fin du texte : deux regex non ancrées remplacées par un parcours à reculons. 5 000 sauts de ligne envoyés au wizard public : 8 s → moins de 10 ms |
| `pages/templates/pages/V2/vues/compte/punchclock.html` | `badge.long_description` rendu avec `|safe` dans un `<div>` (le `<div>` de l'éditeur s'affichait en clair) |
| `pages/templates/pages/classic/vues/compte/punchclock.html` | idem |
| `tests/pytest/test_texte_riche_normalisation.py` | 4 tests ajoutés (entités, adresse entre chevrons, temps, commande avec `&amp;`), un test renommé |

Vérifié : 38 tests verts ; chaque correction est vue échouer sous mutation. Les
deux pages punchclock (V2 et classic) contrôlées dans Chrome avec un badge de test.

## Rendu des six templates passés en `<div>` (contrôlé dans Chrome)
Texte riche de test (paragraphes, ligne vide, liste) sur chaque source :
- skin classic : accueil (`lead`), adhésions et carte d'adhésion (`card-text`) :
  tout le texte dans le bloc, même couleur, puces présentes ;
- formulaire d'adhésion (panneau V2), crowds détail et liste : tout le texte dans
  le bloc, même couleur, mais **sans puces** (reset `ul { list-style: none }` du
  CSS V2) et sans marge après la description courte. Défaut de style déjà connu,
  hors périmètre (SPEC §4).

---

# Corrections après la seconde relecture Fable, focus XSS (2026-11-27)

| Fichier / File | Changement / Change |
|---|---|
| `Administration/utils.py` | `texte_brut_vers_html` : `escape()` puis `urlize(autoescape=False)`, et plus aucun décodage d'entités. Un lien collé avec `&region=sud` n'est plus cassé en `®ion=sud` (urlize décode l'URL avant d'écrire le `href`) |
| `Administration/management/commands/normaliser_textes_riches.py` | Le décodage des entités se fait ici, seulement pour un texte sans balise déjà en base (sortie de nh3) |
| `api_v2/serializers.py` | `ProductCreateSerializer.validate_description` : description de produit convertie, nettoyée (nh3) et rangée. Elle était écrite telle quelle, puis rendue en `|safe` (adhésions, page Badgeuse) : XSS possible avec une clé API d'admin |
| `api_v2/openapi-schema.yaml` | `description` de `ProductCreate` documentée |
| `tests/pytest/test_texte_riche_normalisation.py` | URL avec `&region=` intacte, commande avec `&nbsp;`, description produit nettoyée |

Vérifié : 38 tests verts, chaque correction vue échouer sous mutation, 425 tests voisins verts.

---

# Fermeture des écritures non nettoyées (2026-11-27)

Trois chemins écrivaient du HTML sans `clean_html` dans des champs rendus en
`|safe` (faille XSS préexistante). Ils passent maintenant par la même chaîne que
l'admin : `normaliser_html_editeur(clean_html(texte_brut_vers_html(...)))`.
/ Three write paths skipped sanitizing; they now use the admin's chain.

| Fichier / File | Changement / Change |
|---|---|
| `onboard/tasks.py` | `create_tenant_from_draft` : `Configuration.long_description` saisie à l'onboarding (n'importe qui peut créer un lieu) |
| `ApiBillet/serializers.py` | `ProductCreateSerializer.validate_long_description`, `EventCreateSerializer.validate_long_description`, `EventWriteSerializer.validate_description` (API historique, clé d'admin) |
| `Administration/admin_tenant.py` | `EventResource.before_save_instance` : import CSV des events (ne passe pas par `save_model`) |
| `tests/pytest/test_texte_riche_normalisation.py` | 4 tests (3 serializers de l'API historique, import CSV) |

Vérifié : 42 tests verts, chaque branchement vu échouer sous mutation (sauf
l'onboarding, voir ci-dessous), 810 tests voisins verts (API historique, import,
onboarding).

**Non testé automatiquement :** le branchement de l'onboarding. Le tester demande de
créer un schéma de lieu complet (`create_tenant_from_draft`), qui n'a aucun test
aujourd'hui. Test manuel : créer un lieu par l'onboarding avec une description sur
plusieurs lignes contenant `<script>alert(1)</script>` ; l'accueil du lieu affiche
les sauts de ligne et aucun script ne s'exécute.

