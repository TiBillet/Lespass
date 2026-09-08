# Ecarts avec la maquette : correctifs et finitions / Mockup gaps: fixes and polish

**Date :** 2026-09-08
**Migration :** Non

## Resume / Summary

**Quoi / What :** relecture complete de la maquette et comparaison avec
l'admin. Corrige : deux `<h1>` par page, le nom du lieu absent du rail sur
trois ecrans, le tableau de bord appele « Site d'administration », l'absence
de retour depuis un module. Ajoute : une description sous chaque page, des
pastilles d'icone aux couleurs de leur categorie, « Tableau de bord » en
entree autonome du rail.
/ Full mockup review: fixed two <h1> per page, the venue name missing from
the rail on three screens, the dashboard's generic title, and the lack of a
way back from a module. Added page descriptions and per-category icon colours.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/settings.py` | `SITE_HEADER` devient un callable ; `+ SITE_SUBHEADER`, `+ SITE_SYMBOL` ; `+ 2` entrees dans `SITE_DROPDOWN` |
| `Administration/admin/site.py` | `+ index_title` |
| `Administration/admin_tenant.py` | re-export de `nom_du_lieu`, pour que `SITE_HEADER` puisse le pointer |
| `Administration/admin/dashboard.py` | `+ nom_du_lieu`, `+ DESCRIPTION_DES_PAGES` ; `title` = le parent dans les deux vues ; `+ lien_du_domaine`, `+ categorie_ouverte` ; « Tableau de bord » sorti en groupe sans titre |
| `Administration/templates/admin/{index,module_page,domaine_page}.html` | etendent `unfold/layouts/base.html` ; `{% block title %}` ; `<h1>` → `<h2>` |
| `Administration/templates/admin/module_page.html` | `+` lien de retour, descriptions, categorie sur la liste |
| `Administration/templates/admin/dashboard.html` | `+` en-tete de page |
| `static/css/tibillet-admin.css` | `+` lien de retour, description de ligne, pastilles par categorie, degrade sur la pastille de marque |
| `tests/pytest/test_admin_tableau_de_bord.py` | `+ 14` tests (35 au total) |

## Les correctifs

### 1. Deux `<h1>` sur les pages de domaine et de module

Unfold affiche deja le titre en barre haute (`welcomemsg.html`), et mes
gabarits en ajoutaient un dans le contenu : « Lespass » apparaissait **deux
fois**, et la page avait deux `<h1>`.

`{% header_title %}` est en realite un **fil d'Ariane** — sur une changelist
il rend « Billetterie › Évènements ». On lui donne donc le **parent** :

| Page | Barre haute | Contenu |
|---|---|---|
| Page de domaine | Tableau de bord | ◆ Lespass |
| Page de module | Lespass | ◆ Agenda et Billetterie |

Et le titre du contenu passe en `<h2>` : la barre haute garde le seul `<h1>`,
comme sur toutes les changelists. **Le niveau de titre ne dicte pas la
taille** — celle-ci vient du CSS, le titre reste le plus gros texte de la page.

`{% block title %}` est surcharge dans les deux gabarits pour que l'onglet du
navigateur porte le vrai nom de la page.

### 2. Le haut du rail etait vide

Ni nom de lieu ni logo sur le tableau de bord, la page de domaine et la page
de module — alors qu'une **changelist les affichait**. Le rail changeait donc
d'aspect selon la page.

Cause : ces trois gabarits etendaient `unfold/layouts/base_simple.html`, qui
ne definit pas le bloc `branding`. **Le correctif tient en un mot** : etendre
`unfold/layouts/base.html`, qui n'est que `base_simple` + ce bloc.

Contenu : `SITE_HEADER` devient un **callable** rendant le nom du lieu
(`Configuration.organisation`), avec un repli sur « TiBillet » — le cas d'un
lieu sans nom existe. `SITE_SUBHEADER` affiche « Votre espace TiBillet », et
`SITE_SYMBOL` donne son glyphe a la pastille, a laquelle le CSS ajoute le
degrade de marque.

### 3. Le tableau de bord s'appelait « Site d'administration »

Titre generique de Django, jamais regle. `StaffAdminSite.index_title` dit
maintenant « Tableau de bord », et la page a enfin un en-tete dans son
contenu — comme les deux autres.

### 4. Pas de retour depuis un module

« Lespass » etait du texte brut en haut de la page de module. C'est
desormais un lien `← Lespass` vers la page du domaine.

## Les finitions

### Une description sous chaque page

`DESCRIPTION_DES_PAGES` couvre les **54 pages** d'admin — reprises de la
maquette la ou elle en proposait, redigees pour le reste. Meme cle que
`CATEGORIE_DES_PAGES`, et un test verifie que les deux tableaux se couvrent
exactement : ni page oubliee, ni description orpheline.

**Une page absente du tableau s'affiche sans description.** On n'invente pas
de texte pour combler un trou.

### Les pastilles suivent leur categorie

Comme la maquette : vert pour Gerer, orange pour Configurer, bleu pour
Analyser. Les onglets etaient deja aux bonnes couleurs, pas les pastilles.
La categorie est posee sur la **liste** (`data-categorie`), pas sur chaque
ligne : toutes les lignes affichees appartiennent au meme onglet.

### « Tableau de bord » en tete du rail

Il etait enterre dans le groupe repliable « Configuration generale ». Un
groupe Unfold **sans titre** ne rend que ses liens : c'est ainsi qu'on obtient
une entree autonome, sans surcharge de gabarit.

### Le menu du lieu

Le menu qui s'ouvre sous le nom du lieu ne proposait qu'un lien vers
`tibillet.coop`. Il en compte maintenant trois :

```
🏠  Voir mon site                     le site public du lieu
✏️  Modifier l'identité de mon lieu   sa page de configuration
💎  TiBillet                          le site du projet
```

Les deux entrees qui concernent **le lieu** sont groupees, le lien externe
reste en dernier.

**« Voir mon site »** pointe sur `/`, un lien **relatif** : le site public
d'un lieu est la racine de **son** domaine. C'est donc juste pour tous les
lieux, sans fabriquer d'URL absolue ni lire le domaine principal. Verifie sur
les six lieux de la base : tous repondent en 200.

**« Modifier l'identité de mon lieu »** utilise `reverse_lazy` plutot qu'un
chemin ecrit a la main : si ce ModelAdmin est un jour desenregistre, on le
saura au demarrage plutot que par un lien mort.

**Pourquoi dans le menu et pas un bouton.** La maquette epingle un crayon a
droite du nom du lieu. Le reproduire imposait de forker
`unfold/helpers/navigation_header.html` : ce gabarit n'expose aucun bloc,
`element_classes` n'injecte que des classes, et un pseudo-element CSS ne peut
etre ni focusable ni cliquable de facon fiable. Ce second fichier forke ne
valait pas un clic economise — l'entree vit donc dans le menu qui s'ouvre
deja sous le nom.

## Une decision assumee

**Les domaines sans module actif restent masques du rail.** La maquette les
garde visibles, estompes. On garde notre comportement : le **tableau de bord
est la surface de decouverte** — il montre les 5 domaines avec « Aucun module
activé ici » — et le **rail est la surface de travail**. Un rail rempli
d'entrees mortes est du bruit. Unfold masque de toute facon un groupe sans
liens : afficher un domaine vide demanderait de lui inventer une entree.

## A tester / To test

| Verification | Attendu |
|---|---|
| Haut du rail, sur les 4 types de page | le nom du lieu + « Votre espace TiBillet », **identique partout** |
| Un lieu sans nom | affiche « TiBillet », jamais un rail sans titre |
| `/admin/` | titre « Tableau de bord », en-tete avec icone et sous-titre |
| `/admin/module/agenda/` | lien `← Lespass` en haut ; barre haute = « Lespass » |
| Onglets d'un module | pastilles **vertes** en Gérer, **oranges** en Configurer, **bleues** en Analyser |
| Lignes de pages | une phrase sous chaque nom |
| Rail | « Tableau de bord » seul en tete, sans chevron |
| Clic sur le nom du lieu | trois entrees : Voir mon site, Modifier l'identite, TiBillet |

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_admin_tableau_de_bord.py -v
```

