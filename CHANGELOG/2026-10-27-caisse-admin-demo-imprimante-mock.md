# Caisse admin de démo avec imprimante mock / Admin demo till with mock printer

**Date :** 2026-10-27
**Migration :** Non

## Resume / Summary
**Quoi / What :** le flush (`demo_data_v2`) crée sur `lespass` un terminal LaBoutik « Caisse admin (démo) » dont le compte est l'admin (`ADMIN_EMAIL`) et dont l'imprimante est « Console (mock) ». L'admin qui tient la caisse dans son navigateur voit ses tickets dans les logs Celery.
/ The flush seeds a LaBoutik terminal "Caisse admin (démo)" owned by the admin account (`ADMIN_EMAIL`), with the mock printer. Tickets printed from the admin's browser show up in the Celery logs.

**Pourquoi / Why :** une imprimante appartient à un terminal (`imprimante_du_terminal`). En session admin, il n'y avait pas de terminal, donc aucune impression testable en dev sans appairer un appareil. Aucun code applicatif ne change : la règle de prod s'applique telle quelle.
/ A printer belongs to a terminal. An admin session had none, so nothing could be printed in dev without pairing a device. No application code changes: the production rule applies as is.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/management/commands/demo_data_v2.py` | Nouveau seed `_seed_caisse_admin_demo()`, appelé après `_seed_kiosk_demo()` |
| `tests/e2e/test_caisse_liste_detail_ventes.py` | `test_le_bouton_reimprimer_envoie_l_uuid_de_la_vente` attend « Impression lancée » (l'admin a maintenant une imprimante) |

### Attention
L'action admin **« Générer un nouveau code PIN »** sur « Caisse admin (démo) » désactive le compte du terminal (`is_active=False`), c'est-à-dire **le compte admin**. Ne pas l'utiliser sur ce terminal.

---

## Comment tester (a la main) / Manual test

### Test 1 — ticket de vente
1. Flush (ou relancer `demo_data_v2`).
2. Dans un terminal : `docker logs -f lespass_celery 2>&1 | grep -A 30 "MOCK PRINTER"`
3. Se connecter avec le compte `ADMIN_EMAIL`, ouvrir la caisse, faire une vente, cliquer « Imprimer » sur l'écran de succès.
4. Attendu : « Impression lancée » dans la caisse, et le ticket encadré en ASCII dans les logs Celery.

### Test 2 — réimpression
1. Liste des ventes → déplier une vente → « Ré-imprimer ».
2. Attendu : « Impression lancée », ticket dans les logs Celery.

### Verifs DB / Playwright
- `docker exec lespass_django poetry run python /DjangoFiles/manage.py tenant_command shell --schema=lespass -c "from laboutik.models import Terminal; print(Terminal.objects.filter(name='Caisse admin (démo)').values('terminal_role','term_user__email','printer__name'))"`
- E2E : `tests/e2e/test_caisse_liste_detail_ventes.py -k reimprimer`
