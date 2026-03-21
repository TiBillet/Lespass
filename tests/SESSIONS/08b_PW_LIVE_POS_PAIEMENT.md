# Session 08b — POS paiement + adhesion NFC

## Statut : FAIT (2026-03-21)

## Depend de : 08a (fixtures conftest.py, pattern pos_page)

## Objectif

Convertir les 2 tests POS complexes qui utilisent le POS avec interactions HTMX lourdes.

## Ce qui a ete fait

### conftest.py modifie

- `pos_page` : ajout parametre `comportement` pour filtrer par type de PV (ex: `pos_page(page, comportement="A")` pour PV Adhesions)

### 2 fichiers crees

| Fichier | Tests | Source TS | Resultat |
|---|---|---|---|
| `test_pos_paiement.py` | 8 | PW 39 | 8 PASS |
| `test_pos_adhesion_nfc.py` | 8 | PW 44 | 8 PASS |

### Resultats

- **30 tests E2E** (14 existants 08a + 16 nouveaux)
- **28 passed, 2 skipped** (Biere/Coca couleurs — memes skips que 08a)
- **178 tests pytest inchanges**

### Details test_pos_paiement.py (PW 39)

| Test | Quoi | Mode |
|---|---|---|
| 01 | Deux paiements consecutifs especes + CB (fix HTMX reset) | Especes + CB |
| 02 | Verification admin LigneArticle | Admin Django |
| 03 | NFC cashless solde suffisant (CLIENT1) + verif DB LigneArticle + Transaction | NFC |
| 04 | NFC carte inconnue (CLIENT4 E85C2C6E) → "Carte inconnue" | NFC erreur |
| 05 | NFC solde insuffisant (CLIENT3) → "Il manque" | NFC erreur |
| 06 | NFC puis especes consecutifs (reset HTMX NFC→cash) | NFC + Especes |
| 07 | Deux NFC consecutifs (reset NFC→NFC) | NFC + NFC |
| 08 | NFC multi-articles (Chips+Cacahuetes) + verification solde exact (-350c) | NFC + DB |

### Details test_pos_adhesion_nfc.py (PW 44)

| Test | Chemin | Mode |
|---|---|---|
| chemin_5 | ESPECE → saisir email → confirmation → payer | Formulaire |
| chemin_5bis | CB → saisir email → confirmation → payer | Formulaire |
| chemin_3 | ESPECE → scanner carte (user connu CLIENT3) → confirmation → payer | NFC + user |
| chemin_1 | CASHLESS → NFC carte avec user (CLIENT3) → confirmation directe | NFC + user |
| chemin_2 | CASHLESS → NFC carte anonyme (CLIENT1) → formulaire → confirmation | NFC anonyme |
| chemin_4 | ESPECE → scanner carte (anonyme CLIENT1) → formulaire → payer | NFC anonyme |
| retour_id | Bouton retour depuis ecran identification | Navigation |
| retour_form | Bouton retour depuis formulaire email | Navigation |

### Points d'attention documentes

1. **`transaction.atomic()`** : `WalletService.crediter()` utilise `select_for_update()` → doit etre dans un `with db_transaction.atomic():`. Le code django_shell multi-ligne (avec `\n`) fonctionne car subprocess passe les args en liste.

2. **Fixture `nfc_setup` (scope=module)** : setup lourd (asset TLF + wallet + credit) partage entre les 6 tests NFC. Scope `module` evite de recreer l'asset a chaque test.

3. **Fixture `adhesion_cards_setup` (scope=module)** : setup/teardown cartes CLIENT1 (anonyme) et CLIENT3 (user jetable) via `reset_carte()`. L'ordre des tests est important (chemin 2 AVANT chemin 4).

4. **`pos_page(comportement="A")`** : nouveau parametre pour filtrer le PV par type. Utilise par les tests adhesion.

## Verification

```bash
docker exec lespass_django poetry run pytest tests/e2e/ -v --tb=short
# 28 passed, 2 skipped (~2m53s)

docker exec lespass_django poetry run pytest tests/pytest/ --co -q | tail -1
# 178 tests collected
```
