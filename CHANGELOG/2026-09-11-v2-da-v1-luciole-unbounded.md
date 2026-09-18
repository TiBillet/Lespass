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
  pointent sur les jetons de la DA. Panneaux latéraux et accordéons prennent le
  style sans être réécrits.
- **LE PIÈGE À CONNAÎTRE — un jeton du socle se surcharge sur `.tb-page`, jamais
  sur `:root`.** Le pont ci-dessus ne portait **rien** pour les pages CMS, et
  c'est structurel : `tb-blocs.css` déclare ses jetons sur `.tb-page, .tb-jetons`
  (bloc lignes 37-97), donc sur l'élément lui-même. Or une propriété
  personnalisée se résout **élément par élément** : l'ancêtre le plus proche qui
  la déclare gagne, quelles que soient la spécificité et l'ordre de chargement
  des feuilles — l'héritage depuis `:root` ne sert qu'aux éléments sans
  déclaration plus proche. Une surcharge sur `:root` est donc toujours perdante
  pour `.tb-page` et ses descendants. Conséquences trouvées en production :
  **sept** sélecteurs s'affichaient en serif système (étiquettes du sommaire et
  du menu, questions de FAQ, titres de cartes et de sous-cartes, liens
  précédent/suivant, citation) et l'accent des blocs valait `var(--bs-primary)`,
  le bleu `#0d6efd` de Bootstrap, au lieu du letchi. Toutes les surcharges de
  jetons du socle sont désormais regroupées dans un seul bloc `.tb-page` de la
  section « PAGE CMS », avec cette explication. C'est aussi pourquoi
  `--tb-sticky-top` y fonctionnait, lui, dès le départ.
  / A base token must be overridden on `.tb-page`, never on `:root`: custom
  properties resolve per element, so the nearest declaring ancestor wins.
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
| `pages/static/V2/css/V2.css` | Fusion DA v1, pont Bootstrap/tb-blocs, ajouts (barre utilisateur, menu du lieu, cartes, page événement, compte, Pages CMS, nouveaux blocs) ; **correctif** `--tb-sticky-top: 5rem` (le sommaire passait sous la barre utilisateur) ; sommaire de page déplacé à gauche comme la maquette ; sections et entrées du sommaire numérotées par compteurs CSS ; **correctif de cadrage** `--tb-gouttiere: 0px` + `--tb-largeur-max: 100%` (la page CMS était 128 px plus étroite que le bandeau du lieu et décalée de 64 px) ; **correctif des jetons** `--tb-police-titre` / `--tb-accent` / `--tb-accent-contraste` déplacés de `:root` vers `.tb-page` ; étiquette du sommaire alignée sur `.toc__label` |
| `pages/static/pages/css/tb-blocs.css` | **Correctif du socle** : la règle qui replie le sommaire entre 62rem et 75rem n'était pas conditionnée au mode trois colonnes, contrairement aux trois règles voisines — une page à sommaire sans menu latéral n'affichait plus que l'étiquette « SOMMAIRE » au-dessus d'une colonne vide. Corrigé pour **tous les skins** (le défaut existait aussi en classic) |
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
| `pages/models.py` | Constantes + choix EQUIPE / FRISE / RESSOURCES ; constantes + choix `VERTICAL` / `HORIZONTAL` du bloc LIEU |
| `pages/blocs_catalogue.py` | Affichages permis et champs rendus des 3 nouveaux affichages ; **bloc LIEU** : `affichage` ajouté à ses champs, `AFFICHAGES_PAR_TYPE["LIEU"] = ("VERTICAL", "HORIZONTAL")`, défaut `VERTICAL`. **Volontairement aucune entrée dans `CHAMPS_PAR_AFFICHAGE`** : les deux dispositions consomment les mêmes champs, et `image`/`image_secondaire` doivent rester proposées puisque le skin faire_festival les rend |
| `pages/migrations/0004_alter_bloc_affichage.py` (nouveau) | `AlterField` des choix de `Bloc.affichage` (changement de CHOICES seulement). **Aucune migration de données** : les blocs LIEU existants gardent un `affichage` vide et retombent sur `bloc_lieu.html`, donc leur aspect ne change pas |
| `pages/templates/pages/V2/partials/bloc_lieu_horizontal.html` (nouveau) | Affichage HORIZONTAL du bloc LIEU : carte Leaflet en bandeau `.about-banner` pleine largeur, infos pratiques en rangée de `.info-card` (`.grid--3`). Les trois `data-testid` de l'affichage vertical sont conservés |
| `pages/templatetags/pages_tags.py` | Tag `cartes_infos_pratiques` : découpe la liste plate de `contenu` en cartes étiquetées (un item `badge` ouvre une carte). En Python parce que le langage de gabarit ne sait pas accumuler une liste |
| `pages/management/commands/charger_site_lespass.py` | Page « Qui sommes-nous ? » de démo (`_construire_qui_sommes_nous`) : les 3 nouveaux affichages + bloc LIEU en affichage **HORIZONTAL**, intertitres en blocs TEXTE pour alimenter le sommaire |
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
1. Appliquer la migration, puis charger la page de démo :
   `docker exec lespass_django poetry run python manage.py charger_site_lespass --no-skin`
   (sans `--no-skin`, la commande repasse le tenant en skin classic). La page est
   servie sur `/qui-sommes-nous/` et figure dans le menu du lieu. Elle enchaîne :
   intro, « Le lieu » (bloc LIEU), « Le collectif » (EQUIPE), « L'histoire »
   (FRISE), « Le projet », « Les ressources » (RESSOURCES), appel à l'action.
