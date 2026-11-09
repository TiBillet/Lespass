# Caisse : vrai solde après vente, et adhésion sur carte anonyme avec complément / Register: real after-sale balance, and memberships on anonymous cards with a complement

**Date :** 2026-10-31
**Migration :** Non

## Resume / Summary
**Quoi / What :** après un paiement cashless, l'écran de succès montre ce qui a été payé, monnaie par monnaie, FED compris (ligne « TiBillet »), et le solde total en euros de la carte (monnaies de la cascade + FED), en plus gros chiffre. Le solde de chaque monnaie n'est plus affiché : le détail est au check carte. Les points et le temps gardent leur reste, car ils ne sont pas dans le total en euros. Le FED est lu à chaque vente, avant le débit, même quand la monnaie locale couvre tout ; le solde après vente se calcule (FED lu − FED débité), sans nouvel appel à Fedow, sauf rattachement de la carte par une adhésion. Fedow injoignable : la vente passe, l'écran affiche le total local et « TiBillet : Indisponible ». Un lieu sans ancien Fedow n'affiche aucune mention.
/ After a cashless payment, the success screen shows what was paid per currency, FED included, and the card's euro total as its biggest figure. Per-currency balances move to the card check, except points and time. FED is read on every sale, before the debit; the after-sale balance is computed. Fedow down: the sale goes through and the screen says so.

**Pourquoi / Why :** l'écran ne lisait que les monnaies locales débitées. Une carte avec 5 € de CAB et 45 € de FED affichait 1,90 € après un café, alors que le check carte affichait 46,90 € (retour de La Cabine). L'unification du 2026-10-18 portait sur le check carte et l'écran « Client identifié », pas sur cet écran.
/ The screen only read the debited local currencies: a card with 46.90 € showed 1.90 €. The 2026-10-18 unification covered other screens.

**Corrigé au passage / Also fixed :** une carte anonyme qui prend une adhésion voit son portefeuille éphémère fusionné dans celui de l'adhérente pendant la vente. L'écran lisait encore l'ancien portefeuille et affichait 0,00 € au lieu du solde réel. Après ce rattachement, le portefeuille local et le FED sont relus : le FED du compte de l'adhérente compte dans le total.
/ An anonymous card taking a membership showed 0.00 € after its wallet merged. Wallet and FED are now read again after the merge.

**Adhésion sur carte anonyme avec complément / Membership on an anonymous card with a complement :** le complément (espèces, CB ou 2ᵉ carte) n'identifiait pas l'adhérent : la carte était débitée, la ligne créée, et aucune adhésion n'existait. Le complément identifie maintenant l'adhérent par l'e-mail saisi, avant tout débit, le déclare au réseau juste avant le bloc atomic, rattache la CARTE 1 (jamais la 2ᵉ carte), crée l'adhésion et affiche les avertissements de rattachement. L'adhésion du complément garde le montant du prix libre, le prénom et le nom saisis ; ceci vaut aussi pour une carte déjà liée, qui garde sinon son parcours.
/ The complement never identified the member: the card was debited and no membership existed. It now identifies, declares, attaches card 1 and creates the membership, with the free-price amount and the typed names.

**Écran de complément / Complement screen :** « Payé par la carte » compte aussi le FED, pour que total − payé = reste. Le second écran (2ᵉ carte insuffisante) ajoute une pastille TiBillet pour le FED de la carte 1. Le champ caché `total_nfc_carte1` reste le montant local : seul l'affichage change.
/ "Paid by card" includes FED so the sum adds up; the hidden field stays local.

