"""
Tests du cache SEO en fragments par tenant (CHANTIER-07).
/ Tests for the per-tenant SEO cache fragments.

LOCALISATION : tests/pytest/test_seo_cache_fragments.py
Voir SESSIONS/SEO/CHANTIER-07-cache-fragments.md.

Reutilise la base de dev (schema lespass), comme test_seo_aggregate_points / e2e_slugs.
"""

import pytest

from Customers.models import Client


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de base de test).
    # / Reuse dev DB (no test DB creation).
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()


@pytest.mark.django_db
def test_refresh_tenant_ecrit_les_3_fragments_du_tenant_seulement():
    """refresh_tenant_seo_cache(X) ecrit TENANT_SUMMARY/EVENTS/POINTS pour X."""
    from seo.tasks import refresh_tenant_seo_cache
    from seo.models import SEOCache

    lespass = Client.objects.get(schema_name="lespass")
    resultat = refresh_tenant_seo_cache(str(lespass.uuid))

    assert resultat["tenant"] == str(lespass.uuid)
    for cache_type in (SEOCache.TENANT_SUMMARY, SEOCache.TENANT_EVENTS, SEOCache.TENANT_POINTS):
        assert SEOCache.objects.filter(cache_type=cache_type, tenant=lespass).exists(), cache_type


@pytest.mark.django_db
def test_rebuild_aggregate_points_est_la_concat_des_fragments():
    """AGGREGATE_POINTS = somme des points de tous les fragments TENANT_POINTS."""
    from seo.tasks import refresh_seo_cache, rebuild_seo_aggregates
    from seo.models import SEOCache

    refresh_seo_cache()        # peuple tous les fragments + agregats
    rebuild_seo_aggregates()   # recombine (idempotent)

    total_fragments = 0
    for entry in SEOCache.objects.filter(cache_type=SEOCache.TENANT_POINTS):
        total_fragments += len(entry.data.get("points", []))

    agg = SEOCache.objects.get(cache_type=SEOCache.AGGREGATE_POINTS, tenant=None)
    assert len(agg.data.get("points", [])) == total_fragments


@pytest.mark.django_db
def test_pa_id_uniques_dans_agregat_apres_refactor():
    """Le pa_id reste unique cross-tenant apres recombinaison (bug 1 preserve)."""
    from seo.tasks import refresh_seo_cache
    from seo.models import SEOCache

    refresh_seo_cache()
    agg = SEOCache.objects.get(cache_type=SEOCache.AGGREGATE_POINTS, tenant=None)
    pa_ids = [p["pa_id"] for p in agg.data.get("points", [])]
    assert len(pa_ids) == len(set(pa_ids))  # zero collision


@pytest.mark.django_db
def test_rebuild_ne_touche_pas_federation_incoming():
    """rebuild_seo_aggregates ne recalcule PAS FEDERATION_INCOMING (reserve au beat)."""
    from seo.tasks import refresh_seo_cache, rebuild_seo_aggregates
    from seo.models import SEOCache

    refresh_seo_cache()  # calcule FEDERATION_INCOMING (au beat)
    avant = SEOCache.objects.get(cache_type=SEOCache.FEDERATION_INCOMING, tenant=None).updated_at

    rebuild_seo_aggregates()  # ne doit pas toucher FEDERATION_INCOMING
    apres = SEOCache.objects.get(cache_type=SEOCache.FEDERATION_INCOMING, tenant=None).updated_at

    assert avant == apres


