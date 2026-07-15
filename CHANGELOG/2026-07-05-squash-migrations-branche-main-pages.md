# Squash des migrations de la branche main-pages / main-pages branch migrations squash

**Date :** 2026-07-05
**Migration :** Oui — 3 fichiers neufs, jamais déployés / Yes — 3 fresh files, never deployed

Les migrations intermédiaires de la branche (jamais passées en prod, qui
s'arrête à `BaseBillet/0220_lignearticle_idempotency_key` et `seo/0004`) ont
été supprimées et régénérées en UNE migration par app :
- **`pages/0001_initial`** (remplace 0001→0013) — app entière.
- **`BaseBillet/0221_remove_configuration_skin_configuration_module_pages_and_more`**
  (remplace 0220_configuration_module_pages→0225) — schéma (module_pages,
  externalapikey.page, retrait de Configuration.skin) + les 2 opérations de
  données pour les tenants de PROD : copie `skin` → `pages.ConfigurationSite`
  AVANT le RemoveField, et création de la home par défaut (idempotente, dans
  la langue du tenant via `translation.override`). L'ex-0222 (redondante avec
  la home 0225) n'est pas reprise.
- **`seo/0005_alter_seocache_unique_together_and_more`** (régénérée) —
  dédoublonnage RunPython AVANT les 2 contraintes uniques partielles.

Validé : `makemigrations --check` → « No changes detected », `migrate --plan`
sans erreur. Le `down -v` + flush repartira sur ce graphe propre ; en prod, la
chaîne s'ancre exactement sur l'état déployé.
