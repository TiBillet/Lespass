# Un seul rapport des ventes, sur les montants entiers (chantier 05, fiche F) / One single sales report, on integer amounts (worksite 05, sheet F)

**Date :** 2026-10-03
**Migration :** Non (F-1) ; **Oui (F-2a)** : `BaseBillet/migrations/0233_heure_de_fermeture_et_index_vente.py`, `comptabilite/migrations/0005_cloture_unique_chainee.py` — `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

## Resume / Summary
**Quoi / What :** nouveau module `comptabilite/rapport.py`, classe `RapportDesVentes(debut, fin)` : le rapport des ventes réglées d'une période, toutes origines, par sommes de champs entiers. /
New module `comptabilite/rapport.py`, class `RapportDesVentes(debut, fin)`: the report of the settled sales of a period, every origin, by sums of integer fields.

**Pourquoi / Why :** chantier 05 « montants entiers », fiche F : un seul moteur de rapport, sans `amount × qty` ni arrondi, qui sépare le chiffre d'affaires, les règlements, les recharges, les écarts et les points. /
Worksite 05, sheet F: one single report engine, with no recomputation, separating revenue, payments, top-ups, gaps and points.

Sections ci-dessous : F-1a (sections 1, 2, 3, 5, 6, 7, 8), F-1c (corrections), F-1b (sections 4, 9, 10, 11, rapport X), F-1e (corrections de la relecture de F-1b), F-1d (avoirs : refus en points, coût d'achat), F-1f (corrections de la relecture de F-1d et F-1e), F-2a (la clôture unique), F-2b (les lecteurs), F-2c et F-2d (corrections de la relecture), F-2e (corrections de la relecture Fable), F-3a (la ventilation et le FEC), F-3b / F-3c (le CSV comptable retiré : le FEC est le seul export comptable). / Sections below: F-1a to F-1f, F-2a to F-2e, F-3a, F-3b / F-3c.

## F-1a — Le rapport : chiffre d'affaires, règlements, réconciliation, offerts, annexe, points

**Migration :** Non — **Chaînes i18n :** oui (liste plus bas).

### Resume / Summary
**Quoi / What :**
- `RapportDesVentes(debut, fin)` lit les ventes `REGLEE` avec `debut <= datetime_encaissement < fin` (borne de fin exclue), leurs articles et leurs règlements. Une méthode par section ; `toutes_les_sections()` rend un dictionnaire sérialisable en JSON (entiers et textes), prêt pour `ClotureCaisse.rapport_json` (F-2). Montants signés (avoirs, espèces rendues, remboursements négatifs) ; l'affichage en positif est pour F-2b. /
  Reads settled sales with `debut <= settlement < fin`; one method per section; a JSON-serializable dict; signed amounts.
- Section 1 (en-tête) : lieu (`Configuration.organisation`), période, plage des numéros, nombre de ventes, dont gratuites (VENTE réglée à total 0). Ni niveau, ni n° de clôture, ni perpétuel (F-2).
- Section 2 (chiffre d'affaires) : TTC / HT / TVA, par taux, par catégorie (clé = uuid de la catégorie de caisse, sinon `type_<code du type de produit>`, avec son `nom`), par origine, par journal (`journal_pour` ; journal impossible → « ? », le rapport ne tombe pas).
- Section 3 (règlements, natures VENTE, AVOIR, CORRECTION) : argent par moyen, cashless par moyen puis par monnaie (clé = uuid, « sans_monnaie » sinon), hors argent (offert = règlements FREE, recharge cadeau comprise ; points par monnaie).
- Section 5 (réconciliation) : argent reçu (toutes natures, vidages compris, Q-F4) = ventes payées en argent + recharges + remboursements + cartes vidées + écarts (tous les écarts ; remboursements = argent des avoirs moins leurs écarts). Juste par construction. Nombres seulement : la phrase est écrite par l'affichage (F-2b).
- Section 6 (offerts) : bouton OFFRIR, articles du chiffre d'affaires seulement.
- Section 7 (annexe) : avoirs (dont retours consigne en unités, dont remboursements Stripe à faire à la main), recharges et cartes (recharges par moyen d'argent de leur vente, « plusieurs_moyens » sinon ; cadeau émis ; cartes vidées, espèces rendues, jetons repris), écarts d'encaissement, corrections (moyen avant → après, opérateur).
- Section 8 (points) : par monnaie, en centièmes de points : net et offert (recharge offerte en points). Toute autre somme ne lit que les ventes en euros.
- `tests/pytest/fabriques_vente.py` : `fabriquer_vente_encaissee` reçoit `point_de_vente` et `operateur` (facultatifs, défaut inchangé).

**Écart au message de l'orchestrateur (constat c) :** « ventes payées en argent » = argent des ventes **VENTE et CORRECTION** − recharges − écarts hors avoirs. L'argent des avoirs est dans « remboursements » (moins leurs écarts, comptés dans « écarts ») : compté aussi dans « ventes », il l'aurait été deux fois et la phrase ne tomberait plus juste. /
"Sales paid in money" excludes credit notes: their money is in "refunds".

**Pourquoi / Why :** fiche F §1, §2, §6 ; brief 05-F-1a ; décisions Q-F4, Q-F5 et constats a-i (SUIVI §4-§6, 2026-10-03).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/rapport.py` | Nouveau : `RapportDesVentes` (sections 1, 2, 3, 5, 6, 7, 8) |
| `tests/pytest/test_rapport_unique.py` | Nouveau : 27 tests (schéma dédié `test_rapport_unique`) |
| `tests/pytest/fabriques_vente.py` | `fabriquer_vente_encaissee` : paramètres facultatifs `point_de_vente`, `operateur` |

### Chaînes i18n / i18n strings
Workflow i18n à lancer par le mainteneur (pas de `makemessages`). / i18n workflow to be run by the maintainer.
- Nouvelles (source FR) : « À corriger : voir « Plan complet ? » » ; « Sans monnaie » ; « Plusieurs moyens ». (« Sans catégorie » et la phrase de réconciliation, ajoutées puis retirées en F-1c, ne sont plus dans le code.)

### Tests vus rouges / Tests seen red
Avant tout code de production, `make test ARGS="tests/pytest/test_rapport_unique.py"` : 18 puis 22 échecs (après les quatre tests ajoutés par les réponses du mainteneur), tous à l'appel du rapport, après l'écriture et la vérification des ventes :
```
E       ModuleNotFoundError: No module named 'comptabilite.rapport'
======================== 22 failed, 2 warnings in 2.81s ========================
```
Puis vert : `test_rapport_unique.py` 22 passed ; avec `test_vente_*.py` et `test_caracterisation_*.py` : 180 passed ; `manage.py check` : aucun problème.