@pytest.mark.django_db
def test_get_events_for_tenants_exclut_les_events_archives():
    """
    Regression : un event archive (archived=True) ne doit PLUS remonter dans
    get_events_for_tenants, meme s'il reste publie et futur. Sinon il continue
    d'apparaitre sur la carte SEO apres archivage.
    / Regression: an archived event must not show up in get_events_for_tenants,
    even if still published and in the future.
    """
    from django.utils import timezone
    from datetime import timedelta
    from django_tenants.utils import tenant_context
    from BaseBillet.models import Event
    from seo.services import get_events_for_tenants

    lespass = Client.objects.get(schema_name="lespass")
    futur = timezone.now() + timedelta(days=30)

    with tenant_context(lespass):
        # Un event publie futur NON archive (doit apparaitre) et un archive (doit disparaitre).
        # / A published future event NOT archived (should appear) and an archived one (should not).
        event_visible = Event.objects.create(
            name="SEO archive test - visible", datetime=futur, published=True, archived=False,
        )
        event_archive = Event.objects.create(
            name="SEO archive test - archive", datetime=futur, published=True, archived=True,
        )
    try:
        resultats = get_events_for_tenants([(str(lespass.uuid), lespass.schema_name)])
        uuids = {e["uuid"] for e in resultats}
        assert str(event_visible.uuid) in uuids, "L'event publie non archive doit remonter."
        assert str(event_archive.uuid) not in uuids, "L'event archive ne doit PAS remonter."
    finally:
        # Nettoyage : la base de dev n'est pas rollback (django_db_setup reutilise la base).
        # Suppression en SQL brut pour eviter le signal post_delete de stdimage, qui
        # plante sur un event sans image (name=None). Nos events n'ont aucune relation.
        # / Cleanup: dev DB is not rolled back. Raw SQL delete to bypass stdimage's
        # post_delete signal (crashes on a null image name). Our events have no relations.
        from django.db import connection as conn
        with tenant_context(lespass):
            with conn.cursor() as cur:
                cur.execute(
                    'DELETE FROM "BaseBillet_event" WHERE uuid IN (%s, %s)',
                    [str(event_visible.uuid), str(event_archive.uuid)],
                )


# ---------------------------------------------------------------------------
# Débounce trailing du rebuild d'agrégats (CHANTIER-08)
# / Trailing debounce of the aggregate rebuild
# ---------------------------------------------------------------------------
#
# Bug : un event/adresse fraichement sauvé n'apparait pas sur la carte tant
# que le beat 4h ne tourne pas. Cause : le rebuild d'agrégats était planifié
# en "front montant" (au début de la rafale de modifs), donc il pouvait
# recombiner un fragment TENANT_POINTS pas encore à jour, sans qu'aucun
# rebuild de rattrapage ne soit garanti. Le fix : débounce "front descendant"
# (trailing) — le rebuild s'exécute APRES la dernière modif.


@pytest.fixture(autouse=True)
def _debounce_isole_en_public():
    """
    Isole les tests touchant le débounce du rebuild.
    / Isolate tests touching the rebuild debounce.

    Les clés de débounce sont GLOBALES : le code (planifier_rebuild_agregats /
    garde de rebuild_seo_aggregates) y accède sous schema_context("public") pour
    neutraliser le préfixe de schema de django-tenants. On force donc le schema
    public pendant tout le test, sinon un test précédent de la suite peut laisser
    un autre schema courant et les cache.set/get directs des tests viseraient une
    clé préfixée différente du code (faux négatifs en suite complète).
    De plus, Memcached est partagé sans rollback : on vide les clés avant/après.
    / Debounce keys are GLOBAL (accessed under the public schema by the code).
    We pin the public schema for the whole test and clear the keys before/after.
    """
    from django.core.cache import cache
    from django_tenants.utils import schema_context

    cles = ("seo_rebuild_echeance", "seo_rebuild_planifie", "seo_rebuild_plafond")
    with schema_context("public"):
        for cle in cles:
            cache.delete(cle)
        yield
        for cle in cles:
            cache.delete(cle)


