# Virements reçus FED : la vente « virement reçu » en direct et son rattrapage / Received FED transfers: the "transfer received" sale, live and caught up

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Le webhook Stripe `transfer.created` écrit maintenant la vente « virement reçu » du `Paiement_stripe` `T` qu'il crée : un article `VR` (quantité 1, TVA 0, hors chiffre d'affaires, monnaie FED) et un règlement Stripe en ligne `SN`, encaissés maintenant, clé `virement-recu-<uuid du paiement>`. Un échec de cette écriture ne fait pas perdre le virement : réponse 201 comme avant et une ligne ERROR au journal, avec la pile d'appels (Sentry). Le journal et la réponse affichent l'uuid court du paiement (et non plus `<bound method …uuid_8>`).
- Une seule fabrique écrit cette vente : `ecrire_la_vente_d_un_virement_recu` (`BaseBillet/services_vente.py`). Elle sert au webhook, à la reprise des ventes et à la commande de rattrapage. Si la monnaie FED est introuvable, elle lève une erreur explicite et n'écrit rien. La lecture du montant et de la date dans `metadata_stripe` devient publique dans ce module (`montant_et_date_du_transfert`).
- Nouvelle commande `rattraper_les_virements_recus [--schema <lieu>] [--executer]`, à blanc par défaut : chaque paiement `T` validé et sans vente reçoit sa vente. Elle prend la date du transfert si celui-ci est après la fin de la dernière clôture du lieu (tous niveaux) ; sinon elle date la vente « maintenant » et le rapport compte ce cas « période close ». Le rapport ne contient que des nombres, des montants, des schémas et des domaines ; une erreur sur un paiement est comptée, nommée par l'uuid court du paiement sur la sortie d'erreur, et la commande continue.

/ The `transfer.created` webhook now writes the VR sale of its T payment (one shared factory, also used by the takeover); a failure keeps the transfer (201 + ERROR log). A new dry-run-by-default command catches up the T payments without a sale.

**Pourquoi / Why :** Depuis la mise en production du chantier 05, un virement FED reçu (cas réel : La Filature, 1 893,00 €, 2026-10-12) créait un paiement validé sans vente : il manquait dans les ventes, les clôtures et les exports. Brief : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-briefs/05-VR-1.md`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/services_vente.py` | `PREFIXE_DE_LA_CLE_D_UN_VIREMENT_RECU`, `montant_et_date_du_transfert` (déplacée), `ecrire_la_vente_d_un_virement_recu` (fabrique) |
| `BaseBillet/reprise_des_ventes.py` | importe `montant_et_date_du_transfert` au lieu de la définir |
| `BaseBillet/reprise_des_ventes_ecriture.py` | un virement reçu du plan est écrit par la fabrique (clé `reprise-<clé>`, date du plan) ; `_creer_l_article_d_un_virement_recu` et `ORIGINE_D_UN_VIREMENT_RECU` supprimés |
| `ApiBillet/views.py` | branche `transfer.created` : appel de la fabrique dans un `try/except`, `uuid_8()` |
| `comptabilite/management/commands/rattraper_les_virements_recus.py` | nouvelle commande de rattrapage |
| `tests/pytest/test_virement_recu_vente.py` | 14 tests (fabrique, dont son atomicité, et commande) ; les dates de transfert sont placées après les clôtures déjà en base |
| `tests/pytest/test_webhook_transfer_created.py` | 3 tests `D` + une assertion sur le rejeu (test B) |

Chaînes i18n ajoutées : aucune.

---

## Comment tester (a la main) / Manual test
### Test 1 — rattrapage à blanc puis réel (dev)
1. `docker exec lespass_django poetry run python /DjangoFiles/manage.py rattraper_les_virements_recus`
2. Vérifier : un bloc par lieu qui a des paiements `T` sans vente, puis le total (paiements trouvés, montant, illisibles, ventes à écrire, ventes à dater maintenant). Rien n'est écrit.
3. Relancer avec `--executer` (ou `--schema <lieu> --executer`) : ventes écrites, ventes datées maintenant (période close), erreurs.
4. Relancer `--executer` une seconde fois : `Ventes écrites : 0`.
5. Dans `/admin/BaseBillet/vente/`, la vente « Virement pot central » apparaît, réglée, avec un règlement « Online: Stripe CC ».

### Test 2 — production (La Filature)
Le mainteneur lance les commandes, une à la fois, **hors de hh:00 à hh:05** (le filet horaire
des clôtures tourne à l'heure pile : une J créée entre la lecture de la dernière clôture et
l'écriture de la vente laisserait la vente dans une J déjà close) :
1. à blanc `--schema ffe52f5e8b134bf6b62b4d5b2b346763` : `Paiements trouvés : 1`, `Montant : 1893.00 €` ;
2. `--executer` : `Ventes écrites : 1`. Si une clôture finit après le 2026-10-12 05:17 UTC : `Ventes datées maintenant (période close) : 1` ;
3. la vente de 1 893,00 € est visible dans `/admin/BaseBillet/vente/`.

### Test 3 — webhook
Un prochain `transfer.created` réel : la vente apparaît tout de suite, et le journal affiche `Paiement_stripe.objects.created : <8 caractères>`.

### Verifs automatiques
`make test ARGS="tests/pytest/test_virement_recu_vente.py tests/pytest/test_webhook_transfer_created.py tests/pytest/test_reprise_des_ventes.py"`
