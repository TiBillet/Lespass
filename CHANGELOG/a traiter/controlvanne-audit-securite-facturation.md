# controlvanne : restes de l'audit du 2026-09-26 (lots 1 et 2 traités)

**Relevé du 2026-09-26.** Il vient de trois audits en lecture seule de
`controlvanne/` : djc côté Python, djc côté templates/JS, et hallmark sur
l'interface. Les lots 3 (écran kiosk) et 4 (calibration, i18n, a11y) ont été
corrigés : voir `CHANGELOG/2026-09-26-controlvanne-audit.md`. Les lots 1
(sécurité) et 2 (facturation) ont été traités le 2026-09-28.

Chaque point **critique** a été vérifié dans le code. Les autres viennent des
audits et sont à confirmer au moment de les traiter.

**Traités :** tous les points instruits des lots 1 (sécurité) et 2
(facturation).
- 1.4, 1.5, 1.6 → `CHANGELOG/2026-09-28-controlvanne-securite-cles-calibration.md` ;
- 1.1, 1.2, 1.3 → `CHANGELOG/2026-09-28-controlvanne-websocket-acces-et-groupes-par-lieu.md` ;
- 2.1 à 2.6 → `CHANGELOG/2026-09-28-controlvanne-facturation.md`.

Il ne reste ci-dessous que des points relevés par les audits mais **non
instruits** (pas de scénario d'échec mesuré).

---

## Hors lots, relevés mais non instruits

- `ws_payloads.py` n'est importé nulle part, `force_close` n'est jamais émis,
  `RfidSession.last_message` n'est jamais écrit, `controlvanne/tests.py` est
  vide, et `ConfigurationTireuse` n'a aucun champ.
- `billing.py` importe des fonctions privées de `laboutik/views.py`
  (`_obtenir_ou_creer_wallet`, `_calculer_qty_partielles`) : il faudrait les
  déplacer dans un module `services`.
- `REMOTE_ADDR` derrière Traefik donne l'IP du proxy, pas celle du Pi.
- ~~Docstring de `AuthKioskView` contradictoire~~ : corrigée le 2026-09-28 avec
  la suppression de `KioskTokenView` (elle décrit maintenant le vrai parcours
  `?kiosk_token=`).