@pytest.mark.django_db
def test_rebuild_se_reprogramme_si_une_modif_plus_recente_a_repousse_l_echeance(monkeypatch):
    """
    Coeur du fix race (CHANTIER-08) : si l'échéance est dans le futur (une modif
    vient d'arriver), rebuild_seo_aggregates NE recombine PAS tout de suite — il
    se replanifie pile à l'échéance. Évite de figer l'agrégat à partir d'un
    fragment pas encore à jour.
    / Race fix core: if the deadline is in the future, rebuild_seo_aggregates
    must NOT recombine now — it reschedules itself for the deadline.
    """
    import time
    from django.core.cache import cache
    from seo import tasks
    from seo.models import SEOCache

    # Une modif "très récente" : échéance loin dans le futur.
    # / A "very recent" change: deadline far in the future.
    cache.set("seo_rebuild_echeance", time.time() + 100, 3600)

    # On capture la reprogrammation sans l'envoyer au broker.
    # / Capture the reschedule without sending it to the broker.
    reprogrammations = []
    monkeypatch.setattr(
        tasks.rebuild_seo_aggregates,
        "apply_async",
        lambda *args, **kwargs: reprogrammations.append(kwargs),
    )

    agg_avant = SEOCache.objects.filter(
        cache_type=SEOCache.AGGREGATE_POINTS, tenant=None
    ).first()
    updated_avant = agg_avant.updated_at if agg_avant else None

    resultat = tasks.rebuild_seo_aggregates()

    # Il s'abstient et se replanifie une seule fois.
    # / It abstains and reschedules itself exactly once.
    assert resultat.get("rescheduled") is True
    assert len(reprogrammations) == 1

    # L'agrégat n'a pas été recombiné (updated_at inchangé).
    # / The aggregate was not recombined (updated_at unchanged).
    if updated_avant is not None:
        agg_apres = SEOCache.objects.get(
            cache_type=SEOCache.AGGREGATE_POINTS, tenant=None
        )
        assert agg_apres.updated_at == updated_avant


@pytest.mark.django_db
def test_rebuild_recombine_quand_l_echeance_est_atteinte():
    """
    Échéance déjà dépassée -> rebuild_seo_aggregates recombine pour de vrai
    (pas d'abstention). / Past deadline -> the rebuild actually recombines.
    """
    import time
    from django.core.cache import cache
    from seo import tasks
    from seo.models import SEOCache

    cache.set("seo_rebuild_echeance", time.time() - 10, 3600)

    resultat = tasks.rebuild_seo_aggregates()

    assert "rescheduled" not in resultat
    assert "points" in resultat  # il a bien recombiné / it did recombine
    assert SEOCache.objects.filter(
        cache_type=SEOCache.AGGREGATE_POINTS, tenant=None
    ).exists()


@pytest.mark.django_db
def test_rebuild_force_ignore_l_echeance_future():
    """
    force=True (le beat 4h) recombine toujours, même si une échéance est dans
    le futur. / force=True (the 4h beat) always recombines, ignoring the deadline.
    """
    import time
    from django.core.cache import cache
    from seo import tasks

    cache.set("seo_rebuild_echeance", time.time() + 100, 3600)

    resultat = tasks.rebuild_seo_aggregates(force=True)

    assert "rescheduled" not in resultat
    assert "points" in resultat


@pytest.mark.django_db
def test_planifier_rebuild_pousse_l_echeance_et_debounce_la_planification(monkeypatch):
    """
    planifier_rebuild_agregats pousse l'échéance à chaque appel, mais ne planifie
    qu'UNE tâche rebuild par fenêtre (verrou seo_rebuild_planifie).
    / planifier_rebuild_agregats pushes the deadline on each call but schedules
    only ONE rebuild task per window.
    """
    import time
    from django.core.cache import cache
    from seo import tasks

    appels = []
    monkeypatch.setattr(
        tasks.rebuild_seo_aggregates,
        "apply_async",
        lambda *args, **kwargs: appels.append(kwargs),
    )

    tasks.planifier_rebuild_agregats()
    echeance_1 = cache.get("seo_rebuild_echeance")
    assert echeance_1 is not None and echeance_1 > time.time()
    assert len(appels) == 1

    # 2e modif rapprochée : pas de nouvelle planification (débounce), mais
    # l'échéance est repoussée. / Second close change: no new schedule, but the
    # deadline is pushed forward.
    tasks.planifier_rebuild_agregats()
    echeance_2 = cache.get("seo_rebuild_echeance")
    assert len(appels) == 1
    assert echeance_2 >= echeance_1


# ---------------------------------------------------------------------------
# Plafond "maxWait" anti-famine du débounce global (CHANTIER-08 §10)
# / "maxWait" cap against starvation of the global debounce
# ---------------------------------------------------------------------------
#
# Sans plafond, un flux continu de modifs (< fenêtre trailing) repousserait
# l'échéance indéfiniment et le rebuild ne partirait jamais avant le beat 4h
# (famine). Le plafond garantit un rebuild au plus tard REBUILD_MAXWAIT secondes
# après la PREMIERE modif d'une série.


