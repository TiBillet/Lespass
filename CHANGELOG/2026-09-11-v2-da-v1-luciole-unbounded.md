# Skin V2 : Direction artistique v1 (Luciole / Unbounded) / V2 skin: art direction v1

**Date :** 2026-09-11
**Migration :** Oui — `pages/migrations/0003_alter_bloc_affichage.py`

## Resume / Summary
**Quoi / What :** le skin V2 adopte la maquette `TEMP-tibillet-lespass-main/`
(commit 49d31d0 « Direction artistique v1 »).
- Nouvelle palette TiBillet (letchi, zanana, chouchou, loséyan, violet) et dégradés.
- **La couleur est réservée aux gestes TiBillet** (carte, solde, recharge,
  action principale) ; le contenu d'un lieu (tags, filtres, frise…) passe en
  encre et papier.
- Polices auto-hébergées : Luciole pour le texte, Unbounded pour les grands titres.
- Barre utilisateur unique (plus de double navbar), menu du lieu branché sur
  `main_nav`, cartes événement « date à cheval » (une ou deux dates).
- Pages refaites : événement (nouvelle maquette), adhésions, Mon espace et
  toutes ses sous-pages.
- Trois nouveaux affichages de bloc SECTION pour une page « Qui sommes-nous » :
  EQUIPE, FRISE, RESSOURCES.

/ The V2 skin adopts the DA v1 mockup: new palette, colour reserved for TiBillet
gestures, self-hosted Luciole/Unbounded fonts, single user bar, rebuilt event,
membership and account pages, three new SECTION displays for an "About us" page.

**Pourquoi / Why :** nouvelle direction artistique livrée le 08/09. Le V2 était
construit sur la 1re version de la maquette (27/08, Lora/Inter, vert).

## Choix d'implementation / Implementation notes
- **Fusion à trois voies du CSS** : `V2.css` = ancienne maquette + ajouts V2 ;
  on a appliqué le diff de la maquette avec `git merge-file` (2 conflits,
  résolus à la main). Les ajouts V2 (carte Leaflet, page Réseau) sont conservés.
- **Pont Bootstrap** en tête de `V2.css` : les variables `--bs-*` et `--tb-*`
  pointent sur les jetons de la DA. Panneaux latéraux, accordéons et blocs CMS
  prennent le style sans être réécrits.
- **Un seul composant carte** `cotton/V2/event_card.html`, deux modes :
  `mode="event"` (agenda, accueil) et `mode="resa"` (Mon agenda).
- **Modules de Mon espace** en `<details>` natifs : repliables sans JS, au
  clavier. Le glisser-déposer de la maquette n'est pas porté (ordre non enregistré).
- **Sections sans données masquées** en `{% comment %} V2-HERE` (aucun faux
  contenu en prod). Liste complète : `CHANGELOG/a traiter/v2-da-v1-points-laisses-de-cote.md`.
- **Pagination de l'agenda réparée** en V2 : `#event_list` + `#paginator` en
  dernière case de la grille, nouvelle `vues/agenda_liste.html` V2.
