# Revue post-sessions : fix i18n CTA de la home auto-créée + vues ff sur base_template + test E2E skin ff / Post-sessions review: auto-home CTA i18n fix + ff views on base_template + ff skin E2E test

**Date :** 2026-07-05
**Migration :** Non (la 0225, non committée, est corrigée en place) / No (0225, uncommitted, fixed in place)

- **Fix i18n CTA (bug confirmé en base)** : `construire_page_accueil` fige les
  libellés CTA via `gettext()` non-lazy, mais la migration 0225 tournait sans
  langue activée → 22 tenants FR migrés avaient « Calendar »/« Subscriptions »
  gravés en anglais. Fix : `translation.override(config.language or 'fr')`
  autour de l'appel dans la migration ET au step 6ter d'`onboard/tasks.py`
  (l'`activate()` implicite de create_tenant était fragile). Les 22 tenants
  dev touchés ont été réparés (Agenda / Adhésions).
- **Vues faire_festival → `base_template`** : `accueil/agenda/evenement/
  adhesions.html` étendaient `shell.html` en dur → chaque navigation HTMX
  recevait le document COMPLET (htmx s'en sortait via DOMParser mais ~15 %
  de transfert en trop et incohérence avec classic). Elles étendent désormais
  `base_template` comme classic (fragment headless en HTMX). Iso-rendu
  vérifié : 0 diff sur les pages complètes (hors token CSRF).
- **Nouveau test E2E `test_skin_faire_festival_navigation.py`** : le skin ff
  n'était couvert par AUCUN test E2E (angle mort qui a laissé passer le bug
  des panneaux). Le test verrouille : swap HTMX → fragment headless (pas de
  document imbriqué, une seule navbar) + ouverture des panneaux contact et
  connexion après swap.
