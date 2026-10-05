# Adhésions actives après un paiement cashless / Active memberships after a cashless payment

**Date :** 2026-10-03
**Migration :** Oui — `laboutik/migrations/0007_laboutikconfiguration_show_membership_after_payment.py` et `0008_alter_laboutikconfiguration_show_membership_after_payment.py`
(`docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing`)

## Resume / Summary
**Quoi / What :** Nouveau réglage laboutik « Afficher les adhésions au retour d'un paiement » (admin > Configuration laboutik > Écran de fin de paiement). Activé, l'écran de succès d'un paiement cashless liste les adhésions actives du titulaire de la carte (nom + date de fin), comme la popup « Vérifier une carte ». Désactivé par défaut.
/ New laboutik setting: when on, the cashless payment success screen lists the card holder's active memberships. Off by default.

**Pourquoi / Why :** Le caissier voit tout de suite si le client est adhérent, sans repasser par « Vérifier une carte ».
/ The cashier sees at once whether the customer is a member.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/models.py` | Champ `LaboutikConfiguration.show_membership_after_payment` |
| `Administration/admin/laboutik.py` | Section « Écran de fin de paiement » avec le réglage |
| `laboutik/views.py` | `_adhesions_actives_de_la_carte()` (partagé avec `retour_carte`) et `_adhesions_a_afficher_apres_paiement()` (lit le réglage) ; contexte `adhesions_actives` dans `_payer_par_nfc()` |
| `laboutik/templates/laboutik/partial/hx_return_payment_success.html` | Bloc « Adhésions actives » sous les cartes |
| `tests/pytest/test_laboutik_adhesions_apres_paiement.py` | 7 tests (helper, réglage, rendu) |

---

## Comment tester (a la main) / Manual test

### Test 1 — réglage désactivé (défaut)
1. Admin > Configuration laboutik : « Afficher les adhésions au retour d'un paiement » décoché.
2. Caisse : payer un article en cashless avec la carte d'un adhérent.
3. L'écran « Paiement réussi » n'affiche AUCUN bloc « Adhésions actives ».

### Test 2 — réglage activé
1. Cocher le réglage, enregistrer.
2. Refaire le paiement cashless avec la carte d'un adhérent.
3. Sous le cadre de la carte : bloc « Adhésions actives », nom de l'adhésion et « Expire jj/mm/aaaa ».

### Test 3 — cas limites
- Carte anonyme (sans utilisateur) : pas de bloc.
- Adhésion annulée par l'admin : n'apparaît pas.
- Adhésion résiliée par l'adhérent mais pas encore échue : apparaît jusqu'à sa date de fin.
- Paiement en espèces ou CB : pas de bloc (seul le paiement cashless lit une carte).

### Verifs DB / Playwright
- `poetry run pytest -q tests/pytest/test_laboutik_adhesions_apres_paiement.py`
- E2E à écrire : paiement NFC avec réglage activé, vérifier `[data-testid="paiement-succes-adhesions"]`.
