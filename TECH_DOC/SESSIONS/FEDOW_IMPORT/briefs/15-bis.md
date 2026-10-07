# Brief — 15-bis : corrections de la relecture Opus du diff de la spec 15

## RÈGLE ABSOLUE — À LIRE EN PREMIER
AUCUNE commande git d'écriture. Git en lecture seule. Jamais de « Co-Authored-By ». `poetry`,
`pytest`, `ruff`, `manage.py` par `docker exec lespass_django`. `ruff format` / `--fix` : fichiers
NEUFS seulement. Jamais `makemessages`. Pas de `runserver`. Jamais deux pytest en parallèle ; tests
par make après 3 réponses 200. **Ne modifie jamais le code de production pendant l'étape
« tests ».** Ne modifie jamais `lespass` ni un lieu de démo depuis un test ; jamais de `Client` réel
créé dans un test ; `Configuration` par `update()` / `bulk_create()` ; `get_solo()` écrit la ligne
si elle manque (lire par `objects.first()`). Aucune mutation jouée par toi.

## RÈGLE DE LISIBILITÉ
Skills `djc`, `unfold`, `tibillet-test` ; `GUIDELINES.md`.

## Source
Relecture Opus du diff de la spec 15 (2026-10-06) : 0 bloquant, I1-I2, M1-M9 ; suivi
`CHANTIER-15-10-14-SUIVI.md` §5 (décisions).

## Ce que tu corriges
1. **I1 — Lieu v2 : appairage d'une caisse LaBoutik V1 refusé** (décision du mainteneur) :
   `ApiBillet/views.py` `Onboard_laboutik` (~l.998-1048) refuse un lieu dont le moteur est `v2`
   (lecture par `lieu_en_moteur_legacy()` ; réponse d'erreur claire, au format des autres refus de
   cette vue). Un lieu legacy appaire comme aujourd'hui.
2. **I2 — Vérification de départ automatique** : une fixture `autouse`, portée session, dans
   `tests/pytest/conftest.py`, qui ne vérifie que « aucun `Client` `test_*` en `legacy` » et
   « `lespass` en `v2` » (une requête, accès base débloqué explicitement), et échoue (`pytest.fail`,
   jamais `skip`) avec la consigne (`down -v` + flush, ou mise à jour SQL des `test_*`). La vérification
   complète (`moteurs_de_depart_verifies`, `festival` legacy…) reste à la demande. Les E2E : la fixture
   reste à la demande (la spec 14 la demandera).
3. **M1** — `lieu_en_moteur_legacy()` (`Customers/models.py`) : le schéma public est TOUJOURS fermé
   (`schema_name == get_public_schema_name()` → `True`), quelle que soit la valeur de la ligne ; docstring
   juste.
4. **M2** — L'encart BETA n'apparaît pas sur une carte fermée par le verrou (cartes génériques ~l.2617
   et carte caisse ~l.2791 de `dashboard.py`).
5. **M3** — Le total d'un domaine compte toutes les cartes réelles (0/N, vrai) ; seule la pastille
   « Découvrir » (`_compter_les_cartes_eteintes`) exclut les cartes fermées et éteintes.
6. **M4** — La requête « le lieu a des assets legacy » est faite une seule fois par requête HTTP
   (mémoire sur `request`, comme `_tb_badge_propositions`) ; corrige le nombre d'appels dans la doc.
7. **M5** — Tests manquants : `FederationAdmin.has_delete_permission` (URL `…_federation_delete` dans la
   liste du test 11) ; `AssetAdmin.save_related` qui retire un lieu legacy déjà dans `pending_invitations`.
8. **M6** — Piège du schéma de connexion : une entrée dans `tests/PIEGES.md` (après l'annulation d'une
   transaction, Postgres remet le `search_path` mais django-tenants croit encore être sur le lieu de la
   dernière requête HTTP ; un signal qui lit `connection.schema_name` se trompe ; parade : créer dans
   `schema_context(...)` explicite). Cherche les autres fixtures de portée module qui créent un asset
   `fedow_core` TLF / TNF sans `schema_context` et liste-les (corrige-les de la même façon si c'est
   simple et sûr, sinon liste).
