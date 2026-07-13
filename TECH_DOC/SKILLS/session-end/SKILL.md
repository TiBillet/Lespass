---
name: session-end
description: "Skill de cloture de session. Utiliser a la fin de chaque session de developpement pour auditer le code, verifier la conformite djc, lancer les tests, mettre a jour la documentation, et fournir des instructions de test manuel. Declencher quand l'utilisateur dit 'fin de session', 'on a fini', 'cloture', '/session-end', 'wrap up', ou quand le travail de dev est termine et qu'on veut tout verifier avant de quitter."
---

# Session End — Cloture de session de developpement

Skill rigide : suivre les etapes dans l'ordre. Ne pas sauter d'etape.
Chaque etape produit un livrable visible par le mainteneur.

Ce skill orchestre la fin de session. Il garantit que le code est propre,
conforme, teste, documente, et que le mainteneur sait exactement quoi
verifier a la main.

## Prerequis

Avant de lancer ce skill, identifier :
- **Quels fichiers ont ete modifies/crees** dans cette session (`git diff --name-only` depuis le dernier commit de debut de session, ou depuis le debut du travail)
- **Quel domaine metier** est concerne (adhesions, reservations, POS/laboutik, crowds, admin, API...)
- **Quelles fonctionnalites** ont ete ajoutees ou modifiees

## Mode rapide vs complet

Par defaut : **mode rapide** (etapes 1-9).

Avec `--full` : ajoute les etapes 10-12 (ecriture test E2E, non-regression E2E complete, Chrome).

Le mainteneur peut aussi demander des etapes individuelles.

---

## Etape 1 — Ruff : lint et formatage

Lancer ruff sur tous les fichiers Python modifies dans la session.

```bash
# Identifier les fichiers Python modifies
git diff --name-only --diff-filter=ACMR HEAD~X -- '*.py'

# Corriger les problemes auto-corrigeables
docker exec lespass_django poetry run ruff check --fix <fichiers>

# Formater
docker exec lespass_django poetry run ruff format <fichiers>

# Verifier qu'il ne reste rien
docker exec lespass_django poetry run ruff check <fichiers>
```

Si ruff signale des erreurs non auto-corrigeables, les corriger manuellement.
Ne pas passer a l'etape suivante tant que ruff est propre.

**Livrable** : zero erreur ruff sur les fichiers touches.

## Etape 2 — Audit de conformite djc

Relire chaque fichier modifie/cree et verifier la conformite avec le skill `/djc`.

### Checklist de conformite

Pour les **fichiers Python** :
- [ ] Noms de variables verbeux et explicites
- [ ] Commentaires bilingues FR/EN (methode FALC)
- [ ] LOCALISATION indiquee dans les docstrings
- [ ] `ViewSet` explicite (pas de `ModelViewSet`)
- [ ] Validation par DRF `Serializer` (pas de Django Forms)
- [ ] `gettext_lazy` pour tous les textes visibles
- [ ] Pas de comprehensions complexes — boucles `for` simples
- [ ] Pas de `window.xxx` / bootstrap JSON dans les contextes de template

Pour les **templates HTML** :
- [ ] `data-testid` sur chaque element interactif et bloc de contenu
- [ ] `aria-hidden="true"` sur les icones decoratives
- [ ] `aria-live="polite"` sur les zones mises a jour par HTMX
- [ ] `{% translate %}` / `{% blocktrans %}` pour tout texte visible
- [ ] Anti-blink : `hx-get` + `hx-target="body"` + `hx-push-url="true"` pour la navigation
- [ ] Pas de `hx-boost` — `hx-get`/`hx-post` explicites
- [ ] `hx-swap` explicite quand le comportement differe du defaut `innerHTML`

Pour les **fichiers JavaScript** :
- [ ] Commentaires FALC bilingues avec LOCALISATION
- [ ] Documentation des COMMUNICATION (evenements emis/recus)
- [ ] Pas de logique metier cote client — si c'est le cas, deplacer cote serveur + HTMX partial
- [ ] Validation client via `htmx:configRequest` avant les requetes HTMX

Pour les **admin Unfold** :
- [ ] Styles inline (pas de classes Tailwind custom)
- [ ] Helpers definis au niveau module (pas dans la classe ModelAdmin)

**Si des non-conformites sont trouvees** : les corriger immediatement.
Relancer ruff apres chaque correction Python.

**Livrable** : liste des fichiers audites + corrections appliquees.

## Etape 3 — Tests pytest du domaine touche

Lancer les tests unitaires/integration qui couvrent le domaine modifie.
Consulter la section "Lancer par domaine" du skill djc pour les commandes exactes.

```bash
# Exemple pour LaBoutik/POS
docker exec lespass_django poetry run pytest tests/pytest/test_pos_*.py tests/pytest/test_caisse_*.py -v

# Exemple pour adhesions
docker exec lespass_django poetry run pytest tests/pytest/test_membership_*.py -v
```

