# Pages : aperçu en direct des blocs, fin du JSON, blocs rendus dans la fiche Page

## G. Suites de l'audit : scripts tiers, menu « + » à la demande, limites de validation / Audit follow-ups

**Origine :** point 2 de `CHANGELOG/a traiter/pages-apercu-admin-suites.md`, sorti de ce fichier le 2026-09-24.

**Quoi / What :**
1. **Scripts tiers.** Le document d'aperçu (fiche Bloc et fiche Page) ne charge plus formbricks, même s'il est configuré pour le lieu : `{% if formbricks_api_host and not apercu_admin %}` dans les 3 shells. C'était le seul script tiers. Les autres (htmx, bootstrap, panier…) sont locaux et ne font aucune requête au chargement.
2. **Menu « + » chargé à la demande.** Chaque barre de bloc embarquait le menu complet des modèles, soit ~25 liens par bloc (~1250 pour une page de 50 blocs). Désormais, la barre ne porte que l'URL de son menu. À la première ouverture, htmx fait un `hx-get` (`hx-trigger="toggle from:closest details once"`) vers la nouvelle vue `vue_menu_ajout` (route `pages_page_menu_ajout`), qui renvoie la liste pour cette position.
   - Le menu est découpé en deux gabarits : `_menu_modeles.html` (le conteneur) et `_menu_modeles_liens.html` (la liste). Le menu « + Ajouter un bloc en premier » de l'en-tête, seul de son espèce, reste construit tout de suite.
   - Le menu est réorienté (vers le haut s'il déborde) à l'ouverture, puis de nouveau quand sa liste arrive (`htmx:afterSettle`).
3. **Une seule source pour les limites.** `ApercuBlocSerializer` lit maintenant ses longueurs maximales et ses bornes sur le modèle `Bloc` (`_longueur_max_du_modele`, `_bornes_du_modele`), au lieu de les recopier. Elles avaient déjà divergé : `nombre_max` était limité à 1–1000 dans l'aperçu, contre 0–32767 à l'enregistrement. Aucune migration : rien n'a changé sur le modèle.

Au passage, les commentaires et le message affiché quand on ajoute un bloc sans page reprennent le libellé du bouton, renommé « + Ajouter un bloc en premier ».

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/{classic,V2,faire_festival}/shell.html` | formbricks absent quand `apercu_admin` |
| `pages/admin_apercu.py` | `vue_menu_ajout` ; URL du menu dans `_elements_avec_outils` ; limites du serializer lues sur le modèle |
| `pages/admin.py` | Route `pages_page_menu_ajout` ; libellé du bouton dans le message et les commentaires |
| `pages/templates/admin/pages/apercu/_menu_modeles.html`, `_menu_modeles_liens.html` (nouveau), `_outils_bloc.html` | Menu à la demande |
| `pages/static/pages/admin/apercu_page_outils.js` | Réorientation du menu à l'arrivée de sa liste |
| `tests/pytest/test_pages_admin_apercu.py` | 4 tests (menu à la demande et refus, limites identiques au modèle, pas de formbricks) |

### Tests à réaliser / How to test
1. Fiche Page avec plusieurs blocs : ouvrir le + d'un bloc. « Chargement des modèles… » apparaît brièvement, puis la liste. Choisir un modèle : la fiche d'ajout s'ouvre, avec le bloc placé juste après.
2. Même chose sur un bloc en bas de page : le menu s'ouvre vers le haut.
3. Fiche Bloc, bloc Liste : saisir 0 dans « Nombre d'éléments ». L'aperçu l'accepte, comme l'enregistrement.

### Migration
- **Migration necessaire / Migration required:** Non

---

## F. Corrections suite à l'audit djc / Fixes after the djc audit

**Quoi / What :** un agent relecteur (skill djc) a audité l'ensemble. Il n'a trouvé aucun problème bloquant. Corrections appliquées :

1. **Cache memcached** : délais d'attente et tolérance aux pannes. Voir la section B de `CHANGELOG/2026-09-23-cache-memcached-concurrence.md`.
2. **↑ ↓ ✕ atomiques.** `deplacer_bloc` et la suppression tournent dans une transaction. Les blocs de la page sont verrouillés (`select_for_update`, posé par `renumeroter_blocs` dès qu'une transaction est ouverte). Les boutons sont désactivés pendant la requête (`hx-disabled-elt`) : un double-clic ne laisse jamais deux blocs à la même position.
3. **Identifiant invalide.** « abc » à la place d'un UUID donnait une 500. `uuid_ou_none()` vérifie désormais la valeur avant toute requête : les fiches redirigent comme le fait l'admin, et les vues répondent 404. `object_id` passe aussi par `escapejs` dans `hx-vals`.
4. **Rien ne change en silence.** Un type d'info pratique inconnu (venu de l'API) reste affiché tel quel dans le select, et l'enregistrement le refuse avec un message. Les clés inconnues et les éléments illisibles sont signalés par un avertissement au-dessus de l'éditeur (`lignes_pour_affichage` rend une liste d'avertissements).
5. **Plafond** de 1000 lignes de galerie lues par l'aperçu (`TOTAL_FORMS` d'un POST forgé).
6. **JS.** Plus de variable globale (`window.…`) : le drapeau d'`apercu.js` devient un `data-*`, et la liste des fichiers choisis est calculée dans `hx-vals`. Les iframes déjà chargées avant le script sont prises en compte.
8. **Accessibilité.**
   - Le menu des modèles devient une liste de liens (plus de `role="menu"` sans navigation aux flèches), avec un survol en CSS.
   - Les menus se ferment avec Échap (le focus revient sur le bouton) ou au clic à côté.
   - Chaque barre d'actions est placée juste après son bloc dans le DOM : Tab passe du bloc à sa barre.
   - Plus d'`aria-live` sur l'aperçu, qui aurait annoncé chaque frappe.
9. **i18n** : le `placeholder` du lien d'une ressource est traduisible.
11. **Tests.**
    - Le test des combinaisons simule le skin au lieu de modifier la base, et vérifie le skin **réellement rendu** (il aurait détecté le bug memcached).
    - Nouveaux tests : utilisateur connecté non admin, sens inconnu, `vue_ligne_vide` refusée, identifiants invalides, verrou `FOR UPDATE`, type inconnu, plafond de la galerie, backend de cache et ses options.
12. **CHANGELOG** : la section A décrit l'état final.

10. **Commentaires périmés** : réécrits pour décrire l'état final (en-tête de `pages/admin.py`, docstrings de `PageAdmin` et `BlocAdmin`, message d'ajout sans page, `admin_apercu.py`, `editeur_items.py`).
    - `_ANCRE_ONGLET_BLOCS` → `_ANCRE_CONTENU_DE_LA_PAGE` et `_url_onglet_blocs_de_la_page` → `_url_contenu_de_la_page` : il n'y a plus d'onglet.
    - Le message « l'affichage choisi n'existe pas pour ce type » est retiré : avec le select « Modèle », ce cas n'arrive plus que par une requête forgée. Le garde-fou serveur reste.
13. **Doc « APPELE PAR / FLUX »** dans les 7 gabarits qui n'en avaient pas : `ligne_lieu.html`, `ligne_cartes.html`, `ligne_gps.html`, `_boutons_ligne_editeur.html`, `bloc/before.html`, `partials/apercu_iframe.html`, `partials/apercu_erreurs.html`.
    - `widgets/_boutons_ligne.html` est renommé `_boutons_ligne_editeur.html`. Ses ↑ ↓ ✕ ressemblent à ceux de `apercu/_outils_bloc.html`, mais ce ne sont pas des doublons. Les premiers déplacent une **ligne à l'intérieur d'un bloc**, dans le DOM, sans requête : rien n'est enregistré avant « Enregistrer ». Les seconds déplacent ou suppriment **un bloc entier**, par une requête écrite en base tout de suite. Chaque fichier renvoie maintenant à l'autre, et l'en-tête de `_outils_bloc.html` détaille toute sa chaîne d'appel, de `PageAdmin` jusqu'à `apercu_page_outils.js`.
    - Le gabarit d'une ligne n'est plus fabriqué (`f"ligne_{editeur}.html"`) mais lu dans la table `GABARIT_LIGNE_PAR_EDITEUR` (`pages/admin_widgets.py`) : une recherche du nom de fichier mène au code qui l'utilise.

Non traités, notés dans `CHANGELOG/a traiter/pages-apercu-admin-suites.md` : le point 7 (en-tête « N blocs » périmé après une action dans l'iframe) et les suggestions de l'audit.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/settings.py` | `connect_timeout`, `timeout`, `ignore_exc` |
| `pages/services.py` | Transaction et verrou dans `deplacer_bloc` / `renumeroter_blocs` |
| `pages/admin_apercu.py` | `uuid_ou_none`, suppression atomique, plafond de galerie |
| `pages/admin.py` | Identifiants vérifiés dans les deux `changeform_view` |
| `pages/editeur_items.py`, `pages/admin_widgets.py` | Avertissements au lieu d'un simple drapeau |
| `pages/templates/admin/pages/**` | `hx-disabled-elt`, menu en liste de liens, type inconnu, placeholder, `hx-vals` |
| `pages/static/pages/admin/apercu.js`, `apercu_page_outils.js` | Drapeau en `data-*`, iframes déjà chargées, fermeture des menus, barres après leur bloc |
| `tests/pytest/test_pages_admin_apercu.py` | 10 tests de plus, test des skins sans toucher à la base |

### Migration
- **Migration necessaire / Migration required:** Non

---

## E. Bouton « Retour à la page », skin parfois faux dans l'aperçu / "Back to the page" button, occasionally wrong skin

**Quoi / What :**
1. En haut de la fiche d'un bloc, au-dessus du formulaire, un bouton **« ← Retour à la page « X » »** ramène à la section « Contenu de la page ». Il est aussi présent à l'ajout, puisque la page vient de `?page=`. Si des modifications ne sont pas enregistrées, le navigateur demande confirmation (`warn_unsaved_form`).
2. **Aperçu parfois dans le mauvais style :** le problème ne venait pas de l'aperçu, mais du cache memcached sous requêtes simultanées. Voir `CHANGELOG/2026-09-23-cache-memcached-concurrence.md`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/admin.py` | `change_form_outer_before_template`, `page_du_bloc` / `url_retour_page` dans `changeform_view` |
| `pages/templates/admin/pages/bloc/retour_page.html` (nouveau) | Le bouton |
| `tests/pytest/test_pages_admin_apercu.py` | 2 tests |

### Migration
- **Migration necessaire / Migration required:** Non

---

## D. Emplacement d'image dans l'aperçu / Image placeholder in the preview

**Quoi / What :** quand on choisit une image dans la fiche d'un bloc, l'aperçu en direct montre tout de suite un **emplacement hachuré**, à la place et au format de la future image. Il est remplacé par la vraie image à l'enregistrement.
- Concerne l'image, la seconde image, la photo d'auteur (emplacement carré), et les lignes de l'encart « Images de galerie », y compris les références `![x](galerie:N)` d'un texte Markdown.
- La case « Effacer » d'une image enregistrée la retire de l'aperçu. Une ligne de galerie cochée « Supprimer » aussi.
- Les vidéos n'ont pas d'emplacement : une balise `<video>` ne peut pas afficher d'image.

**Comment / How :** l'aperçu n'envoie toujours pas les fichiers. Le navigateur envoie seulement la liste des champs qui ont un fichier choisi (`fichiers_choisis`, via `hx-vals`). Le serveur pose alors, sur le bloc **non enregistré**, un objet `ImageDeRemplacement` : il a `url`, `width` et `height` pour chaque variation StdImage, avec des tailles au bon format, si bien que la mise en page est celle de la vraie image. La galerie de l'aperçu est reconstruite depuis les lignes du formulaire, et posée dans le cache de `prefetch_related`.

/ A chosen image shows as a hatched placeholder in the live preview, sized like the real one. Files are still not uploaded: only the list of filled file inputs is sent.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/admin_apercu.py` | `ImageDeRemplacement`, `poser_les_images_de_remplacement`, reconstruction de la galerie |
| `pages/templates/admin/pages/bloc/apercu_panneau.html` | `hx-vals` : `fichiers_choisis` ; texte d'aide |
| `pages/static/pages/admin/image_a_venir.svg`, `image_a_venir_carree.svg` (nouveaux) | Images de remplacement |
| `tests/pytest/test_pages_admin_apercu.py` | 6 tests |

### Tests à réaliser / How to test
1. Bloc Carte : choisir une image sans enregistrer. L'aperçu montre l'emplacement hachuré au-dessus du titre. Enregistrer, rouvrir : la vraie image est là.
2. Citation : choisir une photo d'auteur, un emplacement rond ou carré apparaît.
3. Images › Galerie en grille : ajouter deux lignes dans l'encart et y choisir des fichiers : deux emplacements apparaissent. Cocher « Supprimer » sur une ligne enregistrée : elle disparaît de l'aperçu.
4. Bloc avec image enregistrée : cocher « Effacer », l'image disparaît de l'aperçu.

### Migration
- **Migration necessaire / Migration required:** Non

---

## C. Une seule iframe pour la fiche Page, « Modèle de bloc » / Single iframe for the Page form, "Block model"

**Quoi / What :**
1. **Fiche Page : une seule iframe.** Toute la page est rendue dans UN document (`vue_apercu_page`), dans la vraie grille du skin : les cartes voisines se rangent côte à côte, comme sur le site.
   - Chaque bloc est encadré, avec une barre compacte posée sur son bord haut : rang, modèle, ↑ ↓, ✎ Modifier, ✕, et + (ajouter après).
   - Les barres ne sont pas dans la grille. Un `<template>` invisible suit chaque bloc, et `apercu_page_outils.js` les copie dans un calque posé par-dessus. Le `<template>` est placé **après** le bloc, parce qu'une règle de `tb-blocs.css` teste le premier enfant de la grille.
   - ↑ ↓ ✕ font un `hx-post` depuis l'iframe. Le serveur répond `HX-Refresh`, et seule l'iframe se recharge : le formulaire de la page n'est pas touché.
   - Il n'y a plus de file de chargement : une page ne fait plus qu'une requête d'aperçu.
2. **« Modèle de bloc ».** Dans la fiche Bloc, un seul select remplace « Type de bloc » et « Affichage ». Il est groupé par type (`<optgroup>`), avec une valeur `TYPE:AFFICHAGE`.
   - Les champs `type_bloc` et `affichage` restent dans le formulaire, cachés : Alpine y recopie le modèle, pour que les autres champs s'affichent ou se cachent aussitôt.
   - La valeur **enregistrée** vient de `BlocAdminForm.clean()`, qui redécoupe le modèle : l'enregistrement ne dépend pas du JavaScript. L'aperçu en direct lit aussi le modèle.
   - Les menus « + » de la fiche Page proposent directement les modèles, et pré-remplissent la fiche d'ajout.
   - Le modèle de données, l'API et les gabarits ne changent pas : en base, c'est toujours type + affichage.

/ Whole page in one iframe with overlaid action bars; one "block model" select instead of type + affichage.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/admin_apercu.py` | `rendre_document_apercu` (1 bloc ou toute la page), `modeles_de_bloc`, `menu_d_ajout`, `vue_apercu_page`, réponses `HX-Refresh` ; retrait de la liste de blocs et de l'aperçu par bloc |
| `pages/admin.py` | Champ `modele`, `clean()`, type et affichage cachés, `PageAdmin.changeform_view` (menu « Ajouter en tête »), route `pages_page_apercu` |
| `pages/templates/pages/{classic,V2,faire_festival}/apercu.html` | Renommés depuis `apercu_bloc.html` ; boucle commune |
| `pages/templates/admin/pages/apercu/_blocs.html`, `_outils_bloc.html`, `_menu_modeles.html` (nouveaux) | Boucle des blocs, barre d'actions, menu des modèles |
| `pages/templates/admin/pages/page/blocs_de_la_page.html` | En-tête + une seule iframe ; `liste_blocs.html` et `_ajouter_bloc_ici.html` supprimés |
| `pages/static/pages/admin/apercu_page_outils.js` (nouveau) | Cadres et barres par-dessus les blocs |
| `pages/static/pages/admin/apercu.js` | File de chargement retirée |
| `pages/static/pages/admin/editeur_markdown.js` | Rafraîchit l'éditeur au changement de `id_modele` |
| `pages/README.md` | Modèle de bloc, barre d'actions |

### Tests à réaliser / How to test
1. Ouvrir une page avec 3 blocs « Carte » à la suite : ils sont côte à côte dans l'aperçu, chacun avec son cadre et sa barre.
2. ↓ sur un bloc : l'aperçu se recharge avec le nouvel ordre, et le formulaire de la page garde ses modifications non enregistrées.
3. ✕ : une confirmation s'affiche, puis le bloc disparaît de l'aperçu.
4. + sur le bloc 2 → « Images › Galerie en grille » : la fiche d'ajout s'ouvre avec ce modèle déjà choisi. Enregistrer : le bloc est en 3ᵉ position.
5. Fiche d'un bloc : changer « Modèle de bloc » de Carte à Citation. Les champs auteur apparaissent, le badge disparaît, et l'aperçu passe en citation.

### Migration
- **Migration necessaire / Migration required:** Non

---

## B. Champs inutiles cachés, page du bloc non modifiable / Useless fields hidden, block page locked

**Quoi / What :**
1. **Audit des champs.** Tous les gabarits de bloc des 3 skins ont été comparés au catalogue. Les champs du modèle correspondaient, avec trois exceptions, maintenant cachées :
   - **Éléments d'une section** : chaque clé n'apparaît que si le gabarit la rend. La **Frise** n'a plus de badge. Le **lien** n'apparaît que pour **Ressources**. Nouvelle table `CLES_ELEMENT_PAR_AFFICHAGE` dans `pages/blocs_catalogue.py`.
   - **Image et seconde image d'un LIEU** : seul le skin faire_festival les rend. Elles sont cachées pour les autres skins. Nouvelle table `SKINS_PAR_CHAMP_DU_TYPE`, et un champ caché `skin_du_site` qui porte le skin dans le scope Alpine.
   - **Page à lister (LISTE)** : n'apparaît que si la source est « sous-pages ».
2. **Page du bloc.** Il n'y a plus de select « Page » dans la fiche d'un bloc. Le champ est caché ; à la modification, il est `disabled`, et Django ignore toute valeur postée.
   - Un bloc s'ajoute donc toujours depuis sa page : sans `?page=` valide, le formulaire d'ajout renvoie vers la liste des pages avec un message.
   - « Enregistrer et ajouter un nouveau » reste dans la même page, juste après le bloc créé.

/ Fields a template never renders are hidden (sub-card keys per affichage, LIEU images outside faire_festival, LISTE source page). The block page is no longer a select.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/blocs_catalogue.py` | `CLES_ELEMENT_PAR_AFFICHAGE`, `SKINS_PAR_CHAMP_DU_TYPE` |
| `pages/admin.py` | Conditions skin et source ; `page` et `skin_du_site` cachés ; `add_view` exige `?page=` ; `response_add` pour « ajouter un nouveau » |
| `pages/admin_widgets.py` | Expressions Alpine par clé de sous-carte, tirées du catalogue |
| `pages/templates/admin/pages/widgets/ligne_cartes.html` | Chaque champ n'est montré que pour les affichages qui le rendent |
| `tests/pytest/test_pages_admin_apercu.py` | 8 tests de plus |

### Migration
- **Migration necessaire / Migration required:** Non

---

## A. Aperçu en direct, éditeurs de lignes, blocs rendus / Live preview, line editors, rendered blocks

> **Mise à jour :** cette section décrit l'état **final**. La fiche Page (point 3) et le choix du type ont été revus en C, les champs inutiles cachés en B, les emplacements d'image ajoutés en D, et l'audit a fait l'objet de corrections en F.

**Quoi / What :** l'admin du constructeur de pages (`pages/`) montre enfin ce qu'on construit.

1. **Fiche Bloc : aperçu en direct.** À droite du formulaire (au-dessus sous 1280 px), le bloc s'affiche avec le vrai thème du site. Il se met à jour environ 0,6 s après la dernière frappe, ou quand on change un select, l'éditeur riche (Trix) ou l'éditeur Markdown. Un bouton bascule la largeur Ordinateur / Mobile. Le bloc n'est **jamais enregistré** par l'aperçu.
2. **Plus de JSON.** `contenu` et `points_gps` ne se saisissent plus en JSON brut. On remplit des **lignes de champs**, avec les boutons + Ajouter, ↑, ↓ et ✕ :
   - LIEU : « Infos pratiques » (type, texte ; titre et lignes pour un transport), et « Points sur la carte » (latitude, longitude, nom). La virgule française est acceptée ;
   - SECTION en Équipe, Frise, Ressources ou Média + sous-cartes : « Éléments de la section » (titre, texte, badge, et lien pour Ressources).
3. **Fiche Page : la page rendue.** Sous le formulaire, la section « Contenu de la page » affiche toute la page dans **une seule iframe**, comme sur le site. Chaque bloc a une barre d'actions : ↑ ↓ (déplacement immédiat), Modifier, ✕ (avec confirmation), et + (ajouter un bloc juste après). On choisit un **modèle de bloc**, on arrive sur la fiche Bloc pré-remplie, et « Enregistrer » ramène à la page, le bloc à la bonne place. Détails en C.

/ Live block preview next to the form, line editors instead of raw JSON, rendered blocks with ↑ ↓ ✎ 🗑 and "+ Add a block here" on the Page form.

**Pourquoi / Why :** jusqu'ici, on remplissait un bloc sans voir le résultat, et certains blocs demandaient d'écrire du JSON à la main.

**Choix techniques :**
- Un seul moteur de rendu, `pages/admin_apercu.py:rendre_document_apercu()`. Il produit un document complet avec le skin du lieu (`pages/<skin>/apercu.html`, repli sur classic), sans navbar ni pied de page (drapeaux `embed` et `apercu_admin`). Le tout est affiché dans une iframe : le CSS du site ne se mélange pas à celui d'Unfold.
- L'aperçu en direct passe par `ApercuBlocSerializer` (DRF) et par `nettoyer_bloc()`, **la même fonction** que `BlocAdmin.save_model`. L'aperçu ne montre donc jamais un HTML que l'enregistrement aurait filtré.
- Les lignes sont postées avec des noms répétés (`contenu_lieu__texte`…). L'ordre du DOM est l'ordre enregistré (`pages/editeur_items.py`).
- L'onglet inline « Blocs » (`BlocInline`) est **supprimé** : son formset aurait renvoyé des positions périmées après un déplacement HTMX. Son rôle est repris par la nouvelle section.
- La fiche Page n'utilise qu'**une** iframe (C) : une seule requête d'aperçu par page. La cause des erreurs sous requêtes simultanées (cache memcached) est corrigée à part, voir `CHANGELOG/2026-09-23-cache-memcached-concurrence.md`.
- L'API v2 et le modèle ne changent pas : le stockage reste en JSON.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/admin.py` | `BlocInline` et `save_formset` retirés ; `get_urls` sur `PageAdmin` et `BlocAdmin` ; `change_form_outer_after_template` ; champs éditeurs dans `BlocAdminForm` ; `save_model` passe par `nettoyer_bloc`, `appliquer_editeurs_de_lignes` et gère `inserer_apres` ; `delete_model` et `response_delete` ramènent à la page |
| `pages/admin_apercu.py` (nouveau) | Vues d'aperçu (en direct, page entière), ↑ ↓, suppression, ligne vide ; `ApercuBlocSerializer` ; `nettoyer_bloc` |
| `pages/admin_widgets.py` (nouveau) | `EditeurLignesWidget` et `LignesField` |
| `pages/editeur_items.py` (nouveau) | Schémas, lecture du POST, nettoyage et validation des lignes |
| `pages/services.py` | `renumeroter_blocs`, `deplacer_bloc`, `inserer_bloc_apres` |
| `pages/templates/pages/{classic,V2,faire_festival}/apercu.html` (nouveaux) | Document d'aperçu, par skin (boucle commune : `admin/pages/apercu/_blocs.html`) |
| `pages/templates/pages/V2/shell.html` | En-tête du lieu masqué quand `apercu_admin` est posé |
| `pages/templates/admin/pages/bloc/before.html`, `apercu_panneau.html`, `partials/apercu_iframe.html`, `partials/apercu_erreurs.html` (nouveaux) | Panneau d'aperçu en direct |
| `pages/templates/admin/pages/page/blocs_de_la_page.html` (nouveau) | Section « Contenu de la page » : en-tête et iframe unique |
| `pages/templates/admin/pages/widgets/*.html` (nouveaux) | Éditeurs de lignes |
| `pages/static/pages/admin/apercu.js`, `apercu_bloc.css` (nouveaux) | Hauteur des iframes, fermeture des menus ; disposition en 2 colonnes |
| `pages/static/pages/admin/editeur_markdown.js` | Émet `input` à chaque frappe (pour l'aperçu) |
| `pages/README.md` | Guide utilisateur mis à jour (aperçu, éditeurs, plus de JSON) |
| `tests/pytest/test_pages_admin_apercu.py` (nouveau) | Tests de l'aperçu, des éditeurs, des modèles, des emplacements et des corrections d'audit |
| `tests/pytest/test_pages.py` | Test `save_formset` retiré ; tests d'inline et de `conditional_fields` adaptés |

### Tests à réaliser / How to test

**Automatiques :**
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pages_admin_apercu.py tests/pytest/test_pages.py tests/pytest/test_pages_api.py -q
```

**Manuels (admin lespass) :**
1. **Fiche Page.** Ouvrir une page qui a des blocs : la section « Contenu de la page » affiche la page entière dans une iframe, chaque bloc encadré avec sa barre d'actions.
   - ↑ / ↓ : l'ordre change, seule l'iframe se recharge.
   - ✕ : une confirmation s'affiche, puis le bloc disparaît.
   - « + » sur le bloc 1 → « Section › Carte » : on arrive sur la fiche Bloc, avec la page et le modèle pré-remplis. « Enregistrer » ramène à la page, et le bloc est en 2ᵉ position.
2. **SECTION / Carte.** Taper un titre : l'aperçu se met à jour. Changer le modèle de bloc : les champs et l'aperçu suivent. Basculer sur Mobile.
3. **TEXTE.** Taper dans l'éditeur Markdown : l'aperçu suit, et `![x](galerie:1)` affiche l'image de la galerie.
4. **LIEU.** Ajouter une info « Transport » (titre + deux lignes), un point GPS `43,5568` / `1,4835`, puis monter et supprimer des lignes. La carte et les infos de l'aperçu suivent. Enregistrer, rouvrir : les lignes sont bien là. Aucun JSON n'est visible.
5. **SECTION / Frise.** Ajouter trois étapes, puis réordonner avec ↑ ↓. Enregistrer et vérifier l'ordre sur le site public.
6. **Erreur.** Saisir une latitude « abc » : l'aperçu affiche « Aperçu indisponible » avec le message. Enregistrer affiche l'erreur sous le champ.
7. Refaire 1 et 2 avec les skins V2 et faire_festival (Site web personnalisé → Configuration du site).

**Vérification en base (LIEU) :**
```bash
docker exec -it lespass_django poetry run python manage.py tenant_command shell --schema=lespass
```
```python
from pages.models import Bloc
Bloc.objects.filter(type_bloc="LIEU").values_list("contenu", "points_gps")[:3]
```

**Nouvelles chaînes à traduire / New strings :** oui (gabarits `admin/pages/**` et `pages/editeur_items.py`). `makemessages` n'a pas été lancé.

### Migration
- **Migration necessaire / Migration required:** Non

### Plan B (non fait) / Plan B (not done)
Une édition directe dans le bloc est possible par-dessus ce travail. Il faudrait des attributs `contenteditable` et `data-champ` dans les gabarits de bloc (mode `apercu_admin`), plus un `postMessage` vers le formulaire parent. Coût : annoter environ 60 gabarits sur 3 skins.