@pytest.mark.django_db
def test_rebuild_recombine_quand_le_plafond_maxwait_est_atteint():
    """
    Anti-famine : même si l'échéance trailing est repoussée dans le futur (flux
    continu), le rebuild DOIT recombiner dès que le plafond maxWait est atteint.
    / Anti-starvation: even with the trailing deadline pushed into the future,
    the rebuild MUST recombine once the maxWait cap is reached.
    """
    import time
    from django.core.cache import cache
    from seo import tasks

    cache.set("seo_rebuild_echeance", time.time() + 100, 3600)   # trailing repoussé loin
    cache.set("seo_rebuild_plafond", time.time() - 1, 3600)       # plafond DÉPASSÉ

    resultat = tasks.rebuild_seo_aggregates()

    assert "rescheduled" not in resultat   # il recombine, ne se replanifie PAS
    assert "points" in resultat


@pytest.mark.django_db
def test_planifier_pose_le_plafond_maxwait_une_seule_fois(monkeypatch):
    """
    Le plafond maxWait est posé UNE FOIS au début d'une série de modifs et n'est
    PAS repoussé par les modifs suivantes (sinon il ne plafonnerait rien).
    / The maxWait cap is set ONCE at the start of a burst and is NOT pushed by
    later changes.
    """
    import time
    from django.core.cache import cache
    from seo import tasks

    monkeypatch.setattr(
        tasks.rebuild_seo_aggregates, "apply_async", lambda *a, **k: None
    )

    tasks.planifier_rebuild_agregats()
    plafond_1 = cache.get("seo_rebuild_plafond")
    assert plafond_1 is not None and plafond_1 > time.time()

    # 2e modif rapprochée : l'échéance trailing bouge, le plafond NON.
    tasks.planifier_rebuild_agregats()
    plafond_2 = cache.get("seo_rebuild_plafond")
    assert plafond_2 == plafond_1


# ---------------------------------------------------------------------------
# Cache L1 des agrégats GLOBAUX partagé cross-schema (CHANTIER-08, bug L1)
# / Cross-schema sharing of the GLOBAL aggregates L1 cache
# ---------------------------------------------------------------------------
#
# Bug : CACHES['default'] utilise KEY_FUNCTION=django_tenants.cache.make_key,
# qui préfixe chaque clé par le schema courant. Les agrégats SEO globaux
# (tenant=None) étaient donc dupliqués par schema dans le L1 : le worker
# (qui s'exécute dans le schema du tenant déclencheur) écrivait une clé
# invisible depuis le schema public (page ROOT) et les autres tenants.
# Résultat : la carte affichait du cache périmé jusqu'au TTL (4h).


@pytest.mark.django_db
def test_l1_aggregat_global_est_partage_entre_tous_les_schemas():
    """
    Un agrégat global (tenant=None) écrit dans le L1 depuis un schema tenant
    doit être lu À L'IDENTIQUE depuis le schema public ET depuis un autre tenant.
    / A global aggregate written to L1 from one tenant schema must be read
    identically from the public schema AND from another tenant.
    """
    from django_tenants.utils import tenant_context
    from seo.services import get_memcached_l1, set_memcached_l1
    from seo.models import SEOCache

    lespass = Client.objects.get(schema_name="lespass")
    coeur = Client.objects.get(schema_name="le-coeur-en-or")

    valeur = {"lieux": [{"name": "SENTINEL_CROSS_SCHEMA", "event_count": 4242}]}

    try:
        # Écriture depuis le schema du tenant lespass (comme le fait le worker).
        # / Write from the lespass tenant schema (as the worker does).
        with tenant_context(lespass):
            set_memcached_l1(SEOCache.AGGREGATE_LIEUX, None, valeur)

        # Lecture depuis public (page ROOT /explorer/).
        # / Read from public (ROOT /explorer/ page).
        assert get_memcached_l1(SEOCache.AGGREGATE_LIEUX, None) == valeur

        # Lecture depuis un AUTRE tenant (page /federation/ du Coeur en or).
        # / Read from ANOTHER tenant (Coeur en or /federation/ page).
        with tenant_context(coeur):
            assert get_memcached_l1(SEOCache.AGGREGATE_LIEUX, None) == valeur
    finally:
        # Nettoyage : on efface la clé globale (Memcached partagé, pas de rollback).
        # / Cleanup: delete the global key (shared Memcached, no rollback).
        from django.core.cache import cache
        from django_tenants.utils import schema_context
        with schema_context("public"):
            cache.delete("seo:aggregate_lieux:global")


