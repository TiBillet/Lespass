---
name: i18n-translate
description: >-
  Traduit et nettoie les fichiers gettext .po du projet TiBillet/Lespass (Django
  multi-tenant). Deux modes : SYNC (corriger les fuzzy et les chaines manquantes
  dans locale/fr et locale/en apres un makemessages) et NEWLANG (creer une langue
  supplementaire es/de/it/... depuis zero). Utilise ce skill des que l'utilisateur
  parle de traductions, i18n, fichiers .po, locale/, msgstr fuzzy, chaines non
  traduites, "ajouter une langue", "nettoyer les traductions", ou juste apres avoir
  lance makemessages. Orchestre un workflow multi-agent Sonnet avec validation
  deterministe des placeholders. Ne lance JAMAIS makemessages/compilemessages
  lui-meme (c'est au mainteneur), ne fait AUCUNE operation git.
---

# i18n-translate — traductions .po TiBillet

Ce skill industrialise la traduction des fichiers gettext `.po` avec un workflow
multi-agent. **La valeur n'est pas dans les traductions (jetables) mais dans la
logique difficile a refaire correctement** : detection de langue source par
croisement FR↔EN, gestion de l'echappement `.po`, validation deterministe des
placeholders, traitement propre des fuzzy et des pluriels. Toute cette logique
est dans les scripts Python embarques — fais-leur confiance plutot que de la
reimplementer.

## Garde-fous — non negociables

- ❌ **Ne lance JAMAIS** `makemessages` ni `compilemessages`. C'est le mainteneur
  qui le fait. Ce skill demarre *apres* `makemessages` (les `.po` existent deja)
  et s'arrete *avant* `compilemessages` (il affiche la commande pour le mainteneur).
- ❌ **Aucune operation git** (add/commit/checkout/stash/reset/restore/clean).
  Cette regle est aussi en tete du prompt de chaque agent du workflow.
- ✅ Editer le **contenu** des `.po`, c'est le but du skill — c'est autorise.
- ✅ Avant d'ecrire dans un `.po`, on fait toujours un **dry-run** puis un
  controle d'integrite (nombre de blocs inchange).

## Prerequis et chemins

- **`<skill_dir>`** = le dossier de base de ce skill (donne a l'invocation).
- **`<locale_dir>`** = dossier `locale/` du repo. Par defaut `./locale` depuis la
  racine du projet (ex: `/home/jonas/TiBillet/dev/Lespass/locale`). Si ambigu,
  demande a l'utilisateur.
- **`<workdir>`** = dossier de travail temporaire, ex: `/tmp/i18n_translate`.
  Le **vider au debut** de chaque run : `rm -rf <workdir> && mkdir -p <workdir>`.
- `msgfmt` (gettext) doit etre dispo sur l'hote pour la validation syntaxe.

---

## MODE SYNC — corriger fuzzy + chaines manquantes (FR/EN)

A utiliser juste apres un `makemessages` du mainteneur. Corrige les `fuzzy`
(traductions perimees, affichees) et les **fuites de langue** (une chaine
francaise qui s'affiche en anglais, ou l'inverse). Les entrees deja correctes
(source == langue du fichier, `msgstr` vide = fallback gettext) sont laissees
intactes : c'est ce qui evite des milliers de faux positifs.

**Etapes :**

1. **Extraire** (deterministe) :
   ```bash
   rm -rf <workdir> && mkdir -p <workdir>
   python3 <skill_dir>/scripts/extract_sync.py <locale_dir> <workdir>
   ```
   Lis `<workdir>/meta.json` -> `total`, `starts` (debuts de lots). Si `total`
   vaut 0, il n'y a rien a faire : previens et arrete-toi.

2. **Traduire** via le workflow embarque (lots Sonnet paralleles) :
   ```
   Workflow({
     scriptPath: "<skill_dir>/references/workflow_sync.js",
     args: { workdir: "<workdir>", starts: <starts de meta.json> }
   })
   ```
   C'est une invocation de skill -> l'opt-in Workflow est satisfait.

3. **Fusionner + verifier les placeholders** (deterministe) :
   ```bash
   python3 <skill_dir>/scripts/merge_check.py <workdir>
   ```
   Doit afficher `manquants=0`. Les `anomalies` (placeholders qui ne correspondent
   pas, ou vides) sont mises de cote et **ne seront pas appliquees**. Si des
   anomalies apparaissent, ouvre `<workdir>/flagged.json` et regarde : souvent ce
   sont de faux positifs d'echappement (`\"` vs `"`) que la verif a deja
   normalises ; sinon, corrige a la main apres l'application.

4. **Appliquer** — dry-run d'abord, puis ecriture :
   ```bash
   python3 <skill_dir>/scripts/apply_sync.py <locale_dir> <workdir>            # dry-run
   python3 <skill_dir>/scripts/apply_sync.py <locale_dir> <workdir> --write    # ecrit
   ```

5. **Controle d'integrite + validation gettext** :
   ```bash
   for f in fr en; do
     echo -n "$f blocs="; grep -c '^msgid' <locale_dir>/$f/LC_MESSAGES/django.po
     msgfmt -c -o /dev/null <locale_dir>/$f/LC_MESSAGES/django.po && echo "  msgfmt OK"
   done
   ```
   Le **nombre de blocs doit etre identique avant/apres** (aucune entree perdue).
   `msgfmt -c` valide la syntaxe ET la coherence des placeholders `python-format`.

6. **Rendre la main au mainteneur** (NE PAS l'executer toi-meme) :
   ```
   docker exec lespass_django poetry run django-admin compilemessages
   ```

---

## MODE NEWLANG — creer une langue supplementaire

A utiliser pour ajouter es / de / it / pt / ... Le mainteneur doit d'abord avoir
lance `makemessages -l <code>` (sinon le fichier cible n'existe pas — rappelle-lui).

**Etapes :**

1. **Glossaire fige** (cle de la coherence) — si `<skill_dir>/scripts/glossary/<code>.txt`
   n'existe pas, le creer :
   - Lis `<skill_dir>/scripts/glossary/CONCEPTS.md` (base FR/EN des termes metier).
   - **Enrichis le vocabulaire** depuis les sources du projet :
     - `mcp__atomic__semantic_search` : `"glossaire vocabulaire TiBillet"`,
       `"definition cashless monnaie locale temps"`, `"terme metier billetterie adhesion"`.
     - skill `/djc` : conventions et vocabulaire UI du projet.
   - Produis un glossaire `<code>.txt` : une ligne par concept, format
     `FR | EN | <traduction langue cible>`, plus la liste des noms propres a ne
     pas traduire. **Sauvegarde-le** dans `<skill_dir>/scripts/glossary/<code>.txt`
     (cache : il sera reutilise tel quel aux prochains runs de cette langue).

2. **Extraire** (double reference FR+EN par chaine) :
   ```bash
   rm -rf <workdir> && mkdir -p <workdir>
   python3 <skill_dir>/scripts/extract_newlang.py <locale_dir> <code> <workdir>
   ```
   Lis `<workdir>/meta.json` -> `total`, `starts`.

3. **Traduire** via le workflow embarque :
   ```
   Workflow({
     scriptPath: "<skill_dir>/references/workflow_newlang.js",
     args: {
       workdir: "<workdir>", starts: <starts>,
       langName: "<nom complet, ex: Espagnol>", langCode: "<code>",
       glossary: "<contenu de glossary/<code>.txt>"
     }
   })
   ```

4. **Fusionner + verifier** :
   ```bash
   python3 <skill_dir>/scripts/merge_check.py <workdir>
   ```

5. **Appliquer** (dry-run puis ecriture) :
   ```bash
   python3 <skill_dir>/scripts/apply_newlang.py <locale_dir> <code> <workdir>
   python3 <skill_dir>/scripts/apply_newlang.py <locale_dir> <code> <workdir> --write
   ```

6. **Valider + rendre la main** :
   ```bash
   msgfmt -c -o /dev/null <locale_dir>/<code>/LC_MESSAGES/django.po && echo "msgfmt OK"
   ```
   Puis rappeler au mainteneur de lancer `compilemessages`.

---

## Verification visuelle (Chrome) — optionnel mais precieux

Les `.po` ne couvrent que les chaines **externalisees** (`{% translate %}` / `_()`).
Une verif visuelle du site attrape en plus les **chaines codees en dur**, jamais
mises dans `{% translate %}`, que `makemessages` ne voit pas — c'est un bug de
code, pas de traduction.

A faire **apres** que le mainteneur a lance `compilemessages` (sinon le `.mo` est
encore l'ancien et la verif n'a pas de sens).

1. Charge les outils Chrome via `ToolSearch` (`select:mcp__claude-in-chrome__...`).
2. Ouvre le site dev (demander/confirmer l'URL ; souvent `https://lespass.tibillet.localhost`).
3. Pour tester une langue : passer le navigateur dans la langue cible (header
   `Accept-Language`, selecteur de langue de l'UI, ou suffixe d'URL si le projet
   en a un) et parcourir les pages cles : agenda, adhesion, caisse, compte.
4. Repere les textes affiches dans la **mauvaise langue**. Classe-les :
   - chaine externalisee mais `msgstr` manquant -> relancer le mode SYNC/NEWLANG ;
   - chaine **codee en dur** (pas de `{% translate %}`) -> le signaler comme tache
     de code (le skill ne corrige pas le code applicatif tout seul).
5. Optionnel : `gif_creator` pour garder une trace du parcours verifie.

Reste cible : verifier quelques pages cles, pas crawler tout le site (cf. regles
anti-rabbit-hole des outils navigateur).

---

## Rappels de bord

- Les pluriels (`msgid_plural` / `msgstr[0]`) et les entrees obsoletes (`#~`) sont
  **laisses intacts** par les scripts : les ecrire mal casse la compilation.
- Le workdir contient tous les artefacts (`work_*.json`, `in_*`, `out_*`,
  `results.json`, `flagged.json`) — utile pour deboguer ou relancer un lot.
- Cout : ~100–150k tokens / langue complete (Sonnet). Negligeable sur un plan MAX.
