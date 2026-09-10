# Navigation de l'admin par domaines / Domain-based admin navigation

**Date :** 2026-09-08
**Migration :** Non

## Resume / Summary

**Quoi / What :** la sidebar de l'admin passe d'une liste de ~16 sections a plat
(environ 60 liens) a une arborescence **Domaine -> Module** : 5 domaines
(Lespass, Laboutik, Lerezo, Lekontrib, Lemachines) contenant 14 modules, soit
14 liens. Chaque module a desormais **sa propre page**, qui liste ses admins
rangees sous une rangee d'onglets : **Gerer / Configurer / Analyser**.
/ The admin sidebar moves from ~16 flat sections (about 60 links) to a
Domain -> Module tree: 5 domains, 14 modules, 14 links. A module's pages
become its tabs.

**Pourquoi / Why :** c'est l'arborescence proposee par la maquette
`TEMP-tibillet-admin-main/`. Le point de depart etait favorable : le code
regroupait **deja** les sections en 6 « familles » via un champ `_order`.
Il n'y avait donc pas de structure a inventer, seulement a recaler sur les
5 domaines.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/dashboard.py` | `+ DOMAINES`, `+ CATEGORIES`, `+ CATEGORIE_DES_PAGES` ; `_domaine`/`_order`/`_icone`/`_slug` sur les sections ; `+ page_de_module`, `+ _sections_par_slug`, `+ _page_d_accueil_du_module`, `+ _categoriser_les_pages`, `+ _categorie_active` ; `_domaine`/`_order`/`_icone` sur les 16 sections ; `get_sidebar_navigation` renommee en `_construire_sections_modules` ; `+ get_sidebar_navigation` (repli par domaine) ; `+ _regrouper_sections_par_domaine`, `+ _module_en_lien` ; `+ get_tabs`, `+ _carte_des_liens_vers_modeles`, `+ _onglets_hors_modules` |
| `Administration/admin_tenant.py` | re-export de `get_tabs` |
| `TiBillet/settings.py` | `TABS` : liste statique -> `"Administration.admin_tenant.get_tabs"` |
| `Administration/admin/site.py` | `+ get_urls()` — route `/admin/module/<slug>/` |
| `Administration/templates/admin/module_page.html` | **neuf** — la page d'un module |
| `tests/pytest/test_admin_page_de_module.py` | **neuf** — 6 tests |
| `tests/pytest/test_module_newsletter_activation.py` | 2 tests de sidebar adaptes au nouveau contrat, `+ 1` test de rangement |
| `static/css/tibillet-admin.css` | `+` style de la page de module (`.tb-pagelist`, `.tb-prow-*`) |

Aucun `ModelAdmin`, aucun modele n'a ete touche.

## La contrainte, et le choix qui en decoule

La maquette veut **trois** niveaux : Domaine -> Module -> pages. La sidebar
d'Unfold n'en a que **deux** : un groupe, et ses liens. Un groupe sans liens
est meme purement masque (`has-[ol]:has-[li]:block` dans `app_list.html`), donc
on ne peut pas se contenter d'ajouter un sur-titre de domaine.

**Choix retenu : groupe = DOMAINE, lien = MODULE.** C'est la forme la plus
fidele au rail de la maquette.

Sa consequence directe : **les pages d'un module quittent la sidebar.** Elles
doivent donc reapparaitre ailleurs, sinon 46 pages deviendraient inatteignables.
D'ou les onglets.

> **Ce choix est a l'essai.** Il change la navigation en profondeur : on passe
> d'un clic a deux (choisir le module, puis l'onglet). Si cela s'avere penible
> a l'usage, deux replis existent, et **seule `_regrouper_sections_par_domaine()`
> serait a reecrire** — la construction des sections, elle, n'a pas bouge :
>
> - **repli partiel** : garder les domaines mais y remettre toutes les pages a
>   plat (le groupe Lespass contiendrait une vingtaine de liens) ;
> - **repli complet** : revenir aux modules comme groupes, en recalant
>   simplement les familles sur les 5 domaines.

## Comment ca marche / How it works

### Une seule source pour la sidebar ET les onglets

`_construire_sections_modules(request)` est l'ancienne `get_sidebar_navigation`,
simplement renommee. Elle produit les sections brutes — une par module — et
**n'a pas ete modifiee** : toute la logique de permissions, de modules
desactives et de `_safe_rev` est intacte.

Deux fonctions la consomment :

- `get_sidebar_navigation()` replie ces sections en groupes-domaines ;
- `get_tabs()` en derive la barre d'onglets de chaque module.

C'est ce partage qui garantit qu'une page ajoutee a un module apparait aux deux
endroits **sans double saisie**.

### Les onglets ne sont pas un confort

Ils sont la seconde moitie de la navigation. `UNFOLD["TABS"]` est donc passe
d'une liste statique a un chemin pointe. Verifie dans `unfold/sites.py` :
`_get_config` fait passer la valeur par `_get_value`, qui importe et appelle
un chemin pointe — exactement comme `SIDEBAR.navigation`.

Les deux barres historiques (Formbricks, et Parametres/Cles API/Webhooks) sont
conservees telles quelles dans `_onglets_hors_modules()`.

### Detail : retrouver le modele derriere une URL

Les sections stockent une URL deja calculee (`/admin/BaseBillet/event/`), alors
qu'Unfold attend un nom de modele (`BaseBillet.event`) pour savoir sur quelles
pages afficher une barre d'onglets. `_carte_des_liens_vers_modeles()`
reconstruit la correspondance a partir des modeles reellement enregistres dans
l'admin, plutot que de decouper la chaine d'URL — un nom d'application peut
contenir un souligne (`fedow_core`, `root_billet`), le decoupage serait faux.

## La page d'un module

La sidebar n'affiche qu'UN lien par module. Ce lien ne mene plus a une
changelist au hasard, mais a **la page du module** : une rangee d'onglets
Gerer / Configurer / Analyser, et sous l'onglet ouvert, la liste de ses
admins — une ligne par page.

C'est exactement le parcours de la maquette :
**Lespass > Agenda > Gerer** donne trois lignes (Evenements, Reservations,
Billets).

### Ou ca vit

- **Route** : `/admin/module/<slug>/`, ajoutee par
  `StaffAdminSite.get_urls()` (`Administration/admin/site.py`). L'import de
  la vue y est fait **dans la methode** : un import en tete de fichier serait
  circulaire, l'admin n'etant pas encore prete a ce moment-la.
- **Vue** : `page_de_module()` dans `dashboard.py`.
- **Gabarit** : `Administration/templates/admin/module_page.html`.

L'onglet ouvert vient de `?onglet=...`. Le choix est fait **cote serveur** :
aucun JavaScript, donc rien a casser. Une valeur inconnue retombe sur le
premier onglet plutot que de lever une erreur.

Chaque module porte un identifiant stable (`_slug`) : `agenda`, `caisse`,
`tireuses`... C'est lui qu'on retrouve dans l'URL.

**Exception** : un module qui n'a qu'UNE page (Kiosk) pointe directement sur
elle. Traverser une page intermediaire qui n'affiche qu'une seule ligne
serait de la friction pure.

### Les onglets sur les pages d'admin

Sur une changelist, la barre d'onglets d'Unfold affiche **la meme rangee** de
categories, chacune ramenant a la page du module. On peut donc passer d'une
categorie a l'autre sans repasser par la sidebar.

L'etat actif est calcule dans `get_tabs()`, et non par Unfold : ses liens
pointent vers la page de module, jamais vers la changelist affichee, donc sa
comparaison d'URL ne trouverait jamais rien. Unfold respecte notre valeur — il
ne recalcule `active` que si la cle est absente (`unfold/sites.py`).

**Aucun gabarit d'Unfold n'est surcharge.** Une version intermediaire de ce
travail surchargeait `tab_list.html` pour dessiner deux rangees ; le passage a
la page de module l'a rendue inutile, et elle a ete supprimee.

### Une couleur par categorie

La maquette donne une couleur a chaque famille (`.tab.g` / `.tab.c` / `.tab.a`
dans son `style.css`) :

| Onglet | Pastille | Ouvert : soulignement et texte |
|---|---|---|
| Gerer | vert de marque `#1d9e75` | `--color-primary-600` / `-800` |
| Configurer | orange `#EF9F27` | `--color-orange-500` / `-700` |
| Analyser | bleu `#378ADD` | `--color-blue-500` / `-700` |

