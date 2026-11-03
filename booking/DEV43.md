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
  `git log -p -- booking/spec`.
- The software that `booking/spec/main/` describes is the `booking`
  module. Other apps (e.g. `BaseBillet`, `AuthBillet`) are its
  environment: specify only what `booking` uses of them, never their
  own behavior.
- Work outside `booking/` is outside the process: Pause and the phases
  constrain only `booking/`. An increment may need a change outside
  `booking/` (e.g. settings, URLs, templates); name it in the plan and
  tag it.
- Git: other developers commit to the same branch, so commits between
  `<base>` and `HEAD` may not be yours. Limit every diff, log and tag
  check of the process to `booking/`, e.g.
  `git diff <base> -- booking/ | grep '^+.*@dev43:'` and
  `git ls-files -o --exclude-standard -z booking/ | xargs -0 -r grep -Hn '@dev43:'`.
- Exit commits stage only `booking/` (`git add -A booking/`, plus any
  file outside it that the plan named), never `git add -A`.
