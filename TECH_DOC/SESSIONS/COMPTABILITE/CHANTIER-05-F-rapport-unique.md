# Chantier 05-F — Un moteur de rapport, une clôture, un FEC équilibré

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28)
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D19 à D23, R2
> Effort : 3 j (3 sessions : §2, §3, §4) — Dépend de : B, C, D (toutes les ventes ont
> leur `Vente`), E (plan comptable). **Migration : oui** (champs de clôture).

## 1. Le principe

Le rapport ne lit **que** des ventes encaissées (`Vente.statut = REGLEE`,
`datetime_encaissement` dans la période), leurs articles et leurs règlements, et ne
fait **que des sommes d'entiers**. Plus de `amount × qty`, plus de `Round()`, plus
de filtre par `sale_origin` pour choisir un périmètre : **toutes les origines**.

Nouveau module : `comptabilite/rapport.py`, classe `RapportDesVentes(debut, fin)`
(méthodes explicites, une par section). Il **remplace** `comptabilite/services.py`
`RapportComptableService` dès cette fiche, et `laboutik/reports.py` en fiche G.

## 2. Session F-1 — le rapport (sections du Z)

Définitions (une seule fois, dans le module) :

- **Articles du chiffre d'affaires** = articles des ventes `unite = EUR`, avec
  `hors_chiffre_affaires = False`, natures `VENTE` et `AVOIR`.
- **Argent** = règlements dont le moyen n'est ni `FREE`, ni `LG`, ni `NM`.

| # | Section | Contenu (entiers, sommes) |
|---|---|---|
| 1 | En-tête | lieu, période, niveau, n° de clôture, **plage de ventes [premier n°, dernier n°]**, nombre de ventes |
| 2 | **Chiffre d'affaires** | TTC / HT / TVA ; **par taux** ; par catégorie ; **par origine** (caisse, tireuse, en ligne, QR/NFC, admin, API) ; **par journal** (point de vente, fiche E) |
| 3 | **Règlements** | par moyen **et par monnaie**, en trois blocs : argent (espèces, CB, chèque, Stripe, virement) ; cashless (monnaie locale par nom, fédérée) ; hors argent (offert bouton, jetons, points par monnaie) |
| 4 | Réconciliation | une phrase lisible : « Argent reçu = ventes payées en argent + recharges − remboursements − cartes vidées » avec les chiffres |
| 5 | Avoirs et remboursements | nombre, total, par moyen ; dont **retours consigne** (D11) |
| 6 | Recharges (hors CA) | encaissées par moyen ; cadeau émis ; cartes vidées (espèces rendues) |
| 7 | Offerts | par source (OFFRIR, jetons) : quantités, valeur catalogue, coût d'achat |
| 8 | Points | par monnaie : quantités, valeur en points |
| 9 | Caisse espèces | fond, espèces reçues, sorties (`SortieCaisse`), espèces rendues, solde théorique (reprise de `calculer_solde_caisse`) |
| 10 | **Marge brute** | CA HT − Σ (`qty` × `prix_achat_unitaire`) sur tout ce qui est servi (vendu, offert, points ; retours en négatif). Les articles sans prix d'achat sont **comptés et signalés** (« 12 articles sans prix d'achat : marge incomplète ») |
| 11 | Corrections | ventes `CORRECTION` de la période (moyen avant → après, opérateur) |
| 12 | Détail | billets (par événement, tarif), adhésions (par produit), détail des ventes par produit (qté, TTC, HT, offert, coût), habitus cartes, opérateurs — **reprises** des sections actuelles de `laboutik/reports.py`, réécrites sur les champs entiers |
| 13 | Intégrité | `verifier_chaine_ventes` sur la plage (fiche A) : « OK » ou la liste des anomalies |

Le rapport X (temps réel, admin) = ce même calcul, non stocké.

## 3. Session F-2 — la clôture unique (`comptabilite.ClotureCaisse`)

Champs ajoutés / changés (le reste inchangé) :

