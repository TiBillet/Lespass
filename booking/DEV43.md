# Dev43

The `booking/` module follows the Dev43 process. Before any work in
`booking/`, load the `dev43:core` skill and follow it.

This file is read through a local, git-ignored symbolic link at the
repository root: `ln -s booking/DEV43.md CLAUDE.md`.

## Scope: the booking module only

Dev43 governs only the `booking/` module of this repository, which is
shared with other developers who do not use Dev43. These rules adapt
the Dev43 skills and take precedence over them where they differ.

- Paths: every `spec/` path in the Dev43 skills means `booking/spec/`
  (`booking/spec/main/`, `booking/spec/changes/`,
  `booking/spec/BACKLOG.md`), including in the git commands they give,
  e.g. `git diff <base> -- booking/spec/` and
  `git log -p -- booking/spec`. Likewise, the project's `README.md`
  means `booking/README.md`.
- The software that `booking/spec/main/` describes is the `booking`
  module. Other apps (e.g. `BaseBillet`, `AuthBillet`) are its
  environment: specify only what `booking` uses of them, never their
  own behavior.
- An increment on `booking` may change shared files outside
  `booking/` (e.g. migrations, admin configuration, settings, URLs,
  templates). They are part of the increment, and exit commits stage
  them as usual (`git add -A`).
- Work unrelated to `booking` is outside the process: Pause does not
  constrain it.
- Git: other developers commit to the same branch, so commits between
  `<base>` and `HEAD` may not be yours. When reading the history of an
  increment, keep only its own commits, e.g.
  `git log -p --reverse --grep='^Dev43-Next: ' <first>^..HEAD`.