### Mutations, jouées à la main par l'orchestrateur / Mutations
Numéros de ligne d'avant les corrections F-1c (voir plus bas pour les lignes actuelles).
**18 jouées, 17 tuées, 1 équivalente** (sha256 identique après chaque retour). Résultats :
- l.211 `statut=REGLEE` retiré : **survit, équivalente** — une vente en attente ou annulée n'a jamais d'heure d'encaissement (`annuler_vente` refuse une vente réglée), le filtre de période l'écarte déjà. Gardé comme double sécurité.
- l.259-263 : jouée en deux variantes — produit non regardé (tout article hors CA d'une vente VENTE) → tuée par `test_ecart_d_encaissement_section_et_reconciliation` ; recharge comptée seulement si sa vente n'a que des recharges → tuée par `test_panier_biere_et_recharge_section_recharges` (et « plusieurs moyens »).
- l.238 `hors_chiffre_affaires=False` retiré : tuée par 4 tests (écart, panier, recharge cadeau, recharge encaissée) ; `test_vider_carte_jetons_cadeau_repris` ne la voit pas (le vidage n'est pas une nature du chiffre d'affaires).
- ajoutée : jetons repris lus sous un autre nom de produit → tuée par `test_vider_carte_jetons_cadeau_repris`.
- l.446-447 : jouée en `except KeyError` (le filet n'attrape plus rien) → tuée.
- toutes les autres lignes du tableau : tuées par le test indiqué.

| Mutation (comptabilite/rapport.py) | Test attendu rouge |
|---|---|
| l.211 : retirer `statut=Vente.Statut.REGLEE` (ventes EN_ATTENTE, ANNULEE comptées) | `test_vente_en_attente_hors_rapport` |
| l.223 : lire `LigneArticle` par sa propre date, hors vente | `test_vente_en_attente_hors_rapport` |
| l.95 : retirer `LOCAL_GIFT` de `MOYENS_CASHLESS` (LG dans l'argent) | `test_jetons_dans_le_ca_tva_0_et_dans_le_cashless` |
| l.665 : offerts sur `_articles_des_ventes_reglees()` (recharge cadeau dans la section 6) | `test_recharge_cadeau_puis_jetons_comptes_une_fois` |
| l.259-263 : remplacer le filtre de l'article par un filtre de nature (`vente__nature=VIDAGE_CARTE`) | `test_panier_biere_et_recharge_section_recharges` |
| l.770 : retirer `reference_externe=""` | `test_remboursements_stripe_a_faire_a_la_main_dans_le_z` |
| l.84-88 : ajouter `VIDAGE_CARTE` à `NATURES_DES_REGLEMENTS` | `test_vider_carte_especes_rendues`, `test_vidage_compte_dans_l_argent_recu_pas_dans_la_section_3` |
| l.238 : retirer `hors_chiffre_affaires=False` (jetons repris dans le CA) | `test_vider_carte_jetons_cadeau_repris` |
| l.627 : retirer `- ecarts_des_ventes` | `test_ecart_d_encaissement_section_et_reconciliation` |
| l.87 : retirer `CORRECTION` de `NATURES_DES_REGLEMENTS` | `test_correction_comptee_dans_la_j_de_la_correction` |
| l.213 : `__lt` → `__lte` (borne de fin incluse) | `test_vente_encaissee_a_la_borne_de_fin_hors_periode` |
| l.236 : retirer `vente__unite="EUR"` (points dans le CA) | `test_points_par_monnaie_hors_ca_et_hors_argent` |
| l.281 : `_reglements_d_argent` sans les vidages (`.exclude(vente__nature=VIDAGE_CARTE)`) | `test_vidage_compte_dans_l_argent_recu_pas_dans_la_section_3` |
| l.878 : `== 1` → `>= 1` | `test_recharge_d_une_vente_a_plusieurs_moyens_d_argent_rien_n_est_perdu` |
| l.304 : retirer `nature=Vente.Nature.VENTE` | `test_ventes_gratuites_comptees_dans_l_en_tete` |
| l.446-447 : retirer le `try/except` du journal | `test_journal_impossible_range_la_vente_sous_point_d_interrogation` |

### F-1c — Corrections de la relecture Opus / Opus review fixes
**Quoi / What :**
- **B1** — le cashless est rangé par moyen, PUIS par monnaie (`cashless.par_moyen[moyen].par_monnaie[uuid]`) : une monnaie réglée par deux moyens, ou deux règlements sans monnaie, ne s'écrasent plus. /
  Cashless by method then by currency: nothing is overwritten.
- **I1** — toute somme en euros ne lit que les ventes en euros (`_ventes_en_euros()`) : recharges, cadeau émis, offert de la section 3, avoirs, écarts, cartes vidées, réconciliation, corrections, ventes gratuites. La section 8 rend aussi `offert_en_centiemes` (recharge offerte en points). /
  Euro sums read euro sales only; section 8 also gives the offered part.
- **I3 / 6** — réconciliation : « écarts » = tous les écarts de la période (le total de l'annexe) ; « remboursements » = argent des avoirs moins leurs écarts ; « ventes payées en argent » = argent VENTE + CORRECTION − recharges − écarts hors avoirs. Identité exacte.
- **5** — la phrase de réconciliation n'est plus stockée (un texte traduit ne se scelle pas) ; `_euros_en_texte` retiré.
- **I4 / M8** — clés stables : catégorie = uuid de la catégorie de caisse, sinon `type_<code>` ; produit offert = uuid du produit ; chaque entrée porte `nom`.
- **Annexe** — `avoirs.par_moyen` hors règlements FREE : sa somme vaut le total net des avoirs.
- **djc** — références de session retirées des deux fichiers (règles énoncées au présent) ; chemins de filtre écrits en clair ; requêtes nommées avant les boucles ; sous-requête au lieu de `vente__in=list(...)` ; `TODO :` sur les sections à venir, sur la formule « ventes payées en argent » (écarts QR / NFC, fiche H), sur le signe de la quantité des retours consigne (fiche H) ; commentaire faux sur le partage des expressions retiré ; l'import de `RapportDesVentes` remonte en tête du fichier de tests.
- **Tests** — nouveaux : une monnaie par deux moyens ; invariant « chaque détail additionne son total » (sections 2, 3, 6, 7, points) ; recharge offerte en points ; bouton OFFRIR avec prix d'achat ; réconciliation complète (avoir espèces, avoir Stripe porteur d'un écart, correction, vidage). Réécrits : catégories (clés stables), 7b par `ecrire_la_vente_d_avoir_d_une_ligne(…, None, SaleOrigin.ADMIN)` + `avoirs.par_moyen`, test 4 (`recharges_encaissees.par_moyen == {}`), docstring du test 9.

**Rouge avant le code** (`make test ARGS="tests/pytest/test_rapport_unique.py"`) :
```
FAILED ...::test_bouton_offrir_quantite_valeur_catalogue_et_cout          (par_produit indexé par nom, sans « nom »)
FAILED ...::test_ca_trois_jus_nfc_et_cb_1050_875_175                      KeyError: 'par_moyen'
FAILED ...::test_cashless_une_monnaie_reglee_par_deux_moyens_ne_perd_rien KeyError: 'par_moyen'
FAILED ...::test_chaque_detail_additionne_exactement_son_total            KeyError: 'par_moyen'
FAILED ...::test_chiffre_affaires_par_categorie_avec_et_sans_categorie    clés par nom traduit
FAILED ...::test_jetons_dans_le_ca_tva_0_et_dans_le_cashless              KeyError: 'par_moyen'
FAILED ...::test_recharge_offerte_en_points_comptee_en_section_8_seulement assert 500 == 0
FAILED ...::test_reconciliation_avoirs_correction_vidage_termes_et_egalites écarts 3 != 2, remboursements −5001 != −5000, « phrase » en trop
FAILED ...::test_vider_carte_especes_rendues                              KeyError: 'par_moyen'
FAILED ...::test_vider_carte_jetons_cadeau_repris                         KeyError: 'par_moyen'
================== 10 failed, 17 passed, 2 warnings in 3.75s ===================
```
Déjà verts avant le code : le test 7b réécrit (mutation qui le fait tomber : retirer `reference_externe=""`, ou ne plus grouper `avoirs.par_moyen`) et l'assertion ajoutée au test 4 (mutation : retirer `if net_des_recharges == 0: continue`).

**Vert :** `test_rapport_unique.py` 27 passed ; avec `test_vente_*.py` et `test_caracterisation_*.py` : 185 passed ; `manage.py check` : aucun problème.

**Mutations (non jouées) — `comptabilite/rapport.py`, lignes actuelles :**

| Mutation | Test attendu rouge |
|---|---|
| l.584-587 : grouper par `asset` seul (`.values("asset")`) ou ranger par monnaie seule | `test_cashless_une_monnaie_reglee_par_deux_moyens_ne_perd_rien`, `test_chaque_detail_additionne_exactement_son_total` |
| l.606 : `= {…}` → n'écrire la monnaie que si la clé est absente | `test_cashless_une_monnaie_reglee_par_deux_moyens_ne_perd_rien` |
| l.240 : retirer `.filter(unite="EUR")` | `test_recharge_offerte_en_points_comptee_en_section_8_seulement`, `test_points_par_monnaie_hors_ca_et_hors_argent` |
| l.1045 : retirer `offert_en_centiemes` | `test_recharge_offerte_en_points_comptee_en_section_8_seulement` |
| l.735 : offerts sur `_articles_des_ventes_en_euros()` | `test_bouton_offrir_quantite_valeur_catalogue_et_cout` |
| l.761 : clé = nom du produit | `test_bouton_offrir_quantite_valeur_catalogue_et_cout` |
| l.420 / l.429 : clé = nom de la catégorie / nom traduit du type | `test_chiffre_affaires_par_categorie_avec_et_sans_categorie` |
| l.701 : `remboursements = argent_des_avoirs` | `test_reconciliation_avoirs_correction_vidage_termes_et_egalites` |
| l.718 : `ecarts_hors_avoirs` au lieu de `tous_les_ecarts` | `test_reconciliation_avoirs_correction_vidage_termes_et_egalites` |
| l.710 : retirer `- ecarts_hors_avoirs` | `test_ecart_d_encaissement_section_et_reconciliation`, `test_reconciliation_…` |
| l.679 : ajouter AVOIR aux natures de « ventes payées en argent » | `test_reconciliation_avoirs_correction_vidage_termes_et_egalites` |
| l.816 : retirer `.exclude(moyen=PaymentMethod.FREE)` | `test_chaque_detail_additionne_exactement_son_total` |
| l.949 : retirer `if net_des_recharges == 0: continue` | `test_recharge_cadeau_puis_jetons_comptes_une_fois` |
| ajouter une clé `"phrase"` au retour de la section 5 | `test_reconciliation_avoirs_correction_vidage_termes_et_egalites` |

### Mutations F-1c, jouées à la main par l'orchestrateur
**14 jouées, 13 tuées, 1 équivalente** (sha256 identique après chaque retour). Équivalente : CORRECTION retirée de « l'argent des ventes » — une correction ne va que d'espèces / CB / chèque vers espèces / CB / chèque (`laboutik/views.py`, les paiements NFC ne se corrigent pas) : son argent net vaut toujours 0. Gardée comme double sécurité.

## F-1b — Caisse espèces, marge brute, détail, intégrité, rapport X

**Migration :** Non — **Chaînes i18n :** oui (« Sans catégorie », « Sans opérateur »).

### Resume / Summary
**Quoi / What :**
- Section 4 (caisse espèces, Q-F7) : le tiroir de la caisse LaBoutik V2 seulement — ventes avec un point de vente (avoirs et vidages compris). Fond (`LaboutikConfiguration.fond_de_caisse`), espèces reçues (≥ 0), espèces rendues (≤ 0), sorties (`SortieCaisse`, même borne que les ventes : `debut <= datetime < fin`), solde théorique = fond + reçues + rendues − sorties. Les espèces de l'admin, de l'API v2, du webhook V1 restent en section 3. /
  Cash drawer: V2 register sales only.
- Section 9 (marge brute, D21) : CA HT − Σ `cout_achat` des articles servis (articles du CA et articles des ventes en points ; jamais hors CA). Coût inconnu = `cout_achat` vide et total catalogue non nul. `TODO :` coût d'achat d'un article d'avoir (question au mainteneur). /
  Gross margin on served items; unknown-cost count.
- Section 10 (détail) : billets par événement puis par tarif (reconnus par `reservation`), adhésions par produit, ventes par produit (quantité en texte, TTC, HT, offert, coût, clé `categorie`) — articles du CA, en euros ; les produits additionnent le CA. /
  Detail: tickets, memberships, sales by product.
- Section 11 (intégrité) : `verifier_chaine_ventes` sur la plage de la période → `{"statut": "OK" | "ANOMALIES", "anomalies": [...]}` ; période sans vente : « OK », rien de vérifié. /
  Chain checked over the period's range.
- `laboutik/integrity.py` : `verifier_chaine_ventes(cle, numero_de_la_premiere_vente=None, numero_de_la_derniere_vente=None)`. Sans plage : inchangé. Avec plage : seules ses ventes, la première reliée à l'empreinte stockée de la vente numéro − 1. /
  Optional range; unchanged without it.
- Rapport X : `rapport_x()` = `toutes_les_sections()` + `habitus_cartes` (cartes des ventes VENTE en euros ; médianes sur les seules cartes concernées ; panier moyen divisé par les seules cartes qui dépensent, comme l'ancien moteur ; recharge cadeau seule hors de la médiane des recharges ; nouveaux membres `debut <= date_added < fin` ; reste sur carte lu en direct, cartes anonymes ignorées comme l'ancien moteur ; moyennes et médianes en centimes entiers arrondis demi-haut) + `operateurs` (ventes en euros toutes natures, CA, argent toutes natures ; email permis). Jamais dans le Z stocké. /
  X report adds card habits and operators, never stored.
- Z stocké : l'opérateur d'une correction est l'identifiant de l'utilisateur (uuid en texte, `None` sinon), jamais son email (Q-F6). /
  The stored Z keeps the user id, never the email.
- Mineurs : type de produit « aucun » → « Sans catégorie » ; tri des catégories départagé par uuid ; lignes de totaux écrites en clair ; ventes gratuites toutes unités (recharge offerte en points comprise).

**Pourquoi / Why :** fiche F §2 (sections 4, 9, 10, 11, rapport X), §5, §6 (tests 11, 25c, 26) ; Q-F6, Q-F7.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/rapport.py` | Sections 4, 9, 10, 11 ; `section_habitus_cartes`, `section_operateurs`, `rapport_x()` ; opérateur = identifiant ; mineurs |
| `laboutik/integrity.py` | `verifier_chaine_ventes` : plage facultative |
| `tests/pytest/test_rapport_unique.py` | 21 tests ajoutés, 3 adaptés (opérateur = uuid, clés du Z, docstring) |
| `tests/pytest/test_rapport_unique_comparaison.py` | Nouveau : 3 paiements par la vraie route de caisse, ancien et nouveau rapport égaux (schéma dédié) |
| `tests/pytest/fabriques_vente.py` | `fabriquer_vente_encaissee` : paramètre facultatif `carte` |

### Tests vus rouges / Tests seen red
Avant le code : **17 failed, 29 passed** — `AttributeError` (sections et `rapport_x` absents) à l'appel du rapport, après l'écriture des ventes ; `TypeError` (paramètres de plage absents) ; opérateur = email ; « Sélectionner une catégorie » ; ventes gratuites 0. Verts d'emblée : les 3 comparaisons (mutation : `Sum("total_ttc")` → `Sum("total_ht")` dans `_sommes_ttc_ht_tva`) et le test 26 (mutation : écrire `amount` dans `rapport.py`).
Après le code : `test_rapport_unique.py` + comparaison **46 passed**, puis **49 passed** avec les trois tests d'habitus ajoutés pour couvrir les mutations restantes (panier moyen ramené aux seules cartes qui dépensent), puis **51 passed** avec les deux tests d'une altération après la plage ; `test_vente_*.py`, `test_caisse_ecrit_la_vente.py`, `test_caracterisation_*.py` : 222 passed, 3 failed **sans lien** (`test_recharge_cadeau_melangee_a_d_autres_articles_refusee[espece|nfc]`, `test_complement_refuse_le_melange_recharge_cadeau` : le message de refus de la caisse est rendu en anglais, ils échouent aussi seuls ; aucun code touché sur ce chemin) ; `manage.py check` : aucun problème.

### Mutations (non jouées) — lignes actuelles
| Mutation | Test attendu rouge |
|---|---|
| `rapport.py` l.1214-1216 : coût = Σ quantité × prix d'achat du produit | `test_marge_brute_somme_des_couts_et_compte_inconnus` (et test 26) |
| `rapport.py` l.1192-1196 : `_articles_servis` = articles du CA seulement | `test_marge_brute_compte_les_points` |
| `rapport.py` l.1219 : retirer `.exclude(total_catalogue=0)` (NULL seul) | `test_marge_brute_somme_des_couts_et_compte_inconnus` |
| `rapport.py` l.1218 : `cout_achat=0` au lieu de `cout_achat__isnull=True` | `test_marge_brute_somme_des_couts_et_compte_inconnus` |
| `rapport.py` l.753 : retirer `+ especes_rendues` | `test_caisse_especes_fond_recues_rendues_sorties_solde` |
| `rapport.py` l.747-748 : retirer le filtre de période des sorties | `test_caisse_especes_fond_recues_rendues_sorties_solde` |
| `rapport.py` l.748 : `datetime__lt` → `datetime__lte` | `test_caisse_especes_fond_recues_rendues_sorties_solde` |
| `rapport.py` l.733 : retirer `point_de_vente__isnull=False` | `test_caisse_especes_ignore_les_especes_hors_caisse_v2` |
| `integrity.py` l.394 : retirer le filtre de début de plage | `test_integrite_ignore_une_alteration_hors_de_la_plage` |
| `integrity.py` l.406 : retirer le filtre de fin de plage | `test_integrite_ignore_une_alteration_apres_la_fin_de_la_periode`, `test_verifier_chaine_ventes_ignore_une_alteration_apres_la_plage` |
| `integrity.py` l.400 : `empreinte_de_la_vente_precedente = ""` | `test_integrite_ok_puis_alteration_detectee_sur_la_plage` |
| `rapport.py` l.1419-1421 : retirer le retour « période sans vente » | `test_integrite_d_une_periode_sans_vente_ok_sans_verification` |
| `rapport.py` toutes_les_sections : ajouter `habitus_cartes` ou `operateurs` | `test_rapport_x_ajoute_habitus_et_operateurs_hors_z` |
| `rapport.py` l.1130 : opérateur = `operateur.email` | `test_z_stocke_l_identifiant_de_l_operateur_jamais_son_email`, `test_correction_comptee_dans_la_j_de_la_correction` |
| `rapport.py` l.385 : ventes gratuites sur `_ventes_en_euros()` | `test_vente_gratuite_compte_aussi_la_recharge_offerte_en_points` |
| `rapport.py` l.194-195 : retirer le cas « Sans catégorie » | `test_produit_sans_categorie_ni_type_libelle_sans_categorie` |
| `rapport.py` l.232 : médiane paire tronquée (`// 2`) | `test_habitus_cartes_en_centimes_entiers` |
| `rapport.py` l.1537 : médiane des dépenses sur toutes les cartes (0 compris) | `test_habitus_depenses_sur_les_seules_cartes_qui_depensent` |
| `rapport.py` l.1535 : panier moyen divisé par `nombre_de_cartes` | `test_habitus_depenses_sur_les_seules_cartes_qui_depensent` |
| `rapport.py` l.1506-1507 : garder les recharges à 0 | `test_habitus_recharge_cadeau_seule_hors_de_la_mediane_des_recharges` |
| `rapport.py` l.1528 : `date_added__lt` → `date_added__lte` | `test_habitus_nouveau_membre_a_la_borne_de_fin_hors_periode` |

Les numéros de ligne ci-dessus sont ceux d'avant F-1e.

## F-1e — Corrections de la relecture de F-1b / F-1b review fixes

**Migration :** Non — **Chaînes i18n :** non.

### Resume / Summary
**Quoi / What :**
- Rapport X : `rapport_x()` ne calcule plus la section 11 (intégrité). C'est un contrôle du Z, qui relit chaque vente de la plage (plusieurs requêtes par vente) ; le Z la garde. Mesure sur 20 ventes : 135 requêtes avant, 52 après. /
  The X report no longer computes integrity (a Z check): 135 → 52 queries on 20 sales.
- `verifier_chaine_ventes` : la vente qui précède la plage est la dernière vente réglée de numéro inférieur au début de la plage (plus « numéro − 1 ») ; une vente supprimée juste avant la plage sort en « trou de numéro », comme sur la chaîne entière. /
  The sale before the range is the last settled one numbered below it.
- Tiroir (section 4) : les corrections de moyen de paiement sont à part (`corrections_en_centimes`, net en espèces), hors des espèces reçues et rendues ; le solde les ajoute. /
  Corrections on their own drawer line.
- Marge (section 9) : les articles au coût inconnu se comptent en unités (Σ des quantités, arrondie demi-haut), pas en lignes. /
  Unknown-cost items counted in units.
- Habitus (rapport X) : les cartes viennent de la vente (`Vente.carte`) ET des règlements cashless (`Reglement.carte`, seconde carte d'un paiement à deux cartes), chacune comptée une fois — pour le nombre de cartes et le reste sur carte ; dépense rangée par la carte du règlement ; reste sur carte limité aux monnaies locales du lieu et moyenné par carte ; requêtes nommées avant les boucles, cartes lues par sous-requête. /
  Cards from the sale and the cashless payments, counted once; spending by payment card; remaining balance: venue currencies, per card.
- Code mort retiré (`CLE_SANS_TARIF`, date d'événement vide) ; une seule boucle pour les soldes ; requêtes nommées avant les boucles dans `verifier_chaine_ventes`.
- Comparaison : le scénario espèces compare aussi le tiroir à l'ancien `calculer_solde_caisse()` (l'ancien ne sépare pas reçues, rendues et corrections).

**Pourquoi / Why :** relecture Opus de F-1b (I1, I2, M1-M6, M9) et décisions de l'orchestrateur (corrections du tiroir, unités du coût inconnu).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/rapport.py` | `rapport_x()` sans intégrité ; tiroir : corrections à part ; coût inconnu en unités ; habitus (carte du règlement, monnaies du lieu par carte, sous-requêtes) ; code mort |
| `laboutik/integrity.py` | `verifier_chaine_ventes` : vente avant la plage par `numero__lt` ; requêtes nommées avant les boucles |
| `tests/pytest/test_rapport_unique.py` | 6 tests ajoutés (corrections du tiroir, deux parts, vente supprimée avant la plage, plage qui commence la chaîne, deux cartes, reste sur carte) ; adaptés : tiroirs (clé `corrections_en_centimes`), test 11 (trois planches → 3), rapport X (sans `integrite`), helpers (correction sur un point de vente, règlement avec la carte) |
| `tests/pytest/test_rapport_unique_comparaison.py` | scénario espèces : tiroir comparé à l'ancien moteur |

### Tests vus rouges / Tests seen red
Avant le code : **10 failed, 47 passed** (`corrections_en_centimes` absent ; dépenses 801 au lieu de 401 ; reste 1625 au lieu de 751 ; coût inconnu 1 au lieu de 3, 2 au lieu de 1 ; `integrite` dans le rapport X ; « Trou de numéro » absent ; `KeyError: 'corrections_en_centimes'` dans la comparaison). Vert d'emblée : `test_verifier_chaine_ventes_plage_qui_commence_la_chaine_ok` (mutation : chercher la vente d'avant sans `numero__lt`).
Après le code : `test_rapport_unique.py` + comparaison **57 passed** ; `test_vente_service.py`, `test_vente_*.py`, `test_caracterisation_*.py` : **158 passed** ; `manage.py check` : aucun problème.
Puis les cartes des règlements : `test_habitus_paiement_a_deux_cartes_chaque_carte_compte_sa_depense` vérifie aussi le nombre de cartes (2) et le reste sur carte (201), vu rouge avant le code (`assert 1 == 2`) ; ensuite **57 passed**.

### Mutations (non jouées) — lignes actuelles
| Mutation | Test attendu rouge |
|---|---|
| `integrity.py` l.402 : `numero=numero_de_la_premiere_vente - 1` au lieu de `numero__lt` | `test_verifier_chaine_ventes_vente_supprimee_juste_avant_la_plage` |
| `integrity.py` l.404 : `order_by("numero")` (la plus ancienne) | `test_verifier_chaine_ventes_vente_supprimee_juste_avant_la_plage` |
| `integrity.py` l.400-405 : sans le filtre `numero__lt` | `test_verifier_chaine_ventes_plage_qui_commence_la_chaine_ok` |
| `rapport.py` l.745-749 : ne plus exclure les corrections | `test_caisse_especes_corrections_a_part` |
| `rapport.py` l.768 : retirer `+ corrections` | `test_caisse_especes_corrections_a_part` |
| `rapport.py` l.751 : `montant__gt=0` → `montant__gte=1000` | `test_comparaison_trois_jus_en_especes` |
| `rapport.py` l.1239-1243 : compter les lignes (`.count()`) | `test_marge_brute_un_article_paye_en_deux_parts_compte_un_cout_inconnu`, `test_marge_brute_somme_des_couts_et_compte_inconnus` |
| `rapport.py` l.1508 : retirer `\| Q(pk__in=reglements_cashless…)` (cartes de la vente seulement) | `test_habitus_paiement_a_deux_cartes_chaque_carte_compte_sa_depense` |
| `rapport.py` l.1515 : `.values("vente__carte")` | `test_habitus_paiement_a_deux_cartes_chaque_carte_compte_sa_depense` |
| `rapport.py` l.1551 : retirer le filtre du lieu | `test_habitus_reste_sur_carte_monnaie_du_lieu_et_moyenne_par_carte` |
| `rapport.py` l.1553-1555 : un solde par jeton (sans regrouper par portefeuille) | `test_habitus_reste_sur_carte_monnaie_du_lieu_et_moyenne_par_carte` |
| `rapport.py` `rapport_x()` (l.1699-1712) : ajouter `"integrite"` | `test_rapport_x_ajoute_habitus_et_operateurs_hors_z` |

## F-1d — Avoirs : refusés sur une ligne payée en points ; coût d'achat repris en négatif / Credit notes: refused on points lines; purchase cost taken back

**Migration :** Non — **Chaînes i18n :** oui, 2 nouvelles (voir plus bas).

### Resume / Summary
**Quoi / What :**
- Une ligne payée en points ou en temps ne reçoit plus d'avoir : ligne d'une vente qui n'est pas en euros (vente en points de la caisse, recharge offerte en points ou en temps de l'API v2), ou ligne au moyen « points ou temps » (`NM`), avec ou sans vente. Le refus (`ValueError`) est dans `ajouter_l_article_d_avoir`, commune à tous les producteurs d'avoir (bouton « Avoir », annulations admin, annulation d'adhésion, remboursement Stripe). Nouvelle fonction `ligne_payee_en_points(ligne)`. /
  A line paid in points or time never gets a credit note: refused in the shared `ajouter_l_article_d_avoir`.
- Bouton « Avoir » de l'admin : l'écran ne s'ouvre pas sur une telle ligne (garde au GET et au POST, message « Cette ligne a été payée en points ou en temps : l'avoir est impossible. »). /
  The admin "Credit note" screen does not open on such a line.