Ces valeurs ne sont pas re-saisies dans le CSS : elles viennent des rampes
`orange` et `blue` deja declarees dans `UNFOLD["COLORS"]`. Une seule source
de verite pour la palette.

**On s'accroche au lien, pas a une classe** :
`#tabs-items a[href*="onglet=configurer"]`. Le lien `?onglet=...` est fabrique
par notre code (`get_tabs` et `page_de_module`), il est donc stable. Surtout,
la regle vaut alors AUSSI sur les changelists, ou c'est Unfold qui dessine la
barre et ou il ne rend que le libelle — aucun attribut auquel se raccrocher
autrement. Les barres historiques (Parametres / Cles API / Webhooks) n'ont pas
`onglet=` dans leurs liens : elles ne sont pas touchees.

La pastille est un pseudo-element `::before` : aucun balisage a ajouter, donc
elle apparait des deux cotes sans toucher au gabarit d'Unfold.

Verifie sur les trois surfaces : page de module, changelist d'un module,
barre historique.

### Le rangement des pages

`CATEGORIE_DES_PAGES` associe chaque page a sa categorie. La cle est le modele
(`"BaseBillet.event"`), ou l'URL brute pour les pages qui ne sont pas des
changelists.

**Une page absente du tableau tombe dans « Gerer ».** C'est volontaire : une
page oubliee reste visible plutot que de disparaitre.

