# Redirection des cartes sans /qr/ / Redirect cards printed without /qr/

**Date :** 2026-11-03
**Migration :** Non

## Resume / Summary
**Quoi / What :** l'adresse `https://<lieu>/<uuid>/` redirige (302) vers `https://<lieu>/qr/<uuid>/`.
/ `https://<venue>/<uuid>/` now redirects (302) to `https://<venue>/qr/<uuid>/`.

**Pourquoi / Why :** un lot de cartes NFC de la Raffinerie a ete imprime avec une adresse sans le prefixe `/qr/`. Ces cartes tombaient sur l'attrape-tout des pages et renvoyaient un 404.
/ A batch of NFC cards was printed without the `/qr/` prefix and returned a 404.

La regle s'applique a tous les lieux, sans test sur le nom de domaine : `ScanQrCode` verifie deja la carte aupres de Fedow et redirige vers le domaine du lieu d'origine.
/ The rule applies to every venue: `ScanQrCode` already checks the card with Fedow and redirects to its origin domain.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/urls.py` | Route `<uuid:qrcode_uuid>/` -> `RedirectView` vers `/qr/<uuid>/` |

---

## Comment tester (a la main) / Manual test

### Test 1 — carte connue
1. Prendre l'UUID d'une carte de test (ex : la carte 3).
2. Ouvrir `https://lespass.tibillet.localhost/<uuid>` (sans slash final).
3. Attendu : 301 vers `/<uuid>/`, puis 302 vers `/qr/<uuid>/`, puis le parcours de scan habituel.

### Test 2 — les pages ne sont pas touchees
1. Ouvrir une page publique existante, ex : `/<slug-de-page>/`.
2. Attendu : la page s'affiche comme avant.

### Test 3 — UUID incomplet
1. Ouvrir `/12345678-abcd/`.
2. Attendu : 404 de l'app pages, pas de redirection.

### Verif rapide en ligne de commande
```bash
curl -skI https://lespass.tibillet.localhost/<uuid>/ | grep -i location
# Attendu : location: /qr/<uuid>/
```