- Annulation d'une adhésion payée en points : le formulaire ne propose que « Annuler sans avoir » et le dit (« Adhésion payée en points : aucun avoir n'est possible, et les points ne sont pas rendus sur la carte. ») ; un POST « avec avoir » forcé revient avec cette erreur, rien n'est annulé. /
  A points membership can only be cancelled without a credit note, and the form says so.
- Un avoir reprend en négatif le coût d'achat figé de la ligne qu'il annule, au prorata de la quantité rendue (arrondi demi-haut) ; ligne sans coût → avoir sans coût. Nouveau paramètre `cout_achat_impose` d'`ajouter_article`. Une vente remboursée en entier a une marge nulle et plus d'article « au coût inconnu ». /
  A credit note takes the original line's frozen cost back, negative and prorated.

**Pourquoi / Why :** décisions du mainteneur Q-F8, Q-F10, Q-F11 (refus en points) et Q-F9 (coût repris en négatif), SUIVI §5 ; TODO bug n°28. Sans le refus, « Remboursé par » rendait des espèces pour des points (vente AVOIR ouverte en euros). /
Maintainer decisions Q-F8, Q-F9, Q-F10, Q-F11; bug n°28.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/services_vente.py` | `ligne_payee_en_points` ; refus dans `ajouter_l_article_d_avoir` ; coût de l'avoir au prorata ; `ajouter_article(cout_achat_impose=None)` ; docstrings |
| `Administration/admin_tenant.py` | `emettre_avoir` : garde « ligne payée en points » (GET et POST) |
| `BaseBillet/views.py` | `_contexte_du_formulaire_d_annulation` : `dernier_paiement_en_points`, pas d'option « avec avoir » ; `cancel` : « avec avoir » forcé refusé |
| `Administration/templates/admin/membership/partials/cancel_form.html` | phrase explicite (`data-testid="membership-cancel-payee-en-points"`, `role="note"`), seul « Annuler sans avoir » |
| `comptabilite/rapport.py` | `section_marge_brute` : le TODO devient la règle (docstring seulement) |
| `tests/pytest/test_avoirs_ecrivent_la_vente.py` | 17 tests (refus en points : fonction commune, article d'avoir, GET et POST du bouton, recharge API v2, ligne sans vente NM ; témoin vente en euros à deux moyens ; adhésion en points : formulaire, sans avoir, avec avoir forcé ; coût : miroir, prorata demi-haut, poids, part de cascade, retour de consigne, sans coût, coût imposé non entier) |
| `tests/pytest/test_rapport_unique.py` | `test_marge_brute_d_une_vente_remboursee_en_entier_est_nulle` |

### Chaînes i18n / i18n strings
Nouvelles (source FR) : « Cette ligne a été payée en points ou en temps : l'avoir est impossible. » ; « Adhésion payée en points : aucun avoir n'est possible, et les points ne sont pas rendus sur la carte. » (gabarit et vue, même msgid). Workflow i18n à lancer par le mainteneur.

### Tests vus rouges / Tests seen red
Avant le code : **13 failed, 3 passed** (`DID NOT RAISE` ×4 ; GET `200 == 302` ; POST `['Credit note created.']` ; bouton « avec avoir » présent ; avoir forcé `204 == 200` ; coût `None == -120`, `None == -38`, `None == -280`, `None == -50`, `None == 30`) et la marge **1 failed** (coût 120, marge −120, coût inconnu −1). Vert d'emblée : le témoin, « sans avoir fonctionne », « ligne sans coût » (comportement déjà juste). Ajouté après le code : « coût imposé non entier » (mutation ci-dessous).
Après le code : `test_avoirs_ecrivent_la_vente.py` + `test_rapport_unique.py` **134 passed** ; avec comparaison, `test_stripe_refund.py`, `test_vente_*.py`, `test_caracterisation_*.py`, `test_plan_comptable_unique.py`, `test_montants_article.py`, annulations d'adhésion : **423 passed** ; `manage.py check` : aucun problème.

### Mutations (non jouées) — lignes actuelles
| Mutation | Test attendu rouge |
|---|---|
| `services_vente.py` l.628-632 : garde retirée | `test_avoir_ligne_payee_en_points_refuse_par_la_fonction_commune`, `…_refuse_par_l_article_d_avoir`, `test_avoir_recharge_offerte_en_points_refusee`, `test_avoir_ligne_sans_vente_au_moyen_points_refusee` |
| `services_vente.py` l.797 : `return vente_de_la_ligne_en_points` (unité seule) | `test_avoir_ligne_sans_vente_au_moyen_points_refusee` |
| `services_vente.py` l.797 : `return ligne_au_moyen_points_ou_temps` (NM seul) | `test_avoir_recharge_offerte_en_points_refusee` |
| `admin_tenant.py` l.2189-2194 : garde du GET retirée | `test_avoir_admin_ligne_payee_en_points_l_ecran_ne_s_ouvre_pas`, `…_validation_refusee` |
| `views.py` l.4940 : `and not dernier_paiement_en_points` retiré (`avoir_possible` laissé vrai) | `test_annulation_adhesion_payee_en_points_seulement_sans_avoir_et_le_dit` |
| `views.py` l.5096-5113 : refus de « avec avoir » forcé retiré | `test_annulation_adhesion_payee_en_points_avec_avoir_force_refuse` |
| `cancel_form.html` l.145-155 : phrase retirée | `test_annulation_adhesion_payee_en_points_seulement_sans_avoir_et_le_dit` |
| `services_vente.py` l.716 : `cout_achat_impose` non passé | `test_cout_de_l_avoir_rendu_total_exactement_en_miroir` (et poids, cascade, consigne, marge) |
| `services_vente.py` l.693 : `* quantite` (coût positif) | `test_cout_de_l_avoir_rendu_total_exactement_en_miroir` |
| `services_vente.py` l.695 : `int(...)` au lieu de l'arrondi demi-haut | `test_cout_de_l_avoir_partiel_au_prorata_arrondi_demi_haut` |
| `services_vente.py` l.689-690 : coût d'origine vide traité comme 0 | `test_cout_de_l_avoir_ligne_sans_cout_reste_sans_cout` |
| `services_vente.py` l.542 : `cout_achat=montants["cout_achat"]` (coût imposé ignoré) | `test_cout_de_l_avoir_rendu_total_exactement_en_miroir` |
| `services_vente.py` l.499-503 : contrôle du type retiré | `test_cout_impose_qui_n_est_pas_un_entier_refuse` |

## F-1f — Corrections de la relecture de F-1d et F-1e / F-1d and F-1e review fixes

**Migration :** Non — **Chaînes i18n :** oui, 1 msgid remplacé (voir plus bas).

### Resume / Summary
**Quoi / What :**
- Marge (section 9) : « articles au coût inconnu » ne compte que les articles **vendus** — articles servis des ventes de nature VENTE, quantité > 0. Un avoir n'en est pas un, ni un retour de consigne (vente AVOIR) : le nombre n'est plus jamais négatif (avant : −1 pour l'avoir d'une ligne sans coût dont la vente est dans une autre période, valeur scellée dans le Z). Un gobelet sans prix d'achat vendu puis rendu compte 1. /
  Unknown-cost items are SOLD items only (VENTE sales, quantity > 0): never negative.
- Annulation d'une adhésion payée en points : la phrase devient « Adhésion payée en points **ou en temps** : aucun avoir n'est possible, et les points ne sont pas rendus sur la carte. » (même msgid dans la vue et le gabarit). Sur un POST « avec avoir » forcé, elle n'est plus écrite deux fois : la note du formulaire n'est pas répétée quand l'erreur la porte déjà. /
  The sentence also names time; on a forced POST it is written once.
- Docstrings et commentaires : le rapport X = les sections du Z sans la 11 (intégrité), plus l'habitus et les opérateurs ; le reste sur carte est sommé par portefeuille (l'utilisateur de la carte : deux cartes d'un même utilisateur partagent un solde) et moyenné sur ces soldes. /
  Docstrings: X report without integrity; remaining balance per wallet.
- Tests : trois tests de la caisse (refus d'un panier qui mêle une recharge cadeau à d'autres articles) comparent le message de refus dans la langue de la réponse (`Content-Language`), au lieu de chercher « recharge cadeau » en français ; ils passaient au rouge depuis la traduction anglaise de ce message. Un test renommé (`test_verifier_chaine_ventes_sans_plage_verifie_toute_la_chaine`). /
  Three register tests read the refusal message in the response's language.

**Pourquoi / Why :** relecture Opus de F-1d + F-1e (I1, M2-M6) et décisions de l'orchestrateur (coût inconnu = articles vendus ; « ou en temps »), SUIVI §4 ; trois échecs de la suite complète du 2026-10-03 (langue). /
Opus review of F-1d + F-1e; three language-dependent failures of the full suite.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/rapport.py` | `section_marge_brute` : coût inconnu sur les seuls articles vendus (VENTE, quantité > 0) ; docstring du module (X sans la 11) ; reste sur carte : commentaire et docstring (par portefeuille) |
| `BaseBillet/views.py` | `cancel` : phrase « payée en points ou en temps » |
| `Administration/templates/admin/membership/partials/cancel_form.html` | même phrase ; la note n'est pas répétée quand il y a une erreur |
| `tests/pytest/test_rapport_unique.py` | 3 tests ajoutés (avoir sans coût hors de la période de sa vente → 0 ; gobelet sans prix d'achat vendu puis rendu → 1 ; ligne négative d'une vente VENTE → ne retire rien) ; 1 test renommé ; docstring du module |
| `tests/pytest/test_avoirs_ecrivent_la_vente.py` | phrase « ou en temps » ; 1 test ajouté (la phrase une seule fois sur un POST forcé) |
| `tests/pytest/test_caisse_ecrit_la_vente.py` | 3 tests : message de refus comparé dans la langue de la réponse |

### Chaînes i18n / i18n strings
Remplacée (source FR) : « Adhésion payée en points : aucun avoir n'est possible, et les points ne sont pas rendus sur la carte. » → « Adhésion payée en points ou en temps : aucun avoir n'est possible, et les points ne sont pas rendus sur la carte. » (vue et gabarit, même msgid). L'ancien msgid n'est plus dans le code. Workflow i18n à lancer par le mainteneur.

### Tests vus rouges / Tests seen red
Avant le code :
```
>       assert marge_brute["nombre_d_articles_au_cout_inconnu"] == 0
E       assert -1 == 0
>       assert marge_brute["nombre_d_articles_au_cout_inconnu"] == 1
E       assert 2 == 1
FAILED tests/pytest/test_avoirs_ecrivent_la_vente.py::test_annulation_adhesion_payee_en_points_seulement_sans_avoir_et_le_dit
FAILED tests/pytest/test_avoirs_ecrivent_la_vente.py::test_annulation_adhesion_payee_en_points_avec_avoir_force_refuse
FAILED tests/pytest/test_avoirs_ecrivent_la_vente.py::test_annulation_adhesion_payee_en_points_avec_avoir_force_dit_la_phrase_une_fois
```
Puis, la phrase changée et la note encore répétée : `assert 2 == 1` (la phrase deux fois). Verts d'emblée : les trois tests de la caisse (mutation ci-dessous) et la ligne négative d'une vente VENTE (mutation ci-dessous).
Après le code : `test_rapport_unique.py`, comparaison, `test_avoirs_ecrivent_la_vente.py`, `test_caisse_ecrit_la_vente.py` **207 passed** ; `test_rapport_unique.py` avec le test de la ligne négative **58 passed** ; `test_vente_*.py`, `test_caracterisation_*.py` **158 passed** ; `manage.py check` : aucun problème.

### Mutations (non jouées) — lignes actuelles
| Mutation | Test attendu rouge |
|---|---|
| `rapport.py` l.1246 : retirer `vente__nature=Vente.Nature.VENTE` | `test_marge_brute_un_gobelet_sans_prix_d_achat_vendu_puis_rendu_compte_un` (2 au lieu de 1) |
| `rapport.py` l.1247 : retirer `qty__gt=0` | `test_marge_brute_une_ligne_negative_d_une_vente_ne_retire_rien_au_cout_inconnu` (1 au lieu de 2) |
| `rapport.py` l.1246-1247 : retirer les deux filtres | `test_marge_brute_l_avoir_d_un_article_au_cout_inconnu_ne_compte_pas` (−1), et les deux ci-dessus |
| `cancel_form.html` l.152 et l.160 : retirer `{% if not erreurs %}` / `{% endif %}` | `test_annulation_adhesion_payee_en_points_avec_avoir_force_dit_la_phrase_une_fois` |
| `views.py` l.5104 : ancien texte (« payée en points : ») | `test_annulation_adhesion_payee_en_points_avec_avoir_force_refuse`, `…_force_dit_la_phrase_une_fois` |
| `cancel_form.html` l.157 : ancien texte | `test_annulation_adhesion_payee_en_points_seulement_sans_avoir_et_le_dit` |
| `laboutik/views.py` l.8497 : message de refus remplacé | `test_recharge_cadeau_melangee_a_d_autres_articles_refusee[espece]`, `[nfc]` |
| `laboutik/views.py` l.10964 : message de refus remplacé | `test_complement_refuse_le_melange_recharge_cadeau` |

## F-2a — La clôture unique : J glissante, filet horaire, H / M / A en heure locale, chaîne / The single closure

**Migration :** Oui — `BaseBillet/0233_heure_de_fermeture_et_index_vente` (champ `Configuration.heure_de_fermeture`, index `Vente(statut, datetime_encaissement)`), `comptabilite/0005_cloture_unique_chainee` (champs de clôture). Appliquées en dev par `migrate_schemas --executor=multiprocessing` (tous les schémas, `test_*` compris). — **Chaînes i18n :** oui (liste plus bas).

