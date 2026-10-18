# Caisse : incident annoncé quand la déclaration de l'adhérent échoue après le débit réseau / Register: incident reported when member declaration fails after the network debit

**Date :** 2026-10-18
**Migration :** Non

## Resume / Summary
**Quoi / What :** dans `_payer_par_nfc`, le journal d'incident du débit legacy est préparé
juste après le débit réseau, avant la déclaration de l'adhérent. Si cette déclaration échoue
(`ValueError`), la caisse journalise l'INCIDENT (montant, carte, uuid des transactions
réseau) et affiche au caissier un message rouge : la carte est débitée, l'adhésion n'est pas
enregistrée, ne pas relancer le paiement, prévenir un responsable. Toute autre exception de
la déclaration journalise l'incident puis remonte (500). Chaque journal d'incident porte
maintenant sa cause.
/ The legacy-debit incident log is prepared right after the network debit. If the member
declaration then fails, the incident is logged and the cashier gets a red message: the card
is debited, do not retry.

**Pourquoi / Why :** le débit sur l'ancien Fedow ne se rembourse pas. Si la déclaration de
l'adhérent échouait juste après, le client était débité sans vente, sans journal d'incident,
et le caissier lisait « Réessayez dans un instant » : relancer débitait la carte une 2ᵉ fois.
/ The network debit cannot be refunded: a failed declaration left the card debited with no
incident log, and the cashier was told to retry.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_payer_par_nfc` : message d'incident préparé avant la déclaration ; sortie `ValueError` (journal + message caissier) et sortie imprévue (journal + raise) ; cause ajoutée aux journaux « solde insuffisant » et « égalité rompue » |
| `tests/pytest/test_caisse_ecrit_la_vente.py` | Nouveau test `test_declaration_adherent_refusee_apres_debit_legacy_journalisee` |

**i18n :** 1 nouvelle chaîne traduisible (msgid FR) — workflow i18n à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

### Test 1 — déclaration refusée après débit réseau
1. Une carte de membre avec de l'argent seulement sur l'ancien Fedow.
2. Couper l'accès au réseau JUSTE après le débit (en dev : patcher
   `_declarer_adherent_au_reseau` pour lever `ValueError`).
3. Payer une adhésion en NFC.
4. Attendu : écran rouge « ATTENTION : la carte a été débitée de X € … Ne relancez pas le
   paiement … ». Dans Sentry / les logs : « INCIDENT legacy débité sans LigneArticle — …
   Déclaration de l'adhérent au réseau refusée : … ».

### Test 2 — lieu non relié au réseau, sans débit legacy
1. Payer une adhésion en espèces dans un lieu non relié.
2. Attendu : le message habituel (« Ce lieu n'est pas connecte au reseau TiBillet… »), pas
   d'incident (aucun argent débité).

### Automatique
`make test ARGS="tests/pytest/test_caisse_ecrit_la_vente.py -k legacy_journalisee"`