| Champ | Sens |
|---|---|
| `point_de_vente` | informatif (depuis quel poste la clôture a été lancée), nullable |
| `numero_premiere_vente`, `numero_derniere_vente` | plage couverte |
| `total_ttc`, `total_ht`, `total_tva` | chiffre d'affaires de la période |
| `total_argent_recu` | bloc « argent » des règlements |
| `total_perpetuel` | cumul du CA TTC de toutes les clôtures J depuis la mise en service, jamais remis à zéro (définition actuelle de `comptabilite/tasks.py` ~l.95-110) |
| `nombre_ventes_perpetuel` | cumul du nombre de ventes |
| `hmac_hash`, `previous_hmac` | la clôture est chaînée : HMAC (JSON canonique : totaux, plage, empreinte de la dernière vente couverte, `previous_hmac`) |
| `rapport_json` | **toutes** les sections du §2, figées |
| `hash_lignes` | **retiré** (remplacé par la plage + la chaîne des ventes) |

- Niveaux **J, H, M, A** (D19). Chaque niveau est calculé **directement sur les ventes**
  de sa période (même moteur), pas en additionnant des J : plus de H/M/A vides
  (défaut actuel de `laboutik/tasks.py` ~l.669-800). Un test vérifie Σ des J = M.
- Numérotation : la **séquence globale** actuelle de `comptabilite` (tous niveaux),
  `UniqueConstraint` gardée.
- Une clôture J couvre `[fin de la dernière J, maintenant]`, toutes origines : une
  vente en ligne à 2 h du matin tombe dans la J suivante.
- Tâches Celery `comptabilite/tasks.py` (J/H/M/A) branchées sur le nouveau moteur.
  `tenant_context` inchangé.

⚠ **Transition F → G** : la clôture caisse (`laboutik.ClotureCaisse`, bouton de la
caisse, tâches `laboutik/tasks.py`) tourne encore jusqu'à la fiche G. Entre F et G,
une vente de caisse apparaît donc dans les deux clôtures. Accepté (dev).

## 4. Session F-3 — FEC et CSV comptables, équilibrés par construction

Une seule fonction `ventiler_cloture(cloture)` (`comptabilite/ventilation.py`,
remplace `laboutik/ventilation.py` et la logique de `comptabilite/fec.py`) produit
**une écriture par journal** (point de vente / WEB…) et par clôture J :

| Côté | Ligne | Montant |
|---|---|---|
| Débit | un compte par **(moyen, monnaie)** des règlements d'**argent et cashless** (`compte_pour_reglement`, fiche E) | Σ règlements |
| Crédit | un compte de vente par catégorie (`CategorieProduct.compte_comptable`) | Σ `total_ht` des articles du CA |
| Crédit | un compte de TVA par taux | Σ `total_tva` |
| Crédit | 4191 (avances clients) pour les recharges | Σ `total_ttc` des articles `hors_chiffre_affaires` |

- **Équilibre garanti** : Σ règlements hors offert = Σ nets (égalité de la fiche A) =
  Σ HT + Σ TVA + Σ recharges. La fonction **vérifie** débits = crédits et **refuse**
  l'export sinon (message lisible), au lieu du simple avertissement actuel.
- Montant négatif (avoir, espèces rendues) → écrit **du côté opposé**, en positif
  (convention FEC).
