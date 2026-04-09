# Spec — Simulateur Pi3 pour controlvanne (kiosk debug panel)

**Date** : 2026-04-09
**Statut** : Validé

## Objectif

Permettre de tester le flow complet d'une tireuse (badge NFC → autorisation → tirage → facturation) sans hardware Raspberry Pi, directement depuis le navigateur.

## Principe

Un panneau debug injecté dans le template kiosk quand `DEMO=1`. Il simule le trio hardware (lecteur NFC + électrovanne + débitmètre) via des appels `fetch()` aux mêmes endpoints API que le vrai Pi.

## Activation

- `settings.DEMO = True` (variable d'env `DEMO=1`, même flag que laboutik)
- La vue `kiosk_view` passe `demo_tags` dans le contexte (même pattern que `laboutik/views.py` `_construire_state()`)
- Le panneau n'apparaît que sur la vue single-tap (`slug_focus` matche un bec)
- Réutilise les mêmes `DEMO_TAGID_*` de settings.py :
  - `DEMO_TAGID_CLIENT1` = `B52F9F3B` → Carte client 1
  - `DEMO_TAGID_CLIENT2` = `C63A0A4C` → Carte client 2
  - `DEMO_TAGID_CLIENT3` = `D74B1B5D` → Carte client 3
  - `DEMO_TAGID_CLIENT4` = `E85C2C6E` → Carte inconnue
- Les cartes se rechargent via le point de vente cashless de l'app laboutik

## UI du panneau

Bandeau sous la carte du bec ciblé :

1. **Rangée de boutons carte** — un par `DEMO_TAGID_*` + bouton "Retirer carte"
2. **Slider débit** — apparaît après autorisation réussie. Range 0→100%. Label affiche le débit courant (ex: "25 ml/s"). Slider = ouverture physique du robinet.
3. **Indicateurs** — volume cumulé, état vanne (ouvert/fermé)

## Mécanique JS — simulation fidèle du TibeerController

Le JS reproduit la machine à états du vrai Pi (`controlvanne/Pi/controllers/tibeer_controller.py`) :

```
État : IDLE → CARD_PRESENT → SERVING → IDLE

1. Clic bouton carte :
   - POST /controlvanne/api/tireuse/authorize/ {tireuse_uuid, uid}
   - Si authorized=true : afficher slider, stocker session_id + allowed_ml
   - Si authorized=false : afficher "Refusé"

2. Slider passe de 0 à >0 :
   - POST pour_start (une seule fois)
   - Démarrer setInterval(100ms) qui accumule le volume :
     volume_ml += (slider_pct * MAX_FLOW_ML_S * 0.1)
     MAX_FLOW_ML_S = 50  (500ml pinte en 10s au max)
   - Toutes les 1s : POST pour_update avec volume cumulé
   - Si volume >= allowed_ml : forcer slider à 0, envoyer pour_end

3. Slider revient à 0 :
   - POST pour_end avec volume final
   - Masquer slider

4. Bouton "Retirer carte" :
   - Si en service : pour_end d'abord
   - POST card_removed
   - Reset UI → IDLE
```

## Constantes

| Constante | Valeur | Justification |
|-----------|--------|---------------|
| `MAX_FLOW_ML_S` | 50 | Pinte (500ml) en 10s au débit max |
| `TICK_INTERVAL_MS` | 100 | Même fréquence que la boucle Pi (100ms) |
| `UPDATE_INTERVAL_MS` | 1000 | Même fréquence que `UPDATE_INTERVAL_S` du Pi |

## Auth

Les `fetch()` utilisent le cookie de session (same-origin). L'admin qui consulte le kiosk a déjà une session valide. `HasTireuseAccess` accepte les sessions admin tenant → pas besoin d'API key côté JS.

## Fichiers à créer/modifier

| Fichier | Action |
|---------|--------|
| `controlvanne/viewsets.py` | Ajouter `demo_tags` dans le contexte de `kiosk_view` quand `DEMO=True` |
| `controlvanne/templates/controlvanne/panel_bootstrap.html` | Block conditionnel `{% if demo_tags %}` sous la carte ciblée |
| `controlvanne/static/controlvanne/js/simu_pi.js` | **Nouveau** — state machine + fetch API + slider logic |

## Pas touché

- `panel_kiosk.js` (inchangé — le WebSocket reçoit les updates normalement, le simulateur est un client API comme le Pi)
- La vue multi-tireuse
- Aucun modèle, aucune migration, aucune URL supplémentaire
