"""
Tasks Celery de l'app onboard.
/ Celery tasks for the onboard app.

LOCALISATION: onboard/tasks.py

Deux tasks asynchrones :
  - `onboard_otp_mailer` : envoie l'OTP a saisir dans le wizard.
  - `onboard_ready_mailer` : envoie l'email "espace pret" apres creation.

Securite :
  - Le code OTP clair n'est jamais logge (PII + secret a usage unique).
  - Seul l'envoi a destination est journalise (email + uuid WC).
/ Two async tasks:
  - `onboard_otp_mailer`: sends the OTP to enter in the wizard.
  - `onboard_ready_mailer`: sends the "space ready" email after creation.

Security:
  - The plain OTP code is never logged (PII + one-time secret).
  - Only the recipient/WC uuid is journaled.
"""

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django_tenants.utils import schema_context, tenant_context

from Customers.models import Client
from MetaBillet.models import WaitingConfiguration

logger = logging.getLogger(__name__)

# Adresse d'expedition par defaut, utilisee si DEFAULT_FROM_EMAIL non configure.
# / Fallback sender address when DEFAULT_FROM_EMAIL is not configured.
FALLBACK_FROM_EMAIL = "noreply@tibillet.coop"


@shared_task(name="onboard.tasks.onboard_otp_mailer")
def onboard_otp_mailer(wc_uuid, otp_clair):
    """
    Envoie l'email contenant le code OTP a saisir dans le wizard.
    / Send the email containing the OTP code to enter in the wizard.

    Le code clair n'est jamais persiste cote serveur (cf. otp_hash en DB)
    ni logge. Seul le destinataire est journalise.
    / The plain code is never persisted server-side (cf. otp_hash in DB)
    nor logged. Only the recipient is journaled.

    LOCALISATION: onboard/tasks.py::onboard_otp_mailer

    :param wc_uuid: UUID (str) du WaitingConfiguration concerne.
    :param otp_clair: code OTP en clair (6 chiffres typiquement).
    """
    # Le WaitingConfiguration vit dans le schema "meta" (cf. install.py).
    # MetaBillet est en SHARED_APPS donc accessible depuis tout schema mais
    # on force le contexte pour etre explicite et robuste.
    # / WaitingConfiguration lives in the "meta" schema (cf. install.py).
    # MetaBillet is in SHARED_APPS so it's reachable from any schema, but we
    # force the context to be explicit and robust.
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.get(uuid=wc_uuid)
        # On extrait les champs utiles AVANT de sortir du contexte pour eviter
        # toute lazy-load surprise. / Snapshot fields before leaving the scope.
        destinataire = wc.email
        organisation = wc.organisation

    # Sujet contenant le code (rend les apercus mobiles utiles).
    # / Subject includes the code (handy in mobile previews).
    subject = _("Your TiBillet verification code: %(code)s") % {"code": otp_clair}

    text_body = render_to_string(
        "onboard/emails/otp_code.txt",
        {"otp": otp_clair, "organisation": organisation},
    )
    html_body = render_to_string(
        "onboard/emails/otp_code.html",
        {"otp": otp_clair, "organisation": organisation},
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None) or FALLBACK_FROM_EMAIL,
        to=[destinataire],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)

    # IMPORTANT : ne JAMAIS logger otp_clair. / IMPORTANT: never log otp_clair.
    logger.info("OTP mail sent to %s for WC %s", destinataire, wc_uuid)