# ---------------------------------------------------------------------------
# Publication d'une proposition (agenda participatif) -> rebuild SEO (CHANTIER-08)
# / Publishing a proposal must trigger the SEO rebuild
# ---------------------------------------------------------------------------
#
# Bug : l'action admin "approuver_propositions" publiait via queryset.update(),
# qui NE déclenche PAS le signal post_save -> le rebuild SEO ne partait pas et
# l'event publié n'apparaissait sur la carte qu'au beat 4h. Cas critique pour
# l'agenda participatif (les propositions publiques passent par cette action).


@pytest.mark.django_db
def test_approuver_propositions_declenche_le_rebuild_seo(monkeypatch):
    """
    L'approbation d'une proposition (publish) DOIT déclencher le rebuild SEO,
    sinon l'event publié n'apparaît pas sur la carte avant le beat 4h.
    / Approving a proposal (publish) MUST trigger the SEO rebuild.
    """
    from datetime import timedelta

    from django.contrib.admin.sites import AdminSite
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.test import RequestFactory
    from django.utils import timezone
    from django_tenants.utils import tenant_context

    from Administration.admin_tenant import EventAdmin
    from BaseBillet.models import Event
    import seo.tasks as seo_tasks

    # On capture la planification du rebuild (déclenchée par le signal post_save).
    # / Capture the rebuild scheduling (fired by the post_save signal).
    rebuilds = []
    monkeypatch.setattr(
        seo_tasks.rebuild_seo_aggregates, "apply_async",
        lambda *a, **k: rebuilds.append(1),
    )
    monkeypatch.setattr(
        seo_tasks.refresh_tenant_seo_cache, "apply_async", lambda *a, **k: None
    )

    lespass = Client.objects.get(schema_name="lespass")
    futur = timezone.now() + timedelta(days=30)

    with tenant_context(lespass):
        proposition = Event.objects.create(
            name="Proposition agenda — a approuver",
            datetime=futur, published=False, is_proposal=True,
        )
        try:
            # La création ci-dessus a déjà déclenché le signal post_save : on
            # remet à zéro le compteur ET les verrous de débounce pour n'observer
            # QUE l'effet de l'approbation qui suit.
            # / The create() above already fired post_save: reset the counter and
            # the debounce locks so we only observe the approval's effect.
            from django.core.cache import cache
            from django_tenants.utils import schema_context
            rebuilds.clear()
            with schema_context("public"):
                for cle in ("seo_rebuild_echeance", "seo_rebuild_plafond", "seo_rebuild_planifie"):
                    cache.delete(cle)

            admin_obj = EventAdmin(Event, AdminSite())
            requete = RequestFactory().post("/admin/")
            requete.session = {}
            setattr(requete, "_messages", FallbackStorage(requete))

            admin_obj.approuver_propositions(
                requete, Event.objects.filter(pk=proposition.pk)
            )

            proposition.refresh_from_db()
            assert proposition.published is True
            assert proposition.is_proposal is False
            # Le coeur du test : l'approbation a bien planifie un rebuild SEO.
            # / Core assertion: approval scheduled a SEO rebuild.
            assert len(rebuilds) >= 1, "L'approbation doit declencher un rebuild SEO"
        finally:
            from django.db import connection as conn
            with tenant_context(lespass):
                with conn.cursor() as cur:
                    cur.execute(
                        'DELETE FROM "BaseBillet_event" WHERE uuid = %s',
                        [str(proposition.uuid)],
                    )
