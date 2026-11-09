# make update_nuit : arrêts lisibles et double programmation refusée / Readable stops and no double scheduling

**Date :** 2026-11-03
**Migration :** Non

## Resume / Summary
**Quoi / What :** `scripts/mise_a_jour_prod.sh` ouvre son journal avant de prendre le verrou, et un
`git fetch` en échec s'arrête avec un message `ARRET : …` explicite. `make update_nuit` refuse de
programmer une mise à jour si une autre est déjà dans `atq`.
/ The update script opens its log before taking the lock, and a failed `git fetch` stops with an
explicit `ARRET` message. `make update_nuit` refuses to schedule when an update is already queued.

**Pourquoi / Why :** sous `at`, la sortie du job est perdue (pas de serveur mail) : un arrêt sur
le verrou n'était écrit nulle part. Le `git fetch` en SSH échoue sous `at` (aucun agent SSH
joignable, « Permission denied (publickey) ») et le script mourait sans message d'arrêt. Deux
`make update_nuit` partaient ensemble à 02:05.
/ Under `at`, job output is lost; an SSH fetch fails without an agent; two scheduled updates ran
together.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `scripts/mise_a_jour_prod.sh` | Journal ouvert avant le verrou ; `git fetch \|\| arreter …` |
| `Makefile` | `update_nuit` : lit chaque tâche avec `at -c`, refuse s'il y trouve `make update` |

### Geste à faire une fois sur la prod / One-time step on production
Le fetch doit passer sans agent SSH. Le dépôt étant lu seulement, on le lit en HTTPS :
```bash
git remote set-url origin https://github.com/TiBillet/Lespass.git
git remote set-url --push origin git@github.com:TiBillet/Lespass.git
git fetch
```
Si GitHub demande un mot de passe, le dépôt est privé : utiliser une deploy key en lecture seule,
sans phrase de passe, dans `~/.ssh` de l'utilisateur qui programme.

---

## Comment tester (a la main) / Manual test

### Test 1 — fetch sans agent SSH (sur la prod, après le geste ci-dessus)
1. `SSH_AUTH_SOCK= git fetch` : doit passer.
2. Avec l'ancien remote SSH, `SSH_AUTH_SOCK= make update` doit finir par
   `ARRET : git fetch a echoue …`, écrit dans `logs/mise_a_jour_*.journal`.

### Test 2 — double programmation
1. `make update_nuit` : une tâche apparaît dans `atq`.
2. Relancer `make update_nuit` : refus, avec le numéro de la tâche et `atrm <numero>`.
3. `atrm <numero>`, puis `make update_nuit` : la programmation passe.

### Test 3 — arrêt sur le verrou écrit dans le journal (en dev, jamais en prod : le verrou bloque aussi la sauvegarde)
1. Dans un terminal : `flock logs/mise_a_jour.lock sleep 2000`.
2. Dans un autre : `make update`. Le journal du passage contient « Verrou pris … Attente ».
   (Pour voir l'arrêt lui-même, il faut attendre 30 min.)

### Verifs
- Testé en dev avec de faux `at`/`atq`/`git`/`docker` : refus si une tâche contient
  `make update`, passage si la tâche est autre chose ou s'il n'y a aucune tâche.
- `bash -n scripts/mise_a_jour_prod.sh` : OK.