@shared_task(name="onboard.tasks.onboard_ready_mailer")
def onboard_ready_mailer(wc_uuid):
    """
    Envoie l'email "Votre espace est pret" apres la creation du tenant.
    / Send the "Your space is ready" email after tenant creation.

    Sert de filet de securite si l'utilisateur a ferme l'onglet avant la fin
    de la task asynchrone de creation.
    / Acts as a safety net if the user closed the tab before the async
    tenant-creation task finished.

    LOCALISATION: onboard/tasks.py::onboard_ready_mailer

    :param wc_uuid: UUID (str) du WaitingConfiguration concerne.
    """
    with schema_context("meta"):
        # Pas de `select_related("tenant")` : Client est en SHARED_APPS mais
        # rester defensif et explicite avec deux lectures separees rend le code
        # plus lisible (FALC).
        # / No `select_related("tenant")`: Client is in SHARED_APPS but two
        # explicit reads are more FALC-friendly.
        wc = WaitingConfiguration.objects.get(uuid=wc_uuid)
        tenant = wc.tenant
        destinataire = wc.email
        organisation = wc.organisation

    if tenant is None:
        # On loggue mais on ne raise pas : cette task peut etre appelee comme
        # filet de securite avant que la creation soit terminee.
        # / Log but don't raise: this task may run as a safety net before
        # tenant creation completes.
        logger.warning(
            "onboard_ready_mailer called but WC %s has no tenant yet", wc_uuid
        )
        return

    primary_domain = tenant.get_primary_domain().domain
    admin_url = f"https://{primary_domain}/admin/"

    subject = _("Your TiBillet space %(name)s is ready!") % {"name": organisation}

    text_body = render_to_string(
        "onboard/emails/ready.txt",
        {"organisation": organisation, "admin_url": admin_url},
    )
    html_body = render_to_string(
        "onboard/emails/ready.html",
        {"organisation": organisation, "admin_url": admin_url},
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None) or FALLBACK_FROM_EMAIL,
        to=[destinataire],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)

    logger.info(
        "Ready mail sent to %s for tenant %s (WC %s)",
        destinataire, primary_domain, wc_uuid,
    )


