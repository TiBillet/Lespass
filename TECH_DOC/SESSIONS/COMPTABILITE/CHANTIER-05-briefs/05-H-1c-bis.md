# Brief — 05-H-1c-bis : corrections de la relecture Opus de H-1c

## RÈGLE ABSOLUE — À LIRE EN PREMIER
AUCUN commit, AUCUN `git add`, AUCUNE commande git destructive. Lecture seule autorisée
(`git status`, `git diff`). Pas de `ruff format` ni de `ruff check --fix` sur un fichier
existant. `poetry`, `pytest`, `manage.py` **toujours** dans le conteneur
`lespass_django`. Jamais deux pytest en parallèle. Pas de `makemessages` /
`compilemessages`. Pas de `runserver`. Tests par `make test ARGS="tests/pytest/<fichier>.py"`,
après 3 réponses 200 du serveur. Outil Edit / Write seulement. **Ne modifie jamais le
code de production pendant l'étape « tests », même pour une mutation.** Une série de
modifications liées se termine vite, suivie de `manage.py check`.

## RÈGLE DE LISIBILITÉ — À LIRE EN DEUXIÈME
Skill `djc` chargé (`unfold` pour l'admin), `GUIDELINES.md` lu : FALC, noms verbeux,
commentaires FR puis EN au présent adressés au prochain lecteur (jamais « chantier 05,
session … », jamais « ne … plus » qui raconte un avant), `_()` en français.

## Ce que tu corriges (décisions du 2026-10-05)
1. **Tireuse : on facture le volume autorisé (Q-H13, mainteneur, remplace Q-H11)** —
   `controlvanne/billing.py` `facturer_tirage` : la ligne porte `min(litres servis,
   litres autorisés)` (les litres autorisés = `allowed_ml_session` de la session, posé au
   badge depuis le solde ; arrondis **vers le bas** au ml, pour que le montant ne dépasse
   jamais le solde lu) ; le débordement n'est pas facturé ; `weight_quantity` et le
   décrément du stock gardent le **volume réellement servi** (l'inventaire reste juste).
   L'article d'écart « reçu en moins » ne reste que si l'argent débité est inférieur au
   total de cette ligne (ancien Fedow en échec ou solde baissé depuis le badge). La
   réponse au Pi et l'écran annoncent l'argent débité (inchangé). Un avoir sur une vente
   qui porte un écart est **refusé** (la session H-1d met ce refus dans le service : ne le
   recode pas, vérifie seulement que l'« Avoir total » de l'admin le respecte).
   **Bug antérieur à corriger** : les métadonnées de la ligne QR sont écrites en texte
   JSON (`json.dumps`) dans un `JSONField` → `ajouter_l_article_d_avoir` plante sur
   `.update` (`BaseBillet/services_vente.py` ~l.851). La vue QR écrit un **dict**, et
   l'avoir accepte aussi l'ancien texte (lignes déjà en base, reprise R).
2. **I1 — Réconciliation du rapport** (`comptabilite/rapport.py` ~l.1377-1397) : la
   phrase de réconciliation ne compte que les écarts **en argent** (ceux des ventes sans
   règlement cashless). L'annexe « Écarts d'encaissement » garde le total, avec une ligne
   « dont payés en cashless ». Docstring : une vente mixte (argent + cashless + écart)
   n'existe pas aujourd'hui. TODO retiré.
3. **I2 — Liste des ventes de la caisse** (`laboutik/views.py` ~l.4616-4621,
   `quantite_en_nombre_d_articles`) : les deux produits d'écart ne comptent pas dans le
   nombre d'articles (un tirage avec écart affiche « 1 article »).
4. **I3 — Admin : unité de la tireuse** (`Administration/admin_tenant.py`
   `_unite_d_une_pesee` ~l.2437-2455) : plus d'exclusion de la tireuse ; la catégorie du
   produit est passée à la fonction d'unité (un fût sans stock = « L ») ; docstring au
   présent.
5. **M1 — Page du payeur QR** (`BaseBillet/views.py` ~l.2545) : après un écart, la page
   de confirmation de `valid_payment` affiche l'argent débité (comme les mails et les
   réponses JSON).
6. **M2 — Journaux** : tireuse (`controlvanne/billing.py` ~l.553-557) « non encaissé,
   écart reçu en moins » au lieu de « non facturé » ; QR (~l.2235, ~l.2507) sans « parts ».
7. **M3 — Tirage de moins de 5 ml** : une ligne de fût reste une vente au volume même si
   `weight_quantity` vaut 0 : reconnaître la vente au volume aussi par le type
   `Product.FUT` (`comptabilite/rapport.py` `_ligne_au_poids_ou_au_volume`,
   `quantite_en_nombre_d_articles`), au plus simple.
8. **M4 — CA par moyen** : laisser tel quel (l'invariant tient) ; une phrase au CHANGELOG
   (« un écart d'un tirage payé en plusieurs monnaies est imputé à « plusieurs moyens » »).
9. **M5, M6, M7 — djc** : retirer les renvois de session des docstrings de tests
   (`test_tireuse_et_qr_une_ligne.py` l.4, l.7, l.88 ; `test_caracterisation_qr.py` l.25,
   l.210 — ce fichier : **commentaires seulement**, aucune assertion touchée ;
   `test_qrcodescanpay_flux_complet.py` ; `test_tireuse_ecrit_la_vente.py` ;
   `test_tireuse_ancien_fedow.py`) : la règle au présent, avec D15 / Q-H2 comme référence
   de règle si utile ; « ne porte plus la carte » → « ne porte pas la carte : elle est sur
   la vente et ses règlements » (`test_controlvanne_billing.py`,
   `test_controlvanne_review_fixes.py`, `test_ticket_client_imprime.py`,
   `test_tireuse_ecrit_la_vente.py`) ; la ligne anglaise trop longue de la docstring de
   `facturer_tirage` (~l.401).
10. **Q-H12 abandonnée** (mainteneur) : le filtre « À vérifier » ne change pas.

## Périmètre
`BaseBillet/services_vente.py`, `Administration/admin_tenant.py`,
`comptabilite/rapport.py`, `comptabilite/presentation.py` (si l'annexe des écarts y est
affichée), `laboutik/views.py`, `BaseBillet/views.py`, `controlvanne/billing.py`, les
tests cités au point 9 (commentaires), `tests/pytest/test_tireuse_et_qr_une_ligne.py`
(tests ajoutés), les tests existants qui figent « avoir total refusé sur une vente avec
écart » (les lister), `CHANGELOG/2026-10-04-montants-entiers-H-1.md` (section
H-1c-bis). Tout autre fichier : STOP.

## Tests (dans `tests/pytest/test_tireuse_et_qr_une_ligne.py`, à écrire en premier)
| # | Test | Attendu |
|---|---|---|
| 12 | `test_tireuse_facture_le_volume_autorise_pas_le_debordement` | solde 300, prix 6 €/L, autorisé 500 ml, servi 530 ml : ligne 0,500 L, 300, **aucun écart**, règlement 300 ; stock − 530 ml ; ancien Fedow en échec : écart « reçu en moins » (filet) |
| 13 | `test_avoir_d_une_ligne_qr_possible` | ligne QR payée (métadonnées) : l'avoir de la ligne s'écrit (plus de `ValueError` sur les métadonnées) ; ligne QR ancienne au texte JSON : avoir possible aussi |
| 14 | `test_reconciliation_ecart_cashless_hors_argent` | 10,00 € d'espèces + tirage 300 payé 200 en monnaie locale : « ventes payées en argent » 1000, écarts en argent 0 ; annexe : −100 dont payés en cashless −100 |
| 15 | `test_liste_des_ventes_tirage_avec_ecart_un_article` | la liste des ventes de la caisse affiche 1 article pour un tirage avec écart |
| 16 | `test_admin_tirage_affiche_en_litres` | fiche « Vente » de l'admin d'un tirage (fût sans stock) : « 0,500 L », « 6,00 €/L » |
| 17 | `test_page_du_payeur_qr_affiche_l_argent_debite` | débit partiel 800 sur 1000 : la page de confirmation de `valid_payment` affiche 8,00 € |
| 18 | `test_tirage_de_moins_de_5_ml_reste_au_volume` | tirage de 4 ml : la ligne compte pour 1 article au rapport, unité « L » |

Vus rouges attendus : 12-18 (vert par construction : le dire, avec la mutation).

## Étapes
1. Tests ; les lancer ; coller la sortie ; STOP.
2. (après feu vert) Le code ; tests de la session ; voisins (`test_avoirs_ecrivent_la_vente.py`,
   `test_admin_vente.py`, `test_rapport_unique*.py`, `test_comptabilite_exports.py`,
   `test_menu_ventes.py`, `test_tireuse_*.py`, `test_qrcode*.py`, `test_qrcodescanpay_flux_complet.py`,
   `test_controlvanne_*.py`, `test_ticket_client_imprime.py`, `test_en_ligne_ecrit_la_vente.py`
   pour les écarts Stripe) ; `manage.py check` ; caractérisation verte (seul le test QR de
   Q-H3, déjà modifié en H-1c ; ici : commentaires seulement).
3. Mutations LISTÉES (fichier:ligne exacts, 5 à 6) : débordement facturé (litres servis
   au lieu du minimum) ; métadonnées QR en texte ; écarts cashless comptés en argent ; écarts comptés dans la liste ;
   tireuse exclue de l'unité dans l'admin ; page du payeur au montant demandé.
4. CHANGELOG section H-1c-bis (et la phrase du point 8).

## Rapport final attendu
Fichiers ; sorties ; mutations ; constats ; auto-contrôle djc ; message de commit (sans
Co-Authored-By).
