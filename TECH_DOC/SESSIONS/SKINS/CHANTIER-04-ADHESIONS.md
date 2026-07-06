# CHANTIER-04 — Adhésions → `pages/<skin>/vues/adhesions.html`

**Statut :** en cours (2026-07-04).
**Objectif :** même recette que le CHANTIER-03, pour les adhésions : porter la
vue liste des deux skins vers `pages/<skin>/vues/adhesions.html`, basculer les
rendus de `MembershipMVT` sur `gabarit_skin()` (y compris `embed`, codé en dur
sur reunion), déplacer les partiels HTMX du tunnel vers `commun/adhesion/`, et
poser les blocs du contrat.

## Pièges HTMX chargés (tests/PIEGES.md)
- **9.8** : `form.html` et les templates de statut sont des PARTIELS purs (pas
  d'extends, pas de `<html>`) chargés par HTMX dans `#offcanvas-membership` —
  ils doivent le RESTER (aucun extends ajouté, contenu intact, ids intacts).
- **9.23** : le formulaire renvoie `HX-Redirect` — ne fonctionne que chargé
  depuis la page liste (contexte HTMX). Ne rien changer aux attributs hx-*.
- `#subscribePanel` / `#offcanvas-membership` : ids du contrat, jamais renommés.

## Mapping
| Source | Cible | Nature |
|---|---|---|
| `reunion/views/membership/list.html` | `pages/classic/vues/adhesions.html` | vue skinnable + blocs |
| `faire_festival/views/membership/list.html` | `pages/faire_festival/vues/adhesions.html` (extends shell ff) | vue skinnable |
| `reunion/views/membership/form.html` | `commun/adhesion/form.html` | partiel HTMX (tunnel) |
| `…/404.html` | `commun/adhesion/404.html` | partiel HTMX |
| `…/free_confirmed.html` | `commun/adhesion/free_confirmed.html` | partiel HTMX |
| `…/pending_manual_validation.html` | `commun/adhesion/pending_manual_validation.html` | partiel HTMX |
| `…/already_has_membership.html` | `commun/adhesion/already_has_membership.html` | partiel HTMX |

Noms de fichiers du tunnel conservés (diff minimal, cross-refs JS intactes).

**Ne bougent PAS (C6 — pages fonctionnelles)** : `formbricks.html` et les 3
`payment_already_pending/done/link_invalid.html` (elles étendent `base_template`
→ héritent déjà du shell ; ce sont des pages autonomes ouvertes depuis les
emails de lien de paiement).

## Bascule `BaseBillet/views.py` (MembershipMVT)
- `get_skin_template("views/membership/list.html")` → `gabarit_skin("vues/adhesions.html")`
- `embed` : `render(request, "reunion/views/membership/list.html")` EN DUR →
  `gabarit_skin("vues/adhesions.html")` (même correction assumée qu'au C3 :
  l'iframe suit désormais le skin du tenant).
- 7 rendus en dur `reunion/views/membership/{form,404,free_confirmed,
  pending_manual_validation,already_has_membership}.html` → `commun/adhesion/…`.

## Blocs du contrat (FIGÉS) — `pages/classic/vues/adhesions.html`
`adhesions_entete` (titre) / `adhesions_tunnel` (include du chrome
`commun/offcanvas/adhesion_tunnel.html`) / `adhesions_grille` (boucle produits).
(`carte_adhesion` en partial séparé : reporté au C7 si la grille ff diverge trop
— à trancher à l'exécution.)

## Vérification
Snapshots avant/après (0 diff de contenu attendu), embed 200 ×2 skins,
tests pytest membership + E2E complets **via agent Sonnet** (consigne
mainteneur), parcours Chrome : tunnel adhésion des 2 skins + les 3 flux du
goal (vente Stripe 4242 — qui traverse exactement ce chantier —, recharge
tirelire, vente QR).
