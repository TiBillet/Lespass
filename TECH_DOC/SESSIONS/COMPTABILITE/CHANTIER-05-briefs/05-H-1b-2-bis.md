# Brief — 05-H-1b-2-bis : corrections de la relecture Opus de H-1b-2

## RÈGLE ABSOLUE — À LIRE EN PREMIER
AUCUN commit, AUCUN `git add`, AUCUNE commande git destructive. Lecture seule autorisée
(`git status`, `git diff`). Pas de `ruff format` ni de `ruff check --fix` sur un fichier
existant. `poetry`, `pytest`, `manage.py` **toujours** dans le conteneur
`lespass_django`. Jamais deux pytest en parallèle. Pas de `makemessages` /
`compilemessages`. Pas de `runserver`. Tests par `make test ARGS="tests/pytest/<fichier>.py"`,
après 3 réponses 200 du serveur. Outil Edit / Write seulement. Une série de
modifications liées se termine vite, suivie de `manage.py check`.

## RÈGLE DE LISIBILITÉ — À LIRE EN DEUXIÈME
Skill `djc` chargé (`unfold` pour l'admin), `GUIDELINES.md` lu : FALC, noms verbeux,
commentaires FR puis EN au présent adressés au prochain lecteur, `_()` en français.

## Ce que tu corriges (décisions de l'orchestrateur, 2026-10-05)
1. **I2 — Le ticket ne fusionne plus deux pesées** : `laboutik/affichage_des_ventes.py`
   ~l.431-437 (clé de regroupement) : une ligne au poids ou au volume de la caisse (D15)
   reste UN article (ajouter la ligne à la clé), docstring corrigée. Deux pesées de 350 g
   à 12,90 €/kg = deux lignes « 0,350 kg × 12,90 €/kg 4,52 », jamais « 0,700 kg … 9,04 ».
   Les parts d'un ancien tirage de la tireuse (TODO H-1c) ne changent pas.
2. **I1 — Tireuse dans le Z jusqu'à H-1c** : rien à faire ici (H-1c écrit la tireuse en
   litres avant toute production) ; ne pas aggraver.
3. **Q-H4 partout — admin et Excel (I3)** : `Administration/admin_tenant.py`
   `ArticlesDeLaVenteInline.quantite` (~l.2758) et `LigneArticleInline.qty_decimal`
   (~l.1676) affichent la quantité d'une pesée par `quantite_au_poids_a_la_francaise`
   (« 0,355 kg »), et le prix unitaire « 12,90 €/kg » ; un article à la pièce garde son
   affichage. `comptabilite/excel_export.py` ~l.122 : la cellule de quantité d'une
   pesée porte son unité (format de nombre `0.000 "kg"` / `0.00 "L"` ou texte, au plus
   simple).
4. **Produit vendu au poids et à la pièce (Q-H4)** : le détail des ventes du rapport
   (`comptabilite/rapport.py`) ne mélange jamais deux unités sur une ligne : un produit
   qui a des lignes au poids et des lignes à la pièce donne deux lignes (une par unité).
5. **M1 — commentaires périmés** : `laboutik/views.py` ~l.9512, ~l.9587-9591 (retour de
   consigne : prix positif, total négatif), ~l.6957 (« reçoit les parts »), ~l.7163
   (« Part écrite par le service »). `BaseBillet/tasks.py` ~l.159-175 (facture
   d'adhésion : « parts » de la caisse) : ajouté au périmètre pour ce commentaire seul.
6. **M2 — « Jetons cadeau repris au vidage »** (`laboutik/views.py` ~l.2125) : plus de
   `payment_method = LG` sur la ligne (Q-H2), commentaire « jusqu'à la fiche H » retiré.
   Vérifier qu'aucun lecteur ne le lit (le plan comptable et le rapport le reconnaissent
   par son produit).
7. **M3 — une seule règle « une pesée = un article »** : la fonction de
   `comptabilite/rapport.py` (~l.314) sert aussi `laboutik/views.py` (~l.4611-4619, le
   `Case` en ligne) : une fonction, un préfixe de chemin en paramètre.
8. **M4 — garde de la cascade testée** : un test qui appelle
   `_creer_lignes_articles_cascade` avec un débit faux et attend `EgaliteDeVenteRompue`,
   aucune ligne écrite.
9. **M5 — trous de test** : colonnes vides (Q-H2) sur un retour de consigne en NFC ;
   stock décrémenté par `weight_quantity` sur le chemin cascade.
10. **M6 — commande de table et tarif au poids** : `ouvrir_commande` (~l.13913) refuse un
    tarif `poids_mesure` (et un prix libre sans montant), comme les tarifs en points,
    message `_()` en français.
