# Unreleased — Fix message trompeur sur reservation gratuite anonyme / Misleading message on anonymous free booking

**Date :** 2026-04-21
**Migration :** Non

---

### Correction de la page de confirmation de reservation gratuite / Free booking confirmation page fix

**FR :**
Lorsqu'un visiteur non connecte reservait une activite gratuite avec l'email d'un compte
deja existant et actif, la page de confirmation affichait « Veuillez valider votre e-mail »
alors que les billets etaient deja envoyes (resa en `FREERES_USERACTIV`) et que la
reservation etait confirmee en back-office.

Cause : la vue `EventViewset.reservation` passait `request.user` au template. Quand le
visiteur n'est pas connecte, `request.user` vaut `AnonymousUser` dont `is_active` est
toujours `False`. Le template basculait alors sur la branche « validez votre email »
en ignorant l'etat reel de l'user retrouve en base par email.

Fix : passer `validator.reservation.user_commande` au template. Cet user est celui
resolu par `get_or_create_user(email)` dans le validator, donc coherent avec la
decision prise par `TicketCreator.method_F` pour envoyer (ou non) les billets
immediatement.

**EN :**
When an unauthenticated visitor booked a free activity using the email of an
already-existing active account, the confirmation page showed "Please validate your
e-mail" even though the tickets were already sent and the booking was confirmed.

Root cause: the view passed `request.user` (an `AnonymousUser` with `is_active=False`)
to the template. Fix: pass `validator.reservation.user_commande` instead — the user
resolved by the validator from the submitted email.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `EventViewset.reservation` : passe `validator.reservation.user_commande` au template au lieu de `request.user` |

### Migration
- **Migration necessaire / Migration required:** Non

---