9. **M8 — djc** : « APPELEE PAR (chantier 15) : 15-2… » → les vrais appelants ; imports dans une fonction
   sans raison écrite (`BaseBillet/permissions.py:110`, `tests/pytest/conftest.py:430`,
   `tests/e2e/conftest.py:759`) : remonte-les en tête, ou écris pourquoi (cycle) ;
   `MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY` et `MODULES_V2_FERMES_AUX_LIEUX_LEGACY` déménagent à côté de
   `lieu_en_moteur_legacy()` (`Customers/models.py`) pour supprimer l'import local de `dashboard.py` ;
   le message périmé `test_verrou_moteur_legacy.py:~1108` (« conftest : verifier_les_moteurs_de_depart »).
10. **M9 — spec 15** : §7 (tableau ~l.332-334, plus d'« entrée directe »), §5.4 (`get_distant_fedow_tokens`
    et `admin_my_cards`, pas `tokens_table`), §5.5 (« 4 fois »). M7 : noter dans la spec §5.5 « voulu : un
    lieu v2 sans asset legacy n'a pas d'entrée vers les assets legacy (il crée ses monnaies dans
    fedow_core) » (décision du mainteneur).

## Tests (à écrire en premier, dans `tests/pytest/test_verrou_moteur_legacy.py`)
| # | Test | Attendu |
|---|---|---|
| 23 | `test_lieu_v2_ne_peut_pas_appairer_une_caisse_v1` | `Onboard_laboutik` sur un lieu v2 : refus, rien écrit ; lieu legacy : comme avant |
| 24 | `test_verification_de_depart_automatique` | un `Client` `test_x` posé `legacy` dans une transaction → la fonction de la fixture autouse échoue avec la consigne ; état normal → passe |
| 25 | `test_schema_public_toujours_ferme` | `Client(schema_name="public", moteur_monnaie="v2")` sous `tenant_context` → fermé |
| 26 | `test_carte_fermee_sans_encart_beta` | carte fermée (générique et caisse) : pas d'encart BETA ; v2 : inchangé |
| 27 | `test_total_du_domaine_compte_les_cartes_fermees` | domaine Laboutik d'un lieu legacy : 0/N ; pastille « Découvrir » inchangée |
| 28 | `test_assets_legacy_lus_une_fois_par_requete` | nombre de requêtes de la page d'admin : la requête des assets legacy n'est faite qu'une fois |
| 29 | `test_suppression_federation_fermee_en_legacy` et `test_save_related_retire_un_lieu_legacy_invite` | M5 |
Vus rouges attendus : 23, 24 (si la fonction n'existe pas), 25, 26, 27, 28, 29 (save_related : vert par
construction possible → le dire avec la mutation).

## Périmètre
`ApiBillet/views.py` (`Onboard_laboutik`), `Customers/models.py`, `Administration/admin/dashboard.py`,
`Administration/admin_tenant.py` (déménagement des constantes, imports), `fedow_core/admin.py` (imports
si besoin), `BaseBillet/permissions.py`, `tests/pytest/conftest.py`, `tests/e2e/conftest.py`,
`tests/outils_moteur_de_monnaie.py`, `tests/pytest/test_verrou_moteur_legacy.py`, les fixtures citées au
point 8, `tests/PIEGES.md`, `15-spec-verrou-moteur-legacy.md`, `CHANGELOG/2026-10-06-verrou-moteur-legacy.md`
(section 15-bis). Tout autre fichier : STOP.

## Étapes
1. Tests ; les lancer ; coller la sortie ; STOP (l'orchestrateur prouve le rouge).
2. (après feu vert) Le code ; tests de la session ; voisins (`test_fedow_core*.py`, `test_admin_*` du
   tableau de bord / menu / rail, `test_onboard*` / `test_laboutik_onboard*` s'ils existent, la
   caractérisation) ; `manage.py check`. Pas de suite complète.
3. Mutations LISTÉES (fichier:ligne, 6 à 8).
4. CHANGELOG section 15-bis.

## Rapport final
Fichiers ; sorties ; mutations ; constats ; chaînes i18n. Puis STOP.