Une categorie sans page ne produit pas d'onglet : Newsletter, qui n'a que des
reglages, n'affiche que « Configurer ».

Repartition constatee, tous modules actives :

| Module | Pages | Gerer | Configurer | Analyser |
|---|---|---|---|---|
| agenda | 9 | 3 | 6 | — |
| caisse | 7 | 2 | 3 | 2 |
| tireuses | 11 | 2 | 4 | 5 |
| ressources | 6 | 1 | 5 | — |
| monnaies | 4 | 2 | 1 | 1 |
| federation | 3 | 2 | 1 | — |
| terminaux | 3 | 3 | — | — |
| site-web / adhesion / financement | 2 | 1 | 1 | — |
| inventaire | 2 | 1 | — | 1 |
| newsletter | 2 | — | 2 | — |
| kiosk | 1 | 1 | — | — |

## Correctif : le lien d'un module sortait de l'admin

**Symptome :** cliquer sur « Tireuses connectees » quittait l'admin, et l'admin
des tireuses devenait inatteignable.

**Cause :** `_module_en_lien()` prenait bêtement la **premiere** page du module.
Or la premiere page des tireuses est un lien vers `/controlvanne/kiosk/`, une
page du **site public**, pas de l'admin.

**Correctif :** `_page_d_accueil_du_module()` retient desormais la premiere page
qui commence par `/admin/`, et ne retombe sur la premiere page de la liste que
si le module n'en a aucune.

Verifie sur les 21 liens de la sidebar, tous modules actives : **aucun ne sort
de l'admin**. « Tireuses connectees » ouvre maintenant sur
`/admin/controlvanne/tireusebec/`.

## Verification de non-regression

Le risque numero un de ce chantier, c'est qu'une page devienne inatteignable.
Le controle a ete fait, tous modules actives :

| | |
|---|---|
| Pages avant regroupement | 62 |
| Pages atteignables apres (sidebar + pages de module) | 62 |
| **Pages perdues** | **0** |
| Pages rangees dans exactement une categorie | 62 / 62 |

