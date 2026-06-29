# CHANTIER-08 — Carte réseau : rebuild d'agrégats en débounce « trailing »

> **Hub :** [INDEX.md](INDEX.md) · [SPEC.md](SPEC.md) · suite de [CHANTIER-07](CHANTIER-07-cache-fragments.md)
> **Date :** 2026-06-29
> **Statut :** Implémenté — tests pytest verts, à tester manuellement (worker + beat) / déployer
> **Priorité :** Élevé (bug remonté par des utilisateurs)
> **App impactée :** `seo/` + signal `BaseBillet/signals.py`

---

## 1. Contexte / bug remonté

Des utilisateurs signalent que **les nouveaux évènements et les nouvelles
adresses n'apparaissent pas sur la carte ROOT `/explorer/`** une fois
sauvegardés. Ils n'apparaissent qu'après le passage du beat Celery 4 h.

La carte lit `AGGREGATE_POINTS` (via `build_explorer_data`), qui n'est mis à
jour que par `rebuild_seo_aggregates` (recombinaison des fragments
`TENANT_POINTS`, cf. CHANTIER-07).

## 2. Cause racine

Le signal `declencher_refresh_seo_cache` planifiait deux tâches en **débounce
« front montant »** :

- fragment `refresh_tenant_seo_cache(tenant)` : countdown 30 s, verrou TTL 60 s ;
- rebuild `rebuild_seo_aggregates()` : countdown 180 s, verrou global TTL 180 s.

Le rebuild était donc figé à `T_première_modif + 180 s`. Problèmes :

1. **Race d'ordonnancement (cause principale).** Une modif arrivant tard dans la
   fenêtre (≈ `[T+150, T+180]`) voyait son fragment planifié *après* le rebuild
   déjà programmé. Le rebuild recombinait alors un fragment **pas encore à
   jour**, et **aucun rebuild de rattrapage** n'était garanti (le verrou global
   bloquait toute reprogrammation). → invisible jusqu'au beat 4 h.
   Le CHANTIER-07 §4 l'avait documenté comme « convergence éventuelle,
   acceptable pour du SEO » — inacceptable pour un éditeur qui regarde sa carte.
2. **Fenêtre morte du fragment.** Countdown 30 s < TTL verrou 60 s : entre +30
   (fragment exécuté) et +60 (verrou encore posé), une nouvelle modif du même
   tenant ne replanifiait pas de fragment.
3. **Latence nominale de ~3 min** même dans le cas simple (perception « ça ne
   marche pas »).

Worker + beat confirmés actifs en prod → le bug est bien dans l'ordonnancement,
pas l'infra.

## 3. Décision : débounce « front descendant » (trailing) auto-replanifiant

Le rebuild doit s'exécuter **après la dernière modif**, sur des fragments à jour,
avec une charge bornée et **sans** jamais recalculer les schemas des autres
tenants.

| Élément | Mécanisme |
|---|---|
| Échéance | `seo_rebuild_echeance = now + REBUILD_TRAILING_WINDOW` (15 s), repoussée à **chaque** modif |
| Planification | `planifier_rebuild_agregats()` : ≤ 1 tâche rebuild « en vol » par fenêtre (verrou `seo_rebuild_planifie`) |
| Garde | `rebuild_seo_aggregates(force=False)` : si `echeance - now > REBUILD_MARGE` (2 s) → **se replanifie** pile à l'échéance et rend la main ; sinon **recombine** (et libère `seo_rebuild_planifie`) |
| Beat 4 h | `rebuild_seo_aggregates(force=True)` : recombine toujours (filet anti-dérive) |
| Fragment | countdown **5 s**, TTL verrou **5 s** (aligné → fin de la fenêtre morte) |

**Garantie de correction :** le *dernier* rebuild s'exécute toujours après le
*dernier* fragment (chaque rebuild « trop tôt » se replanifie). Les rebuilds
intermédiaires s'auto-annulent (lecture cache + `return`, coût négligeable).

## 4. Fichiers modifiés