@shared_task(
    name="onboard.tasks.create_tenant_from_draft",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=3,
)
def create_tenant_from_draft(self, wc_uuid):
    """
    Cree le tenant final a partir d'une WaitingConfiguration finalisee.
    / Create the final tenant from a finalized WaitingConfiguration.

    Comportement :
      1. Idempotence : si `wc.tenant_id` est deja rempli, return tout de suite.
      2. Verifie qu'il reste au moins un slot dans le pool `WAITING_CONFIG`.
         Si non : ecrit `wc.error_message` et return sans raise (un admin
         devra rejouer la management command `create_empty_tenant`).
      3. Appelle `wc.create_tenant()` (chaine existante BaseBillet) qui :
         - recategorise un Client WAITING_CONFIG en SALLE_SPECTACLE,
         - cree le Domain primaire,
         - cree l'admin user + Configuration de base,
         - persiste `wc.tenant = tenant` et `wc.created = True`.
      4. Insere les events brouillons dans le schema du nouveau tenant
         avec `published=False` (l'admin pourra relire avant publication).
      5. Federation (V2) : SKIPPE sur cette branche, fedow_core absent
         (cf. bloc commente ci-dessous).
      6. Enqueue `onboard_ready_mailer.delay(wc_uuid=...)`.

    En cas d'exception non geree : `autoretry_for` declenche jusqu'a 3 retries
    avec backoff exponentiel. Au-dela, l'erreur est ecrite dans
    `wc.error_message` et la task abandonne.

    / Behavior:
      1. Idempotent: returns early if `wc.tenant_id` is set.
      2. Checks at least one `WAITING_CONFIG` slot remains in the pool.
         If not: writes `wc.error_message` and returns without raising
         (an admin must replay `create_empty_tenant`).
      3. Calls `wc.create_tenant()` (existing BaseBillet chain) which:
         - re-categorises a Client WAITING_CONFIG -> SALLE_SPECTACLE,
         - creates the primary Domain,
         - creates the admin user + base Configuration,
         - persists `wc.tenant = tenant` and `wc.created = True`.
      4. Inserts draft events into the new tenant schema with
         `published=False` (admin reviews before publishing).
      5. Federation (V2): SKIPPED on this branch, fedow_core absent
         (see commented block below).
      6. Enqueues `onboard_ready_mailer.delay(wc_uuid=...)`.

    Unhandled exceptions trigger `autoretry_for` up to 3 retries with
    exponential backoff. After that, the error is written to
    `wc.error_message` and the task gives up.

    LOCALISATION: onboard/tasks.py::create_tenant_from_draft

    :param wc_uuid: UUID (str) du WaitingConfiguration a finaliser.
    """
    # Import local pour eviter une dependance circulaire au chargement de
    # l'app onboard (BaseBillet.models tire pas mal de monde).
    # / Local import to avoid a circular dependency at app load.
    from django.db import transaction
    from django.utils import timezone  # noqa: F401  # used in skipped federation block

    # === 1. Idempotence : claim Redis distribue ===
    # On utilise `cache.add()` qui retourne True seulement si la cle n'existait
    # pas. C'est atomique cote Redis, ce qui sert de mutex distribue entre
    # workers Celery paralleles (un double-clic utilisateur n'enqueue qu'une
    # vraie execution). TTL 5min : si la task crashe entre temps, le claim
    # expire et un retry pourra reprendre. select_for_update n'aurait pas
    # suffi car wc.create_tenant() dure plusieurs minutes ET fait du DDL
    # (CREATE SCHEMA + migrate_schemas) qui ne peut pas tenir dans une
    # transaction PostgreSQL.
    # / Redis-based distributed claim. `cache.add()` returns True only if
    # the key didn't exist — atomic on the Redis side, acting as a mutex
    # across parallel Celery workers (a double-click only enqueues one real
    # execution). TTL 5min: if the task crashes, the claim expires and a
    # retry can resume. select_for_update would not suffice because
    # wc.create_tenant() takes minutes AND runs DDL (CREATE SCHEMA +
    # migrate_schemas) that cannot live inside a PostgreSQL transaction.
    from django.core.cache import cache
    claim_key = f"onboard:create_tenant_claim:{wc_uuid}"
    got_claim = cache.add(claim_key, "1", timeout=300)
    if not got_claim:
        logger.info(
            "create_tenant_from_draft: WC %s already being processed, skipping",
            wc_uuid,
        )
        return

    # On lit le WC + on verifie idempotence (double-check apres claim).
    # / Read the WC and double-check idempotence after acquiring the claim.
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.get(uuid=wc_uuid)
        if wc.tenant_id is not None:
            logger.info(
                "create_tenant_from_draft: WC %s already has tenant, skipping",
                wc_uuid,
            )
            # On libere le claim avant return (le tenant est deja la).
            # / Release the claim before returning (tenant already exists).
            cache.delete(claim_key)
            return

        # === 2. Pool check (sous claim) ===
        # Les Client vivent en SHARED_APPS (schema public) donc accessibles
        # depuis n'importe quel schema, mais on reste explicite.
        # / Clients live in SHARED_APPS (public schema), reachable from any
        # schema, but we stay explicit.
        pool_count = Client.objects.filter(
            categorie=Client.WAITING_CONFIG,
        ).count()
        if pool_count == 0:
            wc.error_message = (
                "No empty tenant slot available in the pool. "
                "An admin needs to run create_empty_tenant. "
                "/ Pas de slot disponible dans le pool. Un admin doit lancer "
                "create_empty_tenant."
            )
            wc.save(update_fields=["error_message"])
            logger.error(
                "create_tenant_from_draft: no pool slot for WC %s", wc_uuid,
            )
            # On libere le claim, l'admin pourra rejouer apres
            # `create_empty_tenant`. / Release claim, admin will rerun.
            cache.delete(claim_key)
            return

    # === 3. Creation du tenant via la chaine existante BaseBillet ===
    # `wc.create_tenant()` persiste lui-meme `wc.tenant` et `wc.created` en
    # base (cf. BaseBillet/validators.py::TenantCreateValidator.create_tenant).
    # / `wc.create_tenant()` itself persists `wc.tenant` and `wc.created`
    # (cf. BaseBillet/validators.py).
    try:
        new_tenant = wc.create_tenant()
    except Exception as exc:
        # On capture le message, on libere le claim pour permettre un retry
        # propre (sinon le claim TTL bloquerait pendant 5min), puis on raise
        # pour declencher autoretry Celery.
        # / Capture the message, release the claim so retries can proceed
        # (otherwise the 5min TTL would block), then re-raise to trigger
        # Celery autoretry.
        with schema_context("meta"):
            wc.refresh_from_db()
            wc.error_message = f"create_tenant() raised: {exc}"
            wc.save(update_fields=["error_message"])
        cache.delete(claim_key)
        logger.exception(
            "create_tenant_from_draft: create_tenant() failed for WC %s",
            wc_uuid,
        )
        raise

    # === 4. Insertion des events brouillons dans le schema du nouveau tenant ===
    # `events_draft` est un JSONField (liste) — defense en cas de None.
    # / `events_draft` is a JSONField (list) — defensive against None.
    drafts = wc.events_draft or []
    if drafts:
        # Imports locaux : `default_storage` + `File` ne sont utilises que
        # quand des drafts ont une image. / Local imports: only needed when
        # drafts include an image.
        from django.core.files import File
        from django.core.files.storage import default_storage

        with tenant_context(new_tenant):
            from BaseBillet.models import Event
            for ev in drafts:
                image_path = ev.get("image") if isinstance(ev, dict) else None
                try:
                    new_event = Event.objects.create(
                        name=(ev.get("name") or "Sans titre")[:200],
                        datetime=ev.get("datetime"),
                        short_description=(ev.get("description") or "")[:250],
                        # L'admin relira et publiera manuellement.
                        # / Admin reviews and publishes manually.
                        published=False,
                    )
                    # Transfert de l'image draft vers le champ `img` du
                    # vrai Event. On ouvre le fichier source via
                    # `default_storage` (compatible S3) puis on l'attache
                    # via FieldFile.save() qui declenche la generation des
                    # variations StdImage (med, hdr, fhd, thumbnail, ...).
                    # On supprime le fichier source UNIQUEMENT si la copie
                    # a reussi : sinon on garde l'orphelin pour permettre
                    # un debug manuel.
                    # / Transfer the draft image to the real Event's `img`
                    # field. Open the source via `default_storage` (S3
                    # friendly) and attach via FieldFile.save() to trigger
                    # StdImage variations generation. Delete the source
                    # ONLY on successful copy so failures keep the file
                    # for manual debugging.
                    if image_path and default_storage.exists(image_path):
                        import os

                        original_name = os.path.basename(image_path)
                        with default_storage.open(image_path, "rb") as src:
                            # `save=True` (defaut) declenche `model.save()`
                            # qui regenere les variations StdImage.
                            # / `save=True` triggers `model.save()` which
                            # regenerates StdImage variations.
                            new_event.img.save(
                                original_name, File(src), save=True,
                            )
                        # Suppression du fichier draft une fois copie.
                        # / Delete the draft file once successfully copied.
                        try:
                            default_storage.delete(image_path)
                        except Exception as del_exc:  # pragma: no cover
                            logger.warning(
                                "create_tenant_from_draft: copied event image "
                                "but failed to delete source %s: %s",
                                image_path, del_exc,
                            )
                except Exception as exc:
                    # On loggue et on continue : un draft mal forme ne doit
                    # pas faire echouer toute la task (les autres drafts
                    # peuvent etre OK et le tenant est deja cree).
                    # / Log and continue: a malformed draft must not fail the
                    # whole task (the tenant already exists).
                    logger.warning(
                        "Skipping event draft for WC %s: %s", wc_uuid, exc,
                    )

    # === 5. Federation handling — SKIPPED on main-wizard ===
    # fedow_core n'est pas mergee sur cette branche. La FK
    # OnboardInvitation.federation est commentee (cf. Task 3 / onboard/models.py).
    # Quand fedow_core sera mergee : decommenter le bloc ci-dessous.
    # / Federation handling is skipped on main-wizard because fedow_core is
    # not merged. The FK OnboardInvitation.federation is commented out
    # (cf. onboard/models.py). When fedow_core merges, uncomment the block.
    #
    # if wc.invitation_id:
    #     with schema_context("meta"):
    #         wc.refresh_from_db()
    #         inv = wc.invitation
    #     with schema_context("public"):
    #         fed = inv.federation
    #         fed.tenants.add(new_tenant)
    #         inv.used_at = timezone.now()
    #         inv.save(update_fields=["used_at"])

    # === 6. Envoi de l'email "espace pret" ===
    # `wc.tenant` a deja ete persiste par `create_tenant()` (cf. validator).
    # Le mailer pourra donc relire wc.tenant et envoyer le bon admin_url.
    # / `wc.tenant` is already persisted by `create_tenant()` (cf. validator).
    # The mailer can read wc.tenant and send the correct admin_url.
    onboard_ready_mailer.delay(wc_uuid=wc_uuid)

    logger.info(
        "create_tenant_from_draft: success for WC %s -> %s",
        wc_uuid, new_tenant.schema_name,
    )


