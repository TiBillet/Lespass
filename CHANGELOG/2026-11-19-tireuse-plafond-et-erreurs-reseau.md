# Tireuse : plafond contrôlé à chaque tour, erreurs réseau sans plantage / Tap: cap checked every turn, network errors without crash

**Date :** 2026-11-19
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- Le Pi contrôle le plafond de volume à chaque tour de boucle (toutes les 100 ms), et non plus une fois par seconde. Le contrôle a aussi lieu pendant la période de grâce, quand la carte n'est plus lue.
- Une erreur réseau sur `pour_start`, ou sur `pour_end` au plafond, est journalisée. Elle n'arrête plus le programme.

/ The Pi checks the volume cap on every loop turn (100 ms) instead of once per second, also during the grace period. A network error on `pour_start` or on `pour_end` at the cap is logged and no longer stops the program.

**Pourquoi / Why :**
- Avec un contrôle par seconde, la vanne coulait jusqu'à une seconde après le plafond. Ce surplus n'est pas facturé : c'était une perte pour le lieu.
- Une erreur réseau sur ces deux appels remontait jusqu'à `main.py`, qui quittait. systemd relançait le service, avec un `git pull` à chaque fois.

/ One check per second let the valve run up to a second past the cap, unbilled. A network error on these calls killed the program, restarted by systemd with a `git pull`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `controlvanne/Pi/controllers/tibeer_controller.py` | Nouvelle méthode `_fermer_si_plafond_atteint()`, appelée à chaque tour dans `run()`. Elle ferme la vanne avant d'envoyer `pour_end`, dans un `try`. `pour_start` est dans un `try`. `_handle_pouring_loop` n'envoie plus que `pour_update`. |
| `tests/pytest/test_controlvanne_pi_controleur.py` | 3 tests : erreur sur `pour_start`, vanne fermée avant 130 ml pour un plafond de 100 ml, erreur sur `pour_end` au plafond. La vraie boucle `run()` tourne avec une fausse horloge. |

---

## Comment tester (a la main) / Manual test

### Test 1 — plafond
1. Créditer une carte d'un petit montant (environ 10 cl de bière).
2. Badger et laisser couler.
3. Attendu : « Volume max atteint » dans le journal, et la vanne se ferme net, sans couler encore une seconde.

### Test 2 — erreur réseau au plafond
1. Même carte. Couper l'accès au serveur pendant le service (`sudo ip route add blackhole <IP>`).
2. Attendu : la vanne se ferme au plafond, le journal affiche « pour_end au plafond echoue », et le service `tibeer` ne redémarre pas (`systemctl status tibeer`).
3. Rétablir l'accès (`sudo ip route del blackhole <IP>`), retirer la carte : la session est close au dernier volume reçu.

### Tests automatiques
`docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_pi_controleur.py -q`
