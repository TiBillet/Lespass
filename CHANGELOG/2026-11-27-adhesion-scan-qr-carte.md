# Ajout d'adhésion : flasher le QR code de la carte / Add membership: scan the card QR code

**Date :** 2026-11-27
**Migration :** Non

## Resume / Summary

**Quoi / What :** Dans l'admin, page « Ajouter une adhésion », le champ « Numéro de carte »
a un bouton « Flasher le QR code de la carte ». Il ouvre la caméra, lit le QR code imprimé
sur la carte et remplit le champ avec le numéro (les 8 premiers caractères de l'UUID, en
majuscules). Aucune requête serveur au scan : la carte est vérifiée à l'enregistrement,
comme avant.
/ On the admin "Add membership" page, the card number field gets a "scan the card QR code"
button. It reads the QR code with the camera and fills in the number (first 8 characters of
the UUID, uppercase). No server request at scan time.

**Pourquoi / Why :** Recopier à la main les 8 caractères imprimés est lent et source
d'erreurs. / Typing the 8 printed characters by hand is slow and error-prone.

Spec : `TECH_DOC/SESSIONS/QRCODECASHLESS/CHANTIER-04-scan-qr-adhesion.md`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin_tenant.py` | Nouveau widget `CardNumberQrScanWidget` ; utilisé par `MembershipAddForm.card_number` |
| `Administration/templates/admin/widgets/card_number_qr_scan.html` | Nouveau : champ Unfold d'origine + boutons + vidéo + script (lib `commun/js/qr-scanner.min.js`, déjà présente) |
| `tests/pytest/test_admin_membership_scan_qr_carte.py` | Nouveau : la page d'ajout affiche le bouton et charge la lib |
| `TECH_DOC/SESSIONS/QRCODECASHLESS/CHANTIER-04-scan-qr-adhesion.md`, `INDEX.md` | Spec du chantier |

**i18n :** 5 nouvelles chaînes (source FR) — workflow de traduction à lancer.

---

## Comment tester (a la main) / Manual test

Pré-requis : la caméra n'est accessible qu'en HTTPS (c'est le cas de l'admin).
**En dev, le gabarit du widget est mis en cache** par le moteur des formulaires : après
une modification du gabarit, le serveur doit être rechargé.

### Test 1 — scénario nominal
1. Ouvrir `https://lespass.tibillet.localhost/admin/BaseBillet/membership/add/`.
2. Cliquer « Flasher le QR code de la carte ». Autoriser la caméra.
3. Présenter le QR code d'une carte. En dev, la plupart des cartes ne respectent pas la
   règle « numéro = 8 premiers caractères de l'UUID » : afficher sur un téléphone le QR code
   de `https://lespass.tibillet.localhost/qr/a49e8e2a-0000-4000-8000-000000000000/`.
4. Attendu : le champ affiche `A49E8E2A`, la caméra s'éteint, le message
   « Numéro de carte rempli : A49E8E2A » s'affiche.

### Test 2 — cas limites
- **QR code quelconque** (ex. une adresse web sans UUID) → « Ce QR code n'est pas celui
  d'une carte. », la caméra continue de lire.
- **Ancienne carte** (`https://lieu.tld/<uuid>` sans `/qr/`) → le champ est rempli.
- **Caméra refusée** → « Caméra indisponible ou accès refusé. », la saisie à la main
  reste possible.
- **Bouton « Arrêter la caméra »** → la vidéo disparaît, le bouton « Flasher » redevient actif.
- **Carte hors convention** (numéro imprimé ≠ début de l'UUID) → 8 caractères faux, le
  serveur répond « Unknown card number » à l'enregistrement. Limite assumée.

### Verifs DB / Playwright
- `docker exec lespass_django poetry run pytest tests/pytest/test_admin_membership_scan_qr_carte.py`
- Pas d'E2E caméra. Vérifié dans Chrome le 2026-11-27 avec une fausse caméra (un canvas
  qui affiche le QR code, branché sur `navigator.mediaDevices.getUserMedia`) : carte
  `/qr/<uuid>/`, ancienne carte `/<uuid>`, QR code étranger, refus de la caméra.