2. Le sommaire affiche les cinq entrées de la maquette, et l'entrée active suit
   la lecture. Les intertitres sont des titres Markdown (`##`) portés par des
   blocs TEXTE : `table_des_matieres` ne lit QUE ceux-là — le champ `titre` d'un
   bloc SECTION n'entre pas dans le sommaire (c'est pourquoi les blocs EQUIPE /
   FRISE / RESSOURCES ont un `titre` vide, sans quoi l'intertitre sortirait deux fois).
   Au-dessus de 62rem, le sommaire est la **colonne de gauche** (la maquette le
   met à gauche, le socle `tb-blocs.css` à droite) ; en dessous, il repasse dans
   le flux, replié, sous le titre.
   **Défiler jusqu'en bas : le haut du sommaire ne doit JAMAIS passer sous la
   barre utilisateur** (régression corrigée par `--tb-sticky-top: 5rem` ; le
   socle déclare 1,5rem et documente qu'un skin à entête fixe doit le relever,
   ce que V2 ne faisait pas — `faire_festival.css` le fait, lui, à 6,5rem).
   Les sections et les entrées du sommaire sont numérotées `01`→`05` et les deux
   numérotations **concordent** : même compteur sur les mêmes titres `##`
   (rendus en `<h3>`, le moteur démotant d'un niveau). Les numéros viennent de
   compteurs CSS, pas des données : réordonner un bloc dans l'admin les
   renumérote sans rien casser, et `sommaire_actif.js` continue de relier les
   entrées aux titres par leur ancre. Ils n'apparaissent que sur les pages qui
   affichent un sommaire.
3. **Alignement** (critère principal) : à 1280 px et plus, le bord gauche du fil
   d'Ariane, du titre, du texte et des cartes tombe sur la **même verticale** que
   la carte du bandeau du lieu. Comparer avec `/` et `/event/`. La colonne passe
   de 1088 à 1216 px. Un bloc bannière touche les deux bords de l'écran, sans
   bande de papier ni ascenseur horizontal. En mobile, la marge latérale passe de
   36 à 16 px : c'est voulu, elle rejoint celle de l'agenda et du bandeau.
4. **Polices** : l'étiquette du sommaire, celle du menu latéral, les questions de
   FAQ, les titres de cartes et de sous-cartes, les liens précédent/suivant et la
   citation de témoignage passent **du serif système à Luciole**. Seuls le titre
   de page et les titres de blocs restent en Unbounded (deux polices, pas trois).
   Vérifier dans l'inspecteur (« Rendered fonts ») que la fonte rendue est bien
   *Luciole*, et que `Luciole-Bold.woff2` répond 200 après `collectstatic`.
5. **Accent** : filets au-dessus des titres, badges du bloc LIEU, bordure des
   sous-cartes, bande du bloc CTA et bordures des boutons de bloc passent **du
   bleu Bootstrap `#0d6efd` au letchi**.
6. **Sommaire entre 992 et 1200 px** : réduire la fenêtre lentement de 1400 à
   900 px ; la liste reste visible tant que l'étiquette est là, et à aucune
   largeur une colonne ne montre l'étiquette seule. Vérifier **aussi** une page
   qui a un menu latéral **et** un sommaire (là, le sommaire doit bien repasser
   replié dans le flux : garde-fou du socle, conservé) et **une page CMS en skin
   classic**, puisque le correctif touche `tb-blocs.css`, partagé par tous les
   skins.
7. **Grille de cartes** (`.tb-grille`) : le nombre de colonnes peut passer de 3 à
   4 avec l'élargissement — attendu. Cinq colonnes signaleraient un
   `--tb-largeur-boite` mal résolu.
8. **Bloc LIEU en affichage HORIZONTAL** (après `migrate_schemas`, la migration
   `0004` ajoutant les deux choix) : la section « Le lieu » montre un bandeau
   pleine largeur portant une **vraie carte Leaflet** — là où la maquette n'a
   qu'un dégradé, qui sert ici de fond d'attente le temps que les tuiles
   arrivent — puis **trois cartes d'infos en rangée**. Les items `badge` de
   `contenu` en sont les intitulés : « Adresse », « Horaires » et « Nous
   joindre » ouvrent donc une carte chacun. Vérifier que la carte est bien
   découpée par les coins arrondis du bandeau (c'est le rôle de
   l'`overflow: hidden` ajouté) et que la rangée passe à 2 colonnes sous
   1100 px, puis à 1 sous 720 px.
   **Bascule** : repasser le bloc en affichage « Infos à gauche, carte à droite »
   dans l'admin doit rendre exactement la disposition historique. Et le bloc LIEU
   de la page d'accueil, lui, n'a pas été touché : il garde un `affichage` vide
   et s'affiche comme avant — c'est la preuve qu'aucune migration de données
   n'était nécessaire.
   **Skin classic** : un bloc en HORIZONTAL y retombe sur la disposition
   verticale (aucun gabarit classic n'a été écrit pour cet affichage). Pas de
   page cassée, mais le choix y est sans effet.
3. RESSOURCES avec `"url": "javascript:alert(1)"` → **aucun** lien posé.
4. Même page en skin classic : les trois blocs s'affichent (repli classic).

### Verifs automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_pages_api.py -q`
- `docker exec lespass_django poetry run pytest tests/pytest/ -q`
- E2E avec `lespass` en V2 : `test_reservation_validations`, `test_membership_account_states`,
  `test_membership_recurring_cancel`, `test_event_quick_create_duplicate`, `test_login`.
  `test_theme_language` échoue en V2 (pas de mode sombre dans la DA v1, connu).
