"""
Serializers DRF du wizard d'onboarding.
/ DRF serializers for the onboarding wizard.

LOCALISATION: onboard/serializers.py

1 serializer par etape du wizard. On utilise `serializers.Serializer`
explicite (PAS `ModelSerializer`) pour deux raisons :
  - Le brouillon (MetaBillet.WaitingConfiguration) vit dans le schema `meta`,
    pas dans le schema courant : ModelSerializer.save() planterait.
  - La regle djc / FALC du projet : validation explicite, pas de magie.

/ One serializer per wizard step. We use plain `serializers.Serializer`
(NOT `ModelSerializer`) for two reasons:
  - The draft (MetaBillet.WaitingConfiguration) lives in the `meta` schema,
    not the current one: ModelSerializer.save() would crash.
  - djc / FALC project rule: explicit validation, no magic.

NOTE : `postal_code` est aligne en CharField cote modele depuis la
migration `MetaBillet.0016_alter_waitingconfiguration_postal_code`
(Task 12). Plus de cast a faire.
/ NOTE: `postal_code` is now a CharField on the model side since
migration `MetaBillet.0016_alter_waitingconfiguration_postal_code`
(Task 12). No more casting needed.
"""

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


# Choix des suffixes DNS proposes a l'utilisateur. / DNS suffix choices.
# On les declare en tuple immuable au top du module : `ChoiceField` exige
# un iterable de choix, et un tuple en constante module evite la duplication.
# Feedback mainteneur 2026-05-15 : `tibillet.fr` retire du choix utilisateur
# (on ne garde que les domaines coop/re actifs en prod).
# / Declared at module top as an immutable tuple. Maintainer feedback
# 2026-05-15: `tibillet.fr` removed from the user choices (only the active
# coop/re domains remain).
DNS_CHOICES = ("tibillet.coop", "tibillet.re")


class OnboardIdentitySerializer(serializers.Serializer):
    """
    Step 1 — Identite : email + confirmation + identite + nom du lieu + DNS + CGU.
    / Step 1 — Identity: email + confirmation + name + dns + terms.
    """

    email = serializers.EmailField(required=True)
    email_confirm = serializers.EmailField(required=True)
    first_name = serializers.CharField(
        max_length=60, required=True, allow_blank=False,
    )
    last_name = serializers.CharField(
        max_length=60, required=True, allow_blank=False,
    )
    # `max_length=50` : aligne sur la contrainte DB du modele
    # `MetaBillet.WaitingConfiguration.organisation` (CharField max_length=50).
    # Sans cet alignement, un nom > 50 chars passait la validation serializer
    # puis crashait en INSERT PostgreSQL ("value too long for type character
    # varying(50)"). On limite aussi cote HTML via `maxlength="50"` sur
    # l'input #onboard-id-name pour empecher la saisie en amont.
    # / `max_length=50`: aligned on the DB constraint of
    # `WaitingConfiguration.organisation` (CharField max_length=50). Without
    # this alignment, a >50 char name passed serializer validation then crashed
    # on the PostgreSQL INSERT. The HTML input also has `maxlength="50"` to
    # prevent over-typing client-side.
    name = serializers.CharField(
        max_length=50, required=True, allow_blank=False,
    )
    dns_choice = serializers.ChoiceField(
        choices=DNS_CHOICES, default="tibillet.coop",
    )
    cgu = serializers.BooleanField(required=True)

    def validate_cgu(self, value):
        """
        Validation explicite : l'utilisateur DOIT accepter les CGU.
        / Explicit validation: user MUST accept the terms.
        """
        if not value:
            raise serializers.ValidationError(_("You must accept the terms."))
        return value

    def validate_name(self, value):
        """
        Le nom du lieu doit avoir au moins 3 caracteres significatifs
        (strip pour ignorer espaces de bord). On verifie aussi qu'il n'est
        pas deja pris par un tenant existant (check case-insensitive pour
        eviter les ambiguites visuelles "MonLieu" vs "monlieu", meme si la
        contrainte DB sur Client.name est case-sensitive). Sans ce check,
        l'utilisateur ne decouvrirait le conflit qu'a la step Launch quand
        TenantCreateValidator.create_tenant raise — friction UX.

        / The venue name must have at least 3 meaningful chars. Also checks
        the name is not already taken by an existing tenant (case-insensitive
        for visual UX clarity, even though the DB constraint on Client.name
        is case-sensitive). Without this check, the user would only discover
        the conflict at the Launch step.
        """
        valeur_nettoyee = value.strip()
        if len(valeur_nettoyee) < 3:
            raise serializers.ValidationError(
                _("Name must be at least 3 characters."),
            )

        # Imports locaux : evitent la dependance au chargement du module
        # onboard.serializers vers Customers (SHARED_APPS).
        # / Local imports: avoid load-time dependency on Customers.
        from django_tenants.utils import schema_context

        from Customers.models import Client

        # `Client` (= tenant) vit dans le schema `public` (TENANT_MODEL).
        # On force le contexte pour ne pas planter si le serializer est
        # appele depuis un schema tenant.
        # / `Client` lives in `public` schema; force context to avoid crash
        # when the serializer is called from a tenant schema.
        with schema_context("public"):
            nom_deja_pris = Client.objects.filter(
                name__iexact=valeur_nettoyee,
            ).exists()
        if nom_deja_pris:
            raise serializers.ValidationError(
                _("This venue name is already taken. Please choose another."),
            )

        return valeur_nettoyee

    def validate(self, attrs):
        """
        Verifie que les deux emails saisis correspondent (case-insensitive).
        / Verify both emails match (case-insensitive).
        """
        if attrs["email"].lower() != attrs["email_confirm"].lower():
            raise serializers.ValidationError(
                {"email_confirm": _("Emails do not match.")},
            )
        return attrs


