# Brief — « ter » : corrections de la relecture Fable du chantier 15 · 10 · 14, cascade sans monnaie archivée

## RÈGLE ABSOLUE — À LIRE EN PREMIER
AUCUNE commande git d'écriture. Git en lecture seule. Jamais de « Co-Authored-By ». `poetry`,
`pytest`, `ruff`, `manage.py` par `docker exec lespass_django`. `ruff format` / `--fix` : fichiers
NEUFS seulement. Jamais `makemessages`. Pas de `runserver`. Jamais deux pytest en parallèle ; tests
par make après 3 réponses 200. **Ne modifie jamais le code de production pendant l'étape « tests ».**
Ne modifie jamais `lespass` ni un lieu de démo depuis un test. Jamais `ConfigurationSite.get_solo()`.
Aucune mutation jouée par toi.

## RÈGLE DE LISIBILITÉ
Skills `djc`, `unfold`, `tibillet-test` ; `GUIDELINES.md`.

## Source
Relecture Fable du chantier (suivi `CHANTIER-15-10-14-SUIVI.md` §4, §5, §6) et diagnostic de l'échec
de `test_controlvanne_review_fixes.py::TestC1DoubleFacturationConcurrente` (cause : 15 assets
`fedow_core` TLF « E2E Fed V2 … » de `lespass`, `archive=True` mais `active=True`, laissés par l'E2E
`test_federation_asset_fedow_core.py` ; la cascade `AssetService.obtenir_assets_accessibles`
(`fedow_core/services.py` ~l.103) ne regarde pas `archive`, trie par nom et prend le premier TLF ; la
fixture `rf_asset_tlf` (`test_controlvanne_review_fixes.py:42`) filtre `archive=False` : la carte est
créditée sur « Monnaie locale », la cascade cherche sur l'asset archivé → solde 0, rien facturé).

## Ce que tu corriges
1. **Cascade sans monnaie archivée** (décision du mainteneur : « l'exclure de la cascade ») :
   `AssetService.obtenir_assets_accessibles` (et toute autre lecture de la cascade de paiement caisse /
   tireuse / kiosque qui choisit un asset pour débiter) exclut `archive=True`. Docstring : pourquoi (une
   monnaie archivée n'est plus proposée au paiement ; ses jetons restants ne se dépensent plus en
   caisse). Vérifie les appelants (caisse, tireuse, kiosque, vidage de carte, soldes affichés) : le
   **vidage de carte** et l'**affichage des soldes** doivent-ils encore voir une monnaie archivée (pour
   rendre l'argent restant) ? Lis le code : si un appelant a besoin des archivées (vidage, remboursement),
   il ne doit PAS perdre ces jetons — dans ce cas, n'exclure que dans le choix de l'asset à DÉBITER, et
   dis précisément ce que tu as fait et pourquoi. En cas de doute : STOP et rapport.
2. **Fixture robuste** : `rf_asset_tlf` choisit l'asset par la même requête que la cascade (pour ne plus
   dépendre de l'état de `lespass`).
3. **M-1** : un asset `fedow_core` archivé n'apparaît pas dans le panneau des invitations
   (`fedow_core/admin.py` `changelist_view` ~l.544-556) et la route `accept_asset_invitation`
   (~l.486-540) refuse un asset archivé.
4. **M-2** : `tests/e2e/test_federation_asset_fedow_core.py` ~l.233-236 : ajouter
   `assert produit_de_recharge["pv_cashless"] >= 1` (sinon `== 0` est vrai par construction).
5. **M-3** : copier la requête SQL de `compter_avant` (agrégats seulement) dans
   `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-copie-prod.md` §3.3 (le script `db-prod/` est hors git).
6. **M-4** : spec 15 §3 (~l.75-78) : « seul le superadmin y a accès » → la vérité (aucun écran ; le
   moteur ne change que par la base), sans proposer d'outil (décision : on ne touche à rien).
7. **M-5** : libellé `MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY` (`Customers/models.py` ~l.73-75) :
   « Votre lieu utilise l'ancien moteur de monnaie (Fedow) : ce module V2 ne le concerne pas. » (une
   chaîne ; adapte les tests qui la lisent).
8. **M-8** : `tests/pytest/test_verrou_moteur_legacy.py` ~l.1512 : ne plus exiger « exactement 1 requête
   SQL » au total ; compter seulement les requêtes sur `Customers_client` (≤ 1).
9. **Base de dev** : après le code, les 15 assets « E2E Fed V2 … » ne gênent plus (exclus car archivés) :
   ne les modifie pas.

## Tests (à écrire en premier)
| # | Fichier | Test | Attendu |
|---|---|---|---|
| T1 | test neuf ou fichier de la cascade existant (`tests/pytest/test_fedow_core*.py` / `test_caisse_*`) | `test_cascade_ignore_une_monnaie_archivee` | lieu `test_*` dédié : deux TLF actifs, l'un archivé (nom trié en premier) : la cascade choisit le non archivé |
| T2 | idem | `test_vidage_ou_solde_selon_la_decision` | selon ce que tu trouves au point 1 : un jeton sur une monnaie archivée reste visible / rendu là où il doit l'être |
| T3 | `tests/pytest/test_verrou_moteur_legacy.py` (ou un fichier `fedow_core`) | `test_asset_archive_absent_des_invitations_et_refuse` | M-1 : panneau sans l'asset archivé ; POST d'acceptation refusé |
| T4 | `test_controlvanne_review_fixes.py` | (la fixture) | le test C1 passe même avec des TLF archivés-actifs sur `lespass` |
Vus rouges attendus : T1, T3, T4 (T4 est rouge aujourd'hui sur la base de dev). T2 : dis.

## Périmètre
`fedow_core/services.py` (et l'appelant exact si le filtre doit y aller), `fedow_core/admin.py`,
`Customers/models.py` (libellé), `tests/pytest/test_controlvanne_review_fixes.py`,
`tests/pytest/test_verrou_moteur_legacy.py`, le fichier de test de la cascade (neuf ou existant),
`tests/e2e/test_federation_asset_fedow_core.py`, `CHANTIER-05-R-copie-prod.md`,
`15-spec-verrou-moteur-legacy.md`, les tests qui lisent l'ancien libellé, et un CHANGELOG
`CHANGELOG/2026-10-06-verrou-moteur-legacy.md` (section « ter », plus une ligne dans
`2026-10-06-tests-federation-inter-lieux.md` pour M-2). Tout autre fichier : STOP.

## Étapes
1. Tests ; les lancer ; coller la sortie ; STOP (l'orchestrateur prouve le rouge).
2. (après feu vert) Le code ; tests de la session ; voisins (`test_controlvanne_*`, `test_caisse_*`,
   `test_fedow_core*`, `test_kiosk*`, `test_tireuse_*`, `test_pos_vider_carte.py`,
   `test_caisse_vider_carte_deux_fedow.py`, `test_verrou_moteur_legacy.py`, la caractérisation) ;
   `manage.py check`. Lance aussi l'E2E `tests/e2e/test_federation_asset_fedow_core.py` (M-2).
3. Mutations LISTÉES (fichier:ligne, 4 à 6).
4. CHANGELOG.

## Rapport final
Fichiers ; sorties ; la décision prise au point 1 pour le vidage / les soldes, avec sa raison ; mutations ;
constats ; chaînes i18n. Puis STOP.
