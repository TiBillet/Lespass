# Brief — 05-R-N-bis : relecture Fable de l'outil de suppression + renommage des places Fedow

## RÈGLE ABSOLUE — À LIRE EN PREMIER
AUCUN commit, AUCUN `git add`, AUCUNE commande git destructive (`checkout --`, `restore`, `stash`,
`reset`, `clean`), dans Lespass **comme dans Fedow** (`/home/jonas/TiBillet/dev/Fedow`, autre dépôt).
Jamais de « Co-Authored-By ». Lespass : `poetry`, `pytest`, `manage.py` dans `lespass_django`,
jamais deux pytest (`pgrep -af pytest`), 3 × 200 avant `make test`. `ruff format` / `ruff check
--fix` seulement sur les fichiers NEUFS de la session R-N et de celle-ci. La commande de suppression
ne tourne QUE par les tests. Rien sur `copie_prod_*` ni dans `db-prod/` (sauf lecture de
`db-prod/neutraliser_copie_prod.sql`). Fedow : aucun appel au Fedow de dev ni de prod, aucune
commande qui écrit dans une base Fedow ; si la pile de dev de Fedow ne tourne pas, ne la démarre
pas : dis-le. Aucune donnée personnelle dans tes sorties.

## RÈGLE DE LISIBILITÉ — À LIRE EN DEUXIÈME
Skills `djc` et `tibillet-test` ; `GUIDELINES.md` (Lespass) ; dans Fedow, suis le style des
commandes existantes de `fedow_core/management/commands/`.

## Source
Relecture Fable du 2026-10-07 (SUIVI chantier 05, journal du 2026-10-07 et §5) ; enquête
« lieu supprimé recréé » (SUIVI, journal du 2026-10-07) ; fiche R §12 et §18 (mises à jour).

## Partie A — l'outil de suppression (Lespass, tests d'abord)
1. **I-4** — critère 5, clôture « à montant nul » sans test : recrée dans le lieu jetable la table
   `comptabilite_cloturecaisse` de `main` (`git show origin/main:comptabilite/models.py` :
   `total_general`, `nombre_transactions`, et les colonnes non nulles nécessaires) sur le modèle de
   `recreer_le_plan_comptable_de_main` ; une J à 0 → « à supprimer » ; une J à 1 centime, et une J
   à 0 € avec 1 transaction → « gardé ».
2. **I-5** — mails :
   - le CSV `--traces-externes` reçoit une colonne `administrateurs` (adresses des admins du lieu,
     lues avant le `DROP`, séparées par « ; ») : il garde « qui prévenir » si la file Redis est
     perdue. Le CSV reste hors dépôt (il contient des adresses) ;
   - le résumé compte « N lieux supprimés sans administrateur (aucun mail) ».
   Tests : la colonne et le compteur.
3. **M-1** — `BaseBillet_tva` : seulement les taux semés par `main:BaseBillet/migrations/0187_*`
   (lis-les), un autre taux garde le lieu (« table non vide : BaseBillet_tva (taux ajoutés) ») ;
   `Configuration.skin` (colonne de `main`, retirée par `0226`) : si la colonne existe et diffère
   de « reunion », le lieu est gardé (critère 6). Tests (colonne `skin` recréée dans le lieu jetable).
4. **M-2** — critère 2 : un lieu créé il y a exactement `--jours-minimum` jours est **gardé**
   (fiche : « plus de 60 jours »). Test à la limite.
5. **M-3** — `test_reference_inattendue_annule_la_suppression` : exige exactement « gardé » et
   prend un nom qui dit ce qu'il prouve (la docstring renvoie au test 8 ter pour l'annulation).
6. **M-10** — djc : `on_commit` avec une fonction nommée (`functools.partial`) au lieu d'une
   `lambda` ; `nettoyage_des_lieux.py` ~l.799-802 réutilise `nom_lisible_d_une_table`.
7. CHANGELOG `CHANGELOG/2026-10-07-supprimer-lieux-inactifs.md` : section R-N-bis.

## Partie B — renommer les places orphelines dans l'ancien Fedow (dépôt Fedow)
Contexte (enquête) : une place Fedow ne se supprime pas (`fedow_core/admin.py` ~l.26), son nom est
unique (`fedow_core/models.py` ~l.1013, `validators.py` ~l.20). Un lieu supprimé dans Lespass garde
sa place : quelqu'un qui recrée un espace du même nom échoue à l'onboarding.

Écris **une commande Fedow** `fedow_core/management/commands/renommer_places_orphelines.py` :
- `--traces <chemin.csv>` : le CSV `--traces-externes` de Lespass (colonne `place_fedow` = uuid de
  la `Place` Fedow) ; `--suffixe` (défaut « (fermé 2026-10) ») ; `--executer` (sinon à blanc) ;
- pour chaque uuid : `Place` introuvable → signalée ; nom déjà suffixé → sautée (rejouable) ;
  sinon nouveau nom = nom + « » + suffixe, **tronqué** pour tenir dans `max_length` en gardant le
  suffixe entier, et unique (si le nom existe déjà, ajouter un numéro) ;
- une transaction pour tout ; sortie : nombre de places renommées, sautées, introuvables (noms
  affichés seulement pour l'opérateur, pas dans ton rapport) ;
- ne touche à RIEN d'autre (portefeuilles, assets, admins, domaines).
Tests dans les conventions de Fedow (`TESTS.md`, `launcher_test.sh`) **si** la pile de test de
Fedow tourne déjà ; sinon écris-les sans les lancer et dis-le. Documente la commande dans la fiche
R §18 ? Non : je m'en charge. Donne-moi juste la commande exacte à lancer en prod.

## Étapes
1. Tests (A et B), sans code de production, sans lancer pytest. STOP et rapport.
2. Après le feu vert : le code, les tests (Lespass ; Fedow si possible), `manage.py check`.
3. Mutations listées (fichier:ligne → test), non jouées.

## Rapport final
Fichiers (Lespass et Fedow), sorties, mutations, commande Fedow à lancer, écarts, message de
commit proposé pour chaque dépôt (sans Co-Authored-By).
