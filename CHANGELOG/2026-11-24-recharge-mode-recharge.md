# Caisse : « Mode recharge » sur la carte primaire / POS: "Top-up mode" on the primary card

**Date :** 2026-11-24
**Migration :** Oui (`laboutik/migrations/0003_carteprimaire_mode_recharge.py`, schéma + données)

## Resume / Summary
**Quoi / What :** Une nouvelle case « Mode recharge » sur la carte primaire du caissier.
Avec la case : la zone « Recharger » du check carte et les tuiles de recharge de la grille
sont visibles. Sans la case : les deux sont cachées, et le serveur refuse toute recharge
(paiement, « Offrir »). Une recharge n'entre jamais dans une commande de table. La case est
indépendante du mode gérant.
/ A new "Top-up mode" box on the cashier's primary card. With it, the check card "Top up"
zone and the grid's top-up tiles are shown. Without it, both are hidden and the server
refuses any top-up. A top-up never enters a table order.

**Pourquoi / Why :** Le droit de recharger venait d'un point de vente Cashless sur la carte,
et seulement pour le check carte : les tuiles et le serveur ne regardaient rien. On veut un
droit clair, porté par la carte du caissier, et appliqué par le serveur.
/ The right came from a Cashless POS on the card, for the check card only. It is now an
explicit right on the primary card, enforced by the server.

**Migration de données :** chaque carte primaire qui a un point de vente Cashless reçoit
`mode_recharge = True` (ces caissiers rechargent déjà par le check carte). Les autres cartes
restent sans le droit : un gestionnaire coche la case dans l'admin.
/ Every primary card with a Cashless POS gets top-up mode. Others do not.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/models.py` | `CartePrimaire.mode_recharge` |
| `laboutik/migrations/0003_carteprimaire_mode_recharge.py` | Nouveau : champ + droit donné aux cartes avec un point de vente Cashless |
| `Administration/admin/laboutik.py` | `mode_recharge` dans le formulaire, la liste et le filtre des cartes primaires |
| `laboutik/views.py` | `_carte_primaire_peut_recharger` (remplace `_carte_primaire_a_un_point_de_vente_cashless`) ; tuiles de recharge selon le droit (`_construire_donnees_articles(afficher_les_recharges=…)`) ; garde dans `_extraire_articles_du_panier` ; refus d'une recharge dans `ouvrir_commande` et `ajouter_articles` |
| `laboutik/templates/laboutik/partial/hx_card_recharge.html`, `hx_check_card.html` | Commentaires : nouvelle règle |
| `laboutik/management/commands/create_test_pos_data.py` | Carte primaire de démo en mode recharge |
| `tests/pytest/test_retour_carte_recharge.py` | Zone du check carte selon le mode recharge ; refus de `payer` et d'« Offrir » sans le droit |
| `tests/pytest/test_caisse_ecrit_la_vente.py` | Tuile de recharge visible / masquée ; tests de recharge avec une carte en mode recharge |
| `tests/pytest/test_caisse_une_ligne_par_article.py` | Recharge + adhésion dans le même panier ; panier refusé sans le droit ; recharge refusée dans une commande de table |
| `tests/pytest/test_hors_argent_offerts.py`, `test_pos_adhesion_fusion_wallet_fedow.py`, `test_rapatriement_carte_points_de_scan.py`, `test_pos_views_data.py` | Carte primaire en mode recharge pour les tests qui rechargent |

### Nouvelles chaînes i18n / New i18n strings
- `Mode recharge`
- `Autorise ce caissier à recharger les cartes cashless, depuis le check carte et depuis les tuiles de recharge.`
- `Cette carte primaire n'a pas le droit de recharger.`
- `Une recharge se fait au comptoir, pas depuis une commande.`

---

## Comment tester (a la main) / Manual test

### Test 1 — admin
1. Admin > Caisse > Cartes primaires : la colonne et le filtre « Mode recharge » sont là.
2. Ouvrir une carte : la case « Mode recharge » est à côté du mode gérant.

### Test 2 — carte sans le droit
1. Décocher « Mode recharge » sur la carte du caissier.
2. Ouvrir la caisse, point de vente Cashless : aucune tuile de recharge.
3. Check carte d'une carte client : pas de zone « Recharger ».

### Test 3 — carte avec le droit
1. Cocher « Mode recharge ».
2. Point de vente Cashless : les tuiles de recharge sont là. Mettre une recharge et une
   adhésion dans le même panier, payer : les deux passent.
3. Check carte : la zone « Recharger » est là, la recharge crédite la carte.

### Verifs DB / Playwright
- Après `migrate_schemas`, sur un lieu : le nombre de cartes avec `mode_recharge=True`
  égale le nombre de cartes qui ont un point de vente Cashless. En dev (`lespass`, le
  2026-11-24) : 1 carte sur 2, la carte de démo.
  ```python
  CartePrimaire.objects.filter(mode_recharge=True).count()
  CartePrimaire.objects.filter(points_de_vente__comportement="C").distinct().count()
  ```
- `make test ARGS="tests/pytest/test_retour_carte_recharge.py tests/pytest/test_caisse_une_ligne_par_article.py tests/pytest/test_caisse_ecrit_la_vente.py"`

### Déploiement / Deployment
La migration doit passer **avant** que le nouveau code serve des requêtes : pull →
`migrate_schemas` → `supervisorctl restart gunicorn daphne celery`.