**Effet réseau / Network effect :** une lecture Fedow de plus sur les ventes que le local couvre seul, et sur la 2ᵉ carte quand son local couvre le reste, plus une lecture après le rattachement d'une carte par une adhésion. Cette lecture attend Fedow 10 s pour se connecter, puis 10 s pour répondre (`DELAI_DE_LECTURE_DU_FED_EN_SECONDES`), et se dégrade ensuite en silence : caisse, check carte et tireuse en profitent.
/ One more Fedow read on local-only sales, plus one after a membership merge. The read waits 10 s to connect, then 10 s for the reply, and then degrades silently.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | **Nouvelle** fonction `_carte_pour_l_ecran_de_succes` ; `_payer_par_nfc` et `payer_complementaire` lisent le FED à chaque vente et l'utilisent pour l'écran de succès |
| `fedow_connect/fedow_api.py` | `_get` et `NFCcard.retrieve` acceptent un `timeout` (30 s par défaut, inchangé pour les autres appels) |
| `laboutik/views.py` (adhésion) | `_identifier_adherent` accepte la carte de l'adhérent ; **nouvelles** fonctions `_declarer_l_adherent_du_complement`, `_rattacher_la_carte_a_l_adherent`, `_fed_avant_le_paiement` |
| `laboutik/views.py` (complément) | `total_nfc_carte1_euros` affiche local + FED ; pastille TiBillet de la carte 1 au second écran |
| `laboutik/templates/laboutik/partial/_succes_carte.html` | Solde total (`paiement-carte<rang>-solde-total`) et réseau indisponible (`paiement-carte<rang>-reseau-indisponible`) |
| `laboutik/templates/laboutik/partial/_succes_carte.html` (lignes) | Une ligne par monnaie payée, sans avant ni après |
| `laboutik/static/css/overlay.css` | `.succes-paiements`, `.succes-solde-total`, `.succes-reseau-indisponible` ; styles avant / après retirés |
| `tests/pytest/test_ecran_succes_solde_total.py` | **Nouveau** : 13 tests avec Fedow simulé, vus échouer avant la correction et sur des mutations |
| `tests/e2e/test_ecran_succes_solde_total_fedow_reel.py` | **Nouveau** : 4 cas contre le vrai Fedow et le vrai Stripe |
| `tests/pytest/test_adhesion_carte_anonyme_complement.py` | **Nouveau** : 11 tests (espèces, CB, 2ᵉ carte, prix libre, carte déjà liée) ; ils relisent la vente (statut, numéro, client, carte, total, règlements) et l'adhésion (statut, échéance, montant, identité) |
| `tests/e2e/test_adhesion_carte_anonyme_complement_fedow_reel.py` | **Nouveau** : 5 cas à l'écran contre le vrai Fedow (espèces, CB, 2ᵉ carte, prix libre) ; ils relisent aussi la vente et l'adhésion en base |
| `tests/pytest/test_rapatriement_carte_points_de_scan.py` | 2 tests : la liste des appels à Fedow compte la lecture ajoutée |
| `tests/pytest/` (6 fichiers) | Les faux Fedow acceptent le `timeout` |
| `laboutik/templates/laboutik/partial/hx_return_payment_success.html` | Commentaires à jour |

**i18n :** une chaîne nouvelle à traduire, le message « ATTENTION : le réseau a débité %(montant)s €… » de `_declarer_l_adherent_du_complement`. « Solde total », « Payé », « Sur la carte », « Indisponible » et les autres messages d'adhésion existent déjà.

---

## Comment tester (a la main) / Manual test

### Test 1 — le local suffit, la carte porte aussi du FED
1. Une carte avec 5 € de monnaie locale et du FED rechargé en ligne.
2. En caisse, payer un café en cashless.
3. Attendu : le montant payé en monnaie locale, et « Solde total », en plus gros chiffre, égal au check carte.

### Test 2 — local partiel, FED suffisant
1. Une carte avec 1 € de monnaie locale et 3 € de FED, un café à 1,50 €.
2. Attendu : une ligne monnaie locale (− 1,00 €), une ligne TiBillet (− 0,50 €), « Solde total » 2,50 €.

### Test 3 — local et FED insuffisants
1. Même carte, trois cafés (4,50 €) : l'écran du complément annonce 0,50 €.
2. Encaisser en espèces.
3. Attendu : « Solde total » 0,00 €.

### Test 4 — local insuffisant, pas de FED
1. Une carte avec 1 € de monnaie locale, un café à 1,50 €.
2. Encaisser 0,50 € en espèces.
3. Attendu : pas de ligne TiBillet, « Solde total » 0,00 €.

### Test 5 — Fedow arrêté
1. `docker stop fedow_django`, puis payer en monnaie locale.
2. Attendu : la vente passe, avec le total local et « TiBillet : Indisponible ».
3. `docker start fedow_django`.

### Test 6 — adhésion sur une carte anonyme, avec complément
1. Mettre une adhésion à 5,00 € au panier, scanner une carte anonyme à 1,00 €, saisir l'e-mail, le prénom et le nom, choisir la carte.
2. Encaisser les 4,00 € restants en espèces, ou sur une 2ᵉ carte.
3. Attendu : l'adhésion est dans l'admin au nom de cet e-mail, avec le prénom et le nom saisis, et la première carte lui est rattachée. Avec un tarif à prix libre, l'adhésion garde le montant choisi.

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_ecran_succes_solde_total.py tests/pytest/test_adhesion_carte_anonyme_complement.py"`
- `make e2e ARGS="tests/e2e/test_ecran_succes_solde_total_fedow_reel.py -v"` (`stripe listen` requis)
- `make e2e ARGS="tests/e2e/test_adhesion_carte_anonyme_complement_fedow_reel.py -v"`
