# kiosk : la carte est créditée par Lespass, comme à la caisse V2 / kiosk: the card is credited by Lespass, like the V2 POS

**Date :** 2026-09-29
**Migration :** Oui / Yes — `kiosk/migrations/0005_paymentsintent_carte_creditee_le.py`

## Résumé / Summary

**Quoi / What :** quand Stripe confirme un paiement à la borne, Lespass crédite la carte dans sa base
locale (`fedow_core`), avec les mêmes fonctions que la caisse V2 : `_obtenir_ou_creer_wallet` et
`_executer_recharges` (`laboutik/views.py`). Le solde affiché par la borne additionne le Fedow distant
(FED, anciennes monnaies) et la base locale.
/ When Stripe confirms a kiosk payment, Lespass credits the card in its local database, with the
same functions as the V2 POS. The kiosk balance adds remote Fedow + local database.

**Pourquoi / Why :** la carte n'était jamais créditée. Le crédit devait venir du Fedow distant, via
un webhook Stripe qui n'arrivait pas (en local), et qui demandait un patch non livré côté Fedow
(SPEC §8bis). Surtout, la borne est un module V2 : la caisse V2 crédite en local. Avec l'ancien
schéma, la borne et la caisse auraient eu deux soldes différents.
/ The card was never credited (webhook to remote Fedow never arrived, Fedow patch not delivered),
and the kiosk would have disagreed with the V2 POS on the balance.

### Détails / Details
- **Un seul crédit par paiement** : nouveau champ `PaymentsIntent.carte_creditee_le`, posé dans la
  même transaction que le crédit, sous verrou (`select_for_update`). La tâche Celery et le sondage de
  secours peuvent voir le succès en même temps sans double crédit.
- **Point de passage unique** : `PaymentsIntent.get_from_stripe()` crédite dès que le statut devient
  « réussi » (tâche Celery, sondage `payment_status`, annulation `annuler_sur_le_terminal`). Un crédit
  qui a échoué est retenté au prochain passage.
- `get_from_stripe()` n'enregistre plus que le champ `status` (`update_fields`) : une copie en mémoire
  périmée ne peut plus effacer `carte_creditee_le`.
- **Produit utilisé** : « Recharge euros » (`RE`) de la monnaie locale (TLF) du lieu, tarif « Libre ».
  Il est créé tout seul par le signal `fedow_core` avec la monnaie. Ligne de vente en « Carte bancaire
  (TPE) », origine « Caisse » (pas d'origine « Borne » dans `SaleOrigin` pour l'instant).
- Sans monnaie locale (pas de produit `RE` avec tarif libre) : pas de crédit, erreur dans le journal,
  `carte_creditee_le` reste vide (visible dans l'admin des paiements de la borne).

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `kiosk/credit.py` | Nouveau : `trouver_le_produit_de_recharge_de_la_borne`, `crediter_la_carte_du_paiement`. |
| `kiosk/models.py` | Champ `carte_creditee_le`. `get_from_stripe` crédite au succès (+ rattrapage), `save(update_fields=["status"])`. Méthode `crediter_la_carte_si_besoin`. Docstrings mises à jour. |
| `kiosk/migrations/0005_paymentsintent_carte_creditee_le.py` | Nouveau champ. |
| `kiosk/carte.py` | Solde = Fedow distant + jetons locaux (TLF, FED) du portefeuille de la carte (même ordre de priorité que la caisse, sans appel réseau). |
| `kiosk/admin.py` | Colonne « Carte créditée le » dans la liste des paiements. |
| `kiosk/tasks.py` | Commentaires : plus de webhook Fedow. |
| `kiosk/README.md` | Crédit local documenté ; l'extension webhook côté Fedow n'est plus nécessaire. |
| `tests/pytest/test_kiosk_credit.py` | 7 tests : crédit, un seul crédit, statut non réussi, sans carte, via `get_from_stripe`, copie périmée, solde additionné. |

### Migration
- **Migration nécessaire / Migration required :** Oui / Yes
- `docker exec lespass_django poetry run python manage.py migrate_schemas kiosk`
- Redémarrer le worker Celery (il exécute `get_from_stripe`). / Restart the Celery worker.

### Traductions / Translations
Nouvelle chaîne : « Carte créditée le » (`makemessages` non lancé).
