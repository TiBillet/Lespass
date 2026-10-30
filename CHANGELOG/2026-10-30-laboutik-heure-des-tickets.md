# LaBoutik : heure des tickets dans le fuseau du lieu / Ticket times in the venue's time zone

**Date :** 2026-10-30
**Migration :** Non

## Resume / Summary
**Quoi / What :** Le ticket cuisine, le billet imprimé et le reçu de remboursement de carte
affichent l'heure dans `Configuration.fuseau_horaire`.
/ Kitchen tickets, printed entry tickets and card refund receipts use the venue's time zone.

**Pourquoi / Why :** Ces trois formats appelaient `timezone.localtime()` sans fuseau, donc
UTC dans le worker Celery : -1 h à Paris en hiver, -2 h en été.
/ These formats used UTC in the Celery worker.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/printing/formatters.py` | `formatter_ticket_commande`, `formatter_ticket_billet` et le reçu de remboursement lisent le fuseau du lieu |
| `tests/pytest/test_formatters_fuseau_du_lieu.py` | Nouveau : 2 tests |

---

## Comment tester (a la main) / Manual test
1. Redémarrer le worker Celery : il ne recharge pas le code seul.
2. Mode restaurant, table, ajouter un article, « Envoi prépa ».
3. Dans les logs Celery, l'heure du ticket Mock est l'heure de Paris.

### Verifs automatiques
`poetry run pytest tests/pytest/test_formatters_fuseau_du_lieu.py`