| Fichier | Type | Changement |
|---|---|---|
| `seo/tasks.py` | edit | +constantes `REBUILD_TRAILING_WINDOW`/`REBUILD_MARGE` ; +`planifier_rebuild_agregats()` ; `rebuild_seo_aggregates(force=False)` garde + self-reschedule ; beat `rebuild_seo_aggregates(force=True)` |
| `BaseBillet/signals.py` | edit | `declencher_refresh_seo_cache` : fragment countdown/TTL 5 s ; rebuild via `planifier_rebuild_agregats()` (suppr. débounce front montant) |
| `tests/pytest/test_seo_cache_fragments.py` | edit | +fixture nettoyage clés ; +4 tests (abstention/replanif, recombine à l'échéance, `force`, débounce helper) |

## 5. Tests

`pytest tests/pytest/test_seo_cache_fragments.py` → **9 passed**.
Non-régression : `test_seo_aggregate_points`, `test_seo_event_tags`,
`test_federation_config`, `test_federation_view_integration`,
`test_federation_auto_tags` → **28 passed**.

Manuel (worker + beat actifs) : cf. `A TESTER et DOCUMENTER/seo-carte-rebuild-trailing-debounce.md`.

## 6. Hors scope (écarté en brainstorming)

- **Bouton admin « rafraîchir maintenant »** : écarté (risque de spam).
- Rebuild incrémental (delta par tenant) : la recombinaison complète reste légère
  et bornée par le débounce (cf. CHANTIER-07 §9).
- `FEDERATION_INCOMING` reste sur le beat.

## 8. Bug L1 cross-schema (découvert en vérification E2E — cause racine réelle)

La vérification E2E (Chrome + worker réel) a révélé un **second bug, indépendant
du débounce**, qui est la **cause racine** du symptôme « apparaît après ~4 h ».

**Constat :** après le flux automatique, le L2 (DB) était à jour mais le L1
Memcached lu par les pages restait périmé jusqu'au TTL (4 h).

**Cause exacte :** `CACHES['default']` utilise
`KEY_FUNCTION = django_tenants.cache.make_key` → chaque clé est préfixée par le
schema courant. Les agrégats SEO sont globaux (`tenant=None`). Le worker exécute
le rebuild dans le schema du **tenant déclencheur** → il écrit
`lespass:…:seo:aggregate_lieux`, invisible depuis `public` (ROOT) et les autres
tenants. Preuve : même donnée globale lue à 19 en `public`/`lespass` mais à 15 en
`le-coeur-en-or`/`chantefrein`. `make_key` produit
`public:v:1:seo:aggregate_lieux:global` vs `lespass:v:1:…`.

**Fix :** `set_memcached_l1` / `get_memcached_l1` épinglent le schema `public`
(`with schema_context("public")`) → clé L1 **globale** partagée par tous les
schemas. Vérifié E2E : L1 identique sur public/lespass/le-coeur-en-or après un
simple ajout d'event, carte ROOT à jour en ~20 s sans rebuild manuel.

**Note :** ce bug préexistait au débounce. Les deux corrections sont
complémentaires : le débounce trailing garantit un L2 frais rapidement ; le fix
L1 garantit que les pages lisent ce L2 frais.

## 10. Débounce global + plafond maxWait (anti-famine)

Deux limites du débounce trailing initial, corrigées ensemble :

1. **Débounce par-tenant au lieu de global.** Les clés de débounce passaient par le
   cache `default` préfixé par schema (`make_key`) → le verrou « global » était en
   fait par tenant. Sous un pic multi-lieux, N rebuilds redondants (chacun
   recombine pourtant tout le réseau). Fix : les 3 clés (`seo_rebuild_echeance`,
   `seo_rebuild_plafond`, `seo_rebuild_planifie`) sont manipulées sous
   `schema_context("public")` → réellement globales (1 cycle réseau).

2. **Risque de famine du trailing pur.** Sous flux continu (< fenêtre 15 s : import,
   grosse saison), l'échéance était repoussée sans fin → rebuild jamais déclenché
   avant le beat 4 h. Fix : **plafond maxWait** (`REBUILD_MAXWAIT = 60 s`), posé une
   seule fois (`cache.add`) au début d'une série. Le rebuild s'exécute au **plus tôt**
   entre l'échéance trailing (dernière modif + 15 s) et le plafond (1ʳᵉ modif + 60 s).

**Garanties après fix :**
- pic simultané → **1 rebuild** (au lieu de N) ;
- flux dense → **≤ 1 rebuild / 60 s** (charge bornée, pas de famine) — objectif
  « 500 tenants » du CHANTIER-07 enfin tenu ;
- activité isolée → inchangé (~15 s après la modif).

3. **Race résiduelle de clôture (corrigée suite à la revue).** Le verrou
   `seo_rebuild_planifie` était libéré *avant* le recombine : une modif arrivant
   dans cette micro-fenêtre ne pouvait ni se planifier (verrou encore tenu) ni être
   incluse (son fragment est à +5 s, après le recombine) → invisible jusqu'au beat
   4 h. Fix : le verrou reste **tenu pendant tout le recombine** (aucun rebuild
   concurrent), et en fin de recombine on relit l'échéance ; si elle a bougé (modif
   arrivée entre-temps), on **replanifie une passe** pour la rattraper.

