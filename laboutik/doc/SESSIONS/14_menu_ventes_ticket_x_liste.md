# Session 14 — Menu Ventes : Ticket X + liste des ventes

## CONTEXTE

Tu travailles sur `laboutik/` (POS Django + HTMX).
Lis `GUIDELINES.md` et `CLAUDE.md`. Code FALC. **Ne fais aucune opération git.**

Le `RapportComptableService` existe (Session 12). Cette session crée le menu "Ventes"
côté caisse tactile : Ticket X (récap' temps réel) et liste des ventes.

Le menu Ventes est accessible depuis le **burger menu** du header POS.
Il s'affiche dans la zone centrale (le panier reste visible à droite sur desktop).

## TÂCHE 1 — Lire l'existant

1. Lis `laboutik/templates/cotton/header.html` — le burger menu existant.
   Identifie où ajouter l'entrée "Ventes".

2. Lis `laboutik/reports.py` — le service de calcul. Tu vas l'appeler
   sans créer de RapportComptable en DB (c'est un Ticket X = lecture seule).

## TÂCHE 2 — Actions ViewSet

Dans `CaisseViewSet` (`laboutik/views.py`), ajoute :

### `recap_en_cours(GET)` — Ticket X

```python
@action(detail=False, methods=['GET'], url_path='recap_en_cours')
def recap_en_cours(self, request):
    """Ticket X — récap' sans clôture. 3 sous-vues : toutes/par_pv/par_moyen."""
    vue = request.GET.get('vue', 'toutes')
    # Utiliser RapportComptableService.generer_rapport_complet() sans sauvegarder
    # Rendre le template avec le rapport calculé
```

3 sous-vues dans le même partial (onglets HTMX `hx-get` avec `?vue=toutes|par_pv|par_moyen`) :
- `toutes` : synthèse agrégée tous PV
- `par_pv` : un bloc par PV avec ses totaux
- `par_moyen` : tableau croisé type × moyen

### `liste_ventes(GET)` — Historique

```python
@action(detail=False, methods=['GET'], url_path='liste_ventes')
def liste_ventes(self, request):
    """Liste paginée des LigneArticle du service en cours."""
    # Filtres : pv, moyen_paiement, operateur (GET params)
    # Pagination Django avec hx-trigger="revealed" pour scroll infini
```

### `detail_vente(GET)` — Détail d'une vente

```python
@action(detail=False, methods=['GET'], url_path='detail_vente')
def detail_vente(self, request):
    """Détail d'une LigneArticle : articles, total, moyen, actions."""
    ligne_uuid = request.GET.get('ligne_uuid')
```

## TÂCHE 3 — Templates

Crée les templates dans `laboutik/templates/laboutik/partial/` :

- `hx_ventes_menu.html` : sidebar/onglets de navigation (Récap, Liste, Fond, Sortie, Clôture)
- `hx_recap_en_cours.html` : 3 sous-vues avec onglets HTMX
- `hx_liste_ventes.html` : liste scrollable avec filtres, pagination HTMX
- `hx_detail_vente.html` : détail + boutons "Corriger moyen" et "Ré-imprimer"

CSS dans `laboutik/static/css/ventes.css` (pas inline).

## TÂCHE 4 — Intégrer dans le burger menu

Dans `cotton/header.html`, ajouter une entrée "Ventes" qui fait un `hx-get`
vers le menu ventes. Le contenu remplace la zone articles (comme le multi-tarif overlay).

## TÂCHE 5 — Tests

### pytest : `tests/pytest/test_menu_ventes.py`

- `test_recap_en_cours_toutes_caisses` : retourne 200, contient les totaux
- `test_recap_en_cours_par_pv` : retourne 200, un bloc par PV
- `test_liste_ventes_paginee` : retourne 200, contient les LigneArticle
- `test_liste_ventes_filtre_moyen` : filtre par moyen → résultats corrects
- `test_detail_vente` : retourne 200, contient les infos de la LigneArticle

### Playwright

Ajouter dans un nouveau spec ou étendre les tests existants :
- Ouvrir burger menu → cliquer "Ventes" → le menu s'affiche
- Cliquer "Récap'" → les totaux sont visibles
- Cliquer "Liste" → les ventes s'affichent

## VÉRIFICATION

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_menu_ventes.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -v -k "laboutik"
docker exec lespass_django poetry run pytest tests/e2e/ -v -s
```

### Critère de succès

- [ ] Menu "Ventes" accessible depuis le burger menu
- [ ] Ticket X affiche les 3 sous-vues (toutes, par PV, par moyen)
- [ ] Liste des ventes scrollable avec filtres
- [ ] Détail d'une vente avec boutons actions
- [ ] CSS dans un fichier séparé (pas inline)
- [ ] 5+ tests pytest verts
- [ ] Tous les tests existants passent