class OnboardVerifySerializer(serializers.Serializer):
    """
    Step 2 — Verification OTP : code a 6 chiffres exactement.
    / Step 2 — OTP verify: exactly 6 digits.
    """

    otp = serializers.RegexField(regex=r"^\d{6}$", required=True)


class OnboardPlaceSerializer(serializers.Serializer):
    """
    Step 3 — Adresse + coordonnées GPS via le widget carte adresse.
    / Step 3 — Address + GPS coords via the address map widget.

    Les champs `place_*` viennent du widget réutilisable
    `templates/widgets/widget_carte_adresse.html` (préfixe
    `identifiant_widget="place"`). Les 4 champs adresse séparés
    (street_address, postal_code, address_locality, address_country)
    gardent leurs noms historiques pour rester compatibles avec le
    modèle `WaitingConfiguration`.
    """

    # Champs adresse historiques (auto-remplis par le widget).
    # / Historical address fields (auto-filled by the widget).
    street_address = serializers.CharField(
        max_length=255, required=True, allow_blank=False,
    )
    postal_code = serializers.CharField(
        max_length=20, required=True, allow_blank=False,
    )
    address_locality = serializers.CharField(
        max_length=120, required=True, allow_blank=False,
    )
    address_country = serializers.CharField(
        max_length=80, required=True, allow_blank=False,
    )

    # Coordonnées GPS du widget (préfixe identifiant_widget="place").
    # / GPS coords from widget (identifiant_widget="place").
    place_latitude = serializers.FloatField(
        min_value=-90, max_value=90, required=True,
    )
    place_longitude = serializers.FloatField(
        min_value=-180, max_value=180, required=True,
    )
    place_adresse = serializers.CharField(
        required=False, allow_blank=True, max_length=500,
    )