11. **M7 — Sunmi intégrée** (`laboutik/printing/sunmi_inner.py` ~l.135-150) : imprime le
    détail du poids (`weight_detail` : « 0,350 kg × 12,90 €/kg »).
12. **M8 — `reset_carte`** (`laboutik/utils/test_helpers.py` ~l.92, outil de test DEBUG) :
    ne lève plus `ProtectedError` (les règlements portent le portefeuille) ; supprimer
    d'abord ce qui le protège, ou délier sans supprimer, au plus simple ; un test.
13. **I4 — API v2** : rien à coder (Q-H8 : après la production) ; écrire dans la section
    H-1b-2 du CHANGELOG que `/api/v2/sales/` ne publie plus `payment_method` pour les
    ventes de caisse, et qu'un retour sort à prix positif et quantité −1, une pesée en kg.

## Périmètre
`laboutik/affichage_des_ventes.py`, `laboutik/printing/formatters.py` (si la clé y vit),
`laboutik/printing/sunmi_inner.py`, `Administration/admin_tenant.py`,
`comptabilite/excel_export.py`, `comptabilite/rapport.py`, `laboutik/views.py`,
`BaseBillet/tasks.py` (commentaire), `laboutik/utils/test_helpers.py`,
`tests/pytest/test_caisse_une_ligne_par_article.py` (tests ajoutés), les tests existants
qui figent la fusion des pesées ou l'affichage de la quantité (les lister),
`CHANGELOG/2026-10-04-montants-entiers-H-1.md` (sections H-1b-2 et H-1b-2-bis). Tout
autre fichier : STOP.

## Tests (dans `tests/pytest/test_caisse_une_ligne_par_article.py`, à écrire en premier)
| # | Test | Attendu |
|---|---|---|
| 13 | `test_deux_pesees_deux_articles_au_ticket` | deux pesées de 350 g : le ticket et le détail montrent deux articles « 0,350 kg × 12,90 €/kg 4,52 » |
| 14 | `test_admin_quantite_d_une_pesee_avec_l_unite` | fiche « Vente » de l'admin et inline des lignes : « 0,355 kg », « 12,90 €/kg » |
| 15 | `test_excel_quantite_d_une_pesee_avec_l_unite` | export tableur du Z : la cellule de quantité du comté porte l'unité |
| 16 | `test_rapport_produit_au_poids_et_a_la_piece_deux_lignes` | comté au kilo + portion à la pièce : deux lignes au détail du Z, une en kg, une en pièces |
| 17 | `test_jetons_repris_au_vidage_sans_moyen_sur_la_ligne` | vidage avec jetons cadeau : la ligne « Jetons cadeau repris » n'a pas de `payment_method` |
| 18 | `test_garde_de_la_cascade_debit_faux_rien_d_ecrit` | débit faux → `EgaliteDeVenteRompue`, aucune ligne |
| 19 | `test_retour_consigne_nfc_sans_moyen_ni_carte` | retour de consigne remboursé sur la carte : colonnes vides |
| 20 | `test_stock_decremente_par_le_poids_en_cascade` | pesée payée en NFC deux monnaies : stock − 350 g |
| 21 | `test_commande_de_table_refuse_un_tarif_au_poids` | ouvrir une commande avec un tarif au poids → refus |
| 22 | `test_sunmi_interne_imprime_le_prix_au_kilo` | ticket Sunmi intégré d'une pesée : « 12,90 €/kg » présent |
| 23 | `test_reset_carte_ne_plante_plus` | `reset_carte` sur une carte qui a des règlements : pas d'erreur |

Vus rouges attendus : 13-17, 19 (peut-être vert), 21-23 ; 18, 20 peuvent être verts
(garde-fous) : donner la mutation.

## Étapes
1. Tests ; les lancer ; coller la sortie ; STOP.
2. (après feu vert) Le code ; tests de la session ; voisins (`test_menu_ventes.py`,
   `test_ticket_client_imprime.py`, `test_admin_vente.py`, `test_comptabilite_exports.py`,
   `test_rapport_unique*.py`, `test_caisse_vider_carte_deux_fedow.py`,
   `test_commandes*.py` ou les fichiers de commandes de table, `test_impression*.py`) ;
   `manage.py check` ; caractérisation verte sans modification.
3. Mutations (fichier:ligne exacts), 5 à 6 : pesées refusionnées ; unité absente dans
   l'admin ; deux unités mélangées au détail ; `payment_method` LG remis ; tarif au poids
   accepté en commande ; prix au kilo absent du Sunmi.
4. CHANGELOG sections H-1b-2 (note API v2) et H-1b-2-bis.

## Rapport final attendu
Fichiers ; sorties ; mutations ; constats ; auto-contrôle djc ; message de commit (sans
Co-Authored-By).