Ce controle est desormais **automatise** :
`tests/pytest/test_admin_page_de_module.py::test_aucune_page_d_admin_ne_devient_inatteignable`.
C'est le test le plus important du chantier — sans lui, une page retiree d'une
categorie disparaitrait sans bruit.

## Rangements qui relevent d'un choix

- **Ressources** (`module_booking`) est absent de la maquette. Range dans
  **Lespass** : c'est une reservation faite par le public, comme l'agenda.
- **Blog** et **Reseaux sociaux**, presents dans la maquette sous Lespass,
  **n'existent pas encore** dans le projet.
- **Configuration generale** (en tete), **Ventes & comptabilite** et
  **Configuration racine** (en pied) restent des entrees autonomes avec tous
  leurs liens, conformement au rail de la maquette.

## A tester / To test

### 1. La sidebar

Ouvrir `/admin/` sur un lieu ou **tous** les modules sont actifs. Attendu :

```
    Configuration generale     (Tableau de bord, Parametres, Comptes)
--- Lespass                    (Site web, Agenda, Adhesion, Ressources, Newsletter)
--- Laboutik                   (Caisse & Restaurant, Inventaire)
--- Lerezo                     (Federation, Monnaies & cashless)
--- Lekontrib                  (Financement participatif)
--- Lemachines                 (Kiosk, Tireuses, Terminaux)
--- Ventes et comptabilite     (Rapports, Lignes comptables)
--- Configuration racine       (En attente, Tenants, Domaines iframe)
```

Puis sur un lieu ou peu de modules sont actifs : les domaines sans aucun
module actif doivent **disparaitre entierement** (et non apparaitre vides).

### 2. La page d'un module — le point critique

Cliquer sur chaque module de la sidebar. Attendu : **une** rangee d'onglets,
puis la liste des admins de l'onglet ouvert.

| Verification | Attendu |
|---|---|
| `/admin/module/agenda/` | onglets **Gerer** (actif) et Configurer ; 3 lignes : Evenements, Reservations, Billets |
| `/admin/module/agenda/?onglet=configurer` | **Configurer** actif ; 6 lignes (Produits, Carrousel, Codes promo, Tags, Adresses, Scan) |
| `/admin/module/tireuses/` | 3 onglets : Gerer (2), Configurer (4), Analyser (5) |
| `/admin/module/newsletter/` | un **seul** onglet, Configurer — ce module n'a que des reglages |
| Kiosk (module a une seule page) | pas de page intermediaire : on arrive **droit** sur la changelist |
| `/admin/module/nimportequoi/` | **404**, sans casser l'admin |
| `?onglet=nimportequoi` | retombe sur le premier onglet, sans erreur |

Puis, depuis une changelist (`/admin/BaseBillet/event/`) : **une seule**
rangee d'onglets, chacun ramenant a la page du module.

Verifier aussi que le badge d'adhesions recentes est bien remonte sur le lien
« Adhesion » de la sidebar.

### 3. Permissions

Se connecter avec un gestionnaire **non-root** : le groupe « Configuration
racine » doit disparaitre, et aucun onglet ne doit pointer vers une page
interdite.

### 4. Tests automatiques

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_module_newsletter_activation.py -v
docker exec lespass_django poetry run pytest tests/e2e/test_admin_*.py -v -s
```

Les tests E2E naviguent dans l'admin : ce sont eux qui diront si un parcours
s'appuyait sur un lien de sidebar qui n'existe plus.

**Deja verifie :** `manage.py check` propre ; 0 page perdue sur 62 ;
6 tests de `test_module_newsletter_activation.py` au vert.

## Suites / Next steps

1. **Le sous-titre des domaines** (« La vitrine du lieu et tout ce qui parle a
   votre public. ») est present dans `DOMAINES` mais pas affiche : la sidebar
   d'Unfold n'a pas d'emplacement pour lui.
3. **Blog et Reseaux sociaux** restent a creer, cote Lespass.
