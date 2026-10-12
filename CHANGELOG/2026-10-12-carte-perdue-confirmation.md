# Carte perdue : confirmation avant de détacher / Lost card: confirmation before detaching

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Les deux boutons « J'ai perdu ma carte » du skin V2 (`/my_account/`, sous « Ma carte », et le tableau des cartes) demandent une confirmation : « Déclarer la carte <numéro> perdue ? Elle sera détachée de votre compte : plus personne ne pourra payer avec. Votre solde reste sur votre compte, et vous pourrez lier une nouvelle carte. »
- Un **seul** gestionnaire `htmx:confirm` (fenêtre SweetAlert) vit maintenant dans `pages/V2/shell.html`, dans le `<head>` : il tourne une fois par chargement complet. Les copies des pages réservations et bookings V2 sont retirées : recopié dans une page, il s'empilait à chaque navigation HTMX et un clic pouvait ouvrir plusieurs fenêtres. Titre et boutons traduits (« Confirmer ? », « Oui », « Non »). Si SweetAlert n'est pas chargé, htmx garde sa confirmation native.

/ The V2 lost-card buttons now ask for confirmation; a single SweetAlert `htmx:confirm` handler lives in the V2 shell (page copies removed).

**Non concerné / Not covered :** le skin classic (son bouton « carte perdue » n'a pas de confirmation).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/shell.html` | gestionnaire global `htmx:confirm` |
| `pages/templates/pages/V2/vues/compte/index.html` | `hx-confirm` sur « J'ai perdu ma carte » |
| `pages/templates/pages/V2/vues/compte/partials/card_table.html` | idem |
| `pages/templates/pages/V2/vues/compte/reservations.html`, `bookings.html` | copie du gestionnaire retirée |
| `tests/pytest/test_mon_espace_v2_boutons_qrcode.py` | 2 tests (vérifiés par mutation) |

**i18n :** nouvelles chaînes (question de carte perdue, « Confirmer ? », « Oui », « Non ») — `makemessages` à lancer.

## Comment tester (a la main) / Manual test
1. Avec une carte liée, cliquer « J'ai perdu ma carte » : la fenêtre s'ouvre ; « Non » ne fait rien ; « Oui » détache la carte.
2. Annuler une réservation : une seule fenêtre, même après plusieurs allers-retours entre les pages du compte.

`docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_mon_espace_v2_boutons_qrcode.py -q`
