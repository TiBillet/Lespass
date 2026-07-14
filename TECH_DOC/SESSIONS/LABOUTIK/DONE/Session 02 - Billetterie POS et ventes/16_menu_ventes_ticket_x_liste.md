# Session 16 — Menu Ventes : Ticket X + liste des ventes

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django + HTMX).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune operation git.**

Le `RapportComptableService` existe (session 12). Cette session cree le menu "Ventes"
cote caisse tactile : Ticket X (recap temps reel) et liste des ventes.

Le menu Ventes est accessible depuis le **burger menu** du header POS.
Il s'affiche dans la zone centrale (le panier reste visible a droite sur desktop).

## TACHE 1 — Lire l'existant

1. Lis `laboutik/templates/cotton/header.html` — le burger menu existant.
   Identifie ou ajouter l'entree "Ventes".

2. Lis `laboutik/reports.py` — le service de calcul. Tu vas l'appeler
   sans creer de ClotureCaisse en DB (c'est un Ticket X = lecture seule).

## TACHE 2 — Actions ViewSet

Dans `CaisseViewSet` (`laboutik/views.py`), ajoute :

### `recap_en_cours(GET)` — Ticket X

3 sous-vues (onglets HTMX `hx-get` avec `?vue=toutes|par_pv|par_moyen`) :
- `toutes` : synthese agregee tous PV
- `par_pv` : un bloc par PV avec ses totaux
- `par_moyen` : tableau croise type x moyen

### `liste_ventes(GET)` — Historique

Liste paginee des LigneArticle du service en cours.
Filtres : pv, moyen_paiement, operateur (GET params).
Pagination HTMX avec `hx-trigger="revealed"` pour scroll infini.

### `detail_vente(GET)` — Detail d'une vente

Detail d'une LigneArticle : articles, total, moyen, actions.

## TACHE 3 — Templates

Cree les templates dans `laboutik/templates/laboutik/partial/` :

- `hx_ventes_menu.html` : sidebar/onglets de navigation
- `hx_recap_en_cours.html` : 3 sous-vues avec onglets HTMX
- `hx_liste_ventes.html` : liste scrollable avec filtres, pagination HTMX
- `hx_detail_vente.html` : detail + boutons "Corriger moyen" et "Re-imprimer"

CSS dans `laboutik/static/css/ventes.css` (pas inline).

## TACHE 4 — Integrer dans le burger menu

Dans `cotton/header.html`, ajouter une entree "Ventes" qui fait un `hx-get`
vers le menu ventes. Le contenu remplace la zone articles.

## TACHE 5 — Tests

### pytest : `tests/pytest/test_menu_ventes.py`

- `test_recap_en_cours_toutes_caisses` : retourne 200, contient les totaux
- `test_recap_en_cours_par_pv` : retourne 200, un bloc par PV
- `test_liste_ventes_paginee` : retourne 200, contient les LigneArticle
- `test_liste_ventes_filtre_moyen` : filtre par moyen → resultats corrects
- `test_detail_vente` : retourne 200, contient les infos de la LigneArticle

## VERIFICATION

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_menu_ventes.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
```

### Critere de succes

- [ ] Menu "Ventes" accessible depuis le burger menu
- [ ] Ticket X affiche les 3 sous-vues (toutes, par PV, par moyen)
- [ ] Liste des ventes scrollable avec filtres
- [ ] Detail d'une vente avec boutons actions
- [ ] CSS dans un fichier separe (pas inline)
- [ ] 5+ tests pytest verts
- [ ] Tous les tests existants passent