- **Nouveaux affichages SECTION** : ils lisent `contenu` (liste d'items texte),
  comme MEDIA_ET_CARTES. Gabarits V2 **et** classic : classic est le repli de
  `templates_bloc`, sans lui les skins reunion/faire_festival planteraient.
- Tous les `data-testid` existants sont conservés (58 valeurs avant, 105 après,
  aucune perdue).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/static/V2/css/V2.css` | Fusion DA v1, pont Bootstrap/tb-blocs, ajouts (barre utilisateur, menu du lieu, cartes, page événement, compte, Pages CMS, nouveaux blocs) |
| `pages/static/V2/fonts/` (nouveau) | Luciole (4 woff2, CC BY 4.0) + Unbounded variable latin (SIL OFL) + licences |
| `pages/static/pages/css/tb-blocs.css` | Styles classic des affichages EQUIPE / FRISE / RESSOURCES |
| `pages/templates/pages/V2/partials/navbar.html` | Barre utilisateur unique (Mon espace / connexion, langue, contact, panier) |
| `pages/templates/pages/V2/tenant_header.html` | Menu du lieu = Accueil + boucle `main_nav` (menus déroulants), site web du lieu |
| `pages/templates/pages/V2/partials/footer.html` | Boutons `btn--grad-chaud/calme/frais`, contact en `<button>` |
| `pages/templates/cotton/V2/event_card.html` | Composant unique, modes `event` / `resa`, multi-jours |
| `pages/templates/cotton/V2/membership_card.html` | `.offer-card` seule (doublon Bootstrap retiré) |
| `pages/templates/pages/V2/vues/accueil.html` | Cartes via le composant, sections sans données masquées |
| `pages/templates/pages/V2/vues/agenda.html` | Tags neutres, recherche `#search_form`, `#event_list`, pagination |
| `pages/templates/pages/V2/vues/agenda_liste.html` (nouveau), `agenda_liste_suite.html`, `vues/partials/agenda_voir_plus.html` (nouveau) | Pagination HTMX de l'agenda |
| `pages/templates/pages/V2/vues/evenement.html` | Nouvelle maquette : `.event-hero`, infos pratiques, bénévoles, hôte |
| `pages/templates/pages/V2/partials/reservation_declencheur.html`, `evenement_benevoles.html` | Restyle DA (ids et testids conservés) |
| `pages/templates/pages/V2/vues/adhesions.html` | En-tête de page, grille d'offres, lieux voisins en `service-card` |
| `pages/templates/pages/V2/vues/compte/account_base.html` (nouveau) | Base des pages compte V2 (plus de `<main>` imbriqué) |
| `pages/templates/pages/V2/vues/compte/index.html` | Mon espace : carte, solde, `btn--signature`, raccourcis, modules (responsabilités, agenda, services, ressources) |
| `pages/templates/pages/V2/vues/compte/*.html`, `membership/*`, `partials/*` | Sous-pages du compte au style DA |
| `pages/templates/pages/{V2,classic}/partials/bloc_section_{equipe,frise,ressources}.html` (nouveaux) | Nouveaux affichages SECTION |
| `pages/templates/pages/classic/vues/compte/membership/memberships.html` | Correctif : chemin d'include (slash manquant, le gabarit plantait) |
| `pages/models.py` | Constantes + choix EQUIPE / FRISE / RESSOURCES |
| `pages/blocs_catalogue.py` | Affichages permis et champs rendus des 3 nouveaux affichages |
| `pages/migrations/0003_alter_bloc_affichage.py` (nouveau) | `AlterField` des choix de `Bloc.affichage` |
| `BaseBillet/views.py` | `MyAccount.list` : la boucle des adhésions portait sur la liste vide (« Mes services » toujours vide) ; `logger.error` de debug retiré |

### Migration
- **Migration necessaire / Migration required :** Oui
- `pages/migrations/0003_alter_bloc_affichage.py` (changement de choix seulement,
  pas de SQL). Commande : `docker exec lespass_django poetry run python manage.py migrate_schemas`

---

## Comment tester (a la main) / Manual test

Prérequis : un tenant en skin V2 (Admin → Configuration du site → skin « Thème V2 »).
Vérifier chaque page à 375, 768 et 1280 px de large : pas de défilement
horizontal, boutons et badges sur une seule ligne.

### Test 1 — Structure commune
1. Barre du haut : liseré multicolore, « Mon espace » avec initiales (ou « Log in »
   si anonyme → ouvre le panneau de connexion), langue, contact, panier.
2. En-tête du lieu : logo ou initiale, nom (lien vers l'accueil), adresse, site
   web s'il est renseigné ; menu = Accueil + entrées de `main_nav` (Pages CMS,
   Réseau, Agenda, Adhésions). Mobile : le menu défile à l'horizontale.
3. Footer : fond gris froid, trois boutons en dégradé, « Contact » ouvre le panneau.

### Test 2 — Accueil et agenda
1. Accueil : carte Leaflet, 3 prochains événements (date posée sur la couture
   image/texte), aucune section « initiatives » ni « services ».
2. Agenda : clic sur un tag → pastille noire active ; recherche + Entrée ;
   « Load more events » ajoute les cartes **dans** la grille.
3. Un événement sur plusieurs jours affiche deux pastilles reliées par une flèche.

### Test 3 — Page événement
1. Bandeau : image, tags, dates, titre Unbounded, fiches Quand / Où / Organisé par.
2. Bouton de réservation (testid `booking-open-panel`) → panneau `#bookingPanel`.
   `?openbookingPanel=1` l'ouvre au chargement.
3. Événement avec actions bénévoles : section bénévoles, accordéon, postuler.

### Test 4 — Adhésions
1. Grille d'offres ; « Subscribe » (testid `membership-open-<uuid>`) ouvre le tunnel.
2. Lieux fédérés en cartes neutres avec lien « Voir les adhésions ↗ ».

### Test 5 — Mon espace et sous-pages
1. Carte TiBillet (dégradé nuit), solde en dégradé chaud, « Recharger » en
   bouton signature → formulaire de recharge.
2. Modules repliables au clavier (Tab + Entrée) : Mes responsabilités (lien
   back-office, classe `btn-admin-tenant`), Mon agenda (cartes « Voir le billet »),
   Mes services (adhésions de tous les lieux).
3. Compte neuf : invitations « Parcourir l'agenda » / « Voir les adhésions ».
4. Sous-pages : porte-monnaie (tableau des monnaies au défilement, historique
   au clic), adhésions (arrêt du prélèvement), réservations (annulation avec
   confirmation SweetAlert, affichage du billet), carte, préférences, pointeuse.

### Test 6 — Page « Qui sommes-nous » (Pages CMS)
1. Appliquer la migration, puis créer une Page avec des blocs SECTION en
   affichage EQUIPE, FRISE et RESSOURCES. `contenu`, par exemple :
   `[{"titre": "2019", "texte": "Premières réunions"}, {"titre": "2022", "texte": "Ouverture du lieu"}]`
2. Cocher « afficher le sommaire » : le sommaire prend le style de la maquette,
   l'entrée active suit la lecture.
3. RESSOURCES avec `"url": "javascript:alert(1)"` → **aucun** lien posé.
4. Même page en skin classic : les trois blocs s'affichent (repli classic).

### Verifs automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py -q`
- `docker exec lespass_django poetry run pytest tests/pytest/ -q`
- E2E avec `lespass` en V2 : `test_reservation_validations`, `test_membership_account_states`,
  `test_membership_recurring_cancel`, `test_event_quick_create_duplicate`, `test_login`.
  `test_theme_language` échoue en V2 (pas de mode sombre dans la DA v1, connu).