- Offerts, jetons, points : **aucune écriture** (pas d'argent).
- Compte manquant → refus explicite (fiche E), jamais de ligne sautée.
- Les profils CSV comptables (Sage, EBP, Paheko… : `laboutik/csv_comptable.py`,
  `comptabilite/csv_comptable.py`, `laboutik/profils_csv.py` / `comptabilite/profils_csv.py`)
  lisent **cette** ventilation. Un seul jeu de profils survit (celui de la caisse s'il
  est le plus complet — à vérifier au démarrage ; l'autre est retiré en H).
- Clôtures H/M/A : écriture = somme des écritures J de la période (plus d'écriture vide).

## 5. Test de comparaison avec les anciens rapports

`tests/pytest/test_rapport_unique_comparaison.py` (**schéma dédié**) : un scénario
couvrant toutes les origines (fabriques + chemins réels des fiches B-D : espèces, CB,
NFC multi-monnaie, jetons, OFFRIR, points, recharge, consigne + retour, vider carte,
tireuse, QR, billet Stripe, adhésion admin, avoir Stripe partiel, correction).

- Mêmes chiffres que l'ancien moteur caisse + l'ancien moteur en ligne **sur tout ce
  que ces moteurs calculaient juste**.
- **Écarts attendus, listés un par un dans le test** (chacun avec sa raison) :
  troncatures corrigées (1049 → 1050) ; recharges sorties du CA ; jetons sortis des
  encaissements et du CA ; tireuse comptée une seule fois ; adhésion multi-moyens
  comptée entière ; avoirs admin visibles ; moyens hors des 5 seaux visibles.

Un écart **non listé** fait échouer le test.

## 6. Tests

Fichiers : `tests/pytest/test_rapport_unique.py`, `tests/pytest/test_cloture_unique.py`,
`tests/pytest/test_fec_equilibre.py` — **schéma dédié** (ils lisent tout le lieu).

| # | Test | Attendu |
|---|---|---|
| 1 | `test_ca_trois_jus_nfc_et_cb_1050_875_175` | l'exemple fil rouge, au centime |
| 2 | `test_ca_par_taux_egal_somme_des_lignes` | Σ par taux = Σ lignes, exactement |
| 3 | `test_jetons_hors_ca_et_hors_argent_mais_dans_offerts` | bière 300 jetons + 200 CB → CA 200, argent 200, offerts 300 |
| 4 | `test_recharge_encaissee_hors_ca_puis_consommation_dans_ca` | recharge 2000 CB puis bière 500 LE → CA 500, argent 2000 |
| 5 | `test_consigne_dans_ca_retour_en_avoir` | vente 100, retour −100 → CA 0, ligne « retours consigne » 1 |
| 6 | `test_vider_carte_especes_rendues_dans_recharges` | section 6 |
| 7 | `test_points_hors_ca_section_points` | section 8 |
| 8 | `test_ventilation_par_origine_et_par_journal` | caisse BAR + web → deux lignes |
| 9 | `test_marge_brute_compte_offerts_et_signale_sans_prix_achat` | valeurs + compteur |
| 10 | `test_vente_en_attente_hors_rapport` | checkout non payé → absent |
| 11 | `test_cloture_j_plage_de_numeros_et_perpetuel` | plage, perpétuel = précédent + CA |
| 12 | `test_cloture_mensuelle_egale_somme_des_journalieres` | Σ J = M (tous totaux) |
| 13 | `test_cloture_hebdomadaire_non_vide` | H calculée sur les ventes |
| 14 | `test_cloture_chainee_et_alteration_detectee` | modifier `rapport_json` → vérification KO |
| 15 | `test_fec_equilibre_sur_le_scenario_complet` | débits = crédits, au centime |
| 16 | `test_fec_avoir_ecrit_du_cote_oppose_en_positif` | aucun montant négatif dans le FEC |
| 17 | `test_fec_refuse_si_compte_manquant` | message explicite, aucun fichier |
| 18 | `test_fec_un_journal_par_point_de_vente` | `JournalCode` BAR / WEB |
| 19 | `test_fec_aucune_ecriture_pour_offerts_et_points` | |
| 20 | `test_aucun_amount_fois_qty_dans_le_rapport` | garde : le source de `comptabilite/rapport.py` ne contient ni `F("amount")` ni `amount *` |

Vus rouges : tous (module absent), puis sur le scénario, 15 échoue sur l'ancien FEC
(déséquilibre TTC + TVA) — noter la sortie.

Mutations : lire `LigneArticle` hors vente (10) ; inclure LG dans l'argent (3) ;
inclure les recharges dans le CA (4) ; M = Σ des J stockés au lieu du calcul direct
(12, sur un scénario avec une vente modifiée entre-temps : doit rester détecté par
l'intégrité) ; supprimer le refus d'export (15, 17) ; écrire un avoir en négatif (16).

CHANGELOG : `CHANGELOG/2026-MM-JJ-montants-entiers-F-rapport-unique.md`.
