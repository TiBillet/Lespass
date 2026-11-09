# Borne kiosk : les Pi suivent main / Kiosk: Pi devices follow main

**Date :** 2026-10-27
**Migration :** Non

## Resume / Summary
**Quoi / What :** la borne kiosk (Raspberry Pi) s'installe et se met a jour depuis la branche `main`, et non plus `main-fedow-import`. / The kiosk Pi installs and updates from `main` instead of `main-fedow-import`.
**Pourquoi / Why :** la branche `main-fedow-import` a ete supprimee de GitHub : l'URL d'installation renvoyait 404. Meme correction que pour les tireuses (PR #488). / The `main-fedow-import` branch was deleted from GitHub, so the install URL returned 404. Same fix as the beer taps (PR #488).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `kiosk/Pi/Makefile` | URL `curl` d'installation et `GIT_BRANCH` par defaut -> `main` |
| `kiosk/README.md` | URL `curl` d'installation et exemple `tibillet.conf` -> `main` |

---

## Comment tester (a la main) / Manual test
### Test 1 — URL d'installation
1. `curl -sI https://raw.githubusercontent.com/TiBillet/Lespass/main/kiosk/Pi/Makefile | head -1`
2. Attendu : `HTTP/2 200` (une fois ce changement pousse sur `main`).

### Test 2 — borne deja installee
Une borne clonee sur `main-fedow-import` ne se met plus a jour (la branche distante n'existe plus) :
la repointer a la main sur `main`, ou la reinstaller.
