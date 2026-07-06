# CHANTIER-05 — Accueil / infos pratiques / le faire festival / réseau

> **CORRECTIF 2026-07-05** : les migrations `vues/infos_pratiques.html` et
> `vues/le_faire_festival.html` décrites ci-dessous étaient du **code mort** —
> leurs routes avaient déjà été retirées de `BaseBillet/urls.py` au profit de
> pages CMS homonymes (catch-all `/<slug>/`). Vues et gabarits supprimés le
> 2026-07-05 (cf. CHANGELOG). Seuls `vues/accueil.html` et `vues/reseau.html`
> restent actifs.

**Statut :** terminé (2026-07-04), corrigé le 2026-07-05.
**Objectif :** dernières vues skin-aware de `get_skin_template` → `pages/<skin>/vues/`.

## Mapping
| Source | Cible | Note |
|---|---|---|
| `reunion/views/home.html` | `pages/classic/vues/accueil.html` | fallback historique quand aucune page CMS d'accueil |
| `faire_festival/views/home.html` | `pages/faire_festival/vues/accueil.html` | extends shell ff |
| `faire_festival/views/infos_pratiques.html` | `pages/faire_festival/vues/infos_pratiques.html` | **n'existe QUE côté ff** — la version reunion n'a jamais existé ; la résolution échoue à l'identique pour un tenant reunion (comportement préservé) |
| `faire_festival/views/le_faire_festival.html` | `pages/faire_festival/vues/le_faire_festival.html` | idem, ff only |
| `reunion/views/federation/explorer.html` | `pages/classic/vues/reseau.html` | ff n'en a pas → fallback classic (identique à aujourd'hui) |

## Bascule `BaseBillet/views.py` (4 sites)
`get_skin_template("views/home.html")` → `gabarit_skin("vues/accueil.html")` ;
`…infos_pratiques…` → `gabarit_skin("vues/infos_pratiques.html")` ;
`…le_faire_festival…` → `gabarit_skin("vues/le_faire_festival.html")` ;
`…federation/explorer…` → `gabarit_skin("vues/reseau.html")`.
Après ce chantier, **plus AUCUN appelant de `get_skin_template`** (la ligne 138
est un exemple de docstring) → suppression au C8.

## Vérification
Snapshots home ×2 skins + /network/ (explorer) + /infos_pratiques/ (chantefrein),
0 diff de contenu attendu. Tests via agent Sonnet groupés avec C6.