### Resume / Summary
**Quoi / What :** la clôture `comptabilite` devient la clôture unique du lieu, toutes origines, bâtie sur `RapportDesVentes`. La J est glissante (de la fin de la J précédente au moment de la clôture ; la première commence à la première vente réglée ; aucune J sans vente depuis la précédente). Sa fin est fixée sous le verrou du lieu des ventes, dans une transaction courte (une vente prend son heure et son numéro sous ce même verrou : toute vente encaissée ensuite est après la fin, donc dans la J suivante) ; le rapport est calculé hors verrou (la caisse n'attend pas, même avec des milliers de ventes) ; numéro, perpétuels et empreinte sont posés sous un verrou des clôtures du lieu (`cloture-<schéma>`), qui revérifie qu'aucune J n'est née entre-temps. H / M / A : rapport hors verrou, numéro et empreinte sous le verrou des clôtures. Une tâche Celery **horaire** (`cron_clotures_automatiques`, `crontab(minute=0)`) remplace les quatre tâches J/H/M/A : pour chaque lieu, le filet J au seuil « heure de fermeture + 2 h » en heure locale (une J si la dernière finit avant le seuil courant et qu'il y a une vente depuis ; jamais une égalité d'heure), puis la semaine, le mois, l'année précédents en heure locale, calculés sur les ventes, jamais créés vides. Une seule chaîne de clôtures, tous niveaux : `hmac_hash` / `previous_hmac` (clé du lieu), `rapport_json` compris (`comptabilite/integrite.py`). `verify_clotures` vérifie cette chaîne et, pour chaque J, la chaîne des ventes de sa plage. Champs ajoutés : `point_de_vente` (informatif), `numero_premiere_vente`, `numero_derniere_vente`, `total_argent_recu`, `nombre_ventes_perpetuel`, `hmac_hash`, `previous_hmac` ; `hash_lignes` retiré. `Configuration.heure_de_fermeture` (défaut 02:00) dans l'onglet « Réglages ». Menu : « Rapport des ventes », « Ancien rapport caisse ». Plus de garde « modules billetterie / adhésion » : un lieu caisse seule a ses clôtures. /
The `comptabilite` closure becomes the venue's single closure, every origin, built on `RapportDesVentes`: sliding J under the sales lock; one hourly task with a local-time safety net at closing time + 2 h, then the previous calendar week / month / year in local time, computed on sales, never empty; one chain of closures (HMAC, stored report included); the audit command checks it; new closing-time setting; renamed menu entries; no module guard.

**Pourquoi / Why :** fiche F §3, tronc D19 (une seule clôture, chaînée) et D28 (la journée du Z ; filet à l'heure de fermeture + 2 h, heure locale). Les bornes calculées en heure du serveur et les tâches H/M/A à heure UTC fixe clôturaient avec un jour (ou un mois) de décalage les lieux loin de l'UTC. /
Sheet F §3, D19 and D28; server-time bounds and fixed-UTC tasks closed far-from-UTC venues a day (or a month) late.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/models.py` | champs de la clôture unique, `hash_lignes` retiré, aides en français |
| `comptabilite/integrite.py` (neuf) | `calculer_hmac_cloture`, `verifier_chaine_clotures` |
| `comptabilite/tasks.py` | J glissante en trois temps (fin sous le verrou des ventes, rapport hors verrou, création sous le verrou des clôtures), H/M/A en heure locale, pas de clôture vide, perpétuels, en-tête du rapport, `generer_les_clotures_automatiques(_du_lieu)` ; garde modules retirée ; J avec bornes → `ValueError` |
| `comptabilite/management/commands/generer_cloture.py` | J sans bornes (`CommandError` si données) ; message « rien à clôturer » |
| `comptabilite/management/commands/verify_clotures.py` | chaîne des clôtures + chaîne des ventes de chaque J, au lieu de `hash_lignes` |
| `TiBillet/celery.py` | une tâche horaire `cron_clotures_automatiques` au lieu de `cron_cloture_quotidienne / hebdomadaire / mensuelle / annuelle` |
| `BaseBillet/models.py` | `Configuration.heure_de_fermeture` |
| `BaseBillet/models_vente.py` | index `vente_statut_encaissement` |
| `Administration/admin_tenant.py` | champ `heure_de_fermeture` après `fuseau_horaire` |
| `Administration/admin/dashboard.py` | libellés « Rapport des ventes », « Ancien rapport caisse » |
| `Administration/management/commands/_demo_data_v2_ventes.py` | `seed_clotures_demo` sans bornes (J glissante, H précédente) ; le reset ne supprime plus de clôture (elles sont chaînées) ; `_bornes_cloture_demo` retirée |
| `tests/pytest/test_cloture_unique.py` (neuf) | 20 tests, schéma dédié (dont : deux passages de la tâche à la même heure → une J ; vente encaissée pendant le calcul → J suivante ; J créée par un autre appel pendant le calcul → rien) |
| `Administration/management/commands/demo_data_v2.py` | message « rien a cloturer (aucune vente) » au lieu de « skip (modules billetterie/adhesion off) » |
| `tests/pytest/test_comptabilite_celery.py` | **réécrit** : la tâche horaire remplace les tâches quotidienne et hebdomadaire (leurs tests retirés) ; les tests d'email passent en schéma dédié avec une J glissante (une J glissante sur le lieu `lespass` de la base de dev couvrirait toutes ses ventes) ; le patch du test « pas de config » vise `comptabilite.tasks.CeleryMailerClass` (l'ancien `BaseBillet.tasks.CeleryMailerClass` n'interceptait rien) |
| `tests/pytest/test_comptabilite_verify.py` | **réécrit** en schéma dédié : `hash_lignes` retiré → clôture altérée (`rapport_json`) détectée ; trou de numéro ; chaîne saine sans anomalie |
| `tests/pytest/test_menu_rapports.py` | les deux nouveaux libellés vérifiés |
| `tests/pytest/test_admin_configuration_onglets.py` | `heure_de_fermeture` ajouté à `CHAMPS_ATTENDUS` (nouveau champ exposé, voulu) ; commentaire « 25 champs » |
| `tests/pytest/test_comptabilite_service.py` | retrait de `test_generer_cloture_pour_tenant_cree_une_cloture` et `test_generer_cloture_idempotent` : ils testaient la tâche de clôture (J à bornes, `hash_lignes`, ancien rapport), désormais couverte par `test_cloture_unique.py` (test 14, « J sans vente ») ; le reste (ancien moteur) inchangé |

### Chaînes i18n / i18n strings
Nouveaux msgid (français) : « Heure de fermeture », « Heure locale de fermeture du lieu. Si personne n'a fait la clôture de la journée, elle est faite automatiquement deux heures après. », « Rapport des ventes », « Ancien rapport caisse », « Point de vente », « Poste depuis lequel la clôture a été lancée (pour information). », « Numéro de la première vente », « Numéro de la dernière vente », « Chiffre d'affaires TTC de la période. », « Argent reçu (centimes) », « Tout l'argent entré moins tout l'argent sorti sur la période. », « Nombre de ventes », « Nombre de ventes perpétuel », « Somme des nombres de ventes de toutes les clôtures journalières depuis la mise en service. », « Toutes les sections du rapport des ventes, figées au moment de la clôture. », « Empreinte », « Empreinte HMAC de la clôture, chaînée avec la clôture précédente. », « Empreinte précédente », et les deux aides réécrites de `niveau` et `total_perpetuel`. Workflow i18n à lancer par le mainteneur.

### Tests vus rouges / Tests seen red
Avant le code : `test_cloture_unique.py`, `test_comptabilite_verify.py`, `test_comptabilite_celery.py`, `test_menu_rapports.py` → **20 failed, 3 passed** (verts voulus : les deux tests d'email, comportement inchangé ; « chaîne saine », garde contre une fausse alerte). Causes : `comptabilite.integrite` absent, `generer_les_clotures_automatiques_du_lieu` absent, champs absents, J calendaire (`2026-03-09 00:00 != 2026-03-10 17:00`), J et M créées sans vente, lieu caisse seule sans J (garde modules), `cron_clotures_automatiques` absent, libellé « Rapport ventes en ligne ».
Après le code : ces fichiers + `test_admin_configuration_onglets.py` **29 passed** ; `test_comptabilite_service.py`, `test_rapport_unique.py`, comparaison, `test_vente_*.py`, `test_caracterisation_*.py`, `test_demo_data_ventes.py` **240 passed** ; `manage.py check` sans problème ; `makemigrations --check` : aucun changement.
Après la J en trois temps (verrou court) : les 5 fichiers de la session + `test_demo_data_ventes.py` + `test_rapport_unique.py` **96 passed** (3 tests ajoutés, verts à l'écriture : ils décrivent la J en trois temps déjà codée).
Lecteurs du rapport stocké (session F-2b, attendu) : `test_comptabilite_admin.py::test_admin_changeform_injecte_cloture_et_rapport` (failed), `test_comptabilite_exports.py` (6 errors), `test_comptabilite_csv_comptable.py` (8 errors) — leurs fixtures créent une J **à bornes** sur la base de dev (`ValueError`). `test_plan_comptable_unique.py` passe.

### Mutations (non jouées) — lignes actuelles
| Mutation | Test attendu rouge |
|---|---|
| `comptabilite/tasks.py` l.515-517 : `timezone.localtime(timezone.now(), UTC)` (filet à 4 h UTC) | `test_filet_4h_heure_locale_du_lieu` (la Martinique crée une J) |
| `comptabilite/tasks.py` l.335-339 : filet sur l'égalité d'heure (`maintenant_local.hour == seuil.hour`) | `test_filet_4h_heure_locale_du_lieu` (tâche de 5 h 30 : aucune J), `test_filet_4h_cree_la_j_seulement_s_il_y_a_des_ventes` (5 h) |
| `comptabilite/tasks.py` l.335-339 : `filet_deja_passe = False` (sans « dernière J avant le seuil ») | `test_filet_ne_cree_qu_une_j_par_jour_meme_avec_des_ventes_l_apres_midi`, `test_filet_4h_heure_locale_du_lieu`, `test_filet_suit_l_heure_de_fermeture_plus_deux_heures` |
| `comptabilite/tasks.py` l.418 : M = somme des J de la période | `test_mois_calendaire_egal_ventes_du_mois` (1050 au lieu de 350) |
| `comptabilite/tasks.py` l.474 (début du `tenant_context`) : garde « modules billetterie / adhésion » remise | `test_lieu_caisse_seule_a_ses_clotures` |
| `comptabilite/tasks.py` l.414-416 : condition « période sans vente » retirée | `test_mois_sans_vente_pas_de_cloture` |
| `comptabilite/tasks.py` l.421 : `del sections_du_rapport["caisse_especes"]` retiré | `test_cloture_h_m_a_sans_section_caisse_especes` |
| `comptabilite/integrite.py` l.97 : `rapport_json` hors du message | `test_cloture_chainee_et_alteration_detectee`, `test_verify_clotures_signale_une_cloture_alteree` |
| `comptabilite/tasks.py` l.284 : `previous_hmac=""` | `test_cloture_chainee_et_alteration_detectee`, `test_verify_clotures_chaine_saine_aucune_anomalie` |
| `comptabilite/tasks.py` l.259 : perpétuel non cumulé | `test_cloture_j_fin_de_service_plage_et_perpetuel` (350 au lieu de 1050) |
| `comptabilite/tasks.py` l.382-386 : `une_j_creee_entre_temps = False` (plus de revérification sous le verrou des clôtures) | `test_j_creee_par_un_autre_appel_pendant_le_calcul_rien_n_est_cree` (2 J) |
| `comptabilite/tasks.py` l.324 : verrou des ventes retiré (plage prise par date, sans verrou) | **non couverte** : il faut un encaissement réellement simultané (deux connexions), impossible dans un `TestCase` |
| `comptabilite/tasks.py` l.325 → après l.363 : fin fixée après le calcul du rapport | **non couverte** : l'heure est figée par le test (`timezone.now` remplacé), la fin ne change pas ; seule une horloge réelle et deux connexions le verraient |

## F-2b — Les lecteurs du rapport stocké : fiche admin, rapport temps réel, PDF, tableur, CSV, email / Readers of the stored report

**Migration :** Non. — **Chaînes i18n :** oui (liste plus bas).

### Resume / Summary
**Quoi / What :** tous les lecteurs de la clôture lisent la nouvelle forme de `rapport_json` (forme unique, Q-F1 : aucune lecture de l'ancienne). Un module neuf, `comptabilite/presentation.py`, prépare les sections une seule fois (`sections_pour_affichage`) ; la fiche de l'admin, le rapport temps réel, le PDF, le tableur et le CSV les écrivent toutes, dans l'ordre de la fiche §2 : l'essentiel (en-tête, chiffre d'affaires, règlements en trois blocs, caisse espèces si présente, réconciliation, offerts), puis, repliés dans des `<details>` à l'écran, l'annexe, les points, la marge brute, le détail, l'intégrité. La phrase de réconciliation est écrite à l'affichage, avec « − » et des montants positifs (« Argent reçu 5,00 € = ventes payées en argent 10,50 € + recharges 0,00 € − remboursements 3,50 € − cartes vidées 2,00 € + écarts d'encaissement 0,00 € ») ; les lignes dont le libellé dit que l'argent sort (avoirs, remboursements, espèces rendues, cartes vidées, jetons repris) s'écrivent en positif, les sommes nettes gardent leur signe. L'opérateur d'une correction, stocké par son identifiant, est affiché par son nom (nom complet, sinon email ; « compte supprimé » s'il n'existe plus). L'intégrité dit « OK » ou liste les anomalies (numéro de vente, raison) en rouge ; les écarts d'encaissement et la marge incomplète sont en rouge. Une seule fonction écrit un montant : `euros_a_la_francaise` (« 1 050,00 € », espaces insécables, signe « − » typographique). Le rapport temps réel lit `RapportDesVentes(debut, fin).rapport_x()` (habitus des cartes et opérateurs, sans intégrité). Le tableur écrit les montants en nombres (euros, format « € ») pour qu'on puisse les additionner. L'email de clôture montre « Chiffre d'affaires TTC » et « Ventes ». /
Every closure reader now reads the new `rapport_json` through one presentation module (`sections_pour_affichage`): admin page, real-time X report, PDF, spreadsheet, CSV, in the sheet's order, details folded; the reconciliation sentence with positive amounts after "−"; the operator's name instead of the stored id; integrity "OK" or the anomalies; one French amount formatter; numbers in the spreadsheet; the email shows the revenue incl. tax.

**Pourquoi / Why :** fiche F §2 (l'essentiel d'abord, le détail replié), SUIVI §4 (la phrase de réconciliation est écrite par l'affichage), §5 Q-F6 (le Z stocke l'identifiant de l'opérateur, l'écran retrouve son nom). Depuis F-2a, `rapport_json` a la forme de `RapportDesVentes` : les anciens lecteurs (clés `totaux_par_moyen`, `tva`, `detail_ventes`…) affichaient des sections vides. /
Sheet F §2, SUIVI §4 and Q-F6; since F-2a the old readers showed empty sections.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/presentation.py` (neuf) | `euros_a_la_francaise`, `quantite_lisible`, `phrase_de_reconciliation`, `sections_pour_affichage` (une fonction par section, nom de l'opérateur en une requête) |
| `comptabilite/admin.py` | `changeform_view` passe `sections` ; `rapport_temps_reel` lit `RapportDesVentes(...).rapport_x()` (plus `RapportComptableService`), passe `rapport`, `sections`, `nombre_de_ventes` ; colonne « Chiffre d'affaires TTC » à la française ; `_format_euros` et l'import de `enrichir_rapport_pour_affichage` retirés |
| `comptabilite/pdf.py` | `html_du_pdf_de_la_cloture` (testable) + `generer_pdf_cloture` ; plus d'`aplatir_detail_ventes` / `enrichir_rapport_pour_affichage` |
| `comptabilite/excel_export.py` | les sections, montants en nombres (format `#,##0.00 "€"`), alertes en rouge ; titre « Clôture n° … » et empreinte de la clôture |
| `comptabilite/csv_export.py` | les sections (« [Titre] », phrase, tableaux), montants à la française ; empreinte de la clôture au lieu de `hash_lignes` (retiré en F-2a) |
| `comptabilite/tasks.py` (mail seulement) | `chiffre_affaires_ttc_en_euros` (`euros_a_la_francaise(total_general)`) ; sujet « Clôture … n° … » |
| `comptabilite/templates/comptabilite/admin/_sections_rapport.html` | réécrit : boucle sur `sections`, `<section>` + carte Unfold pour l'essentiel, `<details>` pour le reste, styles inline |
| `comptabilite/templates/comptabilite/admin/_contenu_section_rapport.html` (neuf) | phrase et tableaux d'une section (`data-testid`, `scope="col"`, rouge pour les alertes) |
| `comptabilite/templates/comptabilite/admin/change_form_before.html` | carte « Synthèse » (qui lisait `hash_lignes`) retirée : l'en-tête est la 1ʳᵉ section ; empreinte `hmac_hash` affichée ; icônes `aria-hidden` |
| `comptabilite/templates/comptabilite/views/rapport_temps_reel.html` | « Ventes » (`nombre_de_ventes`) au lieu de « Transactions » |
| `comptabilite/templates/comptabilite/pdf/rapport_comptable.html` | réécrit : toutes les sections dépliées ; pied = empreinte de la clôture |
| `comptabilite/templates/comptabilite/email/cloture_rapport_email.html` | « Chiffre d'affaires TTC », « Ventes », montant à la française |
| `tests/pytest/test_comptabilite_admin.py` | **réécrit** en schéma dédié (`test_comptabilite_admin`), vraies ventes par le service, J glissante : la fixture créait une J à bornes sur la base de dev (refusée depuis F-2a). Les tests de création / unicité de `ClotureCaisse` dans la base de dev sont retirés (couverts par `test_cloture_unique.py`, et ils écrivaient dans la base de dev) ; le test du gabarit sur l'ancienne forme (`totaux_par_moyen`, `infos_legales`) est remplacé ; les clés `cloture_total_*_euros` ne sont plus attendues (montants écrits par la présentation). 12 tests neufs : ordre des sections, `<section>` / `<details>`, M sans caisse espèces, phrase de réconciliation, opérateur (nom, email, compte supprimé), intégrité OK / anomalies, temps réel sur le moteur unique, habitus et opérateurs sans intégrité, montants à la française |
| `tests/pytest/test_comptabilite_exports.py` | **réécrit** en schéma dédié (`test_comptabilite_exports`), scénario mêlé (espèces, CB, monnaie locale, avoir, carte vidée) puis J glissante (même raison). Les tests « le fichier existe » deviennent : toutes les sections dans l'ordre (CSV, tableur, PDF), totaux = rapport stocké, tableur en nombres, vrai PDF, email (chiffre d'affaires TTC) ; FEC et CSV comptable : la forme du fichier seulement (contenu : F-3), sans passer par le client HTTP |
| `tests/pytest/test_comptabilite_csv_comptable.py` | **réécrit** en schéma dédié (`test_comptabilite_csv_comptable`), deux ventes et une J glissante (même raison) ; les 9 tests de forme gardés tels quels |

### Chaînes i18n / i18n strings
Nouveaux msgid (français), à traduire par le workflow i18n du mainteneur :
- `comptabilite/presentation.py` : titres de section (« En-tête », « Chiffre d'affaires », « Règlements », « Caisse espèces », « Réconciliation », « Offerts », « Annexe : avoirs, recharges, écarts, corrections », « Points », « Marge brute », « Détail des ventes », « Intégrité », « Habitus des cartes », « Opérateurs ») ; titres de tableau (« Par taux de TVA », « Par catégorie », « Par origine », « Par journal », « Argent », « Cashless », « Hors argent », « Points par monnaie », « Par produit », « Avoirs », « Recharges et cartes », « Écarts d'encaissement », « Corrections de moyen de paiement », « Billets », « Adhésions », « Ventes par produit ») ; colonnes (« Libellé », « Valeur », « Montant », « Nombre », « TTC », « HT », « TVA », « Taux », « Catégorie », « Origine », « Journal », « Moyen », « Monnaie », « Produit », « Quantité », « Valeur catalogue », « Coût d'achat », « Numéro de vente », « Moyen avant », « Moyen après », « Opérateur », « Événement », « Date », « Tarif », « Offert », « Raison », « dont offerts ») ; libellés (« Lieu », « Niveau », « Numéro de clôture », « Début », « Fin », « Ventes », « n° %(premier)s à %(dernier)s », « Aucune vente », « Nombre de ventes », « dont ventes gratuites », « Total perpétuel », « Nombre de ventes perpétuel », « Chiffre d'affaires TTC », « Chiffre d'affaires HT », « Total argent », « Total cashless », « Fond de caisse », « Espèces reçues », « Espèces rendues », « Sorties de caisse », « Solde théorique », « Argent reçu », « Ventes payées en argent », « Recharges », « Remboursements », « Cartes vidées », « Quantité offerte », « Valeur catalogue offerte », « dont %(moyen)s », « dont retours consigne », « dont remboursements Stripe à faire à la main », « Recharges encaissées », « Cadeau émis », « dont espèces rendues », « dont jetons cadeau repris », « Sans opérateur », « compte supprimé », « Marge brute », « Nombre de cartes », « Total des dépenses », « Panier moyen », « Dépense médiane », « Recharge médiane », « Reste moyen sur carte », « Reste médian sur carte », « Nouveaux membres », « Argent ») ; phrase (« ventes payées en argent », « recharges », « remboursements », « cartes vidées », « écarts d'encaissement ») ; phrases (« Aucune vente en points ou en temps. », « Aucune vente sur cette période. », « Marge incomplète : %(nombre)s article(s) sans prix d'achat. » (singulier / pluriel), « %(nombre)s anomalie(s) dans la chaîne des ventes. » (singulier / pluriel)) ;
- `comptabilite/excel_export.py`, `csv_export.py` : « Clôture n° %(numero)s — %(niveau)s », « Empreinte de la clôture », « Rapport de clôture », « Numéro de clôture » ;
- gabarits : « Empreinte de la clôture », « Ventes », « Chiffre d'affaires TTC », « Clôture {{ niveau }} n° {{ numero }}. », « Clôture n° {{ numero }} », « Clôture n° {{ numero }} — {{ niveau }} » ; `admin.py` : « Chiffre d'affaires TTC » (colonne).

### Tests vus rouges / Tests seen red
Avant le code (tests écrits, module absent) : `test_comptabilite_admin.py` et `test_comptabilite_exports.py` → **2 errors** à la collecte (`ModuleNotFoundError: No module named 'comptabilite.presentation'`, `ImportError: cannot import name 'html_du_pdf_de_la_cloture'`) ; `test_comptabilite_csv_comptable.py` → **9 passed** (forme seulement, verte voulue : la fixture est la seule chose changée). Module de présentation écrit, admin pas encore branché : `test_comptabilite_admin.py` → **10 failed, 7 passed** (`KeyError: 'sections'`, `KeyError: 'chiffre_affaires'` sur le rapport temps réel encore sur l'ancien service, phrase / « compte supprimé » / « 4242 » absents de l'ancien gabarit).
Après le code : les trois fichiers + `test_cloture_unique.py`, `test_rapport_unique.py`, `test_comptabilite_celery.py` **118 passed** ; avec `test_comptabilite_verify.py`, `test_comptabilite_service.py`, `test_menu_rapports.py`, `test_plan_comptable_unique.py`, `test_demo_data_ventes.py`, `test_rapport_unique_comparaison.py` **230 passed** ; `manage.py check` sans problème.

### Mutations (non jouées) — lignes actuelles
| Mutation | Test attendu rouge |
|---|---|
| `comptabilite/presentation.py` l.721 : `euros_a_la_francaise(reconciliation["remboursements_en_centimes"])` (montant négatif dans la phrase) | `test_phrase_de_reconciliation_montants_positifs_avec_moins`, `test_csv_totaux_egaux_au_rapport`, `test_pdf_totaux_egaux_au_rapport` |
| `comptabilite/presentation.py` l.676 : `montant_a_ecrire = montant_du_rapport` (signe d'un terme « − » perdu) | les trois mêmes |
| `comptabilite/presentation.py` l.975 : `nom_de_l_operateur = identifiant_de_l_operateur` (opérateur par son uuid) | `test_operateur_d_une_correction_affiche_par_son_nom`, `test_operateur_sans_nom_affiche_par_son_email` |
| `comptabilite/presentation.py` l.977 : `nom_de_l_operateur = identifiant_de_l_operateur` | `test_operateur_disparu_affiche_compte_supprime` |
| `comptabilite/tasks.py` l.422 : `del sections_du_rapport["caisse_especes"]` retiré (section 4 en M) | `test_section_caisse_especes_absente_d_une_m` (et `test_cloture_h_m_a_sans_section_caisse_especes`) |
| `comptabilite/admin.py` l.270 : `RapportComptableService(datetime_debut, datetime_fin).generer_rapport_complet()` (temps réel sur l'ancien service) | `test_rapport_temps_reel_lit_le_moteur_unique`, `test_rapport_temps_reel_montre_habitus_et_operateurs_sans_integrite` |
| `comptabilite/csv_export.py` l.43 : `if section["repliee"]: continue` (CSV qui oublie l'annexe et la suite) | `test_csv_contient_toutes_les_sections_dans_l_ordre` |
| `comptabilite/excel_export.py` l.118 : `for section in sections[:-1]:` (tableur sans l'intégrité) | `test_tableur_contient_toutes_les_sections_dans_l_ordre` |
| `comptabilite/templates/comptabilite/pdf/rapport_comptable.html` l.36 : `{% for section in sections %}{% if not section.repliee %}` … (PDF sans le détail) | `test_pdf_contient_toutes_les_sections_dans_l_ordre` |
| `comptabilite/excel_export.py` l.81 : `value=cellule_du_rapport["texte"]` (montant en texte) | `test_tableur_totaux_en_nombres_egaux_au_rapport` |
| `comptabilite/presentation.py` l.117 : `return f"{signe}{partie_entiere_avec_milliers}"` (montant sans les centimes) | `test_montant_a_la_francaise_avec_centimes_et_milliers`, et tous les tests de totaux |
| `comptabilite/tasks.py` l.631 : `euros_a_la_francaise(cloture.total_argent_recu)` | `test_email_de_cloture_montre_le_chiffre_d_affaires_ttc` (10,50 € au lieu de 17,50 €) |

## F-2c — Corrections de la relecture de la clôture / Closure review fixes

**Migration :** Non — **Chaînes i18n :** oui, 1 (« Réinitialiser (service en cours : depuis la dernière clôture journalière) », remplace « Réinitialiser (aujourd'hui 04:00 → maintenant) »).

### Resume / Summary
**Quoi / What :** (1) le filet automatique fait le Z que personne n'a fait, sans couper le service suivant : il ne crée une J que s'il y a des ventes dans [fin de la dernière J, seuil[, et cette J **finit au seuil** (un Z demandé garde « maintenant ») ; (2) le seuil est comparé en UTC (nuits de changement d'heure : pas de J qui finit dans le futur, pas de seconde J, pas de J retardée) ; (3) la tâche horaire envoie une sous-tâche Celery par lieu, chaque envoi et chaque sous-tâche journalise son erreur avec le schéma du lieu ; (4) les clôtures H / M / A ne calculent ni ne stockent plus l'intégrité (ni la caisse espèces) ; (5) « période déjà clôturée » : vue avant le calcul et sous le verrou, une seule fois chacune (la double vérification de la tâche horaire est retirée) ; une période déjà clôturée rend None ; (6) la J refuse d'être créée dans une transaction ouverte (`atomic(durable=True)`) ; (7) `generer_cloture` : une erreur dans un lieu n'arrête pas les autres (code de sortie non nul à la fin), bornes sans fuseau refusées, bornes H / M / A qui ne sont pas la période du lieu en heure locale refusées ; (8) `verify_clotures` vérifie la continuité des J (la J n+1 commence où la J n finit ; sa première vente suit la dernière de la J n) ; (9) rapport temps réel : période par défaut = le service en cours (depuis la fin de la dernière J, sinon la première vente), heures saisies et affichées en heure du lieu ; (10) références de session retirées de `test_comptabilite_admin.py`. /
The net closes the Z nobody made without cutting the next service (ends at the threshold); UTC comparisons on DST nights; one Celery sub-task per venue; no integrity in H / M / A; single already-closed check; J refused inside an open transaction; robust command with checked bounds; J continuity in the audit; real-time report in the venue's time zone, from the last J.

**Pourquoi / Why :** relecture Opus de F-2a + F-2b (SUIVI §4) : la règle du filet coupait un service en deux (une vente à 18 h après un Z déclenchait une J à 19 h), contraire à D28 ; tâche horaire séquentielle sous la limite de temps de Celery ; intégrité d'une année recalculée vente par vente ; heures du serveur dans le rapport temps réel. /
Opus review: the net rule cut a service in two (against D28); sequential hourly task; yearly integrity recomputed per sale; server time in the real-time report.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/tasks.py` | filet : fin = seuil, ventes dans [debut, seuil[ ; seuil en UTC (`FUSEAU_UTC`) ; temps 1 en `atomic(durable=True)` ; sections H / M / A sans caisse espèces ni intégrité (non calculées) ; « déjà clôturée » → None ; `_bornes_donnees_verifiees` (fuseau, période locale) ; `generer_les_clotures_automatiques_du_lieu` en `@shared_task` avec `try/except` journalisé ; une sous-tâche `.delay` par lieu |
| `comptabilite/integrite.py` | `verifier_continuite_des_journees` |
| `comptabilite/management/commands/generer_cloture.py` | erreur par lieu journalisée, `CommandError` à la fin ; message « déjà clôturée » |
| `comptabilite/management/commands/verify_clotures.py` | continuité des J |
| `comptabilite/admin.py` | `rapport_temps_reel` : période depuis la dernière J (ou la première vente), heures du lieu ; `_parse_datetime_param(..., fuseau_du_lieu)` |
| `comptabilite/templates/comptabilite/views/rapport_temps_reel.html` | période affichée en heure du lieu (formatée par la vue) ; libellé « Réinitialiser » |
| `TiBillet/celery.py` | docstring (sous-tâches) |
| `tests/pytest/test_cloture_unique.py` | 15 adapté (vente après le seuil → J du lendemain) ; ajoutés : J du filet finit au seuil, Z puis vente du soir, première vente à 18 h, nuit d'été, nuit d'hiver, J refusée dans une transaction, erreur journalisée d'un lieu, H/M/A sans intégrité, 4 tests de la commande ; en-tête des règles |
| `tests/pytest/test_comptabilite_celery.py` | sous-tâche par lieu ; erreur d'un lieu journalisée, les autres envoyés |
| `tests/pytest/test_comptabilite_verify.py` | deux tests de continuité des J |
| `tests/pytest/test_comptabilite_admin.py` | période par défaut depuis la dernière J / la première vente ; heures du lieu (Martinique) ; aide `_rapport_temps_reel` en heure du lieu ; « SUIVI §4 et §5, Q-F6 » et « Q-F6 » remplacés par la règle |

### Tests vus rouges / Tests seen red
Avant le code : `test_cloture_unique.py`, `test_comptabilite_celery.py`, `test_comptabilite_verify.py`, `test_comptabilite_admin.py` → **22 failed, 37 passed**. Causes : intégrité stockée dans la M ; `RuntimeError not raised` ; J créées à 5 h / 19 h (`2 != 1`, `1 != 0`) ; J du filet finie à 5 h 30 au lieu de 4 h ; nuits de changement d'heure (`1 != 0`) ; commande sans refus (`unexpectedly None`), erreur d'un lieu qui arrête tout (`RuntimeError: panne simulée`) ; aucun journal d'erreur ; sous-tâches non envoyées (`set() == {…}`) ; continuité absente de `verify_clotures` ; rapport temps réel : début à 4 h UTC, heure saisie lue en UTC. Verts d'emblée : « accepte le mois du lieu », « deux appels à la même heure » (gardes).
Après le code : les 4 fichiers **59 passed** ; `test_comptabilite_exports.py`, `test_rapport_unique.py`, `test_demo_data_ventes.py`, `test_comptabilite_csv_comptable.py`, `test_menu_rapports.py`, `test_admin_configuration_onglets.py` **92 passed** ; `manage.py check` sans problème.

### Mutations (non jouées) — lignes actuelles
| Mutation | Test attendu rouge |
|---|---|
| `comptabilite/tasks.py` l.360 : `fin = timezone.now()` en mode filet (le filet coupe le service) | `test_filet_4h_cree_la_j_seulement_s_il_y_a_des_ventes`, `test_la_j_du_filet_finit_au_seuil`, `test_filet_apres_un_z_la_vente_du_lendemain_soir_attend_le_seuil_suivant`, `test_premiere_vente_du_lieu_a_18h_aucune_j_avant_le_seuil` |
| `comptabilite/tasks.py` l.188 : comparaison à l'horloge (`maintenant_local >= datetime.combine(…)`) | `test_filet_nuit_du_passage_a_l_heure_d_ete_une_seule_j`, `test_filet_nuit_du_passage_a_l_heure_d_hiver_une_seule_j` |
| `comptabilite/tasks.py` l.354 : `atomic()` au lieu de `atomic(durable=True)` | `test_cloture_j_refusee_dans_une_transaction_ouverte` |
| `comptabilite/tasks.py` l.466-476 : ajouter `"integrite": rapport_de_la_periode.section_integrite()` | `test_cloture_h_m_a_sans_section_integrite`, `test_cloture_h_m_a_sans_section_caisse_especes` |
| `comptabilite/tasks.py` l.683 : appel direct `generer_les_clotures_automatiques_du_lieu(schema_name)` | `test_cron_clotures_automatiques_lance_une_sous_tache_par_lieu` |
| `comptabilite/tasks.py` l.682-688 : `try/except` de l'envoi retiré | `test_cron_une_erreur_dans_un_lieu_est_journalisee_et_n_empeche_pas_les_autres` |
| `comptabilite/tasks.py` l.656-658 : `try/except` de la sous-tâche retiré | `test_tache_d_un_lieu_journalise_son_erreur_avec_le_nom_du_lieu` |
| `comptabilite/tasks.py` l.580-586 : garde « borne sans fuseau » retirée | `test_generer_cloture_refuse_des_bornes_sans_fuseau` |
| `comptabilite/tasks.py` l.593-600 : garde « période du lieu » retirée | `test_generer_cloture_refuse_un_mois_qui_n_est_pas_celui_du_lieu` |
| `generer_cloture.py` l.97-101 : `try/except` par lieu retiré | `test_generer_cloture_une_erreur_dans_un_lieu_n_arrete_pas_les_autres` |
| `generer_cloture.py` l.112-115 : `CommandError` finale retirée | `test_generer_cloture_une_erreur_dans_un_lieu_n_arrete_pas_les_autres`, les deux tests de refus |
| `comptabilite/integrite.py` l.144 : condition de début retirée | `test_verify_clotures_signale_une_j_qui_ne_commence_pas_a_la_fin_de_la_precedente` |
| `comptabilite/integrite.py` l.165 : condition de première vente retirée | `test_verify_clotures_signale_une_j_dont_la_premiere_vente_ne_suit_pas` |
| `comptabilite/admin.py` l.265 : `debut_defaut = fin_defaut` (sans la dernière J) | `test_rapport_temps_reel_bornes_par_defaut_depuis_la_derniere_j` |
| `comptabilite/admin.py` l.271 : `debut_defaut = fin_defaut` (sans la première vente) | `test_rapport_temps_reel_sans_j_commence_a_la_premiere_vente` |
| `comptabilite/admin.py` l.59 : `timezone.get_current_timezone()` (heure du serveur) | `test_rapport_temps_reel_heures_du_lieu`, `test_rapport_temps_reel_lit_le_moteur_unique` |
| `comptabilite/admin.py` l.312 : `localtime(datetime_debut)` sans le fuseau du lieu | `test_rapport_temps_reel_heures_du_lieu` |
| `comptabilite/tasks.py` l.481-485 : revérification « déjà clôturée » sous le verrou retirée | **non couverte** : il faut deux appels réellement simultanés (deux connexions) |

## F-2d — Corrections de la relecture des lecteurs ; mentions légales dans le Z / Readers review fixes; legal mentions in the Z

**Migration :** Non. — **Chaînes i18n :** oui (liste plus bas).

### Resume / Summary
**Quoi / What :** (Q-F13) l'en-tête du rapport (`section_en_tete`) porte les **mentions légales** du lieu, lues dans `Configuration` au moment du calcul (organisation, adresse = rue de l'adresse postale, code postal, ville, SIREN, numéro de TVA, email, téléphone ; vide = "") : elles sont figées dans le Z et affichées par tous les lecteurs (fiche, rapport X, PDF, tableur, CSV ; une mention vide s'écrit « — »). (I1) `rapport_json` est un `jsonb`, qui ne garde pas l'ordre des clés : l'affichage trie toujours (produits, catégories, adhésions, offerts, opérateurs par nom ; événements par date puis nom ; tarifs par nom ; moyens et monnaies par libellé ; taux par valeur ; journaux par code ; à égalité, par clé). (M6) la phrase de réconciliation est UN seul `gettext` à variables nommées. (M8) `STATUT_INTEGRITE_OK` importé du rapport. (M9) « Compte supprimé » avec majuscule ; titre de la feuille du tableur traduit ; `<html lang>` du PDF = langue active ; heures du mail et date du nom des fichiers exportés (PDF, tableur, CSV) en heure du lieu. (M10) un texte qui commence par `=`, `+`, `-` ou `@` n'est jamais une formule : dans le CSV, il est précédé d'une apostrophe (usage habituel) ; dans le tableur, il reste tel quel dans une case de type texte qui porte le marqueur natif d'Excel (`quotePrefix`), sans apostrophe visible. (M11) le tableau des écarts d'encaissement en alerte porte aussi le texte « Attention : écart d'encaissement » (fiche, PDF, tableur, CSV). Un compte négatif s'écrit avec le signe « − » des montants. /
Legal mentions stored in the Z header and shown by every reader; stable display order whatever the jsonb key order; one translatable reconciliation sentence; venue-time email hours and file names; PDF language; formula protection in exports; a text next to the red gap alert.

**Pourquoi / Why :** décision du mainteneur Q-F13 (les mentions légales d'un Z sont figées avec lui) ; relecture Opus de F-2a + F-2b (I1, M6, M8-M11). /
Maintainer decision Q-F13; Opus review of F-2a + F-2b.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/rapport.py` (`section_en_tete` seulement) | clé `mentions_legales` (8 textes, lus dans `Configuration`) |
| `comptabilite/presentation.py` | mentions dans l'en-tête ; `_valeurs_triees`, `_evenements_tries_par_date` (tri de chaque liste) ; phrase à un seul `gettext` ; `STATUT_INTEGRITE_OK` importé ; « Compte supprimé » ; `commence_comme_une_formule`, `texte_sans_formule` (CSV) ; `nom_du_fichier_de_la_cloture` (date en heure du lieu) ; `message_d_alerte` des écarts ; compte négatif avec « − » |
| `comptabilite/pdf.py` | nom du fichier en heure du lieu |
| `comptabilite/excel_export.py` | réécrit en noms verbeux (`classeur`, `feuille`, `case`, `numero_de_ligne`) ; un texte qui commence comme une formule : case de type texte + `quotePrefix` (marqueur natif d'Excel, sans apostrophe visible) ; feuille « Rapport » traduite ; message d'alerte ; nom du fichier en heure du lieu |
| `comptabilite/csv_export.py` | textes protégés contre les formules (`_ecrire_une_ligne`) ; message d'alerte ; nom du fichier en heure du lieu ; BOM nommé |
| `comptabilite/tasks.py` (mail seulement) | `debut_en_heure_du_lieu`, `fin_en_heure_du_lieu` dans le contexte du mail |
| `comptabilite/templates/comptabilite/admin/_contenu_section_rapport.html` | message d'alerte écrit (icône `aria-hidden`) |
| `comptabilite/templates/comptabilite/pdf/rapport_comptable.html` | `lang` = langue active ; message d'alerte |
| `comptabilite/templates/comptabilite/email/cloture_rapport_email.html` | période en heure du lieu |
| `tests/pytest/test_rapport_unique.py` | 2 tests : mentions légales dans l'en-tête ; mentions vides = "" (la configuration est remise à la fin du test : son cache survit à l'annulation) |
| `tests/pytest/test_comptabilite_admin.py` | `setUp` écrit les mentions (cache) ; « Compte supprimé » attendu avec majuscule (M9) ; 2 tests : mentions affichées et figées après un changement d'adresse ; texte d'alerte des écarts |
| `tests/pytest/test_comptabilite_exports.py` | `setUp` écrit une adresse postale et les mentions ; aides `cloture=` optionnel ; 10 tests : mentions dans le PDF, dans le tableur et le CSV ; chaîne des clôtures saine après le scénario mêlé (`verifier_chaine_clotures == []`) ; ordre produits / événements après la base (fiche, PDF, tableur, CSV) ; « =1+1 » dans le CSV (apostrophe) et dans le tableur (valeur « =1+1 », `data_type == "s"`, `quotePrefix`, aucune case formule) ; `lang` du PDF ; mail en heure du lieu ; nom des fichiers en heure du lieu |
| `tests/pytest/test_cloture_unique.py` | docstring de `test_mois_sans_vente_pas_de_cloture` : la règle (« une période sans vente n'a jamais de clôture ») au lieu d'une référence à une décision |

### Chaînes i18n / i18n strings
Nouveaux msgid : « Adresse », « Code postal », « Ville », « SIREN / SIRET », « Numéro de TVA », « Email », « Téléphone », « Attention : écart d'encaissement », « Rapport » (feuille du tableur), « Compte supprimé » (remplace « compte supprimé »), la phrase « Argent reçu %(argent_recu)s = ventes payées en argent %(ventes_payees_en_argent)s %(signe_recharges)s recharges %(recharges)s %(signe_remboursements)s remboursements %(remboursements)s %(signe_cartes_videes)s cartes vidées %(cartes_videes)s %(signe_ecarts)s écarts d'encaissement %(ecarts)s » (remplace « Argent reçu », « ventes payées en argent », « recharges », « remboursements », « cartes vidées », « écarts d'encaissement » en minuscules, qui ne servent plus dans la phrase). Workflow i18n à lancer par le mainteneur.

### Tests vus rouges / Tests seen red
Avant le code (tests F-2d sélectionnés par `-k`) : **12 failed, 7 passed** — `KeyError: 'mentions_legales'` (×2), SIREN / adresse absents (fiche, PDF, CSV), « Compte supprimé » absent, « Attention : écart d'encaissement » absent, `'03/10/2026 11:37'` (heure de Martinique) absent du mail, `'cloture-2-20261005.csv' == 'cloture-2-20261004.csv'`, `<html lang="en">` absent, ordre de la fiche `64080 < 59192` (Abricot après Banane), `'=1+1` absent. Vert voulu : la chaîne des clôtures saine (contrôle de bout en bout).
Après le code : `test_comptabilite_admin.py`, `test_comptabilite_exports.py`, `test_comptabilite_csv_comptable.py`, `test_rapport_unique.py`, `test_cloture_unique.py` **141 passed** ; après la retouche (marqueur natif du tableur, test « =1+1 » coupé en deux, références de décision retirées du code) **142 passed** ; `test_comptabilite_celery.py`, `_verify`, `_service`, `test_menu_rapports.py`, `test_plan_comptable_unique.py`, `test_demo_data_ventes.py`, `test_rapport_unique_comparaison.py` **118 passed** ; `manage.py check` sans problème.

### Mutations (non jouées) — lignes actuelles
| Mutation | Test attendu rouge |
|---|---|
| `comptabilite/rapport.py` l.424 : clé `mentions_legales` retirée | `test_en_tete_porte_les_mentions_legales_du_lieu`, et tous les lecteurs (`KeyError`) |
| `comptabilite/rapport.py` l.399 : `"ville": ""` | `test_en_tete_porte_les_mentions_legales_du_lieu`, `test_mentions_legales_affichees_et_figees_dans_le_z`, `test_pdf_imprime_les_mentions_legales_du_lieu` |
| `comptabilite/presentation.py` l.436 : mention lue dans `Configuration.get_solo()` au lieu du Z | `test_mentions_legales_affichees_et_figees_dans_le_z` |
| `comptabilite/presentation.py` l.320 : tri retiré (`sort` supprimé) | `test_ordre_des_produits_et_des_evenements_stable_apres_la_base` |
| `comptabilite/presentation.py` l.1260 : `detail["billets"].values()` | le même (Zénith / Atelier) |
| `comptabilite/presentation.py` l.1311 : `detail["ventes_par_produit"].values()` | le même (Abricot / Banane) |
| `comptabilite/presentation.py` l.180 : `return texte` (plus d'apostrophe) | `test_csv_un_nom_qui_commence_par_egal_est_precede_d_une_apostrophe` |
| `comptabilite/csv_export.py` l.45 : `append(texte)` | le même |
| `comptabilite/excel_export.py` l.77 : `case.data_type = "s"` retiré (la case reste une formule) | `test_tableur_un_nom_qui_commence_par_egal_est_un_texte_jamais_une_formule` |
| `comptabilite/excel_export.py` l.78 : `case.quotePrefix = True` retiré | le même |
| `comptabilite/excel_export.py` l.72 : `value=texte_sans_formule(texte)` (apostrophe visible) | le même |
| `comptabilite/presentation.py` l.195 : `cloture.datetime_fin` sans le fuseau du lieu | `test_nom_des_fichiers_date_en_heure_du_lieu` |
| `comptabilite/tasks.py` l.752 : `timezone.localtime(cloture.datetime_debut)` (heure du serveur) | `test_email_de_cloture_en_heure_du_lieu` |
| `pdf/rapport_comptable.html` l.15 : `lang="fr"` | `test_pdf_porte_la_langue_active` |
| `comptabilite/presentation.py` l.1068 : `message_des_ecarts = ""` | `test_ecart_d_encaissement_en_alerte_porte_un_texte` |
| `admin/_contenu_section_rapport.html` l.30-37 : bloc du message retiré | le même |
| `comptabilite/presentation.py` l.1114 : « compte supprimé » | `test_operateur_disparu_affiche_compte_supprime` |
| phrase en morceaux (M6), import de `STATUT_INTEGRITE_OK` (M8), titre de feuille traduit (M9) | **non couvertes** : le résultat français est identique ; seule une traduction anglaise compilée le verrait |

## F-2e — Corrections de la relecture Fable : H / M / A après le filet, rattrapage, barrière, fuseau figé, libellés / Fable review fixes

**Migration :** Non. — **Chaînes i18n :** oui (liste plus bas).

### Resume / Summary
**Quoi / What :** (M-1) une H / M / A n'est créée qu'après le filet du jour où elle finit (le seuil de ce jour-là : fermeture + 2 h) : la J de la dernière soirée est créée avant elle, et la H / M / A porte les perpétuels de cette J ; vaut aussi pour la commande `generer_cloture`. (M-2) la tâche horaire crée toutes les périodes finies qui manquent depuis la dernière clôture du niveau (sinon depuis la première vente du lieu), dans l'ordre chronologique. (I-2) juste avant le calcul d'une H / M / A, le verrou des ventes du lieu est pris puis relâché dans une transaction courte et durable : un encaissement commencé avant est terminé ; une H / M / A demandée dans une transaction ouverte lève `RuntimeError`. (M-5) l'en-tête stocke le nom du fuseau du lieu au calcul (`fuseau_horaire`) ; un Z s'affiche dans ce fuseau (repli : le fuseau actuel). (M-4) un Z sans mentions légales s'affiche (« — »). (M-6) l'en-tête dit « Opérations numérotées », puis « dont avoirs », « dont cartes vidées », « dont corrections » (lus dans l'annexe) au lieu de « Nombre de ventes ». (M-7) l'offert des règlements s'appelle « Offert (bouton OFFRIR et cadeaux émis) ». (M-3) les jetons cadeau repris s'écrivent tels quels (sans `abs()`). (I-1) les gabarits de page (`change_form_before.html`, `rapport_temps_reel.html`) sont rendus par des tests. djc : tri par une fonction du module (plus de fonction dans une fonction) ; `envoyer_email_cloture` en commentaires FR puis EN et `for` simple ; commentaires du test de l'email FR puis EN. /
Periods closed after the net of their last day, every missing period caught up, a barrier on the sales lock, the time zone frozen in the Z, clearer labels, page templates rendered by tests.

**Pourquoi / Why :** relecture Fable intermédiaire de F-1 et F-2 (I-1, I-2, M-1 à M-9) et décisions de l'orchestrateur. /
Intermediate Fable review of F-1 and F-2.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/tasks.py` | `_bornes_de_la_periode_qui_contient` (la période précédente s'en déduit) ; `_seuil_du_filet_d_un_jour` (partagé avec le seuil courant) ; `_filet_du_jour_de_la_fin_passe` ; `_creer_la_cloture_d_une_periode` : filet du jour de la fin, barrière `atomic(durable=True)` + verrou des ventes ; `_periodes_finies_a_cloturer` et boucle de rattrapage dans `generer_les_clotures_automatiques_du_lieu` ; `envoyer_email_cloture` (commentaires, `for`) ; docstrings |
| `comptabilite/rapport.py` (`section_en_tete` seulement) | clé `fuseau_horaire` |
| `comptabilite/presentation.py` | `_fuseau_d_affichage_du_rapport` ; `mentions_legales` avec repli ; lignes « Opérations numérotées », « dont avoirs / cartes vidées / corrections » ; « Offert (bouton OFFRIR et cadeaux émis) » ; jetons repris sans `abs()` ; `_criteres_de_tri_d_un_element` au niveau du module |
| `tests/pytest/test_cloture_unique.py` | test 17 adapté (aucune H à 1 h 10, la H à 4 h 10) ; 6 tests : M de fin de mois après la J de la dernière soirée, M demandée trop tôt, trois H rattrapées dans l'ordre, H depuis la première vente, décembre et année au 1ᵉʳ janvier, H / M / A refusée dans une transaction ouverte |
| `tests/pytest/test_comptabilite_admin.py` | 9 tests : gabarit de la fiche d'une J et d'une M, gabarit du rapport temps réel rendu par la vue, opérations numérotées, offert des règlements, Z sans mentions légales, fuseau figé, repli du fuseau, jetons repris tels quels |
| `tests/pytest/test_rapport_unique.py` | contrat de l'en-tête ; 1 test : `fuseau_horaire` dans l'en-tête |
| `tests/pytest/test_comptabilite_celery.py` | commentaires FR puis EN |

### Chaînes i18n / i18n strings
Nouveaux msgid : « Opérations numérotées », « dont avoirs », « dont cartes vidées », « dont corrections », « Offert (bouton OFFRIR et cadeaux émis) ». « Nombre de ventes » et « Offert » restent utilisés ailleurs (opérateurs du rapport X, détail par produit). Workflow i18n à lancer par le mainteneur.

### Tests vus rouges / Tests seen red
Avant le code (sélection `-k`) : **12 failed, 6 passed** — `RuntimeError not raised` (H / M / A dans une transaction), `1 != 0` (H créée à 1 h 10 ; M créée à 0 h 30), M demandée à 0 h 30 créée, `2 != 4` (une seule H rattrapée), première H au 9 mars au lieu du 2, `KeyError: 'Opérations numérotées'`, `KeyError: 'mentions_legales'` (`presentation.py`), « Opérations numérotées » absent du gabarit de la fiche, `'Offert' == 'Offert (bout...cadeaux émis)'`, `KeyError: 'fuseau_horaire'` (×2). Verts voulus : gabarit de la M, gabarit du temps réel, repli du fuseau (gardes). Ajoutés après le code, jamais vus rouges : décembre / année, jetons repris tels quels (couverture du découpage des périodes et de M-3).
Après le code : `test_cloture_unique.py`, `test_comptabilite_admin.py`, `_exports`, `_celery`, `_verify`, `test_rapport_unique.py`, `test_demo_data_ventes.py` **162 passed**, puis **164 passed** avec les deux tests ajoutés ; `test_comptabilite_csv_comptable.py`, `_service`, `test_plan_comptable_unique.py`, `test_rapport_unique_comparaison.py`, `test_fedow_public_depots_bancaires.py`, `test_rapport_temps_reel.py`, `test_menu_rapports.py` **128 passed** ; `manage.py check` sans problème.

### Mutations (non jouées) — lignes actuelles
| Mutation | Test attendu rouge |
|---|---|
| `comptabilite/tasks.py` l.532 : `if False:` (filet du jour de la fin ignoré à la création) | `test_m_demandee_avant_le_filet_du_jour_ou_elle_finit_n_est_pas_creee` |
| `comptabilite/tasks.py` l.217 : seuil de la veille du jour de la fin | `test_m_de_fin_de_mois_creee_apres_la_j_de_la_derniere_soiree`, `test_cloture_hebdomadaire_calendaire_non_vide`, `test_m_demandee_avant_…` |
| `comptabilite/tasks.py` l.543 : `atomic()` sans `durable=True` (ou barrière retirée) | `test_cloture_h_m_a_refusee_dans_une_transaction_ouverte` |
| `comptabilite/tasks.py` l.784 : `periodes_finies[-1:]` (la dernière seulement) | `test_tache_arretee_trois_semaines_rattrape_les_trois_h_dans_l_ordre`, `test_premier_passage_cree_les_h_depuis_la_premiere_vente_du_lieu` |
| `comptabilite/tasks.py` l.712-718 : `return []` sans clôture du niveau | `test_premier_passage_…`, `test_tache_arretee_trois_semaines_…`, `test_mois_calendaire_egal_ventes_du_mois` |
| `comptabilite/tasks.py` l.135-136 : décembre → `date(jour.year, 13, 1)` | `test_decembre_et_annee_clotures_au_premier_janvier` |
| `comptabilite/tasks.py` l.255 : seuil d'aujourd'hui au lieu de la veille | `test_filet_par_defaut_a_4h_pas_avant`, `test_filet_suit_l_heure_de_fermeture_plus_deux_heures` |
| `comptabilite/rapport.py` l.428 : clé `fuseau_horaire` retirée | `test_en_tete_porte_le_fuseau_du_lieu_au_moment_du_calcul`, `test_z_garde_le_fuseau_de_sa_cloture_quand_le_lieu_change_de_fuseau` |
| `comptabilite/presentation.py` l.1555 / l.1584 : fuseau actuel du lieu | `test_z_garde_le_fuseau_…` |
| `comptabilite/presentation.py` l.441 : `en_tete["mentions_legales"]` | `test_fiche_d_un_z_sans_mentions_legales_ne_plante_pas` |
| `comptabilite/presentation.py` l.503 : « Nombre de ventes » | `test_en_tete_compte_les_operations_…`, `test_gabarit_de_la_fiche_d_une_j_…` |
| `comptabilite/presentation.py` l.516 / l.522 / l.528 : une ligne lit le nombre d'une autre | `test_en_tete_compte_les_operations_…` (1, 2, 3) |
| `comptabilite/presentation.py` l.739 : « Offert » | `test_offert_des_reglements_dit_bouton_offrir_et_cadeaux_emis` |
| `comptabilite/presentation.py` l.1107 : `abs(...)` | `test_jetons_cadeau_repris_ecrits_tels_quels` |
| `comptabilite/admin.py` l.334 : clé `sections` renommée ; `change_form_before.html` : `cloture.hmac_hash` renommé | `test_gabarit_de_la_fiche_d_une_j_…`, `test_gabarit_de_la_fiche_d_une_m_…` |
| `comptabilite/admin.py` l.312 / l.318 : clé `datetime_debut_affiche` ou `nombre_de_ventes` renommée | `test_gabarit_du_rapport_temps_reel_rendu_par_la_vue` |
| `comptabilite/tasks.py` l.711 : départ au `datetime_debut` de la dernière clôture ; l.708 : `order_by("datetime_fin")` | **équivalentes** : une période déjà clôturée est écartée par la création ; seul le coût change |
| `comptabilite/presentation.py` l.332 / l.1287 : `sort()` sans `key` | **équivalente** : les critères finissent par la clé, unique ; aucune valeur n'est comparée |

## F-3a — La ventilation comptable d'une J et le FEC, équilibrés par construction / J accounting breakdown and FEC, balanced by construction

**Migration :** Non. — **Chaînes i18n :** oui (liste plus bas).

### Resume / Summary
**Quoi / What :**
- Nouveau module `comptabilite/ventilation.py`. `ventiler_cloture(j)` rend une écriture par journal, avec une ligne par compte. Elle lit les ventes réglées en euros de la J et le plan comptable du moment.
- Chaque écriture est vérifiée : si les débits ne valent pas les crédits, l'export est refusé (« écart de N centimes »).
- `comptabilite/fec.py` est réécrit sur cette ventilation. Plus aucun compte écrit en dur.
- Le FEC est en **UTF-8 sans BOM** : le texte de loi (article A47 A-1) n'admet pas CP1252.
- `EcritureNum` vaut « n° de la J-journal ». Il est le même dans le FEC de la J et dans celui de son mois, mais il n'est pas continu : c'est un fichier d'import, et le logiciel comptable renumérote.
- La date d'une écriture est la date de début de service de sa J, dans le fuseau figé dans son rapport. Il n'y a plus de repli sur le fuseau actuel du lieu.
- Le FEC d'une semaine, d'un mois ou d'une année met bout à bout les J datées dans la période.
- Le nom du fichier porte une date locale : pour une J, son début de service ; pour une période, son dernier jour.
- Export refusé, avec un message dans l'admin, dans ces cas :
  - un compte manque ;
  - deux points de vente ont le même code journal ;
  - un point de vente prend le code d'un journal d'origine (CAISSE, TIREUSE, WEB, ADMIN).
- Le refus nomme la J en cause.
- `laboutik/plan_comptable.py` :
  - `compte_de_tva_pour_taux` cherche par le taux : un compte actif d'abord (le plus petit numéro), sinon un compte inactif. « Inactif » cache seulement le compte des menus de choix : l'export s'en sert quand même ;
  - le code journal renseigné est nettoyé comme le nom (lettres A à Z) ;
  - « Plan complet ? » signale les codes réservés ; pour la TVA, un compte de ce taux, actif ou non, suffit.
- Le nombre de requêtes d'un export ne grandit pas avec le nombre de ventes : les comptes sont gardés dans des dictionnaires locaux.

/ One balanced entry per journal, built from the current chart; FEC in UTF-8 without BOM; stable but non-continuous entry numbers; dated by the start of service; periods = their dated J; local-date file name; refusals for missing accounts and reserved or duplicated journal codes; constant query count.

**Pourquoi / Why :** fiche F §4, tronc D22 et D23 : un seul FEC, équilibré par construction. L'ancien FEC n'écrivait plus rien sur la clôture unique, et l'ancien FEC de la caisse était déséquilibré (voir plus bas). /
Sheet F §4: one FEC, balanced by construction.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/ventilation.py` | neuf : `ventiler_cloture`, `EcritureDesequilibree`, `codes_journal_refuses_a_l_export` |
| `comptabilite/fec.py` | réécrit sur la ventilation ; UTF-8 ; date de début de service ; périodes ; nom de fichier |
| `comptabilite/admin.py` | `exporter_fec` : refus = message d'erreur, aucun fichier |
| `laboutik/plan_comptable.py` | `compte_de_tva_pour_taux`, `comptes_du_plan_par_defaut_du_lieu`, `points_de_vente_au_code_journal_reserve`, `LIBELLE_DU_JOURNAL_SANS_POINT_DE_VENTE` ; code journal nettoyé ; « Plan complet ? » (TVA actifs, codes réservés, code renseigné sans lettre) |
| `tests/pytest/test_fec_equilibre.py` | neuf, 29 tests |
| `tests/pytest/test_comptabilite_exports.py` | FEC : catégorie du jus, équilibre, virgule, UTF-8 |
| `tests/pytest/test_rapport_unique.py` | test 26 étendu à `ventilation.py` |

### Chaînes i18n / i18n strings
Nouveaux msgid :
- « Export FEC refusé : %(raison)s Voir « Plan complet ? » en tête du plan comptable. »
- « Export FEC refusé : %(raison)s »
- « Le code journal « %(code)s » du point de vente « %(nom)s » ne contient aucune lettre. Donnez-lui un code en lettres. »
- « Le code journal « %(code)s » de %(noms)s est réservé aux ventes sans point de vente. Donnez-lui un autre code. »

Workflow i18n à lancer par le mainteneur.

### Déséquilibre de l'ancien code / Old code imbalance
Le scénario du test 19 (`test_fec_equilibre.py`) joué sur les anciens FEC, une J de 21 ventes : chiffre d'affaires TTC 5900, HT 5511, TVA 389, argent reçu 6701.
- `comptabilite/fec.py` (ancien) : **aucune ligne d'écriture** (il lit les clés de l'ancien rapport : `totaux_par_moyen`, `detail_ventes`, `tva`) ; débits 0, crédits 0.
- `laboutik/fec.py` + `laboutik/ventilation.py`, sur une ancienne clôture caisse calculée par l'ancien moteur (`RapportComptableService`) sur la même plage : 3 lignes — 419100 débit 3,00 ; 707000 crédit 8,83 ; 445711 crédit 1,17 → **débits 300 c, crédits 1000 c, écart −700 c** (avertissement seulement, export non refusé). L'ancien moteur ne voit en règlements que les 3,00 € de jetons (espèces, CB, chèque, Stripe, monnaie locale : 0).
/ Test 19's scenario on the old FECs: the old `comptabilite/fec.py` writes no line; the old `laboutik/fec.py` writes debits 300, credits 1000, gap −700 (warning only).

### Tests vus rouges / Tests seen red
- Avant le code : `test_fec_equilibre.py` ne se collecte pas (`No module named 'comptabilite.ventilation'`).
- Le test 26 lève `FileNotFoundError` (`ventilation.py` absent).
- Le test FEC des exports échoue sur `assert 0 > 0` (l'ancien FEC n'écrit aucune ligne).
- Après le code et les corrections : `test_fec_equilibre.py` 29 passed ; la suite comptabilité + avoirs + caisse 598 passed.
- Mutations jouées à la main par l'orchestrateur : toutes tuées. Les survivantes ont reçu un test : compte au solde nul, J datée du 1ᵉʳ jour du mois suivant, article hors chiffre d'affaires offert qui n'est pas une recharge, valeur exacte d'`EcritureNum`.

## F-3b / F-3c — Le CSV comptable est retiré : le FEC est le seul export comptable / Accounting CSV removed: the FEC is the only accounting export

**Migration :** Non. — **Chaînes i18n :** oui (liste plus bas).

### Resume / Summary
**Quoi / What :**
- Le **CSV comptable est retiré** de la clôture. Il n'y a plus de bouton « CSV comptable » sur la fiche, plus d'adresse d'export, plus de profils.
- À la place, une phrase sur la fiche : « Pour votre logiciel comptable (Sage, EBP, PennyLane, Paheko, Odoo…), importez le FEC. »
- Le **FEC est le seul export comptable**. Les autres exports de la clôture (CSV du rapport, tableur, PDF) ne changent pas.
- Les règles du FEC sont rangées dans `comptabilite/ventilation.py` (`ecritures_de_l_export`, déplacées depuis `fec.py`, même comportement) : la date de début de service, les J d'une période, le numéro et le libellé d'une écriture, le nom du fichier, le refus qui nomme la J.
- La doc utilisateur (`TECH_DOC/comptabilite.md`) explique le FEC, le plan comptable, « Plan complet ? », les refus et l'import, en mots simples.
- La même doc est remise à jour pour la trésorière ou le trésorier : le Z et le filet automatique à l'heure du lieu (fermeture + 2 h), les H / M / A créées après le filet de leur dernier jour et jamais vides, les 11 sections du rapport, la chaîne unique des empreintes et `verify_clotures`, une FAQ sans l'ancienne réponse sur LaBoutik.

/ The accounting CSV is removed; the FEC is the only accounting export, and every accounting software imports it.

**Pourquoi / Why :**
- Une relecture a comparé chaque profil CSV au vrai format de son logiciel : **aucun ne le suivait**.
  - PennyLane veut un code journal de 5 lettres au plus.
  - EBP veut un code de 2 à 4 caractères, une ligne de commentaire en tête, des guillemets et des libellés de 40 caractères.
  - Ciel lit des colonnes de largeur fixe.
  - Les autres n'ont pas de documentation publique.
- Un fichier « presque juste » serait refusé à l'import, ou importé de travers.
- Le FEC, lui, est un format légal, que tous ces logiciels importent.
- Le mainteneur a donc décidé de garder seulement le FEC.

/ No CSV profile matched its software's real format; the FEC is a legal format every software imports.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/csv_comptable.py`, `comptabilite/profils_csv.py` | supprimés |
| `comptabilite/templates/comptabilite/admin/export_csv_comptable_form.html` | supprimé |
| `comptabilite/admin.py` | adresse et vue `exporter_csv_comptable` retirées, imports nettoyés |
| `comptabilite/templates/comptabilite/admin/change_form_before.html` | bouton « CSV comptable » retiré ; phrase « importez le FEC » |
| `comptabilite/ventilation.py` | `ecritures_de_l_export` et les règles de l'export, déplacées depuis `fec.py` ; docstrings |
| `comptabilite/fec.py` | écrit sur `ecritures_de_l_export` (sortie inchangée) ; docstring |
| `TECH_DOC/comptabilite.md` | réécrite pour le trésorier : clôtures (Z, filet, H / M / A), sections du rapport, rapport temps réel, FEC, plan comptable, audit d'intégrité, génération manuelle, FAQ |
| `Administration/management/commands/_demo_data_v2_ventes.py` | message de la démo : plus de mention des CSV comptables |
| `tests/pytest/test_comptabilite_csv_comptable.py` | supprimé |
| `tests/pytest/test_comptabilite_admin.py` | plus d'adresse CSV comptable attendue ; test : pas de bouton, pas d'adresse, phrase FEC |
| `tests/pytest/test_comptabilite_exports.py` | test du CSV comptable retiré |
| `tests/pytest/test_plan_comptable_unique.py` | les deux tests (TVA par taux, plan de la caisse) lisent le FEC au lieu du CSV : ils vendent de vraies ventes |
| `tests/pytest/test_fec_equilibre.py` | test du règlement FED au 467000 (seul le CSV le vérifiait) ; djc (plus de `enumerate` ni de `lambda`) |
| `tests/pytest/test_rapport_unique.py` | test 26 : `fec.py` au lieu de `csv_comptable.py` |

### Chaînes i18n / i18n strings
- Nouveau msgid : « Pour votre logiciel comptable (Sage, EBP, PennyLane, Paheko, Odoo…), importez le FEC. »
- Les msgid du CSV comptable ne sont plus dans le code (« CSV comptable », « Export CSV comptable », « Export CSV comptable refusé… », « Avec Paheko… »…). Les `.po` ne sont pas touchés : le workflow i18n les marquera obsolètes.

Workflow i18n à lancer par le mainteneur.

## F-3d — Corrections de la relecture finale / Final review fixes

**Migration :** Non. — **Chaînes i18n :** non.

### Resume / Summary
**Quoi / What :**
- **Compte de TVA inactif** : l'export s'en sert. « Inactif » cache seulement le compte des menus de choix (décision antérieure du mainteneur, qu'une règle de F-3a contredisait). Le FEC prend un compte actif du taux d'abord (le plus petit numéro), sinon un compte inactif. « Plan complet ? » ne signale plus un taux qui n'a qu'un compte inactif.
- **Une J sans vente** donne un FEC avec seulement la ligne d'en-tête, sans erreur. Le nom du fichier prend la date locale de la fin de la J. Le FEC d'une période ignore les J sans vente.
- **Les comptes sont lus une seule fois pour tout un export**, même un mois ou une année : le plan par défaut, le compte de chaque moyen et monnaie, le compte de chaque taux de TVA. Il ne reste, par J, que sa première vente et ses trois requêtes de ventes.
- Le compte des cadeaux à la clientèle passe par une fonction publique du plan comptable (`compte_des_cadeaux_a_la_clientele`).
- Commentaires mis à jour : `laboutik/plan_comptable_par_defaut.py` (plus de renvoi au CSV comptable supprimé) et `laboutik/models.py` (le code journal du point de vente : la vraie raison, sans le profil PennyLane supprimé ; un commentaire seulement, pas de `help_text`).

/ Inactive VAT accounts are still used by the export; a J without sales exports a header-only FEC; accounts are read once per export; public gifts account function; comments.

**Pourquoi / Why :** relecture finale de la fiche F. / Final review of sheet F.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/plan_comptable.py` | `compte_de_tva_pour_taux` (actif d'abord, sinon inactif) ; « Plan complet ? » section 4 ; `compte_des_cadeaux_a_la_clientele` |
| `comptabilite/ventilation.py` | `ventiler_cloture` reçoit les dict des comptes (facultatifs) ; `ecritures_de_l_export` les crée une fois et garde les J sans vente ; filtre des J d'une période |
| `laboutik/plan_comptable_par_defaut.py`, `laboutik/models.py` | commentaires |
| `tests/pytest/test_fec_equilibre.py` | deux tests du compte de TVA inactif remplacés (inactif seul utilisé et non signalé ; l'actif préféré même de numéro plus grand) ; FEC d'une J sans vente ; requêtes d'un mois de 2 J et de 4 J |

---

## Comment tester (a la main) / Manual test
Le rapport n'est encore appelé par aucun écran (branché en F-2). Vérification par le shell :
```bash
docker exec -it lespass_django poetry run python /DjangoFiles/manage.py shell
```
```python
from datetime import timedelta
from django.utils import timezone
from django_tenants.utils import tenant_context
from Customers.models import Client
from comptabilite.rapport import RapportDesVentes
lieu = Client.objects.get(schema_name="lespass")
with tenant_context(lieu):
    rapport = RapportDesVentes(timezone.now() - timedelta(days=1), timezone.now())
    sections = rapport.toutes_les_sections()
    print(sections["chiffre_affaires"]["total_ttc_en_centimes"])
    print(sections["reconciliation"])
```
1. Faire une vente à la caisse (un article en espèces), relancer : le chiffre d'affaires et l'argent augmentent du prix.
2. Vider une carte : la section 3 ne bouge pas ; « argent reçu » baisse des espèces rendues.
3. `import json; json.dumps(sections)` passe sans erreur.
4. `sections["caisse_especes"]` : une vente en espèces à la caisse augmente « reçues » ; une sortie de caisse augmente « sorties » ; le solde suit.
5. `sections["integrite"]` vaut `{"statut": "OK", "anomalies": []}` sur une base saine.
6. `rapport.rapport_x()["operateurs"]` montre l'email du caissier ; `json.dumps(sections)` ne contient aucun « @ ».

### F-1d — Avoirs d'une ligne payée en points
1. Admin → Ventes → une ligne d'une vente en points (caisse, paiement NFC d'une adhésion à tarif en points) → « Avoir » : retour à la liste avec le message « Cette ligne a été payée en points ou en temps : l'avoir est impossible. ».
2. Fiche de l'adhésion → « Annuler l'adhésion » : la phrase « Adhésion payée en points ou en temps : aucun avoir n'est possible… », un seul bouton « Annuler sans avoir ».

### F-1e — Tiroir avec une correction, rapport X sans intégrité
1. À la caisse, vendre un jus en espèces ; dans le détail de la vente, « Corriger moyen » → CB.
2. Dans le shell (même bloc que plus haut, période qui contient la vente) : `sections["caisse_especes"]` — « reçues » compte le jus, `corrections_en_centimes` vaut moins son prix, et `solde_theorique_en_centimes` = fond + reçues + rendues + corrections − sorties.
3. `"integrite" in rapport.rapport_x()` vaut `False` ; `"integrite" in sections` vaut `True`.

### F-1f — Coût inconnu jamais négatif, phrase unique
1. Dans le shell, une période qui contient seulement l'avoir d'une ligne sans prix d'achat (bouton « Avoir » sur une vente de la veille) : `rapport.section_marge_brute()["nombre_d_articles_au_cout_inconnu"]` vaut 0, jamais −1.
2. Envoyer à la main un POST « avec avoir » sur l'annulation d'une adhésion payée en points (outils du navigateur, `with_credit_note=1`) : l'erreur s'affiche, la phrase n'est écrite qu'une fois.

### F-2a — La clôture unique
1. Admin → Paramètres → onglet « Réglages » : le champ « Heure de fermeture » (02:00 par défaut) est sous le fuseau horaire.
2. Menu « Ventes & comptabilité » : « Rapport des ventes », puis « Ancien rapport caisse » (module caisse actif).
3. Faire une vente à la caisse, puis `docker exec lespass_django poetry run python /DjangoFiles/manage.py generer_cloture --niveau=J --tenant=lespass` : une clôture J, de la fin de la J précédente à maintenant (la première commence à la première vente). Relancer aussitôt : « rien a cloturer (aucune vente) ».
4. `... generer_cloture --niveau=J --tenant=lespass --datetime-debut=...` : refusé (la J n'a pas de bornes).
5. `... generer_cloture --niveau=M --tenant=lespass` : la M du mois dernier, en heure locale du lieu, ou « rien a cloturer » si le mois n'a aucune vente.
6. `... verify_clotures --tenant=lespass` : les nouvelles clôtures sont saines. Les clôtures créées avant cette version (ancien format, sans empreinte) sortent en « Empreinte fausse » : il n'y a aucune clôture de ce moteur en production (on repart de zéro).
7. Celery beat : une seule tâche `cron_clotures_automatiques`, chaque heure (`crontab(minute=0)`).

### F-2b — Lire une clôture : fiche, temps réel, PDF, tableur, CSV
Préparer : à la caisse, vendre deux jus en espèces et trois jus payés moitié carte cashless, moitié CB ; faire l'avoir en espèces d'une vente (Admin → Ventes → une ligne → « Avoir », remboursé en espèces) ; vider une carte (espèces rendues) ; corriger le moyen d'une vente (espèces → CB) avec un caissier qui a un prénom et un nom. Puis créer la J : `docker exec lespass_django poetry run python /DjangoFiles/manage.py generer_cloture --niveau=J --tenant=lespass`.
1. Admin → « Rapport des ventes » → la J créée (`https://lespass.tibillet.localhost/`) : en haut, les boutons d'export et l'empreinte de la clôture ; puis, ouvertes, les cartes « En-tête » (lieu, niveau « Journalière », numéro, début, fin, « n° X à Y », nombre de ventes, perpétuels), « Chiffre d'affaires » (TTC / HT / TVA, par taux, catégorie, origine, journal), « Règlements » (Argent, Cashless par monnaie, Hors argent), « Caisse espèces », « Réconciliation », « Offerts » ; dessous, repliés : « Annexe… », « Points », « Marge brute », « Détail des ventes », « Intégrité ».
2. « Réconciliation » : la phrase « Argent reçu … = ventes payées en argent … + recharges … − remboursements … − cartes vidées … ± écarts d'encaissement … » ; aucun montant négatif après un « − » ; la somme se vérifie à la main.
3. Montants : tous à la française (« 1 050,00 € »), jamais « 1050.00 ».
4. Déplier « Annexe » : avoirs et espèces rendues en positif ; la correction avec « Espèces » → « Carte bancaire » et le **nom** du caissier (jamais un identifiant). Écarts d'encaissement en rouge s'il y en a.
5. Déplier « Intégrité » : « OK » (base de dev régénérée) ou la liste des anomalies (numéro de vente, raison) en rouge.
6. Une clôture M (`generer_cloture --niveau=M --tenant=lespass`) : pas de carte « Caisse espèces ».
7. Bandeau « Ouvrir le rapport temps réel » : mêmes sections, sans « Intégrité », avec « Habitus des cartes » et « Opérateurs » (emails des caissiers) ; « Ventes : N » sous la période ; changer la période → les chiffres suivent.
8. Boutons « PDF », « Tableur », « CSV » de la J : les mêmes sections, dans le même ordre, toutes dépliées. PDF : la phrase de réconciliation et les totaux comme à l'écran. Tableur : les montants sont des nombres (sélectionner deux cellules → la somme s'affiche en bas d'Excel / LibreOffice). CSV (ouvert dans LibreOffice, séparateur « ; ») : une ligne « [Titre] » par section.
9. Email : régler « Rapport par email » (destinataire, périodicité journalière), créer une J : le mail dit « Chiffre d'affaires TTC : … € » et « Ventes : N », le PDF est joint.

### F-2c — Le filet sans couper le service, commande robuste, temps réel en heure du lieu
1. Faire une J (`generer_cloture --niveau=J --tenant=lespass`), puis une vente à la caisse. Dans le shell, lancer `from comptabilite.tasks import generer_les_clotures_automatiques_du_lieu; generer_les_clotures_automatiques_du_lieu("lespass")` : avant le seuil (fermeture + 2 h) du lendemain, aucune J n'est créée ; la J du filet, le lendemain, finit exactement au seuil.
2. `generer_cloture --niveau=M --tenant=lespass --datetime-debut=2026-02-01T00:00 --datetime-fin=2026-03-01T00:00` : refus (« fuseau ») et code de sortie non nul ; avec `+01:00` (lieu à Paris) : accepté.
3. `verify_clotures --tenant=lespass` : les J se suivent (aucune « Journée discontinue »).
4. Admin → « Rapport des ventes » → « Ouvrir le rapport temps réel » : la période commence à la fin de la dernière J ; les heures sont celles du lieu (changer le fuseau dans les paramètres → la saisie « 10:00 » reste 10 h du lieu).
5. Celery beat : la tâche horaire envoie une tâche `generer_les_clotures_automatiques_du_lieu` par lieu (journal du worker).

### F-2d — Mentions légales, ordre stable, exports protégés
1. Admin → Paramètres : renseigner l'adresse postale, le code postal, la ville, le SIREN, le numéro de TVA. Faire une vente, puis une J (`generer_cloture --niveau=J --tenant=lespass`). Fiche de la J : l'en-tête montre ces mentions ; le PDF, le tableur et le CSV aussi.
2. Changer la ville dans les paramètres, rouvrir la fiche de la J : l'ancienne ville reste (le Z est figé) ; le rapport temps réel, lui, montre la nouvelle.
3. Détail des ventes de la J : produits dans l'ordre alphabétique, événements par date, à chaque rechargement (fiche, PDF, tableur, CSV).
4. Créer un produit nommé « =1+1 », le vendre, faire une J : dans le tableur, la case montre « =1+1 » sans apostrophe et jamais 2 (la barre de formule montre « '=1+1 », le marqueur texte d'Excel) ; dans le CSV, « '=1+1 ».
5. Paramètres → fuseau « America/Martinique », rapport par email journalier : le mail donne la période en heure de Martinique ; un export fait après 20 h (heure de Martinique) porte la date du jour de Martinique dans son nom.
6. Une J avec un écart d'encaissement (paiement Stripe d'un montant différent) : dans « Annexe », le texte « Attention : écart d'encaissement » au-dessus du tableau rouge.

### F-2e — H / M / A après le filet, rattrapage, fuseau figé, libellés
1. Faire une vente, une J, un avoir, un vidage de carte et une correction de moyen, puis une J (`generer_cloture --niveau=J --tenant=lespass`). Fiche de la J, « En-tête » : « Opérations numérotées » (toutes les opérations), puis « dont avoirs », « dont cartes vidées », « dont corrections » ; plus de ligne « Nombre de ventes ». « Règlements » → « Hors argent » : « Offert (bouton OFFRIR et cadeaux émis) ».
2. Paramètres → fuseau « America/Martinique » ; rouvrir la fiche de la J : début et fin restent à l'heure de Paris (fuseau du calcul). Le rapport temps réel, lui, est en heure de Martinique. Remettre le fuseau.
3. Le 1ᵉʳ du mois avant 4 h (fermeture 02:00), `generer_cloture --niveau=M --tenant=lespass` : « rien a cloturer » ; après 4 h, la M du mois précédent est créée.
4. Rattrapage, dans le shell : arrêter Celery beat plusieurs semaines n'est pas pratique ; avec un lieu qui a des ventes sur plusieurs semaines passées et aucune H, lancer `from comptabilite.tasks import generer_les_clotures_automatiques_du_lieu; generer_les_clotures_automatiques_du_lieu("lespass")` : une H par semaine finie avec des ventes, numérotées dans l'ordre du calendrier ; relancé, rien de plus.
5. Dans le shell, `from django.db import transaction` puis, dans `with transaction.atomic():`, `generer_cloture_pour_tenant("lespass", "M")` sur un mois avec des ventes : `RuntimeError` (la clôture d'une période ne se fait jamais dans une transaction ouverte).

### F-3a — Le FEC d'une J et d'un mois
1. Faire quelques ventes : espèces, CB, une recharge, un avoir. Faire une J (`generer_cloture --niveau=J --tenant=lespass`). Fiche de la J → bouton « FEC » : un fichier `FEC-AAAAMMJJ-n.txt` est téléchargé.
2. L'ouvrir dans un tableur, en UTF-8, séparateur tabulation :
   - 18 colonnes ;
   - une écriture par journal (CAISSE, WEB, ADMIN ou le code d'un point de vente) ;
   - pour chaque `EcritureNum`, la somme des débits égale la somme des crédits ;
   - les montants ont une virgule ;
   - les comptes sont ceux du plan comptable du lieu.
3. Faire la M du mois (`generer_cloture --niveau=M --tenant=lespass`, une fois le mois fini). Exporter son FEC : il contient les écritures des J datées dans le mois, avec les mêmes `EcritureNum`.
4. Refus : renommer un point de vente « Caisse » (ou retirer la catégorie d'un produit vendu), puis exporter le FEC. Rien n'est téléchargé, et un message rouge explique pourquoi. Remettre en ordre.
5. Changer le compte d'une catégorie de caisse, puis réexporter le même FEC : le nouveau compte apparaît (le FEC est recalculé à chaque export).

### F-3b / F-3c — Plus de CSV comptable, le FEC s'importe
1. Fiche d'une J : les boutons sont CSV, Tableur, PDF et FEC. Il n'y a **plus de bouton « CSV comptable »**. Sous les boutons, une phrase dit d'importer le FEC dans le logiciel comptable.
2. Télécharger le FEC et l'importer dans un vrai logiciel comptable (Paheko, PennyLane, EBP…) avec sa fonction « Importer un FEC » : l'import passe, les écritures sont équilibrées, les comptes sont ceux du plan du lieu.
