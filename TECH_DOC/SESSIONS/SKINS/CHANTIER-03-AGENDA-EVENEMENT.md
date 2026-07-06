# CHANTIER-03 — Agenda + détail événement → `pages/<skin>/vues/`

**Statut :** en cours (2026-07-04).
**Objectif :** porter les vues agenda et détail événement des deux skins vers
`pages/<skin>/vues/`, brancher les 5 sites de rendu de `EventMVT` sur
`gabarit_skin()` (y compris la méthode `embed`, aujourd'hui codée en dur sur
reunion), et poser les premiers **blocs nommés** du contrat de skin.
**Zéro changement visible** (une exception assumée, cf. « embed » ci-dessous).

## Lot 1 — Déplacements + bascule des vues (iso-rendu)

### Mapping reunion → classic
| Source `reunion/views/event/` | Cible | Rôle |
|---|---|---|
| `list.html` | `pages/classic/vues/agenda.html` | vue |
| `retrieve.html` | `pages/classic/vues/evenement.html` | vue |
| `partial/list.html` | `pages/classic/vues/agenda_liste.html` | partiel HTMX (recherche/filtres p.1) |
| `partial/list_append.html` | `pages/classic/vues/agenda_liste_suite.html` | partiel HTMX (« voir plus ») |
| `partial/carousel.html` | `pages/classic/partials/carrousel_evenements.html` | habillage |
| `partial/accordion.html` | `pages/classic/partials/evenement_accordeon.html` | habillage |
| `partial/geoloc.html` | `pages/classic/partials/evenement_geoloc.html` | habillage |
| `partial/volunteers.html` | `pages/classic/partials/evenement_benevoles.html` | habillage |
| `partial/booking.html` | `pages/classic/partials/reservation_declencheur.html` | habillage (le tunnel lui-même est déjà `commun/offcanvas/reservation.html`) |
| `partial/search.html` | `commun/agenda/filtres.html` | **chrome/logique** (plan §3.2) |

### Mapping faire_festival
| Source `faire_festival/views/event/` | Cible |
|---|---|
| `list.html` | `pages/faire_festival/vues/agenda.html` (extends → `pages/faire_festival/shell.html` en direct) |
| `retrieve.html` | `pages/faire_festival/vues/evenement.html` (idem) |
| `partial/list_append.html` | `pages/faire_festival/vues/agenda_liste_suite.html` |

ff n'a PAS d'équivalent `agenda_liste.html` : aujourd'hui le fallback
`get_skin_template` sert déjà la version reunion → demain le fallback
`gabarit_skin` sert la version classic. Comportement identique.

### Bascule `BaseBillet/views.py` (5 sites, EventMVT)
| Ligne | Avant | Après |
|---|---|---|
| 2254 | `get_skin_template("views/event/partial/list_append.html")` | `gabarit_skin("vues/agenda_liste_suite.html")` |
| 2256 | `…partial/list.html` | `gabarit_skin("vues/agenda_liste.html")` |
| 2321 | `…views/event/list.html` | `gabarit_skin("vues/agenda.html")` |
| 2332 | `render(request, "reunion/views/event/list.html", …)` (embed EN DUR) | `gabarit_skin("vues/agenda.html")` |
| 2463 | `…views/event/retrieve.html` | `gabarit_skin("vues/evenement.html")` |

**Changement assumé (embed)** : la méthode `embed` rendait TOUJOURS le look
reunion, même pour un tenant en faire_festival. Avec `gabarit_skin`, l'iframe
embed suit désormais le skin du tenant (les guards `{% if not embed %}` des
shells masquent navbar/footer dans les deux cas). C'est la correction de
l'incohérence relevée au gros check.

### Suppressions
Les originaux sont SUPPRIMÉS après bascule (aucune autre référence — vérifié :
seuls les 5 sites de views.py + les includes croisés du cluster lui-même).
`formbricks.html`, `reservation_ok.html` et `wizard/*` (rendus en dur, pages
fonctionnelles) restent dans reunion — CHANTIER-06.

## Lot 2 — Blocs nommés (contrat de skin, iso-bytes)
- `agenda.html` : blocs `agenda_entete`, `agenda_carrousel`, `agenda_filtres`,
  `agenda_liste` autour des sections existantes.
- `evenement.html` : blocs `evenement_entete`, `evenement_media`,
  `evenement_description`, `evenement_reservation`, `evenement_complements`.
- Extraction `pages/classic/partials/carte_evenement.html` si (et seulement si)
  les markups de `agenda_liste` et `agenda_liste_suite` sont identiques (à
  diff-er) ; sinon reporté au CHANTIER-07 avec note.
- Les noms de blocs sont FIGÉS dès ce chantier (décision 2).

## Vérification
Snapshots avant/après par lot (attendu : identique au bit près — les chemins
de templates ne sont pas visibles dans le HTML), check, pytest event/pages,
E2E complets, parcours Chrome (agenda, détail, réservation, recherche/« voir
plus » HTMX, embed sur les 2 skins) + les 3 flux du goal (Stripe 4242,
recharge tirelire, vente QR).

## Hors périmètre
Adhésions (C4), home/infos/réseau (C5), wizard/formbricks/reservation_ok (C6),
suppression de `get_skin_template` (C8).
