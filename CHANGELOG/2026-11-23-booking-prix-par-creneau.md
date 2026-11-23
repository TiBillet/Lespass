# Réservation de ressources : tarifs par créneau / Resource booking: per-slot prices

**Date :** 2026-11-23
**Migration :** Non

## Resume / Summary

**Quoi / What :**
- Le formulaire de réservation d'une ressource affiche les tarifs par créneau : « Plein tarif - 36 € / créneau », « Soutien - prix libre dès 15 € / créneau », « Solidaire - prix libre », « Bénévoles - gratuit ». Le prix reste horaire en base et dans l'admin.
- Un créneau vaut `prix × durée / 60`, arrondi au centime. N créneaux valent N fois ce montant : le réservant paie exactement ce qu'il a lu.
- Une durée multiple de 60 minutes ne change jamais de prix. Pour les autres durées, l'écart avec l'ancien calcul est d'au plus un centime par créneau (3 créneaux de 40 minutes à 10 €/h : 20,01 € au lieu de 20,00 €).
- Le montant d'un prix libre est saisi par créneau, et payé exactement. Le minimum affiché est arrondi au centime supérieur.
- La ligne d'une ressource dans le panier se lit « N × montant d'un créneau = total ».
- Un seul calcul, `booking/montants.py`, pour le formulaire, le panier et le paiement.
- / The booking form shows resource prices per slot. One slot is `prix × duration / 60` rounded to the cent; N slots pay N times that amount. Durations that are multiples of 60 minutes never change. Open prices are typed per slot. The cart line reads "N × slot amount = total". One computation in `booking/montants.py`.

**Pourquoi / Why :**
Un lieu aux créneaux de 3 heures (G'Récup) affichait un prix par heure, et un prix libre saisi par heure : le réservant ne savait pas ce qu'il allait payer. Contribution de Joris (PR #492).
/ A venue with 3-hour slots showed hourly prices and hourly open amounts: bookers could not tell what they would pay. Contributed by Joris (PR #492).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/montants.py` | Nouveau : montant d'un créneau, de N créneaux, minimum d'un prix libre, conversion d'un montant saisi par créneau |
| `booking/booking_engine.py` | `validate_new_booking` calcule le montant et le minimum par `booking/montants.py` |
| `BaseBillet/services_panier.py` | `add_resource` : même calcul que le moteur |
| `booking/views.py`, `BaseBillet/views.py` | Montant d'un prix libre reçu par créneau, ramené à l'heure ; libellés par créneau (`tarifs_du_formulaire`) |
| `booking/templates/booking/partials/book_form.html` | Libellés et champ de montant par créneau |
| `BaseBillet/context_processors.py`, `BaseBillet/templates/htmx/components/panier_item.html` | Ligne du panier « N × montant d'un créneau = total » |
| `env_example` | Bloc LaBoutik V1 commenté : il écrasait les `DEMO_TAGID_*` des tests E2E |
| `booking/tests/test_booking_form_prices.py`, `tests/pytest/test_booking_montant_par_creneau.py` | Nouveaux tests |
| `tests/pytest/test_panier_session.py`, `tests/pytest/test_panier_mvt.py` | Attentes au centime par créneau, ligne du panier |
| `TECH_DOC/SESSIONS/BOOKING/CHANTIER-02-prix-par-creneau.md` | Règles, tableau des arrondis, reste à faire |

**Traductions :** 6 nouvelles chaînes source en français (`prix libre dès %(montant)s € / créneau`, `Montant par créneau, %(montant)s € minimum`, `prix libre`, `Montant par créneau`, `gratuit`, `%(montant)s € / créneau`). Le workflow i18n est à lancer.

---

## Comment tester (a la main) / Manual test

### Test 1 — tarif fixe, créneaux de 40 minutes
1. Dans l'admin, créer une ressource dont la période d'ouverture a des créneaux de 40 minutes, avec un tarif fixe à 10 €/h.
2. Connecté, ouvrir le formulaire de réservation d'un créneau.
3. Vérifier : « <nom> - 6,67 € / créneau ».
4. Réserver 3 créneaux, ajouter au panier : la ligne dit « 3 × 6,67 € = 20,01 € ». Le paiement Stripe demande 20,01 €.

### Test 2 — tarif fixe, créneaux d'une heure (rien ne change)
1. Une ressource à créneaux de 60 minutes, tarif 9,99 €/h.
2. Le formulaire dit « 9,99 € / créneau » ; 2 créneaux coûtent 19,98 €.

### Test 3 — prix libre, créneaux de 180 minutes
1. Tarif à prix libre, minimum 5 €/h, créneaux de 180 minutes.
2. Le formulaire dit « prix libre dès 15 € / créneau », le champ « Montant par créneau, 15 € minimum ».
3. Saisir 14,99 : refusé. Saisir 20 : accepté, on paie 20 € pour un créneau, 40 € pour deux.

### Test 4 — prix libre sans minimum, tarif gratuit
1. Un prix libre à 0 € se lit « prix libre », son champ « Montant par créneau ».
2. Un tarif fixe à 0 € se lit « gratuit ».

### Verifs automatiques
- `docker exec lespass_django poetry run pytest booking/tests/test_booking_form_prices.py tests/pytest/test_booking_montant_par_creneau.py tests/pytest/test_panier_session.py tests/pytest/test_panier_mvt.py -v`
