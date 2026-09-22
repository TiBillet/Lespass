# Panier (Commande) — hub

> Panier d'achat multi-types (billets, adhésions, ressources) : `PanierSession`
> (`BaseBillet/services_panier.py`), `CommandeService` (`BaseBillet/services_commande.py`),
> `PanierMVT` (`BaseBillet/views.py`), modèle `Commande`.

| Chantier | Fichier | Status |
|---|---|---|
| 01 | [`SPEC.md`](SPEC.md) — tests de toute la chaîne du panier, parité avec/sans panier, bugs prouvés par tests rouges, E2E, couverture (`make coverage`) | Fait le 2026-09-21 (code relu par Opus, avis Fable), C27 compris ; décisions restantes au §10 du SPEC |

Contexte historique :
- `CHANGELOG/panier.md` — workflow, bugs connus, « À tester » (Antoine).
- Anciens tests (18-19/04/2026) sur la branche `V2`, lisibles par `git show V2:<chemin>` :
  `tests/pytest/test_panier_*.py`, `test_commande_*.py`, `tests/e2e/test_panier_flow.py`.
- Chantier voisin : `TECH_DOC/SESSIONS/REMBOURSEMENT/` (remboursements avec et sans panier).
- Idée future : `TECH_DOC/SESSIONS/TODO/` (panier en base).

Pour ajouter un chantier : créer `CHANTIER-02-<slug>.md` et l'ajouter au tableau.