**Verifier que le glob matche AVANT de lancer** (`ls tests/pytest/ | grep membership`) :
un glob sans correspondance fait echouer pytest, et les noms de fichiers bougent.
N'invente pas de glob par analogie — `test_adhesions_*` et `test_sepa_*` ont l'air
plausibles, aucun n'existe.

Si des tests echouent : diagnostiquer, corriger, relancer. **Le skill `tibillet-test`
porte l'arbre de decision des echecs typiques** (schemas de test perimes, fuite de schema,
`502` = serveur down). Ne pas passer a l'etape suivante tant que les tests ne passent pas.

**Livrable** : sortie des tests avec 0 echec.

## Etape 4 — Tests E2E du domaine touche

Lancer les tests E2E Playwright du domaine concerne.

```bash
# Prerequis : verifier que Playwright est installe
docker exec lespass_django poetry run playwright install chromium 2>/dev/null

# Exemple pour LaBoutik/POS
docker exec lespass_django poetry run pytest tests/e2e/test_pos_*.py -v -s

# Exemple pour adhesions
docker exec lespass_django poetry run pytest tests/e2e/test_membership_validations.py -v -s
```

Si des tests E2E echouent : diagnostiquer, corriger, relancer.

**Livrable** : sortie des tests E2E du domaine avec 0 echec.

## Etape 5 — Regard critique et suggestions

Prendre du recul et relire le code avec un oeil critique. Se poser ces questions :

1. **Complexite** — Y a-t-il du code qui pourrait etre simplifie ? Des abstractions inutiles ?
2. **Performance** — Requetes N+1 ? Queries lourdes sans `select_related`/`prefetch_related` ?
3. **Securite** — Inputs non valides ? Injections possibles ? Permissions manquantes ?
4. **Edge cases** — Que se passe-t-il si la liste est vide ? Si l'utilisateur n'a pas la permission ? Si le tenant n'existe pas ?
5. **Accessibilite** — Un utilisateur de lecteur d'ecran peut-il utiliser cette feature ?
6. **DRY** — Du code duplique qui merite un refactoring ? (mais pas de sur-ingenierie)

**Etre honnete.** Si le code est bon, le dire. Si des ameliorations sont possibles,
les lister avec :
- **Priorite** (bloquant / recommande / nice-to-have)
- **Fichier et ligne** concernes
- **Ce qu'il faudrait changer** et pourquoi

Les ameliorations bloquantes doivent etre corrigees maintenant.
Les recommandees et nice-to-have sont notees pour le mainteneur.

**Livrable** : liste des suggestions classees par priorite. Corrections bloquantes appliquees.

## Etape 6 — Code Review via superpowers:code-reviewer

Dispatcher un subagent `superpowers:code-reviewer` pour obtenir un regard externe
et independant sur le code de la session. Ce reviewer n'a pas le contexte de la session —
il juge le code objectivement, ce qui attrape les angles morts.

### Procedure

1. Recuperer les SHAs de debut et fin de session :
```bash
# SHA du commit avant le debut du travail de la session
BASE_SHA=$(git log --oneline | grep "dernier commit avant session" | head -1 | awk '{print $1}')
# Ou plus simplement, le SHA du debut de branche / du dernier merge
BASE_SHA=$(git merge-base HEAD origin/main)

# SHA actuel
HEAD_SHA=$(git rev-parse HEAD)
```

2. Dispatcher le subagent code-reviewer (via Agent tool, type `superpowers:code-reviewer`) avec ce contexte :
   - **WHAT_WAS_IMPLEMENTED** : description des fonctionnalites ajoutees/modifiees
   - **PLAN_OR_REQUIREMENTS** : reference au PLAN_LABOUTIK.md ou au prompt de session
   - **BASE_SHA** / **HEAD_SHA** : range git a reviewer
   - **DESCRIPTION** : resume court du travail

3. A la reception du feedback, agir selon la severite :
   - **Critical** : corriger immediatement, relancer ruff + tests
   - **Important** : corriger avant de continuer
   - **Minor** : noter pour le mainteneur dans les suggestions (etape 5)

Le reviewer verifie : qualite du code, architecture, tests, conformite aux requirements,
securite, et production-readiness. Son verdict ("Ready to merge" / "With fixes" / "No")
est un signal fort pour le mainteneur.

**Livrable** : rapport du code-reviewer + corrections des issues Critical/Important.

## Etape 7 — Documenter les pieges dans tests/PIEGES.md


Ouvrir `tests/PIEGES.md` et ajouter les pieges rencontres pendant la session.

Chaque piege suit le format existant du fichier :
- Titre court et clair
- Explication du probleme
- Solution ou contournement
- Exemple de code si pertinent

Ne pas dupliquer un piege deja documente. Si un piege existant merite une mise a jour,
le mettre a jour plutot que d'en creer un nouveau.

