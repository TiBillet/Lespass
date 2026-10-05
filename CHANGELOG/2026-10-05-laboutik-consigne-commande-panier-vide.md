# Caisse : retour de consigne hors commande, panier vide refusé / POS: deposit return kept out of orders, empty cart refused

**Date :** 2026-10-05
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Un retour de consigne ne peut plus entrer dans une commande de table (`ouvrir_commande`, `ajouter_articles`) : refus 400 avant toute écriture.
  / A deposit return can no longer enter a table order: 400 before any write.
- `payer()` refuse un panier vide (400 « Panier vide. ») avant tout routage vers un flux de paiement.
  / `payer()` refuses an empty cart before routing to any payment flow.

**Pourquoi / Why :**
- Issue LaBoutik #44 : un retour de consigne envoyé en préparation donnait une commande impayable (`payer_commande` le refuse).
  / A deposit return sent to preparation produced an unpayable order.
- Issue LaBoutik #39 : paiement NFC sans tag ni article. Le bouton VALIDER est désactivé côté client, mais rien ne bloquait un POST forcé côté serveur.
  / NFC payment with no tag and no item: only the client blocked it.
- Issue LaBoutik #40 (`tag_id="error"`) : déjà corrigée en V2 (`nfc.js` rejette tout tag ≠ 8 caractères, le serveur répond « Carte inconnue »). Aucun changement.
  / Already fixed in V2, no change.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | Garde panier vide dans `payer()` ; garde retour de consigne dans `ouvrir_commande()` et `ajouter_articles()` |
| `tests/pytest/test_pos_retour_consigne.py` | 4 tests : ouvrir/ajouter une commande avec consigne, payer en NFC un panier vide (avec et sans tag) |
| `tests/pytest/test_paiement_especes_cb.py` | Panier vide / produit inconnu : on attend désormais un refus 400 « Panier vide. » (et non un succès vide 200) |

Aucune nouvelle chaîne traduisible (msgids existants réutilisés).

---

## Comment tester (a la main) / Manual test

### Test 1 — commande avec retour de consigne
1. POST JSON `/laboutik/commande/ouvrir/` avec `uuid_pv` et un article dont le produit a `methode_caisse=CR`.
2. Attendu : 400, message « Un retour de consigne se règle au comptoir, pas depuis une commande. », aucune `CommandeSauvegarde` créée.
3. Même chose sur `/laboutik/commande/ajouter/<uuid>/` avec une commande OPEN : 400, aucun article ajouté.

### Test 2 — panier vide
1. POST `/laboutik/paiement/payer/` avec `uuid_pv`, `moyen_paiement=nfc`, un `tag_id` valide (ou aucun), sans aucune clé `repid-*`.
2. Attendu : 400, message « Panier vide. », aucune `LigneArticle` ni transaction.

### Test 3 — non-régression
- Un retour de consigne au comptoir (espèces / NFC) fonctionne toujours.
- Une vente ordinaire et une commande de table ordinaire fonctionnent toujours.

### Verifs DB / Playwright
- `docker exec lespass_django poetry run pytest tests/pytest/test_pos_retour_consigne.py -q`
