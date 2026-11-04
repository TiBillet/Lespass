# Dev43

Le module `booking/` suit le processus Dev43. Avant tout travail dans
`booking/`, charger la skill `dev43:core` et la suivre.

Ce fichier est lu par un lien symbolique local, ignoré par git, à la
racine du dépôt : `ln -s booking/DEV43.md CLAUDE.md`.

## Langue

- Les documents Dev43 de `booking/` et les échanges avec l'humain sont
  en français.
- Les noms de fichiers restent en anglais, comme le code source.

## Périmètre : le module booking seul

Dev43 ne régit que le module `booking/` de ce dépôt, partagé avec
d'autres développeurs qui n'utilisent pas Dev43. Ces règles adaptent les
skills Dev43 et l'emportent sur elles quand elles diffèrent.

- Chemins : tout chemin `spec/` des skills Dev43 désigne
  `booking/spec/` (`booking/spec/main/`, `booking/spec/changes/`,
  `booking/spec/BACKLOG.md`), y compris dans les commandes git qu'elles
  donnent, par exemple `git diff <base> -- booking/spec/` et
  `git log -p -- booking/spec`. De même, le `README.md` du projet
  désigne `booking/README.md`.
- Le logiciel que décrit `booking/spec/main/` est le module `booking`.
  Les autres apps (par exemple `BaseBillet`, `AuthBillet`) sont son
  environnement : on ne spécifie que ce que `booking` en utilise, jamais
  leur propre comportement.
- Un incrément sur `booking` peut modifier des fichiers partagés hors
  de `booking/` (par exemple migrations, configuration de l'admin,
  réglages, URL, gabarits). Ils font partie de l'incrément, et l'humain
  les indexe avec le reste au commit de sortie (`git add -A`).
- Le travail sans rapport avec `booking` est hors du processus : la
  Pause ne le contraint pas.
- Git : d'autres développeurs committent sur la même branche, donc les
  commits entre `<base>` et `HEAD` ne sont pas forcément les nôtres.
  Pour lire l'historique d'un incrément, ne garder que ses propres
  commits, par exemple
  `git log -p --reverse --grep='^Dev43-Next: ' <first>^..HEAD`.
- Commits : conformément à `GUIDELINES.md`, l'agent ne lance aucune
  opération git qui modifie le dépôt ; il garde les commandes de lecture
  (`git log`, `git diff`, `git status`). Là où Dev43 prévoit un commit,
  il écrit le message complet, trailers compris, dans `.git/SQUASH_MSG`,
  s'arrête et attend que l'humain ait commité. Il relit ensuite l'état
  avec `git log`, puis continue. Les autres commandes que Dev43 lui
  demande, par exemple le `git revert` d'un abandon, il les donne à
  l'humain.
