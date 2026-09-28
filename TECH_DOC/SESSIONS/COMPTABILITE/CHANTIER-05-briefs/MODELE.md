# Brief — <session> (ex : 05-B-1)

## RÈGLE ABSOLUE — À LIRE EN PREMIER
AUCUN commit, AUCUN `git add`, AUCUNE commande git destructive (`checkout --`,
`restore`, `stash`, `reset`, `clean`). Lecture seule autorisée (`git status`,
`git diff`). Tu t'arrêtes à la fin de ce brief et tu rapportes : le mainteneur commite.
Pas de `ruff format` ni de `ruff check --fix` sur un fichier existant. `poetry`,
`pytest`, `manage.py` **toujours** dans le conteneur `lespass_django`. Jamais deux
pytest en parallèle (`docker exec lespass_django pgrep -af pytest` avant de lancer).
Pas de `makemessages` / `compilemessages`. Pas de `runserver` (le serveur tourne dans
byobu).

## Ce que tu fais
- Fiche : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-<X>-*.md`, sections **§… à §…**
  (ne pas recopier la fiche ici : la lire).
- Règles communes : tronc `CHANTIER-05-montants-entiers.md` §2 (règle d'or), §8 (méthode).
- Écarts déjà décidés : `CHANTIER-05-SUIVI.md` §4.
- Skills : `djc` (code FALC, commentaires FR/EN au présent) ; `unfold` si admin ;
  `tibillet-test` pour lancer / diagnostiquer les tests. Lire `tests/PIEGES.md` avant
  d'écrire un test.

## Périmètre
- Fichiers que tu as le droit de modifier : <liste exacte>
- Fichiers de tests à créer : <liste>
- **Tout autre fichier : ne pas toucher.** S'il faut en toucher un : arrête-toi et
  rapporte pourquoi.

## Étapes
1. Écrire les tests listés dans la fiche (§ Tests). **Ne pas écrire de code de
   production.** Les lancer, coller la sortie d'échec dans le rapport. Puis STOP :
   l'orchestrateur relance lui-même pour prouver le rouge avant l'étape 2.
2. (après feu vert) Écrire le code. Relancer les tests de la fiche.
3. Ne pas jouer les mutations (l'orchestrateur le fait) : lister, pour chaque
   mutation de la fiche, le fichier et la ligne exacts à muter.
4. Écrire le CHANGELOG `CHANGELOG/2026-MM-JJ-montants-entiers-<session>.md`
   (format du skill `djc` ; migration oui/non ; chaînes i18n ajoutées).

## Ce que la spec ne dit pas
Si la fiche est muette, ambiguë ou fausse face au code : **ne pas inventer**. Écrire le
constat (fichier:ligne, ce que dit la spec, ce que fait le code) et STOP.

## Rapport final attendu
1. Fichiers modifiés / créés (liste exacte).
2. Sortie des tests (rouge à l'étape 1, vert à l'étape 2), sans résumé.
3. Mutations : fichier:ligne à muter, test attendu en échec.
4. Constats hors périmètre ou écarts à la spec.
5. Message de commit proposé (sans Co-Authored-By).