**Deja verifie :** un seul `<h1>` sur les quatre types de page ; le nom du lieu
present partout, avec son repli ; les 54 descriptions couvrent exactement les
54 pages ; 32 tests au vert.

## Note pour plus tard — releve fait, pas traite

### Gains d'usage sur les changelists

1. **Menu « ··· » pour les actions de ligne.** Unfold les affiche toutes cote
   a cote : `EventAdmin` en a **cinq** (Dupliquer +1 jour / +1 semaine /
   +2 semaines / +1 mois, Archiver), `ProductAdmin` quatre. La maquette n'en
   montre que deux. **C'est le gain d'usage le plus net de tout le releve.**
2. **Placeholder de recherche tire de `search_fields`** : « Rechercher :
   email, prénom, nom de famille… » au lieu d'un « Rechercher » qui ne dit pas
   sur quoi. 17 classes ont un `search_fields`.
3. **`list_sections` repliables** : Unfold les affiche toujours depliees ; la
   maquette les replie derriere un chevron. 4 classes, dont `MembershipAdmin`.

### Ecarts d'architecture, hors restylage

4. **Le decoupage des reglages** : la maquette separe Identite du lieu,
   Reglages (fuseau, langue, devise), Paiement (Stripe) et Outils & connexions,
   la ou nous avons une page « Parametres » unique.
5. **Une page = plusieurs ModelAdmins empiles**, avec un badge de role. C'est
   l'idee structurelle la plus forte de la maquette ; nos onglets s'en
   approchent sans l'egaler.
6. **Les animations** : cascade d'apparition des cartes eteintes, et arrivee
   d'un module dans le rail. La seconde est incompatible avec notre bascule,
   qui recharge la page.

### Verifie comme mort — a ne jamais porter

Recherche, cloche et avatar de la barre haute (aucun gestionnaire ; Unfold
fournit les vrais) · `.socle`, `.rail-foot`, `.pip`, `.statepip`,
`toggleCard`, `.hint`, `SIMPLE.siteweb` (orphelins ; `goSimple('siteweb')`
leve une erreur) · les **cartes KPI** de « Ventes & comptabilité » (valeurs
codees en dur : 1 087 adherents, 24 380 €) · sa **carte d'export** (les
`<select>` sont des `<div>`, le bouton n'a pas de gestionnaire ; le projet a
deja de vrais exports CSV/PDF/FEC) · le ruban `.u-origin` et le tableau
« Correspondance des libelles » (documentation de passation : ils affichent
`admin_tenant.py:1617` et feraient fuiter des chemins de code).