**Livrable** : pieges ajoutes/mis a jour dans tests/PIEGES.md (ou "aucun nouveau piege" si la session s'est passee sans surprise).

## Etape 8 — Mettre a jour la documentation projet

Mettre a jour ces fichiers dans cet ordre :

### 8a. `CHANGELOG.md`
- Ajouter une entree en haut du fichier (ordre ante-chronologique)
- Suivre le format existant : Date, Migration (oui/non), Quoi/What, Pourquoi/Why, tableau des fichiers modifies
- Bilingue FR/EN
- Si la session n'a produit que du refactoring interne sans impact utilisateur, noter quand meme avec la mention "Refactoring interne / Internal refactoring"

### 8b. `laboutik/doc/PLAN_LABOUTIK.md`
- Mettre a jour les sections concernees par le travail de la session
- Marquer les taches completees
- Ajouter les notes techniques pertinentes

### 8c. `laboutik/doc/INDEX.md`
- Mettre a jour l'etat d'avancement des taches
- Ajouter les nouvelles taches si necessaire

### 8d. `laboutik/doc/SESSIONS/README.md`
- Ajouter un resume de la session (numero, date, ce qui a ete fait)
- Lister les fichiers crees/modifies
- Noter les decisions prises et pourquoi

**Livrable** : 4 fichiers de doc mis a jour (CHANGELOG + 3 fichiers laboutik).

## Etape 9 — Proposer un test E2E pour les nouveautes

Verifier si les fonctionnalites ajoutees/modifiees ont une couverture E2E.

Si non, **proposer** le test au mainteneur (sans l'ecrire) :
- Decrire les scenarios a couvrir
- Indiquer les `data-testid` utilises
- Lister les pieges connus pour ce domaine (cf. tests/PIEGES.md)
- Estimer le nombre de tests et la complexite

Le mainteneur decide s'il veut que le test soit ecrit maintenant ou dans une prochaine session.

**Livrable** : proposition de test E2E avec scenarios detailles.

---

## Etapes mode `--full` (optionnelles)

### Etape 10 — Ecrire le test E2E propose

Si le mainteneur a valide la proposition (etape 9), ecrire le test en suivant
les regles de `tests/PIEGES.md` :
- Noms verbeux
- Commentaires bilingues FALC
- Pas de `DJANGO_SETTINGS_MODULE` en dur
- Utiliser `data-testid` ou `data-name` pour les selecteurs
- Attention aux pieges documentes (tenant_context, networkidle Stripe, etc.)

Lancer le test et verifier qu'il passe.

**Livrable** : fichier de test E2E + sortie de test verte.

### Etape 11 — Non-regression E2E complete

Lancer l'ensemble des tests E2E pour verifier qu'aucune regression n'a ete introduite.

```bash
docker exec lespass_django poetry run pytest tests/e2e/ -v -s
```

Si un test ancien echoue : diagnostiquer si c'est une vraie regression
ou un test flaky. Corriger les regressions. Documenter les flaky dans tests/PIEGES.md.

**Livrable** : suite E2E complete verte (ou liste des flaky identifies).

### Etape 12 — Verification visuelle Chrome

Utiliser les outils browser (`mcp__claude-in-chrome__*`) pour verifier visuellement
les pages touchees pendant la session :

1. Identifier les URLs des pages modifiees
2. Naviguer vers chaque page
3. Verifier :
   - Le rendu est correct (pas de blink, pas de CSS casse)
   - Les interactions HTMX fonctionnent (clic, swap, toast)
   - Le mode sombre/clair est respecte
   - Pas d'erreurs dans la console JS
4. Capturer un GIF des interactions principales si pertinent

**Livrable** : rapport visuel (OK ou problemes trouves + corrections).

---

## Etape finale — Instructions de test manuel

Rediger pour le mainteneur un guide de test manuel des nouveautes.

### Format

```markdown
## Test manuel — [nom de la feature]

### Prerequis
- [etat de la base, donnees necessaires, tenant a utiliser]

### Scenario 1 : [cas nominal]
1. Aller sur [URL]
2. Cliquer sur [element]
3. Verifier que [resultat attendu]

### Scenario 2 : [cas limite]
1. ...

### Ce qu'il ne faut PAS voir
- [comportements indesirables a surveiller]
```

Etre precis : URLs exactes, elements avec leur `data-testid`, resultats attendus mesurables.

**Livrable** : instructions de test affichees au mainteneur dans la conversation.

---

## Resume des livrables

| Etape | Livrable | Mode |
|-------|----------|------|
| 1. Ruff | 0 erreur lint/format | rapide |
| 2. Audit djc | Liste fichiers audites + corrections | rapide |
| 3. Tests pytest | 0 echec domaine | rapide |
| 4. Tests E2E domaine | 0 echec E2E domaine | rapide |
| 5. Regard critique | Suggestions classees par priorite | rapide |
| 6. Code Review | Rapport code-reviewer + corrections Critical/Important | rapide |
| 7. Pieges | tests/PIEGES.md mis a jour | rapide |
| 8. Documentation | PLAN + INDEX + SESSIONS mis a jour | rapide |
| 9. Proposition E2E | Scenarios proposes (sans coder) | rapide |
| 10. Ecriture test E2E | Test ecrit et vert | --full |
| 11. Non-regression E2E | Suite complete verte | --full |
| 12. Chrome | Rapport visuel | --full |
| Final | Instructions test manuel | toujours |
