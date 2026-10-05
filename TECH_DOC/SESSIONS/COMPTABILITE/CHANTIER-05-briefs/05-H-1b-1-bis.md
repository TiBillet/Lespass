# Brief — 05-H-1b-1-bis : corrections de la relecture Opus de H-1b-1

## RÈGLE ABSOLUE — À LIRE EN PREMIER
AUCUN commit, AUCUN `git add`, AUCUNE commande git destructive (`checkout --`,
`restore`, `stash`, `reset`, `clean`). Lecture seule autorisée (`git status`,
`git diff`). Tu t'arrêtes à la fin de ce brief et tu rapportes. Pas de `ruff format` ni
de `ruff check --fix` sur un fichier existant. `poetry`, `pytest`, `manage.py`
**toujours** dans le conteneur `lespass_django`. Jamais deux pytest en parallèle. Pas
de `makemessages` / `compilemessages`. Pas de `runserver`. Tests par
`make test ARGS="tests/pytest/<fichier>.py"`, après 3 réponses 200 du serveur. Outil
Edit / Write seulement. Une série de modifications liées (route ou admin retirés,
encore référencés ailleurs) se termine vite, suivie de `manage.py check`.

## RÈGLE DE LISIBILITÉ — À LIRE EN DEUXIÈME
Skill `djc` chargé, `unfold` pour l'admin, `GUIDELINES.md` lu : FALC, noms verbeux,
commentaires FR puis EN au présent adressés au prochain lecteur, `_()` en français.

