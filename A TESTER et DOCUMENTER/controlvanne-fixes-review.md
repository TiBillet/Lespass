# Controlvanne : fixes de la review critique (CHANTIER-03)

Réf : `TECH_DOC/SESSIONS/CONTROLVANNE/REVIEW-2026-07-06-tour-critique.md`
et `CHANTIER-03-fixes-review.md`.

## Ce qui a été fait

| Fichier | Fix |
|---|---|
| `controlvanne/viewsets.py` | **C1+I1** : verrou `select_for_update` sur la session + transaction atomique englobant fermeture/réservoir/facturation — plus de double facturation sur pour_end concurrents |
| `controlvanne/signals.py` | Push WS du post_save sous `transaction.on_commit` (requis par C1) ; **I2** : swap de fût sans Stock → réservoir remis à 0 |
| `controlvanne/billing.py` | **C3** : carte sans wallet résoluble → refus propre (None) au lieu d'une Exception→500 |
| `controlvanne/serializers.py` | **I3** : `volume_ml` négatif rejeté (`min_value=0`) |
| `controlvanne/models.py` | **I4** : `close_with_volume` met à jour `dernier_volume_ml` (plus de « 0 cl » sur tirage court) |
| `controlvanne/static/.../panel_kiosk.js` | **C2** : reconnexion WS automatique (backoff 1 s→30 s) + gestion bandeau |
| `controlvanne/templates/base.html` | **C2** : bandeau `#ws-status-banner` « Connexion au serveur perdue — reconnexion en cours… » |
| `tests/pytest/test_controlvanne_review_fixes.py` | **Créé** : 5 tests de garde TDD (dont concurrence à 2 threads) |

## Migration nécessaire : Non

## Tests automatiques

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_review_fixes.py -v
# Attendu : 5 passed (dont test_deux_pour_end_concurrents_facturent_une_seule_fois)
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_*.py tests/pytest/test_discovery_*.py -q
# Attendu : 52 passed
```

## Tests manuels

### Test 1 : reconnexion WebSocket du kiosk (C2) — ⚠️ redémarrer le serveur avant (nouveau JS + template)
1. Ouvrir `https://lespass.tibillet.localhost/controlvanne/kiosk/`
2. Console : « WS connecté sur /ws/rfid/all/ », pas de bandeau
3. Couper le serveur (Ctrl+C dans byobu) → le bandeau jaune « Connexion au
   serveur perdue — reconnexion en cours… » apparaît ; console : « WS fermé —
   reconnexion dans N ms » avec N qui double (1000, 2000, … 30000)
4. Relancer le serveur (`rsp`) → à la reconnexion suivante le bandeau
   disparaît, console « WS connecté », les jauges revivent
5. Badge simulateur (DEMO) : tout fonctionne comme avant

### Test 2 : rejeu de pour_end (C1) — via curl
1. Badger une carte cliente sur le kiosk DEMO d'une tireuse avec fût+prix,
   tirer quelques cl, retirer la carte (facturation OK)
2. Rejouer le même `pour_end` en curl avec la clé API tireuse → réponse 200
   « Session already closed » ou 404 « No open session », JAMAIS de seconde
   LigneArticle (vérifier dans l'admin Ventes)

### Test 3 : carte vierge (C3)
1. Créer une CarteCashless sans user ni wallet (shell) et badger son tag_id
   (input simulateur) → le kiosk affiche un refus, PAS d'erreur 500 dans les
   logs serveur

### Test 4 : swap de fût (I2)
1. Tireuse avec `reservoir_illimite` décoché et un réservoir entamé
2. Changer « Active keg » vers un produit FUT sans Stock inventaire →
   après save, `reservoir_ml` = 0 (jauge vide, honnête) au lieu de la valeur
   de l'ancien fût

## Notes

- **makemessages à lancer** (mainteneur) : nouveau msgid FR du bandeau C2
  (« Connexion au serveur perdue — reconnexion en cours… », base.html kiosk).

- Le comportement S6 « bière déjà servie si SoldeInsuffisant » est inchangé
  (loggé, pas bloquant) ; seule la cohérence transactionnelle a été renforcée.
- Les findings Minor de la review restent en dette (liste dans la REVIEW).
