# Caisse : l'écran « Ventes » reprend la forme de la maquette, chiffres lus dans le rapport unique / Register: the "Sales" screen goes back to the mock-up layout, figures read in the single report

**Date :** 2026-10-05
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- L'écran « Ventes » de la caisse (`GET /laboutik/caisse/recap-en-cours/`) reprend la structure, les titres et la mise en page de la maquette (version d'Antoine, commit `e3f6e7ed`) : chiffres du haut (Total + TVA par taux, fond de caisse + mouvements du tiroir + solde, Sortie de caisse / Imprimer Ticket X / Clôturer toutes les caisses), mini-tableaux « Par moyen de paiement », « Par point de vente », « TVA » (HT, TVA, TTC), « Offerts (hors argent) », « Non monétaire (hors argent) », et trois historiques : « Historique de vente » (par article), « Historique de commande », « Synthèse par moyen ».
- Les sections du rapport complet ajoutées en F / G-2 (en-tête, règlements, réconciliation, annexe, marge brute, détail, habitus des cartes, opérateurs) sont **retirées de la caisse** : elles restent dans l'admin (rapport temps réel, fiche de clôture) et à l'écran de clôture.
- Chaque chiffre est **lu** dans le rapport des ventes unique (`RapportDesVentes`), même période (depuis la dernière J) et même périmètre (toutes origines) que le rapport temps réel de l'admin ; jamais recalculé dans la vue ni le gabarit, jamais l'ancien moteur. Seules les sections utiles sont calculées (plus de `rapport_x()` complet à chaque ouverture).
- Nouvelle méthode publique `RapportDesVentes.chiffre_affaires_par_point_de_vente()` (pas dans le Z) : le CA TTC par point de vente de la vente, les ventes sans point de vente sous « Sans point de vente ».
- La synthèse par moyen croise deux lignes lues telles quelles : « Chiffre d'affaires » (CA par moyen) et « Recharges » (recharges encaissées par moyen, annexe). Les lignes « adhésions » et « billets » de l'ancienne synthèse n'existent pas par moyen dans le rapport unique (elles exigeraient une répartition calculée) : elles sont dans « Chiffre d'affaires ».

/ The register's Sales screen gets the mock-up's structure, titles and layout back (top figures, five summary tables, three histories). The full report sections added in F / G-2 leave the register (they stay in the admin). Every figure is read in the single sales report, same period and scope as the admin's real-time report. New public method `chiffre_affaires_par_point_de_vente()`. The synthesis crosses revenue by method and top-ups by method.

**Pourquoi / Why :** décision du mainteneur : « Pour la caisse, on reste comme il l'a conçu » ; les infos complètes sont réservées à l'admin. / Maintainer's decision: the register keeps the mock-up's design; full information is for the admin.

### D'où vient chaque chiffre / Where each figure comes from
| Écran / Screen | Rapport unique / Single report |
|---|---|
| Total | `section_chiffre_affaires()["total_ttc_en_centimes"]` |
| « N ventes » | `section_en_tete()["nombre_de_ventes"]` (opérations numérotées) |
| TVA (haut et tableau) | `section_chiffre_affaires()["par_taux"]` |
| Fond, mouvements non nuls, solde | `section_caisse_especes()` écrite par `lignes_du_tiroir` |
| Par moyen de paiement | `section_chiffre_affaires()["par_moyen"]`, ordre `codes_des_moyens_dans_l_ordre` |
| Par point de vente | `chiffre_affaires_par_point_de_vente()` (nouvelle) |
| Offerts (hors argent) | `section_offerts()["par_produit"]` (quantité, valeur catalogue) |
| Non monétaire | `section_points()` |
| Historique de vente par article | `par_categorie` (CA) + `section_detail()["ventes_par_produit"]` ; pesée en kg, tirage en L |
| Synthèse par moyen | `par_moyen` (CA) + `section_annexe()["recharges_et_cartes"]["recharges_encaissees"]` |

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/laboutik/partial/hx_recap_en_cours.html` | structure de la maquette (fragment `detail-contenu`, trois boutons d'historique, mini-tableaux) ; textes déjà écrits par la vue |
| `laboutik/templates/laboutik/partial/_ventes_historique_recap.html` | **rétabli** (retiré en G-2) : historique par article, synthèse par moyen (colonnes = moyens présents) |
| `laboutik/views.py` | `recap_en_cours` (`?vue=`, fragment) ; `_contexte_des_chiffres_du_recap`, `_categories_du_detail_des_ventes`, `_synthese_par_moyen`, `_valeurs_triees_par_nom`, `_quantite_a_afficher` remplacent `_contexte_du_recap_du_service` |
| `comptabilite/rapport.py` | `CLE_SANS_POINT_DE_VENTE`, `RapportDesVentes.chiffre_affaires_par_point_de_vente()` |
| `laboutik/static/css/ventes.css` | règles de l'historique rétablies (`tbody + tbody`, `.num-fort`, `.cat-row`) |
| `tests/pytest/test_recap_en_cours_coherence_admin.py` | **neuf** — 5 tests : écran = admin sur un jeu mêlé (espèces, CB, cashless, offert, pesée, tirage, avoir, correction, consigne, recharge, sortie) |
| `tests/pytest/test_rapport_temps_reel.py`, `test_menu_ventes.py`, `test_hors_argent_offerts.py`, `test_vente_en_points.py` | tests de l'écran adaptés ; tests des sections retirées supprimés (sections repliées, phrase de réconciliation) |

### Chaines i18n nouvelles / New i18n strings
- `Chiffre d'affaires` (gabarit de synthèse, via `_()` de la vue)
- `Recharges`
- `Sans point de vente`

Le workflow i18n est à lancer par le mainteneur. / The i18n workflow is left to the maintainer.

---

## Comment tester (a la main) / Manual test
1. Caisse → menu → « Ventes » (`/laboutik/caisse/recap-en-cours/?uuid_pv=<pv>`).
2. Vérifier : Total, ligne TVA, bloc fond de caisse (mouvements + solde), trois boutons d'action, mini-tableaux.
3. Cliquer « Historique de vente » : tableau par catégorie puis article (une pesée en « kg »). Recliquer : la section se ferme.
4. « Synthèse par moyen » : lignes « Chiffre d'affaires » et « Recharges ». « Historique de commande » : liste des ventes.
5. Admin → Comptabilité → Rapport temps réel : Total, par moyen, TVA, tiroir, offerts identiques.