class OnboardDescriptionsSerializer(serializers.Serializer):
    """
    Step "Presentation" — description courte (obligatoire) + description
    longue (optionnelle) + logo (optionnel).

    `short_description` est l'accroche publique (max 280 chars, requise) :
    elle apparait en apercu sur le reseau. Elle a ete regroupee ici avec
    la description longue et le logo (feedback mainteneur 2026-05-14) pour
    rassembler toutes les info de presentation sur une seule page.

    `long_description` est `required=False` : on accepte qu'un lieu lance
    son espace sans avoir encore redige sa presentation longue, l'admin
    pourra la completer plus tard.

    `logo` est valide cote serveur :
      - taille max 5 Mo (`MAX_LOGO_SIZE_BYTES`) pour eviter les uploads
        abusifs (Django renvoie sinon une 400 sans message clair).
      - content_type whitelist (jpeg / png / webp) — les autres formats
        sont rejetes proprement.

    / Step "Presentation" — short description (required) + long description
    (optional) + logo (optional).
    `short_description` is the public pitch (max 280 chars, required).
    `long_description` is `required=False`: a venue can launch its space
    without writing the long pitch yet.
    `logo` is validated server-side (size <=5MB, content_type whitelist).
    """

    # Taille max et content_types acceptes pour le logo.
    # / Max size and allowed content_types for the logo.
    MAX_LOGO_SIZE_BYTES = 5 * 1024 * 1024  # 5 Mo / 5 MB
    ALLOWED_LOGO_TYPES = ("image/jpeg", "image/png", "image/webp")

    short_description = serializers.CharField(
        max_length=280, required=True, allow_blank=False,
    )
    long_description = serializers.CharField(
        max_length=5000,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    logo = serializers.ImageField(required=False, allow_null=True)

    def validate_logo(self, value):
        """
        Refuse les fichiers trop gros ou format non supporte.
        / Reject oversized or unsupported file types.
        """
        if value is None:
            return value
        # Taille / size
        if hasattr(value, "size") and value.size > self.MAX_LOGO_SIZE_BYTES:
            raise serializers.ValidationError(
                _("Logo too large: maximum 5 MB."),
            )
        # Content-type (ImageField a deja valide qu'il s'agit d'une image,
        # mais on restreint en plus aux formats web-friendly).
        # / ImageField already validated that it's an image, but we further
        # restrict to web-friendly formats.
        content_type = getattr(value, "content_type", None)
        if content_type and content_type not in self.ALLOWED_LOGO_TYPES:
            raise serializers.ValidationError(
                _("Logo must be JPEG, PNG or WebP."),
            )
        return value


class OnboardEventDraftSerializer(serializers.Serializer):
    """
    Sous-form de la step 5 : un brouillon d'event.
    Plusieurs instances seront validees ensemble cote vue (Task 14).
    / Step 5 sub-form: one event draft. Multiple instances are validated
    together in the view (Task 14).

    `image` est valide cote serveur (memes regles que le logo de la step 4) :
      - taille max 5 Mo (`MAX_IMAGE_SIZE_BYTES`) pour eviter les uploads abusifs,
      - content_type whitelist (jpeg / png / webp) — formats web-friendly.

    Le fichier valide est ensuite persiste sur disque par la vue via
    `default_storage` (chemin relatif stocke dans le JSONField `events_draft`).

    / `image` is validated server-side (same rules as the step 4 logo):
      - max size 5 MB (`MAX_IMAGE_SIZE_BYTES`),
      - content_type whitelist (jpeg / png / webp).

    The valid file is then persisted to disk by the view via
    `default_storage` (the relative path is stored in the JSONField
    `events_draft`).
    """

    # Taille max et content_types acceptes pour l'image d'event.
    # / Max size and allowed content_types for the event image.
    MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 Mo / 5 MB
    ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")

    name = serializers.CharField(max_length=200, required=True)
    datetime = serializers.DateTimeField(required=True)
    description = serializers.CharField(
        max_length=2000, required=False, allow_blank=True,
    )
    image = serializers.ImageField(required=False, allow_null=True)

    def validate_image(self, value):
        """
        Refuse les fichiers trop gros ou format non supporte.
        / Reject oversized or unsupported file types.
        """
        if value is None:
            return value
        # Taille / size
        if hasattr(value, "size") and value.size > self.MAX_IMAGE_SIZE_BYTES:
            raise serializers.ValidationError(
                _("Image too large: maximum 5 MB."),
            )
        # Content-type (ImageField a deja valide qu'il s'agit d'une image,
        # mais on restreint en plus aux formats web-friendly).
        # / ImageField already validated that it's an image, but we further
        # restrict to web-friendly formats.
        content_type = getattr(value, "content_type", None)
        if content_type and content_type not in self.ALLOWED_IMAGE_TYPES:
            raise serializers.ValidationError(
                _("Image must be JPEG, PNG or WebP."),
            )
        return value
