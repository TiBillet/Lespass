# Tireuse : tirage facturé même sans pour_end, et calibration appliquée au badge / Tap: pour billed without pour_end, calibration applied on badge

**Date :** 2026-11-19
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Une session close par `card_removed` facture au moins le dernier volume reçu par `pour_update`.
- `authorize` renvoie le facteur de calibration du débitmètre. Le Pi l'applique à chaque badge, avant de mesurer la session.
- Le Pi ne relit plus le facteur après une carte de maintenance : le badge suffit.
- Le contrôleur du Pi s'importe sans le matériel : il peut être testé dans le conteneur Django.

/ A session closed by `card_removed` bills at least the last `pour_update` volume. `authorize` returns the calibration factor, applied by the Pi on every badge before measuring. The post-maintenance factor refresh is gone. The Pi controller imports without hardware, so it is testable.

**Pourquoi / Why :**
- Le Pi envoie toujours `card_removed` avec 0 ml. Si son `pour_end` se perdait (4G coupée, délai dépassé), la session était close à 0 ml : la bière servie n'était pas facturée.
- Après « Appliquer » sur la page de calibration, le Pi gardait l'ancien facteur jusqu'à un redémarrage ou une carte de maintenance. Les clients étaient mesurés avec l'ancien facteur, et la série de calibration suivante était fausse.

/ `card_removed` always carries 0 ml: a lost `pour_end` meant an unbilled pour. A new calibration was ignored by the Pi until a restart or a maintenance card.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/viewsets.py` | `_cloturer_session_et_facturer` : plancher au `dernier_volume_ml` de la session verrouillée. `authorize` : `calibration_factor` dans les deux réponses (maintenance et service), débitmètre chargé avec la tireuse. |
| `controlvanne/Pi/controllers/tibeer_controller.py` | Facteur appliqué avant `session_start_vol`. `_rafraichir_calibration` et `last_session_was_maintenance` supprimés. Imports du matériel retirés (inutilisés). |
| `controlvanne/templates/calibration/page.html`, `partial_serie_result.html` | « Le Pi appliquera ce facteur dès le prochain badge. » |
| `controlvanne/README.md` | Le facteur arrive au `ping` et à chaque `authorize`. |
| `tests/pytest/test_controlvanne_api.py` | `test_10b` (facteur dans authorize), `test_11b` (card_removed à 0 ml facture 200 ml). |
| `tests/pytest/test_controlvanne_pi_controleur.py` | Nouveau : contrôleur du Pi avec de faux objets. Facteur appliqué avant la mesure. |

### Ordre de déploiement / Deployment order
**Serveur d'abord, Pi ensuite.** Un Pi à jour face à un serveur ancien ne reçoit plus de nouveau facteur au badge, et il ne relit plus le facteur après une carte de maintenance. Il garderait le facteur lu au démarrage.
/ Server first, then Pi: an updated Pi on an old server only gets the factor at startup.

### Traductions / Translations
Deux chaînes changent dans les gabarits de calibration. `makemessages` reste à lancer par le mainteneur.

---

## Comment tester (a la main) / Manual test

### Test 1 — calibration au badge
1. Sur la page de calibration, appliquer un nouveau facteur.
2. Badger une carte client sur la tireuse.
3. Attendu dans le journal du Pi : « Débitmètre : facteur de calibration mis à jour → <nouveau facteur> », juste avant « Autorise ».

### Test 2 — pour_end perdu
1. Badger, verser un peu, attendre au moins un `pour_update` (1 s).
2. Couper l'accès au serveur (`sudo ip route add blackhole <IP>`), retirer la carte.
3. Rétablir l'accès avant la fin des 3 s de grâce : `pour_end` échoue, `card_removed` passe.
4. Attendu : la session est close et facturée au dernier volume reçu (admin des sessions de la tireuse).

### Tests automatiques
`docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_api.py tests/pytest/test_controlvanne_pi_controleur.py -q`
