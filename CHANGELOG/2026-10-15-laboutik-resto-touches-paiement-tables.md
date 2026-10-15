# LaBoutik : touches de paiement et boutons Tables du mode restaurant / Restaurant payment keys and Tables buttons

**Date :** 2026-10-15
**Migration :** Non

## Resume / Summary

**Quoi / What :**
- **Touches de paiement du clavier du bas** (Espèces, CB, Chèque, Cashless, Mixte,
  Offrir) : elles suivent le même chemin que VALIDER du ticket. Le moyen choisi part
  avec `#addition-form` dans un champ `moyen_prefere`. `moyens_paiement()` garde toutes
  ses vérifications (stock, monnaie, client à identifier…). Ensuite, la tuile de ce moyen
  se déclenche seule (`hx-trigger="load, click"`) : confirmation, attente de carte ou
  répartition. Si le moyen n'est pas proposé pour ce panier, la liste normale s'affiche.
  Le champ est retiré après la réponse : VALIDER du ticket rouvre toujours la liste.
- **Touche VALIDER** du clavier : identique à VALIDER du ticket.
- **Offrir** : grisé si la carte primaire n'est pas en mode gérant.
- **Ticket de caisse / Envoi prépa** : grisés, pas encore branchés (TODO dans le gabarit).
- **Boutons Tables** (en-tête, entrée TABLES du menu burger, bouton « Table » du bas) :
  rechargent le point de vente sans `id_table`, donc affichent la grille des tables.
- Le message « aucun article » est inclus dans l'écran restaurant (touches sur panier vide).

/ Bottom keypad payment keys reuse the VALIDER path and pre-pick a method; the
matching tile fires on display. Tables buttons reload the POS without id_table.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `moyens_paiement()` lit `moyen_prefere` (liste blanche) et le passe au gabarit |
| `laboutik/templates/laboutik/partial/_tuiles_paiement.html` | Tuile du moyen choisi : `hx-trigger="load, click"` |
| `laboutik/templates/laboutik/partial/win_bottom_right.html` | Touches branchées, `restoPayerAvec()`, Offrir/Ticket/Envoi prépa grisés |
| `laboutik/templates/laboutik/partial/win_bottom_left.html` | Bouton « Table » → grille des tables |
| `laboutik/templates/cotton/header.html` | Bouton Tables et entrée TABLES du menu branchés, `data-testid` |
| `laboutik/templates/laboutik/views/restaurant_interface.html` | Inclut `partial/no_articles.html` |
| `laboutik/static/css/win_bottom_right.css` | Style `:disabled` des touches |
| `tests/pytest/test_resto_touches_et_tables.py` | Nouveau : 5 tests |

---

## Comment tester (a la main) / Manual test

Prérequis : un point de vente avec `service_direct = False`, `accepte_commandes = True`.

1. Ouvrir la caisse sur ce PV, « Continuer sans table », ajouter un article.
2. Touche **Espèces** → la liste des moyens s'ouvre, la confirmation espèces par-dessus.
   Valider → vente encaissée.
3. Touche **Chèque** sur un PV qui refuse le chèque → la liste des moyens s'affiche seule.
4. Touche **Cashless** → attente de carte. Touche **Mixte** → écran de répartition.
5. Après une touche annulée, VALIDER du ticket → la liste, sans rien déclencher.
6. Panier vide + touche → message « aucun article ».
7. **Tables** dans l'en-tête, dans le menu burger, et le bouton « Table » du bas →
   spinner puis grille des tables. Depuis « Commande table X », même résultat.

### Verifs automatiques
`poetry run pytest tests/pytest/test_resto_touches_et_tables.py` (5 tests).
Sélecteurs : `resto-touche-*`, `header-tables`, `menu-tables`, `resto-action-table`.
