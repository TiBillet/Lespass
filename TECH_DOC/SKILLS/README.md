# TECH_DOC/SKILLS — Les skills agent du projet

Les skills apprennent à un agent (Claude Code) à travailler correctement sur ce projet :
conventions de code, pilotage de l'API, lancement et diagnostic des tests.

Ils sont **versionnés ici**, dans le dépôt, pour que toute l'équipe en profite et que
les corrections soient partagées. `.claude/` n'est **jamais** committé (c'est de
l'outillage local) : chaque dev crée ses liens une fois.

---

## Les skills

| Skill | Rôle | Quand il se déclenche |
|---|---|---|
| [`djc/`](./djc/) | Conventions de code : Django + HTMX, FALC, ViewSets, serializers DRF, i18n, accessibilité | On écrit du code applicatif |
| [`unfold/`](./unfold/) | Admin Django Unfold : ModelAdmin, inlines, actions, filtres, sections, `add_form` | On touche à `Administration/` ou à un admin |
| [`tibillet-api/`](./tibillet-api/) | Piloter l'API v2 sémantique (schema.org/JSON-LD) : pages, blocs, events, produits | On crée des ressources par l'API |
| [`tibillet-test/`](./tibillet-test/) | Lancer et diagnostiquer les tests : arbre de décision des échecs, purge des schémas | On lance les tests / ils sont rouges |
| [`i18n-translate/`](./i18n-translate/) | Traductions `.po` FR/EN — **ne lance jamais `makemessages`** (c'est le mainteneur) | On parle de traductions, `.po`, fuzzy |
| [`session-end/`](./session-end/) | Clôture de session : audit, conformité, tests, doc | Fin de session |

**Frontières à respecter** (elles ont déjà été violées) :
- Validation dans une **vue** → serializers DRF (`djc`). Validation dans l'**admin** →
  `ModelForm` (`unfold`) : c'est le seul mécanisme que Django y accepte.
- **Lancer/diagnostiquer** les tests → `tibillet-test`. `djc` ne doit PAS dupliquer ses
  commandes : c'est comme ça qu'il s'est mis à annoncer « 234 tests » quand il y en a 787.

---

## Installation (une fois, par dev)

Depuis la racine du dépôt :

```bash
mkdir -p .claude/skills

# Skills liés au dépôt Lespass
ln -sfn "$(pwd)/TECH_DOC/SKILLS/tibillet-api"  .claude/skills/tibillet-api
ln -sfn "$(pwd)/TECH_DOC/SKILLS/tibillet-test" .claude/skills/tibillet-test

# Skills utiles au-delà de Lespass — lien global
for s in djc unfold i18n-translate session-end; do
  ln -sfn "$(pwd)/TECH_DOC/SKILLS/$s" ~/.claude/skills/$s
done
```

Le lien doit être **absolu** (`$(pwd)/...`, pas `../..`) : **un lien relatif n'est pas
résolu** par le chargeur de skills. Relancer Claude Code après création des liens.

Vérifier que tout résout :
```bash
for s in .claude/skills/* ~/.claude/skills/djc; do
  [ -r "$s/SKILL.md" ] && echo "OK    $s" || echo "CASSÉ $s"
done
```

---

## Règle de maintenance — la seule qui compte

**Les skills sont loin du code qu'ils décrivent. C'est à toi d'y penser.**

Regrouper les skills ici les rend trouvables, mais les éloigne du code : rien ne te
rappellera de les mettre à jour. Or **un skill qui ment est pire que pas de skill du
tout — l'agent le croit, et il agit dessus.**

Donc : si tu modifies…

| …ceci | …mets à jour, **dans le même commit** |
|---|---|
| le mapping sémantique de l'API v2, les permissions, le catalogue de blocs | `tibillet-api/SKILL.md` |
| l'infra de test (`conftest.py`), ou tu découvres un piège | `tibillet-test/SKILL.md` **et** `tests/PIEGES.md` |
| une convention de code, un workflow (i18n, CHANGELOG, doc) | `djc/SKILL.md` |

---

## Écrire ou corriger un skill

- **Frontmatter obligatoire** : `name` + `description`. La `description` est ce qui
  décide du **déclenchement** — y écrire les formulations réelles de l'utilisateur
  (« relance les tests », « les tests sont rouges »), pas une définition abstraite.
- **Pas de clé API ni de secret** : ce dossier est versionné. Les scripts lisent la clé
  depuis l'environnement (`$TIBILLET_API_KEY`).
- **Vérifier la cohérence interne.** Un skill qui se contredit d'une section à l'autre est
  un piège : un agent lira la mauvaise. (Cas réel : `djc` recommandait `ruff format` sur
  tout fichier modifié, alors que le même skill expliquait 150 lignes plus haut que c'est
  destructif sur un fichier pré-existant — incident Session 32, 4 h de travail effacées.)
- **Écrire ce qui a coûté cher**, pas ce qui est dans la doc officielle : les pièges, les
  faux verts, les messages d'erreur et leur vraie cause.