## Ce que tu corriges (décisions du 2026-10-05)
1. **B1 — Ancien rapport caisse : adresses coupées dès H-1 (mainteneur).** L'ancien
   moteur (`laboutik/reports.py`) recalcule la TVA depuis le taux : faux sur une part en
   jetons. On coupe l'accès, on ne le corrige pas :
   - la route `CaisseViewSet.rapport_temps_reel` (`laboutik/views.py` ~l.4540) est
     retirée, avec son lien éventuel ;
   - l'admin de l'ancienne clôture de la caisse (`laboutik.ClotureCaisse`,
     `Administration/admin/laboutik.py` ~l.1285 et son enregistrement) n'est plus
     enregistré dans l'admin (le modèle et `laboutik/reports.py` restent jusqu'à H-2) ;
   - `tests/pytest/test_caisse_anciens_rapports.py` (il ne teste que l'ancien moteur) et
     les tests qui n'ouvrent que ces adresses sont retirés ; les lister au CHANGELOG avec
     la raison ;
   - **vérifier d'abord** : si la page `rapport_temps_reel` lit le **nouveau** rapport
     (`comptabilite`), ou si un écran vivant (caisse, admin des ventes) y renvoie : STOP
     et rapporter avant de couper ;
   - `tests/e2e/conftest.py` compare encore avec `comptabilite/services.py` : ne pas y
     toucher, le signaler.
2. **I1 — Avoir d'une vente payée en jetons par deux cartes (orchestrateur)** :
   `_monnaie_et_carte_des_jetons_de_la_vente` (`BaseBillet/services_vente.py` ~l.1240)
   : refuse seulement si les règlements LG de la vente portent **plusieurs monnaies** ;
   une seule monnaie et plusieurs cartes → un seul règlement LG rendu, **sans carte** ;
   une seule carte → avec la carte (comme aujourd'hui). Le compte (419100) ne dépend que
   de la monnaie. L'aperçu de l'« Avoir total » annonce le même résultat que le POST.
3. **I2 — Vente en points** : `ajouter_article` refuse (`ValueError`) une part en jetons
   non nulle sur une vente qui n'est pas en euros (`unite ≠ "EUR"`).
4. **Mineurs** :
   - M1 `Administration/admin_tenant.py` ~l.2283-2287 (« **entièrement** payée en
     jetons ») et ~l.2316 (« le montant de la ligne », pas « l'argent que l'avoir rend ») ;
   - M2 `laboutik/printing/formatters.py` ~l.272 : pas de fonction imbriquée ; une
     fonction de module ou deux blocs explicites ;
   - M3 `comptabilite/rapport.py` ~l.843-852 : un taux n'est retiré du CA par taux que si
     **toutes** ses lignes sont entièrement en jetons (un taux à 0 par ventes et avoirs
     qui s'annulent reste affiché, comme sans jetons) ; docstring du module ~l.26 à jour
     (« jetons : dans le CA, au taux 0 »).
   - M4 `laboutik/plan_comptable.py` ~l.1335-1341 (« Plan complet ? » section 4) :
     n'exige pas de compte de TVA pour une ligne dont la TVA vaut 0 ;
   - M5 `services_vente.py` : la monnaie et la carte des jetons lues **une fois** par
     vente d'origine pendant un avoir ;
   - M6 renommer `test_compte_pour_article_jeton_depense_au_707900`
     (`test_plan_comptable_unique.py` ~l.2020) selon ce qu'il vérifie ; les états de
     départ « comme la caisse l'écrit » à TVA 0 avec une part en jetons
     (`test_fec_equilibre.py` ~l.556, `test_plan_comptable_unique.py` ~l.689,
     `test_avoirs_ecrivent_la_vente.py` ~l.926 et ~l.3838) passent au taux du produit
     (ce que la caisse écrit), résultats inchangés ;
   - M7 tests qui manquent (voir le tableau).
   Non retenus (acceptés) : M8 démo (H-3), M9 colonne « TVA » de l'admin des lignes (le
   taux de la ligne est juste en base).

## Périmètre
`laboutik/views.py` (route retirée), `Administration/admin/laboutik.py`,
`BaseBillet/services_vente.py`, `Administration/admin_tenant.py`,
`laboutik/printing/formatters.py`, `comptabilite/rapport.py`, `laboutik/plan_comptable.py`,
les tests cités, `tests/pytest/test_part_en_jetons.py` (tests ajoutés), les tests qui
n'ouvrent que les adresses coupées (les lister), `CHANGELOG/2026-10-04-montants-entiers-H-1.md`
(section H-1b-1-bis). Tout autre fichier : STOP.

## Tests (dans `tests/pytest/test_part_en_jetons.py`, à écrire en premier)
| # | Test | Attendu |
|---|---|---|
| 15 | `test_ancien_rapport_caisse_n_est_plus_joignable` | l'adresse du rapport temps réel de la caisse et la liste de l'ancienne clôture de la caisse répondent 404 ; le menu n'y renvoie pas |
| 16 | `test_avoir_jetons_payes_par_deux_cartes_un_reglement_sans_carte` | bière 500 : carte A 300 LG, carte B 200 LG (même monnaie) ; avoir total : un règlement LG −500, monnaie de la vente, sans carte ; deux monnaies LG → refus |
| 17 | `test_part_en_jetons_refusee_sur_une_vente_en_points` | `ajouter_article` sur une vente en points avec part en jetons → `ValueError` |
| 18 | `test_plan_complet_signale_le_707900_absent` | part en jetons vendue, compte 707900 supprimé du plan → « Plan complet ? » signale le manque (section 1 bis) |
| 19 | `test_contrainte_signe_de_la_part_en_jetons` | base : part en jetons positive sur un net négatif refusée |
| 20 | `test_part_en_jetons_refusee_hors_chiffre_affaires` | `ajouter_article` d'un article hors CA avec part en jetons → `ValueError` |
| 21 | `test_taux_garde_si_ventes_et_avoirs_s_annulent` | un taux où vente et avoir s'annulent, à côté de jetons, reste dans le CA par taux à 0 |
| 22 | `test_plan_complet_sans_compte_de_tva_pour_une_ligne_sans_tva` | ligne entièrement en jetons au taux 20 % : pas de manque « compte de TVA 20 % » |

Vus rouges attendus : 15, 16, 17, 21, 22 ; 18-20 peuvent être verts (garde-fous) :
donner la mutation qui les fait tomber.

## Étapes
1. Tests ; les lancer ; coller la sortie ; STOP.
2. (après feu vert) Le code ; tests de la session ; voisins (`test_avoirs_ecrivent_la_vente.py`,
   `test_admin_vente.py`, `test_rapport_unique*.py`, `test_fec_equilibre.py`,
   `test_plan_comptable_unique.py`, `test_ticket_client_imprime.py`, `test_menu_rapports.py`,
   `test_rapport_temps_reel.py` si présent, `test_cloture*.py`) ; `manage.py check` ;
   caractérisation verte sans modification.
3. Mutations (fichier:ligne exacts), 5 à 6 : route remise ; admin réenregistré ; refus
   pour deux cartes remis ; carte de la première carte au lieu de vide ; refus « vente en
   points » retiré ; taux retiré dès que le reste vaut 0.
4. CHANGELOG section H-1b-1-bis.

## Rapport final attendu
Fichiers ; sorties ; mutations ; constats ; auto-contrôle djc ; message de commit (sans
Co-Authored-By).
