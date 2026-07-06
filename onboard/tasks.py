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
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.translation import gettext as _
from django_tenants.utils import schema_context, tenant_context

from Customers.models import Client
from MetaBillet.models import WaitingConfiguration

logger = logging.getLogger(__name__)


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
        # Langue captee au POST identity (cf. WaitingConfiguration.language).
        # Sans ce snapshot, gettext serait evalue dans la locale par defaut
        # du worker Celery (LANGUAGE_CODE='en' typiquement) — sujet en anglais.
        # / Language captured at identity POST. Without this snapshot,
        # gettext falls back to the worker's default locale (usually 'en').
        langue_utilisateur = wc.language or "fr"

    # `translation.override` active la locale pour TOUT le bloc : sujet,
    # render des templates `.txt` / `.html`. Restaure la locale precedente
    # en sortie (context manager). Indispensable cote Celery ou il n'y a
    # pas de LocaleMiddleware pour le faire automatiquement.
    # / `translation.override` activates the locale for the whole block:
    # subject + .txt/.html template renders. Restores the previous locale
    # on exit. Required server-side in Celery (no LocaleMiddleware).
    with translation.override(langue_utilisateur):
        # Sujet : code en TETE pour que la notification mobile (qui tronque
        # souvent apres ~30 caracteres) reste lisible — l'utilisateur lit le
        # code sans avoir a ouvrir le mail. Ex iOS / Android : "123456 –
        # votre code TiBillet" affiche les 6 chiffres meme apres troncature.
        # / Subject: code FIRST so the mobile notification (often truncated
        # after ~30 chars) stays useful — user reads the code without opening
        # the mail. iOS / Android: "123456 – your TiBillet code" survives the cut.
        subject = _("%(code)s – your TiBillet verification code") % {"code": otp_clair}

        # Pre-render le texte brut (le HTML est rendu par CeleryMailerClass).
        # / Pre-render the text body (HTML is rendered by CeleryMailerClass).
        text_body = render_to_string(
            "onboard/emails/otp_code.txt",
            {"otp": otp_clair, "organisation": organisation},
        )

        # Import local pour eviter de charger BaseBillet.tasks (et toutes ses
        # dependances Stripe / Fedow / Brevo / Ghost) tant qu'on n'envoie pas
        # de mail. / Local import to avoid loading BaseBillet.tasks (and all
        # its Stripe/Fedow/Brevo/Ghost deps) until we actually send a mail.
        from BaseBillet.tasks import CeleryMailerClass

        mail = CeleryMailerClass(
            email=destinataire,
            title=subject,
            text=text_body,
            template="onboard/emails/otp_code.html",
            context={"otp": otp_clair, "organisation": organisation},
        )
        mail.send()

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
        # Langue captee au POST identity (cf. WaitingConfiguration.language).
        # Cf. commentaire dans onboard_otp_mailer pour la justification du
        # snapshot + translation.override en bas de fonction.
        # / Captured language. See onboard_otp_mailer comment for rationale.
        langue_utilisateur = wc.language or "fr"

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

    # Magic-link admin : on cree l'admin user (idempotent) puis on forge un
    # lien `https://<tenant>/emailconfirmation/<token>?next=<signed_admin>`
    # qui logue l'utilisateur sur le nouveau tenant sans re-saisie email/OTP.
    # Si l'utilisateur a ferme l'onglet pendant la creation tenant, le mail
    # lui permet de revenir et atterrir directement loggue sur l'admin.
    # Le helper `forge_admin_magic_link` reutilise `user.get_connect_token()`
    # (TimestampSigner 72h — TTL aligne sur la duree de vie d'un mail recent).
    #
    # Fallback sur lien direct si la generation echoue (cas exotique :
    # l'admin a supprime le user entre create_tenant et le mailer).
    # / Magic-link: create the admin user (idempotent) then forge a link
    # that logs them in on the new tenant without re-typing email/OTP.
    # Fallback to direct admin URL on failure.
    admin_url = f"https://{primary_domain}/admin/"
    try:
        # Import locaux pour eviter une dependance circulaire au chargement
        # du module onboard.tasks. / Local imports to avoid circular deps.
        from AuthBillet.utils import get_or_create_user

        from onboard.views import forge_admin_magic_link

        # `send_mail=False` : l'utilisateur est deja confirme via OTP.
        # / `send_mail=False`: already confirmed via OTP.
        admin_user = get_or_create_user(destinataire, send_mail=False)
        if admin_user is not None:
            admin_url = forge_admin_magic_link(
                admin_user, tenant, next_path="/admin/",
            )
    except Exception as forge_exc:
        # Log + fallback direct admin URL : l'utilisateur arrivera juste
        # sur la page de login admin. / Log + fallback to direct URL.
        logger.error(
            "onboard_ready_mailer: forge_admin_magic_link failed for WC %s, "
            "falling back to direct admin URL: %s",
            wc_uuid, forge_exc,
        )

    # URL publique du tenant (sans /admin/). Affichee dans la liste
    # "Informations importantes" du mail pour rappeler a l'utilisateur
    # l'adresse publique de son lieu, distincte du magic-link admin.
    # / Public tenant URL (without /admin/). Shown in the "Important info"
    # list to remind users of their public-facing address, distinct from
    # the admin magic-link.
    instance_url = f"https://{primary_domain}/"

    context = {
        "organisation": organisation,
        "admin_url": admin_url,
        "instance_url": instance_url,
    }

    # `translation.override` active la locale pour le rendu du sujet et des
    # templates `.txt` / `.html`. Indispensable cote Celery (pas de
    # LocaleMiddleware). Sans ca, le sujet "Your TiBillet space ... is ready!"
    # sort tel quel en anglais meme pour un utilisateur FR.
    # / Activates locale for subject + template renders. Required in Celery
    # (no LocaleMiddleware). Without it, the subject is rendered in the
    # worker's default locale (often 'en').
    with translation.override(langue_utilisateur):
        subject = _("Your TiBillet space %(name)s is ready!") % {"name": organisation}

        # Pre-render le texte brut (le HTML est rendu par CeleryMailerClass).
        # / Pre-render the text body (HTML is rendered by CeleryMailerClass).
        text_body = render_to_string("onboard/emails/ready.txt", context)

        # Import local : evite la dependance lourde au chargement du module.
        # / Local import: avoids the heavy dep at module load time.
        from BaseBillet.tasks import CeleryMailerClass

        mail = CeleryMailerClass(
            email=destinataire,
            title=subject,
            text=text_body,
            template="onboard/emails/ready.html",
            context=context,
        )
        mail.send()

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

    # === 3bis. Adresse principale du tenant (PostalAddress) ===
    # La step "Votre lieu" du wizard collecte une adresse (rue, code postal,
    # ville, pays, lat, lng). `wc.create_tenant()` (chaine BaseBillet) NE
    # transferait PAS ces donnees vers le tenant nouvellement cree —
    # l'ancien flux `/tenant/new/` n'avait pas ces champs. On le fait ici
    # pour ne pas modifier la chaine partagee. On cree un `PostalAddress`
    # dans le schema du nouveau tenant, avec `is_main=True`, et on le lie
    # via `Configuration.postal_address`.
    #
    # Skip si `wc.street_address` est vide : peut arriver pour l'ancien
    # flow (le widget GPS n'etait pas obligatoire) ou si l'admin manipule
    # le WC en base. / Skip if `wc.street_address` is empty.
    #
    # / "Place" step collects an address. `wc.create_tenant()` doesn't copy
    # it (legacy `/tenant/new/` didn't have these fields). We do it here
    # without modifying the shared chain: create a PostalAddress in the new
    # tenant schema with `is_main=True` and link Configuration.postal_address.
    if wc.street_address:
        # Try/except IMPORTANT : si la creation PostalAddress raise (cas
        # pathologique, ex: contrainte DB exotique), on NE doit PAS re-lever
        # l'exception. Sinon le `autoretry_for=(Exception,)` Celery relance
        # la task, qui voit `wc.tenant_id is not None` au prochain passage
        # (idempotence) et early-return → l'adresse ne serait JAMAIS creee.
        # L'admin peut toujours la saisir manuellement dans l'admin Unfold.
        # `logger.error` remonte sur Sentry (alerte ops).
        # / Try/except CRITICAL: a PostalAddress failure must NOT re-raise,
        # otherwise Celery autoretry sees `wc.tenant_id is not None` and
        # early-returns idempotently → address would never be created.
        # Admin can fill it manually. `logger.error` surfaces to Sentry.
        try:
            with tenant_context(new_tenant):
                from BaseBillet.models import Configuration, PostalAddress

                postal_address = PostalAddress.objects.create(
                    name=wc.organisation,
                    street_address=wc.street_address,
                    postal_code=wc.postal_code or "",
                    address_locality=wc.address_locality or "",
                    address_country=wc.address_country or "",
                    latitude=wc.latitude,
                    longitude=wc.longitude,
                    is_main=True,
                )
                config = Configuration.get_solo()
                config.postal_address = postal_address
                config.save(update_fields=["postal_address"])
            logger.info(
                "create_tenant_from_draft: PostalAddress (is_main=True) "
                "created for WC %s -> tenant %s",
                wc_uuid, new_tenant.schema_name,
            )
        except Exception as addr_exc:
            # ERROR niveau Sentry — admin doit creer l'adresse a la main.
            # / ERROR level for Sentry — admin must create the address manually.
            logger.error(
                "create_tenant_from_draft: PostalAddress creation FAILED "
                "for WC %s on tenant %s (admin must create manually): %s",
                wc_uuid, new_tenant.schema_name, addr_exc,
                exc_info=True,
            )

    # === 3ter. Transfert long_description + logo du wizard vers Configuration ===
    # La step "Presentation" du wizard collecte une description longue et un
    # logo. La chaine BaseBillet `wc.create_tenant()` ne les copie PAS (elle
    # ecrit un texte par defaut "Bienvenue dans votre nouvel espace..." sur
    # `config.long_description`). On les transfere ici pour que le tenant ait
    # bien le contenu saisi par l'utilisateur.
    #
    # Memes precautions que pour PostalAddress (cf. piege #23 : try/except
    # sans re-raise pour ne pas casser l'idempotence Celery).
    # / Transfer wizard long_description + logo to Configuration. The
    # BaseBillet chain `wc.create_tenant()` doesn't copy them (writes a
    # default welcome text). Same try/except precaution as PostalAddress
    # to preserve Celery autoretry idempotence.
    if wc.long_description or wc.logo:
        try:
            with tenant_context(new_tenant):
                from BaseBillet.models import Configuration
                from django.core.files import File
                from django.core.files.storage import default_storage
                import os as _os

                config = Configuration.get_solo()
                config_fields_modifies = []

                # Long description : on override le texte par defaut ecrit
                # par BaseBillet/validators.py:992 SI le user a saisi qqch.
                # / Long description: override the default welcome text if
                # the user actually wrote something.
                if wc.long_description:
                    config.long_description = wc.long_description
                    config_fields_modifies.append("long_description")

                # Logo : `wc.logo` est un FieldFile (StdImageField) qui
                # pointe sur `media/onboard_drafts/<wc_uuid>/...`. On copie
                # le fichier source via `default_storage` (S3 compatible)
                # vers le champ `config.img` du tenant. `FieldFile.save()`
                # avec `save=False` evite un save() premature — on appelle
                # `config.save(update_fields=...)` une seule fois en bas.
                # / Logo: `wc.logo` is a FieldFile on draft storage. Copy
                # via default_storage to `config.img`. `save=False` defers
                # the model save to the consolidated call below.
                if wc.logo and default_storage.exists(wc.logo.name):
                    original_name = _os.path.basename(wc.logo.name)
                    with default_storage.open(wc.logo.name, "rb") as src:
                        # `save=True` declenche `Configuration.save()` qui
                        # regenere les variations StdImage (med, hdr, fhd,
                        # thumbnail). Plus simple et plus fiable que
                        # gerer manuellement les variations.
                        # / `save=True` triggers Configuration.save() which
                        # regenerates StdImage variations.
                        config.img.save(
                            original_name, File(src), save=True,
                        )
                    # On garde le draft original pour debug / rollback ; la
                    # purge des fichiers orphelins est faite par
                    # `purge_stale_onboard_drafts` (cron hebdo).
                    # / Keep the draft for debug/rollback; orphan cleanup
                    # is handled by the weekly purge cron.
                    config_fields_modifies.append("img (StdImage)")
                elif config_fields_modifies:
                    # Pas de logo a copier mais long_description a save.
                    # / No logo but long_description to save.
                    config.save(update_fields=["long_description"])

            logger.info(
                "create_tenant_from_draft: Configuration enrichie pour WC %s "
                "-> tenant %s (champs: %s)",
                wc_uuid, new_tenant.schema_name, config_fields_modifies,
            )
        except Exception as conf_exc:
            # ERROR niveau Sentry — admin pourra completer manuellement
            # depuis l'admin Unfold du tenant. / ERROR for Sentry — admin
            # will complete manually from the tenant's Unfold admin.
            logger.error(
                "create_tenant_from_draft: Configuration long_description/logo "
                "FAILED for WC %s on tenant %s (admin must complete manually): %s",
                wc_uuid, new_tenant.schema_name, conf_exc,
                exc_info=True,
            )

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

        # Parser de datetime : `events_draft` est un JSONField -> les datetimes
        # sont stockes en string ISO 8601 (ex: "2026-06-15T19:00:00+02:00").
        # `Event.objects.create(datetime="...")` ne convertit PAS la string en
        # objet datetime (les DateTimeField.to_python ne sont appeles qu'au
        # full_clean() ou via les forms). Du coup `Event.save()` plante avec
        # `'str' object has no attribute 'astimezone'` quand le post_save signal
        # tente de generer le slug/full_url. Le `try/except Exception` ci-dessous
        # avale l'erreur silencieusement -> 0 events crees, sans trace evidente.
        # On parse explicitement la string en datetime aware avant create().
        # / `events_draft` is a JSONField -> datetimes are ISO 8601 strings.
        # `Event.objects.create(datetime="...")` does NOT auto-convert (only
        # forms/full_clean call DateTimeField.to_python). The post_save signal
        # then crashes on `.astimezone()`. Parse explicitly here.
        from datetime import datetime as datetime_module

        # Accumulateur de warnings pour les drafts skip. Chaque ligne
        # contient le nom du draft + la classe d'exception + le message.
        # Persiste dans `wc.events_creation_warnings` a la fin pour que
        # l'utilisateur le voie sur `/onboard/launch/` (status_done.html).
        # / Accumulator for skipped drafts. Each line: draft name + exception
        # class + message. Persisted to `wc.events_creation_warnings` at the
        # end so the user sees it on `/onboard/launch/`.
        warnings_drafts = []

        with tenant_context(new_tenant):
            from BaseBillet.models import Event
            for ev in drafts:
                image_path = ev.get("image") if isinstance(ev, dict) else None
                try:
                    ev_datetime_brut = ev.get("datetime")
                    if isinstance(ev_datetime_brut, str):
                        # `fromisoformat` accepte le format ISO 8601 standard
                        # (depuis Python 3.7) — celui utilise par DRF /
                        # Django pour serialiser un DateTimeField vers JSON.
                        # / `fromisoformat` accepts standard ISO 8601 — the
                        # format used by DRF / Django when serializing a
                        # DateTimeField to JSON.
                        ev_datetime = datetime_module.fromisoformat(ev_datetime_brut)
                    else:
                        ev_datetime = ev_datetime_brut

                    new_event = Event.objects.create(
                        name=(ev.get("name") or "Sans titre")[:200],
                        datetime=ev_datetime,
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
                    # On loggue ERROR (pas warning) avec le contenu du draft
                    # pour debug, et on accumule un message lisible dans
                    # `warnings_drafts` qui sera persiste apres la boucle.
                    # On ne raise PAS : un draft mal forme ne doit pas tuer
                    # la creation du tenant (deja faite) ni les autres drafts.
                    # / Log ERROR (not warning) with the draft content for
                    # debug, and accumulate a readable message in
                    # `warnings_drafts` to be persisted after the loop.
                    # Don't raise: a malformed draft must not kill the tenant
                    # (already created) nor the other drafts.
                    nom_draft = (ev.get("name") if isinstance(ev, dict) else None) or "(sans nom)"
                    logger.error(
                        "create_tenant_from_draft: skipping event draft for WC %s. "
                        "Draft content: %r. Error: %s: %s",
                        wc_uuid, ev, type(exc).__name__, exc,
                    )
                    warnings_drafts.append(
                        f"« {nom_draft} » : {type(exc).__name__}: {exc}"
                    )

        # Persistance des warnings dans wc.events_creation_warnings.
        # On le fait UNE FOIS apres la boucle pour minimiser les writes.
        # Si la liste est vide, on ne touche pas le champ (defaut "").
        # / Persist warnings to wc.events_creation_warnings ONCE after the
        # loop to minimize writes. If empty, don't touch the field.
        if warnings_drafts:
            with schema_context("meta"):
                wc.refresh_from_db()
                wc.events_creation_warnings = "\n".join(warnings_drafts)
                wc.save(update_fields=["events_creation_warnings"])

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

    # === 6. Ghost newsletter — abonnement du nouvel admin ===
    # On replique le pattern de l'ancien flux `BaseBillet/views.py:3697-3702` :
    # ajouter l'email du createur a la newsletter Ghost (configuree au niveau
    # META). On le fait DANS le contexte du tenant META car `GhostConfig.get_solo()`
    # est tenant-scoped et la config Ghost vit historiquement sur META.
    # Idempotent cote Ghost (verifie si membre existe deja). On wrap dans
    # try/except : un Ghost down ne doit PAS faire echouer la creation tenant.
    # / Ghost newsletter — subscribe the new admin. Replicates the old flow.
    # Wrapped in try/except: Ghost downtime must not fail tenant creation.
    try:
        from BaseBillet.tasks import send_to_ghost_email

        # Re-read WC (schema "meta") pour avoir les valeurs a jour.
        # / Re-read WC (schema "meta") for fresh values.
        with schema_context("meta"):
            wc.refresh_from_db()
            email_admin = wc.email
            nom_organisation = wc.organisation

        meta_tenant = Client.objects.filter(categorie=Client.META).first()
        if meta_tenant is not None:
            with tenant_context(meta_tenant):
                send_to_ghost_email.delay(email_admin, name=nom_organisation)
    except Exception as ghost_exc:
        # On log mais on n'interrompt PAS le flow : Ghost est optionnel.
        # / Log only — Ghost is optional.
        logger.error(
            "create_tenant_from_draft: send_to_ghost_email failed for WC %s: %s",
            wc_uuid, ghost_exc,
        )

    # === 6ter. Page d'accueil par defaut (app pages) ===
    # On cree la home ICI, en fin de tache, une fois l'image (config.img) et la
    # description longue posees (etape 3ter), juste avant l'email "espace pret".
    # Structure : HERO (identite, fond = config.img) -> PARAGRAPHE (description
    # longue saisie au wizard, garde meme vide) -> CTA (modules actifs).
    # Idempotent (construire_page_accueil ne fait rien si une home existe deja).
    # / Default home page (pages app). Created here, at the end of the task, once
    # the image (config.img) and long description are set (step 3ter), right
    # before the "space ready" email. Structure: HERO (identity, background =
    # config.img) -> PARAGRAPH (wizard long description, kept even empty) -> CTA
    # (active modules). Idempotent (does nothing if a home already exists).
    try:
        with schema_context("meta"):
            wc.refresh_from_db()
            description_longue_wizard = wc.long_description or ""

        with tenant_context(new_tenant):
            from BaseBillet.models import Configuration
            from pages.models import Bloc, Page
            from pages.services import construire_page_accueil

            configuration_du_tenant = Configuration.get_solo()

            # Les libelles CTA sont figes en base via gettext() (non lazy).
            # On active EXPLICITEMENT la langue du tenant : ne pas dependre du
            # activate() fait plus haut par create_tenant (fragile au refactor).
            # Meme pattern que onboard_otp_mailer.
            # / CTA labels are frozen in DB via gettext() (not lazy). Explicitly
            # activate the tenant's language: do not rely on the activate() done
            # earlier by create_tenant (fragile). Same pattern as onboard_otp_mailer.
            from django.utils import translation

            with translation.override(configuration_du_tenant.language or "fr"):
                construire_page_accueil(
                    Page, Bloc, configuration_du_tenant,
                    description_longue=description_longue_wizard,
                )
    except Exception as home_exc:
        # Une home ratee ne doit PAS faire echouer la creation du tenant
        # (deja faite). L'admin pourra la creer a la main depuis l'admin pages.
        # / A failed home must not fail tenant creation (already done). The admin
        # can create it by hand from the pages admin.
        logger.error(
            "create_tenant_from_draft: home page creation FAILED for WC %s "
            "on tenant %s: %s",
            wc_uuid, new_tenant.schema_name, home_exc, exc_info=True,
        )

    # === 7. Envoi de l'email "espace pret" ===
    # `wc.tenant` a deja ete persiste par `create_tenant()` (cf. validator).
    # Le mailer pourra donc relire wc.tenant et envoyer le bon admin_url.
    # / `wc.tenant` is already persisted by `create_tenant()` (cf. validator).
    # The mailer can read wc.tenant and send the correct admin_url.
    onboard_ready_mailer.delay(wc_uuid=wc_uuid)

    # Liberation du claim Redis apres succes : permet a un `launch_retry`
    # ulterieur (clic admin) d'enqueuer une nouvelle execution. La
    # protection idempotence reste assuree par le check `wc.tenant_id
    # is not None` au debut de la task. Sans cette liberation, l'admin
    # qui clique "Reessayer" dans les 5min suivant le succes voyait
    # "already being processed, skipping" et pensait que l'action
    # n'avait pas fait effet.
    # / Release Redis claim after success: lets a future `launch_retry`
    # (admin click) enqueue a new run. Idempotency is still guaranteed by
    # the `wc.tenant_id is not None` check at task start. Without this
    # release, admin clicking "Retry" within 5min saw "already being
    # processed" and thought their action had no effect.
    cache.delete(claim_key)

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
