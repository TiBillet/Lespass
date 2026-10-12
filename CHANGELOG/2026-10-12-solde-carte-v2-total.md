# Solde de la carte V2 : euros FED + TLF, cadeau à part / V2 card balance: FED + TLF euros, gift apart

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** sur `/my_account/` (skin V2), le « Solde » de la carte affichait seulement le premier jeton de la liste (le FED, trié en tête). Il additionne maintenant les euros **utilisables dans le lieu courant** : FED (euros fédérés) + TLF (monnaie locale fiduciaire). Dessous, en plus petit : « + X € en cadeau » (TNF du lieu), seulement si le montant n'est pas nul. Le temps (TIM), les points (FID) et la monnaie d'un autre lieu ne comptent pas. La règle « utilisable ici » est celle du tableau des monnaies : la ligne n'est pas grisée.
/ The card balance now sums FED + TLF usable in the current venue; the venue's gift currency (TNF) is shown below, smaller.

**Montant invisible / Invisible amount :** le montant était écrit en dégradé découpé dans le texte (`background-clip: text`, `color: transparent`) avec `--grad-chaud`. Cette variable lit `--letchi-fond`, qui n'est plus définie dans `V2.css` : dégradé invalide, montant invisible. Le montant passe en encre pleine (`--color-text`).
/ The amount used clipped-gradient text on `--grad-chaud`, which reads the undefined `--letchi-fond`: invisible. Now solid ink.

**Pourquoi / Why :** un utilisateur avec de la monnaie locale voyait un solde faux (FED seul), et le montant ne se voyait pas.
/ Users holding local currency saw a wrong balance (FED only), and the amount was invisible.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` (`MyAccount.list`, branche V2) | calcul de `solde_euros_en_centimes` et `solde_cadeau_en_centimes` |
| `pages/templates/pages/V2/vues/compte/index.html` | affiche les deux soldes (`compte-solde`, `compte-solde-cadeau`) |
| `pages/static/V2/css/V2.css` | `.me-card__cadeau` : petit, discret ; `.me-card__amount` en encre pleine |
| `tests/pytest/test_mon_espace_v2_boutons_qrcode.py` | 2 tests (vérifiés par mutation : TLF retiré, filtre « utilisable ici » retiré) |

---

## Comment tester (a la main) / Manual test
### Test 1 — FED + monnaie locale + cadeau
1. Sur un lieu V2 (moteur `fedow_core`), un utilisateur avec une carte, du FED, de la monnaie locale (TLF) et de la monnaie cadeau (TNF) du lieu.
2. `/my_account/` : le solde = FED + TLF ; dessous, « + X € en cadeau ».
3. Comparer avec `/my_account/balance/` : le total correspond aux lignes non grisées FED + TLF.

### Test 2 — sans cadeau
1. Utilisateur sans TNF dans le lieu : pas de ligne cadeau.

`docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_mon_espace_v2_boutons_qrcode.py -q`
