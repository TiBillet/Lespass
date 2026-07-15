# Chantier SEO #02 — Review critique + 10 fixes prod / Critical review + 10 prod fixes

**Date :** 2026-05-13
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Review critique de la session SEO/FEDERATION par un agent + navigation
Chrome MCP. Score initial 79/100, 10 fixes appliques pour atteindre la qualite
prod :

1. **Critical XSS JSON-LD** : helper `json_for_html()` qui translate `<>&` en
   sequences unicode `< > &`. Empeche qu'un admin tenant qui met
   `</script>` dans son nom de configuration casse le HTML des pages de ses
   voisins (qui consomment le SEOCache).
2. **`<h1>` ajoutes** sur `/federation/` tenant et `/explorer/` public (etaient
   absents, 21+ H3 seulement). Visually-hidden, n'affecte pas l'UI.
3. **Open Graph + Twitter tags** : override `og_title`, `twitter_title`,
   `og_description`, `twitter_description` sur le wrapper `/federation/`
   (etaient au fallback "Accueil | <tenant>").
4. **`SECURE_PROXY_SSL_HEADER`** dans settings.py : canonical URLs et JSON-LD
   contiennent maintenant `https://` (etaient en `http://` car Traefik forwarde
   en HTTP au container Django).
5. **N+1 cache landing** : `event_count` lu directement de `AGGREGATE_LIEUX`
   au lieu de 20 appels `get_seo_cache(TENANT_SUMMARY, ...)`.
6. **`_('Local network')`** : navbar label maintenant traduisible (etait
   hardcode).
7. **XML escape sitemap_index** : `xml.sax.saxutils.escape` sur les URLs et
   timestamps (defense en profondeur).
8. **BreadcrumbList shape** : `"item": {"@id": ..., "name": ...}` (forme
   recommandee Google Rich Results, au lieu du string brut qui passe les tests
   mais genere des warnings).
9. **`config.organisation or tenant.name`** : fallback si organisation vide.
10. **`CSS.escape()`** : remplace l'echappement regex maison dans explorer.js,
    avec fallback pour vieux navigateurs.

**EN :** Critical review of the SEO/FEDERATION session by an agent + Chrome MCP
navigation. Initial score 79/100, 10 fixes applied to reach prod quality:

1. **Critical XSS JSON-LD**: `json_for_html()` helper translating `<>&` to
   `< > &` unicode sequences. Prevents a tenant admin who puts
   `</script>` in their configuration name from breaking the HTML of neighbor
   pages (which consume SEOCache).
2. **`<h1>` added** on tenant `/federation/` and public `/explorer/` (were
   missing, 21+ H3 only). Visually-hidden, doesn't affect UI.
3. **Open Graph + Twitter tags**: override `og_title`, `twitter_title`,
   `og_description`, `twitter_description` on the `/federation/` wrapper
   (defaulted to "Accueil | <tenant>").
4. **`SECURE_PROXY_SSL_HEADER`** in settings.py: canonical URLs and JSON-LD
   now contain `https://` (were `http://` because Traefik forwards HTTP to
   the Django container).
5. **N+1 cache landing**: `event_count` read directly from `AGGREGATE_LIEUX`
   instead of 20 `get_seo_cache(TENANT_SUMMARY, ...)` calls.
6. **`_('Local network')`**: navbar label now translatable (was hardcoded).
7. **XML escape sitemap_index**: `xml.sax.saxutils.escape` on URLs and
   timestamps (defense in depth).
8. **BreadcrumbList shape**: `"item": {"@id": ..., "name": ...}` (Google Rich
   Results recommended shape, instead of raw string that passes tests but
   generates warnings).
9. **`config.organisation or tenant.name`**: fallback when organisation empty.
10. **`CSS.escape()`**: replaces homemade regex escaping in explorer.js, with
    fallback for legacy browsers.

**Validation** : tous les fixes verifies via curl + Chrome MCP. Helper
`json_for_html()` teste avec input malicieux (`Foo</script><script>alert(1)`)
→ tous les caracteres dangereux echappes.

---