**Échelle (mesuré) :** à 500 lieux, `AGGREGATE_EVENTS` ≈ 687 o/event → ~1500 events
futurs ≈ 1 Mo = **limite Memcached par défaut**. Au-delà, le `set` L1 échoue. À
traiter séparément (relever `-I` du conteneur `lespass_memcached`, ou borner
l'agrégat aux N prochains mois). Indépendant du débounce.

**Tests (pytest) :** recombinaison au plafond maxWait ; plafond posé une seule
fois ; + fixture `_debounce_isole_en_public` (clés globales = schema public, évite
les faux négatifs d'isolation en suite complète).

## 11. Publication d'une proposition (agenda participatif) → rebuild SEO

Cas découvert en testant « est-ce que tout se lance quand on active *publier* ? ».

- **Toggle « Publier » (liste) et édition (formulaire)** : passent par `save()` →
  signal `post_save` → rebuild SEO. **OK** (vérifié Chrome : event publié présent
  dans `AGGREGATE_EVENTS`, L1 cohérent cross-schema).
- **Action bulk « Approuver et publier les propositions »** : utilisait
  `queryset.update()`, qui **ne déclenche pas `post_save`** → pas de rebuild → l'event
  approuvé n'apparaissait qu'au beat 4 h. **Bug** (cas critique : c'est le chemin de
  validation des propositions publiques de l'agenda participatif).

**Fix :** l'action publie via `save(update_fields=["is_proposal","published"])` par
instance (boucle) au lieu de `update()` en masse. Test pytest :
`test_approuver_propositions_declenche_le_rebuild_seo` (RED avec `update()`, GREEN
avec `save()`).

## 9. Journal

- **2026-06-29** : rapport de diagnostic (race d'ordonnancement) validé par le
  mainteneur ; décision « rebuild en aval du fragment » ; implémentation TDD
  (test RED de la garde trailing → GREEN) ; 9 + 28 tests verts.
- **2026-06-29 (suite)** : vérification E2E Chrome (events admin + agenda
  participatif + fédération par tags). Découverte du **bug L1 cross-schema**
  (cf. §8), cause racine réelle du retard 4 h. Diagnostic systématique
  (make_key préfixe par schema), fix TDD (`schema_context("public")` dans les
  helpers L1), validé de bout en bout dans le navigateur.
- **2026-06-29 (suite 2)** : analyse coût/échelle (500 lieux, 1000+ events) →
  débounce rendu **global** + **plafond maxWait** (cf. §10), fix TDD. Mesure de la
  limite Memcached 1 Mo sur `AGGREGATE_EVENTS` signalée (pansement `-I` ou borne).
- **2026-06-29 (suite 3)** : sur question « est-ce que publier déclenche bien ? »,
  découverte que l'action d'approbation des propositions (`update()`) ne rafraîchit
  pas la carte (cf. §11). Fix TDD (`save()` par instance). Toggle « Publier »
  vérifié OK en conditions réelles (Chrome).