@shared_task(name="onboard.tasks.purge_stale_onboard_drafts")
def purge_stale_onboard_drafts(ttl_days=30):
    """
    Supprime les brouillons de wizard non finalises (sans tenant) plus
    vieux que `ttl_days` jours. Appele par Celery beat (hebdomadaire).
    / Delete unfinalized wizard drafts (no tenant) older than `ttl_days`.
    Called by Celery beat (weekly).

    Comportement :
      - Cible : `WaitingConfiguration` avec `tenant__isnull=True`
        (= jamais finalises) ET `created_at < now - ttl_days`.
      - Les drafts finalises (tenant deja attache) sont conserves :
        on ne purge JAMAIS un WC qui a deja servi a creer un tenant
        (ces WC sont la trace historique de l'onboarding).
      - Retourne le nombre de lignes supprimees.

    / Behavior:
      - Target: `WaitingConfiguration` with `tenant__isnull=True`
        (= never finalized) AND `created_at < now - ttl_days`.
      - Finalized drafts (tenant attached) are kept: we NEVER purge a WC
        that already produced a tenant (historical onboarding trace).
      - Returns the number of deleted rows.

    LOCALISATION: onboard/tasks.py::purge_stale_onboard_drafts

    :param ttl_days: age en jours au-dela duquel un draft est purge (defaut 30).
    """
    # Imports locaux : la task n'est pas chargee a tous les coups, autant
    # garder le scope minimal au top-level du module.
    # / Local imports: the task isn't always loaded, keep module-level scope
    # minimal.
    from datetime import timedelta
    from django.utils import timezone

    threshold = timezone.now() - timedelta(days=ttl_days)

    # WaitingConfiguration vit dans le schema "meta" (cf. install.py).
    # MetaBillet est en SHARED_APPS donc lisible depuis tout schema, mais on
    # reste explicite (FALC + robustesse).
    # / WaitingConfiguration lives in the "meta" schema (cf. install.py).
    # MetaBillet is in SHARED_APPS so reachable from any schema, but we
    # stay explicit (FALC + robustness).
    #
    # NOTE : le champ "date de creation" du modele s'appelle `datetime`
    # (auto_now_add=True), pas `created_at` (cf. MetaBillet/models.py).
    # / NOTE: the model's "creation date" field is `datetime`
    # (auto_now_add=True), not `created_at` (cf. MetaBillet/models.py).
    with schema_context("meta"):
        qs = WaitingConfiguration.objects.filter(
            tenant__isnull=True,
            datetime__lt=threshold,
        )
        count = qs.count()
        # On collecte les UUIDs AVANT la suppression pour pouvoir purger
        # le dossier d'images draft `onboard_drafts/<wc_uuid>/` associe.
        # / Collect UUIDs BEFORE deletion so we can also wipe the associated
        # `onboard_drafts/<wc_uuid>/` draft images folder.
        wc_uuids_to_purge = list(qs.values_list("uuid", flat=True))
        qs.delete()

    # Nettoyage des fichiers orphelins : pour chaque WC purge, on supprime
    # toutes les images draft associees (step 5 events). On reste defensif :
    # un fichier deja absent ne doit pas faire echouer la task.
    # `default_storage` ne fournit pas de suppression recursive de dossier
    # standard — on liste les fichiers du sous-dossier `events/` et on les
    # supprime un par un (suffisant pour le seul sous-dossier produit par
    # le wizard).
    # / Orphan file cleanup: for each purged WC, delete all associated
    # draft images (step 5 events). Stay defensive: missing files must not
    # break the task. `default_storage` lacks standard recursive folder
    # deletion — we list files in the `events/` subfolder and delete them
    # one by one (sufficient for the only subfolder produced by the wizard).
    if wc_uuids_to_purge:
        from django.core.files.storage import default_storage

        for wc_uuid in wc_uuids_to_purge:
            events_dir = f"onboard_drafts/{wc_uuid}/events"
            try:
                # `listdir()` retourne `(directories, files)`. On itere
                # uniquement sur les fichiers du dossier `events/`.
                # / `listdir()` returns `(directories, files)`. Iterate only
                # over the files inside the `events/` folder.
                _, files = default_storage.listdir(events_dir)
            except Exception:
                # Dossier inexistant (le WC n'avait pas d'image) : skip.
                # / Folder absent (the WC had no image): skip.
                continue
            for fname in files:
                try:
                    default_storage.delete(f"{events_dir}/{fname}")
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "purge_stale_onboard_drafts: failed to delete %s/%s: %s",
                        events_dir, fname, exc,
                    )

    logger.info(
        "purge_stale_onboard_drafts: deleted %d stale drafts (older than %d days)",
        count, ttl_days,
    )
    return count
