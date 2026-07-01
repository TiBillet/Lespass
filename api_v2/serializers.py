from decimal import Decimal
from typing import Any, Dict, List, Optional
import random
import string
import socket
import ipaddress
import requests
from urllib.parse import urlparse

from rest_framework import serializers
from django.db import transaction
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.core.files.base import ContentFile

from BaseBillet.models import Event, PostalAddress, Tag, OptionGenerale, LigneArticle, Price, PriceSold, Product, ProductFormField, Reservation, Membership
from crowds.models import Initiative, BudgetItem, Participation, Vote
from fedow_connect.utils import dround
from Administration.utils import clean_html, url_a_schema_dangereux
from django.db.models.fields.files import FieldFile

# Image validation utilities
from PIL import Image, UnidentifiedImageError


def _validate_uploaded_image(file_obj):
    """Strictly validate that the uploaded object is an image and <= 10 MiB.
    - checks declared content_type when available
    - checks file size (<= 10 * 1024 * 1024 bytes)
    - attempts to open via Pillow
    - resets file pointer afterwards
    """
    MAX_BYTES = 10 * 1024 * 1024  # 10 MiB

    # Some storages/adapters set content_type, some don't (e.g., tests)
    content_type = getattr(file_obj, 'content_type', None)
    if content_type and not str(content_type).lower().startswith('image/'):
        raise serializers.ValidationError('Only image files are allowed (image/*).')

    # Check size from UploadedFile when available
    size = getattr(file_obj, 'size', None)
    if size is None:
        # try to derive size from stream if possible without consuming
        try:
            if hasattr(file_obj, 'seek') and hasattr(file_obj, 'tell'):
                pos = file_obj.tell()
                file_obj.seek(0, 2)  # seek to end
                end = file_obj.tell()
                file_obj.seek(pos)
                size = end
        except Exception:
            size = None
    if size is not None and int(size) > MAX_BYTES:
        raise serializers.ValidationError('Image exceeds maximum size of 10 MiB.')

    # Verify with Pillow
    pos = None
    try:
        if hasattr(file_obj, 'tell'):
            pos = file_obj.tell()
        Image.open(file_obj).verify()  # type: ignore
    except (UnidentifiedImageError, OSError):
        raise serializers.ValidationError('Invalid image file.')
    finally:
        try:
            if hasattr(file_obj, 'seek') and pos is not None:
                file_obj.seek(pos)
        except Exception:
            pass


def _hote_est_interne(hote: str) -> bool:
    """Vrai si l'hote resout vers une IP interne/privee (anti-SSRF).
    / True if the host resolves to an internal/private IP (anti-SSRF).

    On refuse loopback, prive, link-local, reserve, multicast, non specifie.
    Si l'hote ne resout pas, on refuse aussi (prudence).
    """
    if not hote:
        return True
    try:
        infos = socket.getaddrinfo(hote, None)
    except Exception:
        return True
    for famille, type_socket, proto, nom_canon, sockaddr in infos:
        ip_txt = sockaddr[0]
        try:
            adr = ipaddress.ip_address(ip_txt)
        except ValueError:
            return True
        if (adr.is_private or adr.is_loopback or adr.is_link_local
                or adr.is_reserved or adr.is_multicast or adr.is_unspecified):
            return True
    return False


def telecharger_et_valider_image(url: str):
    """Telecharge une image distante, la valide (Pillow), renvoie un ContentFile.
    / Downloads a remote image, validates it (Pillow), returns a ContentFile.

    Securite : schema http/https uniquement, anti-SSRF (refuse les hotes internes),
    pas de redirection, timeout, content-type image/*, taille max 10 Mo, verify Pillow.
    Renvoie None si url vide. Leve ValidationError si invalide ou dangereuse.

    NB (limite connue) : il subsiste un petit TOCTOU entre la resolution DNS du
    controle anti-SSRF et la requete reelle ; allow_redirects=False reduit le risque.
    """
    if not url:
        return None
    parse = urlparse(url)
    if parse.scheme not in ("http", "https"):
        raise serializers.ValidationError(_("Schema d'URL non autorise (http/https seulement)."))
    if not parse.hostname or _hote_est_interne(parse.hostname):
        raise serializers.ValidationError(_("Hote d'image non autorise (cible interne refusee)."))
    MAX_OCTETS = 10 * 1024 * 1024  # 10 Mo
    try:
        resp = requests.get(url, timeout=10, allow_redirects=False, stream=True)
        resp.raise_for_status()
    except serializers.ValidationError:
        raise
    except Exception:
        raise serializers.ValidationError(_("Image distante inaccessible : %(u)s") % {"u": url})

    ctype = resp.headers.get("Content-Type", "")
    if ctype and not ctype.lower().startswith("image/"):
        raise serializers.ValidationError(_("L'URL ne pointe pas vers une image."))

    # Refus precoce si l'entete Content-Length annonce deja trop gros.
    # / Early refusal if the Content-Length header already announces too big.
    taille_annoncee = resp.headers.get("Content-Length")
    if taille_annoncee:
        try:
            if int(taille_annoncee) > MAX_OCTETS:
                raise serializers.ValidationError(_("Image trop grande (> 10 Mo)."))
        except (TypeError, ValueError):
            pass  # entete non numerique : on se rabat sur la lecture bornee ci-dessous

    # Lecture bornee : on accumule par blocs et on stoppe des qu'on depasse 10 Mo,
    # sans jamais charger un corps geant en memoire. / Bounded read: accumulate by
    # chunks and stop as soon as we exceed 10 MB, never loading a huge body in memory.
    contenu = b""
    for bloc_octets in resp.iter_content(chunk_size=65536):
        if not bloc_octets:
            continue
        contenu += bloc_octets
        if len(contenu) > MAX_OCTETS:
            resp.close()
            raise serializers.ValidationError(_("Image trop grande (> 10 Mo)."))
    fichier = ContentFile(contenu)
    fichier.content_type = ctype or "image/*"
    _validate_uploaded_image(fichier)
    nom = url.split("?")[0].rsplit("/", 1)[-1] or "image"
    fichier.name = nom
    return fichier


class PostalAddressAsSchemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostalAddress
        fields = (
            "name",
            "street_address",
            "address_locality",
            "address_region",
            "postal_code",
            "address_country",
            "latitude",
            "longitude",
        )

    def _image_urls(self, instance: PostalAddress) -> List[str]:
        urls: List[str] = []
        try:
            if instance.img:
                urls.append(instance.img.url)
        except Exception:
            pass
        try:
            if instance.sticker_img:
                urls.append(instance.sticker_img.url)
        except Exception:
            pass
        return urls

    def to_representation(self, instance: PostalAddress) -> Dict[str, Any]:
        data = super().to_representation(instance)
        # Map to schema.org/PostalAddress
        result: Dict[str, Any] = {
            "@type": "PostalAddress",
            "name": data.get("name"),
            "streetAddress": data.get("street_address"),
            "addressLocality": data.get("address_locality"),
            "addressRegion": data.get("address_region"),
            "postalCode": data.get("postal_code"),
            "addressCountry": data.get("address_country"),
        }
        # Add geo if present
        lat = data.get("latitude")
        lon = data.get("longitude")
        if lat is not None and lon is not None:
            result["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": float(lat),
                "longitude": float(lon),
            }
        # Add image URLs if available
        images = self._image_urls(instance)
        if images:
            result["image"] = images
        return result


# Mapping between internal category codes and schema.org Event subtypes
CATEGORY_TO_SCHEMA_TYPE = {
    Event.CONCERT: "MusicEvent",
    Event.FESTIVAL: "Festival",
    Event.REUNION: "SocialEvent",
    Event.CONFERENCE: "EducationEvent",
    Event.RESTAURATION: "FoodEvent",
    Event.CHANTIER: "Event",  # no precise subtype, keep generic
    Event.ACTION: "Event",     # action slot; modeled as Event + superEvent
}
SCHEMA_TYPE_TO_CATEGORY = {
    "musicevent": Event.CONCERT,
    "festival": Event.FESTIVAL,
    "socialevent": Event.REUNION,
    "educationevent": Event.CONFERENCE,
    "foodevent": Event.RESTAURATION,
    "event": Event.CHANTIER,  # default mapping to generic
}

# Build a normalized mapping from translated display label -> internal code
# so that clients may pass additionalType with the human-readable label.
_display_norm = lambda s: str(s).strip().lower() if s is not None else ""
DISPLAY_TO_CATEGORY = { _display_norm(lbl): code for code, lbl in Event.TYPE_CHOICES }


class EventSchemaSerializer(serializers.ModelSerializer):
    postal_address = PostalAddressAsSchemaSerializer(read_only=True)

    class Meta:
        model = Event
        fields = (
            "uuid",
            "name",
            "short_description",
            "long_description",
            "datetime",
            "end_datetime",
            "full_url",
            "postal_address",
        )

    def _image_urls(self, instance: Event) -> List[str]:
        urls: List[str] = []
        try:
            if instance.img:
                urls.append(instance.img.url)
        except Exception:
            pass
        try:
            if instance.sticker_img:
                urls.append(instance.sticker_img.url)
        except Exception:
            pass
        return urls

    def _additional_properties(self, instance: Event) -> List[Dict[str, Any]]:
        props: List[Dict[str, Any]] = []
        # optionsRadio
        radio_values = list(instance.options_radio.values_list("name", flat=True)) if hasattr(instance, "options_radio") else []
        if radio_values:
            props.append({
                "@type": "PropertyValue",
                "name": "optionsRadio",
                "value": radio_values,
            })
        # optionsCheckbox
        checkbox_values = list(instance.options_checkbox.values_list("name", flat=True)) if hasattr(instance, "options_checkbox") else []
        if checkbox_values:
            props.append({
                "@type": "PropertyValue",
                "name": "optionsCheckbox",
                "value": checkbox_values,
            })
        # custom confirmation message
        if getattr(instance, "custom_confirmation_message", None):
            props.append({
                "@type": "PropertyValue",
                "name": "customConfirmationMessage",
                "value": instance.custom_confirmation_message,
            })
        return props

    def to_representation(self, instance: Event) -> Dict[str, Any]:
        data = super().to_representation(instance)

        # Choose the best description
        description = data.get("long_description") or data.get("short_description")

        # Build schema.org JSON-LD for Event
        # Determine schema.org subtype from internal category
        schema_type = CATEGORY_TO_SCHEMA_TYPE.get(getattr(instance, "categorie", None), "Event")
        payload: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": schema_type,
            # expose semantic additionalType with the human-readable category label
            "additionalType": getattr(instance, "get_categorie_display")() if hasattr(instance, "get_categorie_display") else None,
            "identifier": str(data.get("uuid")) if data.get("uuid") else None,
            "name": data.get("name"),
            "description": description,
            "disambiguatingDescription": data.get("short_description") or None,
            "startDate": data.get("datetime"),
            "endDate": data.get("end_datetime"),
            # location may be a Place with address
            "location": None,
            "url": data.get("full_url"),
            # parent event (schema.org: superEvent)
            "superEvent": ({
                "@type": "Event",
                "identifier": str(getattr(instance.parent, "uuid", "")),
                "name": getattr(instance.parent, "name", None),
            } if getattr(instance, "parent", None) else None),
            # extra mapped fields
            "maximumAttendeeCapacity": getattr(instance, "jauge_max", None),
            "image": self._image_urls(instance) or None,
            "sameAs": data.get("full_url") if getattr(instance, "is_external", False) else None,
            "eventStatus": "https://schema.org/EventScheduled" if getattr(instance, "published", True) else "https://schema.org/EventCancelled",
            "audience": {"@type": "Audience", "audienceType": "private"} if getattr(instance, "private", False) else None,
            "keywords": list(instance.tag.values_list("name", flat=True)) if hasattr(instance, "tag") else None,
            "offers": {
                "@type": "Offer",
                "eligibleQuantity": {
                    "@type": "QuantitativeValue",
                    "maxValue": getattr(instance, "max_per_user", None),
                },
                "returnPolicy": {
                    "@type": "MerchantReturnPolicy",
                    "merchantReturnDays": getattr(instance, "refund_deadline", None),
                },
            },
            "additionalProperty": self._additional_properties(instance) or None,
        }

        # Map location if available
        address = data.get("postal_address")
        if address:
            payload["location"] = {
                "@type": "Place",
                "address": address,
            }

        # Remove nulls for cleanliness (and clean nested offers if empty)
        clean_payload = {k: v for k, v in payload.items() if v not in (None, "", [])}
        # Clean offers substructure if all values are None
        offers = clean_payload.get("offers")
        if isinstance(offers, dict):
            # prune None in eligibleQuantity
            if isinstance(offers.get("eligibleQuantity"), dict):
                if offers["eligibleQuantity"].get("maxValue") in (None, ""):
                    offers.pop("eligibleQuantity", None)
            # prune returnPolicy if days None
            if isinstance(offers.get("returnPolicy"), dict):
                if offers["returnPolicy"].get("merchantReturnDays") in (None, ""):
                    offers.pop("returnPolicy", None)
            if not offers:
                clean_payload.pop("offers", None)
        return clean_payload


class EventCreateSerializer(serializers.Serializer):
    """
    schema.org/Event input serializer for creation (semantic fields only) + semantic @type mapping and optional 'superEvent'.

    Accepted (schema.org) fields:
      - name: Text (required)
      - startDate: DateTime (required)
      - endDate: DateTime (optional)
      - url: URL (optional)
      - sameAs: URL (optional; canonical external URL)
      - maximumAttendeeCapacity: Integer (maps to jauge_max)
      - disambiguatingDescription: Text (maps to short_description)
      - description: Text (maps to long_description)
      - eventStatus: URL or Text (e.g. https://schema.org/EventScheduled)
      - audience: { "@type": "Audience", "audienceType": "private"|"public" }
      - keywords: [Text, ...] (tags)
      - image: [URL or ImageObject] (ignored on create for now)
      - offers: {
          "eligibleQuantity": {"maxValue": int},
          "returnPolicy": {"merchantReturnDays": int}
        }
      - additionalProperty: [
          {"name":"optionsRadio","value":["OptionName", ...]},
          {"name":"optionsCheckbox","value":["OptionName", ...]},
          {"name":"customConfirmationMessage","value":"..."}
        ]
    """
    # Core fields
    name = serializers.CharField(max_length=200)
    startDate = serializers.DateTimeField()
    endDate = serializers.DateTimeField(required=False, allow_null=True)
    # Optional parent (schema.org superEvent) — UUID string; required if mapped category is ACTION
    superEvent = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # Simple mappings
    url = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    sameAs = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    maximumAttendeeCapacity = serializers.IntegerField(required=False, allow_null=True)
    disambiguatingDescription = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    eventStatus = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    audience = serializers.DictField(required=False)
    keywords = serializers.ListField(child=serializers.CharField(), required=False)

    # Nested structures
    image = serializers.ListField(child=serializers.CharField(), required=False)
    offers = serializers.DictField(required=False)
    additionalProperty = serializers.ListField(child=serializers.DictField(), required=False)

    # Semantic category display label (schema.org/Thing.additionalType)
    additionalType = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        # Strictly validate uploaded images if present in request.FILES
        req = self.context.get("request") if hasattr(self, 'context') else None
        if req is not None and hasattr(req, 'FILES'):
            for fname in ("img", "sticker_img"):
                f = req.FILES.get(fname)
                if f:
                    _validate_uploaded_image(f)
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> Event:
        # Extract top-level fields
        name: str = validated_data["name"]
        start = validated_data["startDate"]
        end = validated_data.get("endDate")
        url = validated_data.get("url")
        same_as = validated_data.get("sameAs")
        max_cap = validated_data.get("maximumAttendeeCapacity")
        short_desc = validated_data.get("disambiguatingDescription")
        long_desc = validated_data.get("description")
        # Determine internal category code from semantic @type
        requested_type = (self.initial_data.get("@type") or "Event").strip()
        cat_code = SCHEMA_TYPE_TO_CATEGORY.get(requested_type.lower(), Event.CHANTIER)
        # Allow clients to explicitly set a human-readable category via additionalType (display label)
        addl_type_label = validated_data.get("additionalType")
        if addl_type_label:
            mapped = DISPLAY_TO_CATEGORY.get(str(addl_type_label).strip().lower())
            if mapped:
                cat_code = mapped
        super_event_uuid = validated_data.get("superEvent")
        event_status = (validated_data.get("eventStatus") or "").lower() if validated_data.get("eventStatus") else None
        audience = validated_data.get("audience") or {}
        keywords: List[str] = validated_data.get("keywords") or []
        offers = validated_data.get("offers") or {}
        add_props: List[Dict[str, Any]] = validated_data.get("additionalProperty") or []

        # eventStatus → published
        published = True
        if event_status:
            if "eventscheduled" in event_status:
                published = True
            elif "eventcancelled" in event_status:
                published = False
            else:
                # default to True if unrecognized
                published = True

        # audience → private
        private = False
        try:
            aud_type = (audience.get("audienceType") or "").lower()
            private = aud_type == "private"
        except Exception:
            private = False

        # offers mapping
        max_per_user: Optional[int] = None
        refund_days: Optional[int] = None
        try:
            elig = offers.get("eligibleQuantity") or {}
            max_per_user = elig.get("maxValue")
        except Exception:
            pass
        try:
            ret = offers.get("returnPolicy") or {}
            refund_days = ret.get("merchantReturnDays")
        except Exception:
            pass

        # full_url / external
        full_url = same_as or url
        is_external = bool(same_as)

        # Validate category & parent (semantic rule: ACTION requires superEvent)
        parent_obj = None
        # If superEvent provided with generic Event, we treat it as ACTION
        if super_event_uuid and cat_code == Event.CHANTIER and requested_type.lower() in ("event", "socialevent"):
            cat_code = Event.ACTION
        if cat_code == Event.ACTION and not super_event_uuid:
            raise serializers.ValidationError({"superEvent": "Ce champ est requis quand la catégorie est ACTION."})
        if super_event_uuid:
            try:
                parent_obj = Event.objects.get(uuid=super_event_uuid)
            except Event.DoesNotExist:
                raise serializers.ValidationError({"superEvent": "Evènement parent introuvable."})

        # Generate a unique slug from name to avoid unique constraint violations on repeated tests
        base_slug = slugify(name) or "event"
        slug_value = base_slug
        # If collision, append a short random suffix
        while Event.objects.filter(slug=slug_value).exists():
            suffix = "-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
            slug_value = f"{base_slug}{suffix}"

        # Create Event
        create_kwargs = {
            "name": name,
            "slug": slug_value,
            "datetime": start,
            "end_datetime": end,
            "full_url": full_url,
            "is_external": is_external,
            "short_description": short_desc,
            "long_description": long_desc,
            "published": published,
            "archived": False,
            "private": private,
            "categorie": cat_code,
            "parent": parent_obj,
        }
        if max_cap is not None:
            create_kwargs["jauge_max"] = max_cap
        if max_per_user is not None:
            create_kwargs["max_per_user"] = max_per_user
        if refund_days is not None:
            create_kwargs["refund_deadline"] = refund_days

        event = Event.objects.create(**create_kwargs)

        # keywords → tags
        if keywords:
            for tag_name in keywords:
                if not tag_name:
                    continue
                tag_obj, _ = Tag.objects.get_or_create(name=str(tag_name).strip())
                event.tag.add(tag_obj)

        # additionalProperty → options & custom message
        def _extract_values(prop_name: str) -> List[str]:
            for p in add_props:
                if str(p.get("name")).lower() == prop_name.lower():
                    v = p.get("value")
                    if isinstance(v, list):
                        return [str(x) for x in v]
                    if isinstance(v, str):
                        return [v]
            return []

        radio_names = _extract_values("optionsRadio")
        if radio_names:
            for opt_name in radio_names:
                try:
                    opt = OptionGenerale.objects.get(name=opt_name)
                except OptionGenerale.DoesNotExist:
                    # Create missing options to keep API v2 setup simple
                    # Cree l'option si elle n'existe pas (FALC)
                    opt = OptionGenerale.objects.create(name=opt_name)
                event.options_radio.add(opt)

        checkbox_names = _extract_values("optionsCheckbox")
        if checkbox_names:
            for opt_name in checkbox_names:
                try:
                    opt = OptionGenerale.objects.get(name=opt_name)
                except OptionGenerale.DoesNotExist:
                    # Create missing options to keep API v2 setup simple
                    # Cree l'option si elle n'existe pas (FALC)
                    opt = OptionGenerale.objects.create(name=opt_name)
                event.options_checkbox.add(opt)

        # customConfirmationMessage
        for p in add_props:
            if str(p.get("name")).lower() == "customconfirmationmessage":
                val = p.get("value")
                if isinstance(val, str) and val.strip():
                    event.custom_confirmation_message = val.strip()
                    event.save(update_fields=["custom_confirmation_message"]) 
                break

        return event



class PostalAddressCreateSerializer(serializers.Serializer):
    """
    schema.org/PostalAddress input serializer for creation.

    Accepted fields (schema.org names):
      - name (optional, Text) → internal name helper
      - streetAddress (required, Text)
      - addressLocality (required, Text)
      - addressRegion (optional, Text)
      - postalCode (required, Text)
      - addressCountry (required, Text)
      - geo (optional) { "latitude": number, "longitude": number }
    """

    # Optional label for quick finding later (maps to model.name)
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=400)

    # Required address lines
    streetAddress = serializers.CharField()
    addressLocality = serializers.CharField()
    addressRegion = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    postalCode = serializers.CharField()
    addressCountry = serializers.CharField()

    geo = serializers.DictField(required=False)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        # Validate uploaded images if provided via multipart request
        req = self.context.get("request") if hasattr(self, 'context') else None
        if req is not None and hasattr(req, 'FILES'):
            for fname in ("img", "sticker_img"):
                f = req.FILES.get(fname)
                if f:
                    _validate_uploaded_image(f)
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> PostalAddress:
        geo = validated_data.pop("geo", {}) or {}
        lat = geo.get("latitude")
        lon = geo.get("longitude")
        return PostalAddress.objects.create(
            name=validated_data.get("name") or None,
            street_address=validated_data["streetAddress"],
            address_locality=validated_data["addressLocality"],
            address_region=validated_data.get("addressRegion"),
            postal_code=validated_data["postalCode"],
            address_country=validated_data["addressCountry"],
            latitude=lat,
            longitude=lon,
        )




class SemanticProductFromSaleLineSerializer(serializers.Serializer):
    """
    Sérializer sémantique (schema.org) pour une ligne de vente.

    Objectif:
    - Prendre les mêmes données métier qu'un `LigneArticleSerializer` (même instance source),
      mais produire une représentation sémantique lisible par humains et machines.
    - Sortie au format schema.org avec `@type: Product`.

    Remarques FALC (Facile À Lire et à Comprendre):
    - On décrit le produit de la ligne (Product) avec ses infos principales.
    - On ajoute une offre (Offer) avec le prix unitaire et la devise.
    - On inclut des infos utiles en plus (TVA, quantité, UUID de la ligne) dans `additionalProperty`.
    - Cette classe n'altère pas la donnée en base; elle ne fait que formater la réponse.
    """

    # Ce Serializer est « read-only » et reconstruit un dict sémantique depuis l'instance

    def _absolute_url(self, relative_url: str) -> str:
        request = self.context.get('request')
        if request and relative_url:
            try:
                return request.build_absolute_uri(relative_url)
            except Exception:
                return relative_url
        return relative_url

    def to_representation(self, instance: LigneArticle) -> Dict[str, Any]:
        # Sécurise les accès aux relations
        productsold: PriceSold | None = getattr(instance, 'pricesold', None)
        product: Product | None = None
        if productsold and getattr(productsold, 'productsold', None):
            product = productsold.productsold.product

        # Nom et descriptions
        name = product.name if (product and product.name) else _('Product')
        short_desc = getattr(product, 'short_description', None) if product else None
        long_desc = getattr(product, 'long_description', None) if product else None
        description = long_desc or short_desc

        # Image (si présente)
        image_url = None
        if product and getattr(product, 'img', None):
            try:
                # Tente d'utiliser une variante raisonnable si dispo
                if hasattr(product.img, 'med') and hasattr(product.img.med, 'url'):
                    image_url = self._absolute_url(product.img.med.url)
                elif hasattr(product.img, 'url'):
                    image_url = self._absolute_url(product.img.url)
            except Exception:
                image_url = None

        # Prix unitaire TTC (à partir de LigneArticle.amount en centimes)
        price_unit_eur = None
        if instance.amount is not None:
            try:
                price_unit_eur = str(Decimal(instance.amount) / Decimal('100'))
            except Exception:
                price_unit_eur = None

        # Catégorie (affichage lisible si disponible)
        category = None
        if product and hasattr(product, 'get_categorie_article_display'):
            try:
                category = product.get_categorie_article_display()
            except Exception:
                category = None

        # Identifiants
        sku = str(product.uuid) if product else None
        product_id = str(product.uuid) if product else None

        # Offre schema.org (simplifiée)
        offers = None
        if price_unit_eur is not None:
            offers = {
                "@type": "Offer",
                # Prix TTC unitaire au moment de la vente
                "price": price_unit_eur,
                "priceCurrency": "EUR",
            }

        # Propriétés additionnelles utiles (claires et FALC)
        additional_property = [
            {
                "@type": "PropertyValue",
                "name": "sale_line_uuid",
                "value": str(instance.uuid),
                "description": "Identifiant unique de la ligne de vente",
            },
            {
                "@type": "PropertyValue",
                "name": "quantity",
                "value": str(instance.qty),
                "description": "Quantité vendue",
            },
            {
                "@type": "PropertyValue",
                "name": "vat",
                "value": str(instance.vat),
                "description": "TVA appliquée en pourcentage",
            },
        ]

        if getattr(instance, 'payment_method', None):
            additional_property.append({
                "@type": "PropertyValue",
                "name": "payment_method",
                "value": instance.payment_method,
                "description": "Méthode de paiement",
            })

        if getattr(instance, 'status', None):
            additional_property.append({
                "@type": "PropertyValue",
                "name": "status",
                "value": instance.status,
                "description": "Statut de la ligne",
            })

        # Construction finale schema.org/Product
        data: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": name,
            "sku": sku,
            "category": category,
            "description": description,
            "productID": product_id,
            "datePublished": instance.datetime.isoformat() if instance.datetime else None,
            "offers": offers,
            # Informations complémentaires simples et utiles
            "additionalProperty": additional_property,
        }

        if image_url:
            data["image"] = image_url

        return data


class ProductSchemaSerializer(serializers.Serializer):
    """
    schema.org/Product output serializer for API v2 product resources.
    Sortie schema.org/Product pour les produits API v2.
    """

    def to_representation(self, instance: Product) -> Dict[str, Any]:
        description = instance.long_description or instance.short_description
        category = instance.get_categorie_article_display() if hasattr(instance, "get_categorie_article_display") else None

        offers: List[Dict[str, Any]] = []
        for price in instance.prices.all().order_by("order"):
            offer: Dict[str, Any] = {
                "@type": "Offer",
                "identifier": str(price.uuid),
                "name": price.name,
                "price": str(price.prix),
                "priceCurrency": "EUR",
                "freePrice": bool(price.free_price),
            }

            # Optional semantic helpers
            if price.stock is not None:
                offer["inventoryLevel"] = {
                    "@type": "QuantitativeValue",
                    "value": price.stock,
                }
            if price.max_per_user is not None:
                offer["eligibleQuantity"] = {
                    "@type": "QuantitativeValue",
                    "maxValue": price.max_per_user,
                }

            additional_property = []
            if price.recurring_payment:
                additional_property.append({
                    "@type": "PropertyValue",
                    "name": "recurringPayment",
                    "value": True,
                })
                additional_property.append({
                    "@type": "PropertyValue",
                    "name": "subscriptionType",
                    "value": price.subscription_type,
                })
            adhesion_ids = list(price.adhesions_obligatoires.values_list('pk', flat=True))
            if adhesion_ids:
                additional_property.append({
                    "@type": "PropertyValue",
                    "name": "membershipRequiredProducts",
                    "value": [str(pk) for pk in adhesion_ids],
                })
            if price.manual_validation:
                additional_property.append({
                    "@type": "PropertyValue",
                    "name": "manualValidation",
                    "value": True,
                })
            if additional_property:
                offer["additionalProperty"] = additional_property

            offers.append(offer)

        data: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Product",
            "identifier": str(instance.uuid),
            "sku": str(instance.uuid),
            "name": instance.name,
            "description": description,
            "category": category,
            "offers": offers,
        }

        return {k: v for k, v in data.items() if v not in (None, "", [])}


class ProductCreateSerializer(serializers.Serializer):
    """
    schema.org/Product input serializer for product creation with prices and form fields.
    Serializer simple pour creer un produit, ses tarifs, et son formulaire dynamique.
    """

    name = serializers.CharField(max_length=500)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    category = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    offers = serializers.ListField(child=serializers.DictField(), required=True)
    additionalProperty = serializers.ListField(child=serializers.DictField(), required=False)
    isRelatedTo = serializers.JSONField(required=False)

    def _normalize_category(self, raw: Optional[str]) -> str:
        if not raw:
            return Product.BILLET

        normalized = str(raw).strip().lower()

        display_to_code = {
            str(label).strip().lower(): code
            for code, label in Product.CATEGORIE_ARTICLE_CHOICES
        }

        synonyms = {
            "ticket": Product.BILLET,
            "ticket booking": Product.BILLET,
            "billet": Product.BILLET,
            "free booking": Product.FREERES,
            "reservation gratuite": Product.FREERES,
            "subscription or membership": Product.ADHESION,
            "membership": Product.ADHESION,
            "adhesion": Product.ADHESION,
            Product.BILLET.lower(): Product.BILLET,
            Product.FREERES.lower(): Product.FREERES,
            Product.ADHESION.lower(): Product.ADHESION,
        }

        if normalized in display_to_code:
            return display_to_code[normalized]
        if normalized in synonyms:
            return synonyms[normalized]

        raise serializers.ValidationError({"category": "Unknown category. Use a known label or code."})

    def _extract_additional_property(self, add_props: List[Dict[str, Any]], key: str) -> Any:
        for prop in add_props:
            name = str(prop.get("name", "")).strip().lower()
            if name == key.lower():
                return prop.get("value")
        return None

    def _extract_event_uuid(self, related: Any, add_props: List[Dict[str, Any]]) -> Optional[str]:
        if isinstance(related, str):
            return related
        if isinstance(related, dict):
            identifier = related.get("identifier") or related.get("id") or related.get("uuid")
            if identifier:
                return str(identifier)

        fallback = self._extract_additional_property(add_props, "eventUuid")
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()
        return None

    def _parse_form_fields(self, add_props: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        raw_fields = self._extract_additional_property(add_props, "formFields")
        if raw_fields is None:
            return []
        if isinstance(raw_fields, dict):
            return [raw_fields]
        if isinstance(raw_fields, list):
            return raw_fields
        return []

    def _extract_offer_property(self, offer: Dict[str, Any], key: str) -> Any:
        # Read from offer.additionalProperty (schema.org PropertyValue list)
        add_props = offer.get("additionalProperty") or []
        if isinstance(add_props, dict):
            add_props = [add_props]
        if isinstance(add_props, list):
            for prop in add_props:
                name = str(prop.get("name", "")).strip().lower()
                if name == key.lower():
                    return prop.get("value")
        return None

    def create(self, validated_data: Dict[str, Any]) -> Product:
        name = validated_data["name"]
        description = validated_data.get("description")
        category_raw = validated_data.get("category")
        offers = validated_data.get("offers") or []
        add_props = validated_data.get("additionalProperty") or []
        related = validated_data.get("isRelatedTo")

        if not offers:
            raise serializers.ValidationError({"offers": "At least one offer is required."})

        category_code = self._normalize_category(category_raw)

        form_fields = self._parse_form_fields(add_props)
        field_type_map = {
            "shorttext": ProductFormField.FieldType.SHORT_TEXT,
            "longtext": ProductFormField.FieldType.LONG_TEXT,
            "singleselect": ProductFormField.FieldType.SINGLE_SELECT,
            "radioselect": ProductFormField.FieldType.RADIO_SELECT,
            "multiselect": ProductFormField.FieldType.MULTI_SELECT,
            "boolean": ProductFormField.FieldType.BOOLEAN,
        }

        with transaction.atomic():
            product = Product.objects.create(
                name=name,
                long_description=description,
                publish=True,
                archive=False,
                categorie_article=category_code,
            )

            # Product-level max per user (semantic)
            # Maximum par utilisateur (niveau produit)
            max_per_user = self._extract_additional_property(add_props, "maxPerUser")
            if max_per_user is not None:
                try:
                    product.max_per_user = int(max_per_user)
                    product.save(update_fields=["max_per_user"])
                except Exception:
                    raise serializers.ValidationError({"maxPerUser": "Invalid value for maxPerUser."})

            for idx, offer in enumerate(offers):
                offer_name = offer.get("name")
                offer_price = offer.get("price")
                if not offer_name:
                    raise serializers.ValidationError({"offers": "Each offer must include a name."})
                if offer_price in (None, ""):
                    raise serializers.ValidationError({"offers": "Each offer must include a price."})

                order = int(offer.get("order") or (100 + idx))
                stock = offer.get("stock")
                max_per_user = offer.get("maxPerUser")

                # Support schema.org-like fields
                # inventoryLevel.value -> stock
                inventory_level = offer.get("inventoryLevel")
                if isinstance(inventory_level, dict):
                    inv_val = inventory_level.get("value")
                    if inv_val is not None:
                        stock = inv_val

                # eligibleQuantity.maxValue -> max_per_user
                eligible_quantity = offer.get("eligibleQuantity")
                if isinstance(eligible_quantity, dict):
                    max_val = eligible_quantity.get("maxValue")
                    if max_val is not None:
                        max_per_user = max_val

                # recurring payment and subscription type
                recurring_payment = offer.get("recurringPayment")
                if recurring_payment is None:
                    recurring_payment = self._extract_offer_property(offer, "recurringPayment")
                recurring_payment = bool(recurring_payment)

                subscription_type = offer.get("subscriptionType")
                if subscription_type is None:
                    subscription_type = self._extract_offer_property(offer, "subscriptionType")
                subscription_type = str(subscription_type or "").strip().upper() or None
                if subscription_type and subscription_type not in dict(Price.SUB_CHOICES):
                    raise serializers.ValidationError({"subscriptionType": "Invalid subscription type."})

                # Required membership product for this price
                # Can be passed as offer.membershipRequiredProduct or additionalProperty
                membership_required = offer.get("membershipRequiredProduct")
                if membership_required is None:
                    membership_required = self._extract_offer_property(offer, "membershipRequiredProduct")

                # Manual validation flag
                manual_validation = offer.get("manualValidation")
                if manual_validation is None:
                    manual_validation = self._extract_offer_property(offer, "manualValidation")
                manual_validation = bool(manual_validation)

                price_obj = Price.objects.create(
                    product=product,
                    name=str(offer_name),
                    prix=offer_price,
                    order=order,
                    free_price=bool(offer.get("freePrice")),
                    publish=True,
                    stock=stock,
                    max_per_user=max_per_user,
                    recurring_payment=recurring_payment,
                    subscription_type=subscription_type or Price.NA,
                    manual_validation=manual_validation,
                )

                # Link required membership product if requested
                if membership_required:
                    try:
                        membership_product = Product.objects.get(uuid=str(membership_required))
                    except Product.DoesNotExist:
                        raise serializers.ValidationError({"membershipRequiredProduct": "Product not found."})
                    if membership_product.categorie_article != Product.ADHESION:
                        raise serializers.ValidationError({"membershipRequiredProduct": "Product must be a membership."})
                    price_obj.adhesions_obligatoires.add(membership_product)

            for idx, field in enumerate(form_fields):
                label = field.get("label")
                field_type_raw = field.get("fieldType")
                if not label or not field_type_raw:
                    raise serializers.ValidationError({"formFields": "Each field needs label and fieldType."})

                field_type = field_type_map.get(str(field_type_raw).strip().lower())
                if not field_type:
                    raise serializers.ValidationError({"formFields": f"Unknown fieldType: {field_type_raw}"})

                ProductFormField.objects.create(
                    product=product,
                    label=str(label),
                    field_type=field_type,
                    required=bool(field.get("required")),
                    options=field.get("options"),
                    order=int(field.get("order") or (idx + 1)),
                    help_text=field.get("helpText"),
                )

            event_uuid = self._extract_event_uuid(related, add_props)
            if event_uuid:
                try:
                    event = Event.objects.get(uuid=event_uuid)
                except Event.DoesNotExist:
                    raise serializers.ValidationError({"isRelatedTo": "Event not found."})
                event.products.add(product)

        return product


class ReservationCreateSerializer(serializers.Serializer):
    """
    schema.org/Reservation input serializer for API v2.
    Serializer d'entree pour creer une reservation via API v2.
    """

    # reservationFor est optionnel : si absent, l'événement est déduit
    # à partir des tarifs demandés (cas de la caisse LaBoutik qui ne
    # connaît que le tarif, pas l'événement).
    # / reservationFor is optional: if missing, the event is resolved
    # / from the requested prices (LaBoutik POS only knows the price).
    reservationFor = serializers.DictField(required=False)
    underName = serializers.DictField(required=True)
    reservedTicket = serializers.ListField(child=serializers.DictField(), required=True)
    additionalProperty = serializers.ListField(child=serializers.DictField(), required=False)

    def _extract_property(self, add_props: List[Dict[str, Any]], key: str) -> Any:
        for prop in add_props:
            name = str(prop.get("name", "")).strip().lower()
            if name == key.lower():
                return prop.get("value")
        return None

    def _resolve_event_from_prices(self, reserved_tickets: List[Dict[str, Any]]) -> "Event":
        """
        Déduit l'événement à partir des tarifs demandés.
        / Resolves the event from the requested prices.

        LOCALISATION : api_v2/serializers.py

        Cas d'usage : la caisse LaBoutik vend un billet.
        Elle ne connaît que l'uuid du tarif (Price), pas l'événement.
        On cherche le prochain événement publié qui propose ce produit.

        Règles simples :
        - Aucun événement à venir trouvé : erreur claire.
        - Plusieurs événements possibles : erreur claire.
          L'appelant doit alors préciser reservationFor.
        - Un seul événement : on le retourne.
        """
        from datetime import timedelta
        from django.utils import timezone

        # On récupère les produits des tarifs demandés.
        # / Get the products of the requested prices.
        price_uuids = []
        for item in reserved_tickets:
            price_uuid = item.get("identifier") or item.get("id") or item.get("uuid")
            if price_uuid:
                price_uuids.append(str(price_uuid))

        products_of_requested_prices = Product.objects.filter(prices__uuid__in=price_uuids).distinct()
        if not products_of_requested_prices.exists():
            raise serializers.ValidationError({"reservedTicket": "No product found for the given prices."})

        # Événements publiés à venir qui proposent ces produits.
        # Même fenêtre que ReservationValidator : on garde la veille (J-1).
        # / Published upcoming events offering these products (same J-1 window as ReservationValidator).
        now_minus_one_day = timezone.now() - timedelta(days=1)
        candidate_events = Event.objects.filter(
            published=True,
            datetime__gte=now_minus_one_day,
            products__in=products_of_requested_prices,
        ).distinct().order_by("datetime")

        if candidate_events.count() == 0:
            raise serializers.ValidationError(
                {"reservationFor": "No upcoming event found for this product. Please provide reservationFor."})
        if candidate_events.count() > 1:
            raise serializers.ValidationError(
                {"reservationFor": "Several upcoming events match this product. Please provide reservationFor."})

        return candidate_events.first()

    def create(self, validated_data: Dict[str, Any]) -> Reservation:
        from django.contrib.auth.models import AnonymousUser
        from django.http import QueryDict
        from types import SimpleNamespace

        from BaseBillet.models import Reservation, Ticket, Price
        from BaseBillet.validators import ReservationValidator
        from ApiBillet.serializers import get_or_create_price_sold, dec_to_int
        from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin

        reservation_for = validated_data.get("reservationFor") or {}
        under_name = validated_data.get("underName") or {}
        reserved_tickets = validated_data.get("reservedTicket") or []
        add_props = validated_data.get("additionalProperty") or []

        event_uuid = reservation_for.get("identifier") or reservation_for.get("id") or reservation_for.get("uuid")
        email = under_name.get("email")

        if not email:
            raise serializers.ValidationError({"underName": "email is required."})

        if event_uuid:
            try:
                event = Event.objects.get(uuid=str(event_uuid))
            except Event.DoesNotExist:
                raise serializers.ValidationError({"reservationFor": "Event not found."})
        else:
            # Pas d'événement fourni : on le déduit des tarifs demandés.
            # Cas de la caisse LaBoutik qui ne connaît que le tarif.
            # / No event given: resolve it from the requested prices (LaBoutik POS case).
            event = self._resolve_event_from_prices(reserved_tickets)

        # Billet déjà payé ailleurs (ex : en caisse LaBoutik) ?
        # additionalProperty paymentMethod = "cash" ou "card".
        # Dans ce cas : pas de checkout Stripe, la vente est valide tout de suite.
        # / Ticket already paid elsewhere (e.g., LaBoutik POS)?
        # / additionalProperty paymentMethod = "cash" or "card": no Stripe checkout.
        EXTERNAL_PAYMENT_METHODS = {
            "cash": PaymentMethod.CASH,
            "card": PaymentMethod.CC,
        }
        payment_method_property = self._extract_property(add_props, "paymentMethod")
        paid_externally = False
        external_payment_method = None
        if payment_method_property is not None:
            payment_method_key = str(payment_method_property).strip().lower()
            if payment_method_key not in EXTERNAL_PAYMENT_METHODS:
                raise serializers.ValidationError(
                    {"additionalProperty": "paymentMethod must be one of: cash, card."})
            paid_externally = True
            external_payment_method = EXTERNAL_PAYMENT_METHODS[payment_method_key]

        data = QueryDict(mutable=True)
        data.update({
            "email": email,
            "event": str(event.pk),
        })

        # Options (list of UUID)
        options = self._extract_property(add_props, "options") or []
        if options:
            for opt in options:
                data.update({"options": str(opt)})

        # Promo code
        promo_code = self._extract_property(add_props, "promotionalCode")
        if promo_code:
            data.update({"promotional_code": str(promo_code)})

        # Custom form (object)
        custom_form = self._extract_property(add_props, "customForm") or {}
        if isinstance(custom_form, dict):
            for key, value in custom_form.items():
                data.update({f"form__{key}": str(value)})

        # Reserved tickets (price uuid + qty + custom amount)
        price_qty_pairs = []
        for item in reserved_tickets:
            price_uuid = item.get("identifier") or item.get("id") or item.get("uuid")
            qty = item.get("ticketQuantity") or item.get("qty") or 1
            price_value = item.get("price")
            if not price_uuid:
                raise serializers.ValidationError({"reservedTicket": "identifier is required for each ticket."})
            data.update({str(price_uuid): str(qty)})
            price_qty_pairs.append((str(price_uuid), qty, price_value))
            if price_value is not None:
                data.update({f"custom_amount_{price_uuid}": str(price_value)})

        # Build a fake request for the validator
        fake_request = SimpleNamespace(user=AnonymousUser(), data=data)
        validator_context = {"request": fake_request, "sale_origin": SaleOrigin.API}
        if paid_externally:
            # Vente déjà payée en caisse : origine LaBoutik,
            # le TicketCreator créera la ligne de vente en VALID sans Stripe.
            # / Already paid at the POS: LaBoutik origin, sale line created VALID, no Stripe.
            validator_context["sale_origin"] = SaleOrigin.LABOUTIK
            validator_context["paid_externally"] = True
            validator_context["external_payment_method"] = external_payment_method
        validator = ReservationValidator(data=data, context=validator_context)
        validator.is_valid(raise_exception=True)

        reservation = validator.reservation
        checkout_link = validator.checkout_link

        # Vente payée en caisse : tout est déjà créé et valide.
        # On ne passe pas par les blocs "gratuit" ci-dessous,
        # sinon une deuxième ligne de vente serait créée en double.
        # / Paid at the POS: everything is already created and valid.
        # / Skip the free-booking blocks below to avoid a duplicate sale line.
        if paid_externally:
            return reservation

        # Confirm free reservations (optional)
        confirmed = bool(self._extract_property(add_props, "confirmed"))
        if confirmed and not checkout_link:
            reservation.status = Reservation.VALID
            reservation.save(update_fields=["status"])
            reservation.tickets.all().update(status=Ticket.NOT_SCANNED)

        # Ensure LigneArticle exists for free bookings (source API)
        if not checkout_link:
            for price_uuid, qty, price_value in price_qty_pairs:
                try:
                    price = Price.objects.get(uuid=price_uuid)
                except Price.DoesNotExist:
                    continue
                price_sold = get_or_create_price_sold(price, event=event, custom_amount=price_value)
                LigneArticle.objects.create(
                    pricesold=price_sold,
                    amount=dec_to_int(price_sold.prix),
                    qty=qty,
                    payment_method=PaymentMethod.FREE,
                    sale_origin=SaleOrigin.API,
                    status=LigneArticle.FREERES,
                    reservation=reservation,
                    metadata={"source": "api"},
                )

        return reservation


class ReservationSchemaSerializer(serializers.Serializer):
    """
    schema.org/Reservation output serializer.
    Serializer de sortie pour une reservation API v2.
    """

    def to_representation(self, instance: Reservation) -> Dict[str, Any]:
        # Build reserved tickets list (grouped by price)
        tickets = instance.tickets.all()
        grouped: Dict[str, int] = {}
        for ticket in tickets:
            price_uuid = str(getattr(ticket.pricesold.price, "uuid", "")) if ticket.pricesold else ""
            grouped[price_uuid] = grouped.get(price_uuid, 0) + 1

        reserved_ticket = []
        for price_uuid, qty in grouped.items():
            reserved_ticket.append({
                "@type": "Ticket",
                "identifier": price_uuid,
                "ticketQuantity": qty,
            })

        status_map = {
            Reservation.VALID: "https://schema.org/ReservationConfirmed",
            Reservation.FREERES: "https://schema.org/ReservationPending",
            Reservation.UNPAID: "https://schema.org/ReservationPending",
        }

        return {
            "@context": "https://schema.org",
            "@type": "Reservation",
            "identifier": str(instance.uuid),
            "reservationFor": {
                "@type": "Event",
                "identifier": str(instance.event.uuid),
                "name": instance.event.name,
            },
            "underName": {
                "@type": "Person",
                "email": instance.user_commande.email,
            },
            "reservationStatus": status_map.get(instance.status, "https://schema.org/ReservationPending"),
            "reservedTicket": reserved_ticket,
        }


class MembershipCreateSerializer(serializers.Serializer):
    """
    schema.org/ProgramMembership input serializer for API v2.
    Serializer d'entree pour creer une adhesion via API v2.
    """

    member = serializers.DictField(required=True)
    membershipPlan = serializers.DictField(required=False)
    additionalProperty = serializers.ListField(child=serializers.DictField(), required=False)
    validUntil = serializers.DateTimeField(required=False, allow_null=True)

    def _extract_property(self, add_props: List[Dict[str, Any]], key: str) -> Any:
        for prop in add_props:
            name = str(prop.get("name", "")).strip().lower()
            if name == key.lower():
                return prop.get("value")
        return None

    def create(self, validated_data: Dict[str, Any]) -> Membership:
        from django.contrib.auth.models import AnonymousUser
        from django.http import QueryDict
        from types import SimpleNamespace

        from BaseBillet.validators import MembershipValidator
        from BaseBillet.models import Membership, SaleOrigin, PaymentMethod

        member = validated_data.get("member") or {}
        plan = validated_data.get("membershipPlan") or {}
        add_props = validated_data.get("additionalProperty") or []
        valid_until = validated_data.get("validUntil")

        email = member.get("email")
        first_name = member.get("givenName") or member.get("firstName") or ""
        last_name = member.get("familyName") or member.get("lastName") or ""

        price_uuid = plan.get("identifier") or self._extract_property(add_props, "priceUuid")

        if not email:
            raise serializers.ValidationError({"member": "email is required."})
        if not price_uuid:
            raise serializers.ValidationError({"membershipPlan": "identifier (price UUID) is required."})

        data = QueryDict(mutable=True)
        data.update({
            "email": email,
            "firstname": first_name or "API",
            "lastname": last_name or "Member",
            "price": str(price_uuid),
            "newsletter": "0",
            "acknowledge": "1",
        })

        # Custom amount for free price
        custom_amount = self._extract_property(add_props, "customAmount")
        if custom_amount is not None:
            data.update({f"custom_amount_{price_uuid}": str(custom_amount)})

        # Options (list of UUID)
        options = self._extract_property(add_props, "options") or []
        if options:
            for opt in options:
                data.update({"options": str(opt)})

        # Custom form (object)
        custom_form = self._extract_property(add_props, "customForm") or {}
        if isinstance(custom_form, dict):
            for key, value in custom_form.items():
                data.update({f"form__{key}": str(value)})

        payment_mode = (self._extract_property(add_props, "paymentMode") or "FREE").upper()
        if payment_mode not in ["FREE", "STRIPE"]:
            raise serializers.ValidationError({"paymentMode": "Allowed values: FREE, STRIPE."})

        fake_request = SimpleNamespace(user=AnonymousUser(), data=data)
        validator = MembershipValidator(data=data, context={
            "request": fake_request,
            "payment_mode": payment_mode,
            "sale_origin": SaleOrigin.API,
        })
        validator.is_valid(raise_exception=True)

        membership = validator.membership

        # Optional status override (admin usage)
        override_status = self._extract_property(add_props, "status")
        if override_status:
            allowed = [choice[0] for choice in Membership.STATUS_CHOICES]
            if override_status not in allowed:
                raise serializers.ValidationError({"status": "Invalid membership status."})
            membership.status = override_status
            membership.save(update_fields=["status"])

        # Optional subscription id
        stripe_sub_id = self._extract_property(add_props, "stripeSubscriptionId")
        if stripe_sub_id:
            membership.stripe_id_subscription = str(stripe_sub_id)
            membership.save(update_fields=["stripe_id_subscription"])

        # Optional valid until
        if valid_until:
            membership.deadline = valid_until
            membership.save(update_fields=["deadline"])

        return membership


class MembershipSchemaSerializer(serializers.Serializer):
    """
    schema.org/ProgramMembership output serializer.
    Serializer de sortie pour une adhesion API v2.
    """

    def to_representation(self, instance: Membership) -> Dict[str, Any]:
        return {
            "@context": "https://schema.org",
            "@type": "ProgramMembership",
            "identifier": str(instance.uuid),
            "member": {
                "@type": "Person",
                "email": instance.user.email if instance.user else None,
                "givenName": instance.first_name,
                "familyName": instance.last_name,
            },
            "membershipPlan": {
                "@type": "Offer",
                "identifier": str(instance.price.uuid) if instance.price else None,
                "name": instance.price.name if instance.price else None,
            },
            "validUntil": instance.deadline.isoformat() if instance.deadline else None,
        }


class InitiativeSchemaSerializer(serializers.Serializer):
    """
    schema.org/Project output serializer for Crowds initiatives.
    """

    def to_representation(self, instance: Initiative) -> Dict[str, Any]:
        tags = list(instance.tags.values_list("name", flat=True))
        additional = [
            {"@type": "PropertyValue", "name": "voteEnabled", "value": bool(instance.vote)},
            {"@type": "PropertyValue", "name": "budgetContributif", "value": bool(instance.budget_contributif)},
            {"@type": "PropertyValue", "name": "directDebit", "value": bool(instance.direct_debit)},
        ]
        return {
            "@context": "https://schema.org",
            "@type": "Project",
            "identifier": str(instance.uuid),
            "name": instance.name,
            "description": instance.description,
            "disambiguatingDescription": instance.short_description,
            "dateCreated": instance.created_at.isoformat() if instance.created_at else None,
            "currency": instance.currency,
            "keywords": tags,
            "additionalProperty": additional,
        }


class InitiativeCreateSerializer(serializers.Serializer):
    """
    Input serializer for schema.org/Project creation.
    """
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    disambiguatingDescription = serializers.CharField(required=False, allow_blank=True)
    keywords = serializers.ListField(child=serializers.CharField(), required=False)
    currency = serializers.CharField(required=False, allow_blank=True)
    voteEnabled = serializers.BooleanField(required=False)
    budgetContributif = serializers.BooleanField(required=False)
    directDebit = serializers.BooleanField(required=False)

    def validate_name(self, value: str) -> str:
        return clean_html(value or "")

    def validate_description(self, value: str) -> str:
        return clean_html(value or "")

    def validate_disambiguatingDescription(self, value: str) -> str:
        return clean_html(value or "")

    def save(self, **kwargs) -> Initiative:
        data = self.validated_data
        initiative = Initiative.objects.create(
            name=data["name"],
            description=data.get("description") or "",
            short_description=data.get("disambiguatingDescription") or "",
            currency=data.get("currency") or "€",
            vote=bool(data.get("voteEnabled", False)),
            budget_contributif=bool(data.get("budgetContributif", False)),
            direct_debit=bool(data.get("directDebit", False)),
        )
        keywords = data.get("keywords") or []
        for tag_name in keywords:
            if not str(tag_name).strip():
                continue
            tag, _ = Tag.objects.get_or_create(name=str(tag_name).strip())
            initiative.tags.add(tag)
        return initiative


class BudgetItemSchemaSerializer(serializers.Serializer):
    """
    Output serializer for BudgetItem using schema.org MonetaryAmount-like structure.
    """

    def to_representation(self, instance: BudgetItem) -> Dict[str, Any]:
        amount = dround(instance.amount)
        return {
            "@type": "MonetaryAmount",
            "identifier": str(instance.uuid),
            "name": instance.description,
            "value": str(amount) if amount is not None else None,
            "currency": instance.initiative.currency,
            "actionStatus": instance.state,
            "dateCreated": instance.created_at.isoformat() if instance.created_at else None,
        }


class BudgetItemCreateSerializer(serializers.Serializer):
    description = serializers.CharField(min_length=1)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    actionStatus = serializers.ChoiceField(
        choices=[c[0] for c in BudgetItem.State.choices],
        required=False,
    )

    def validate_description(self, value: str) -> str:
        return clean_html(value or "")

    def validate_amount(self, value: Decimal) -> Decimal:
        self.amount = int(Decimal(value) * 100)
        return value


class ParticipationSchemaSerializer(serializers.Serializer):
    """
    Output serializer for Participation using schema.org Action-like fields.
    """

    def to_representation(self, instance: Participation) -> Dict[str, Any]:
        amount = dround(instance.amount) if instance.amount is not None else None
        payload = {
            "@type": "Action",
            "identifier": str(instance.uuid),
            "description": instance.description,
            "actionStatus": instance.state,
            "object": {
                "@type": "Project",
                "identifier": str(instance.initiative.uuid),
                "name": instance.initiative.name,
            },
            "agent": {
                "@type": "Person",
                "name": instance.participant.full_name_or_email_trunc(),
                "email": instance.participant.email,
            },
            "dateCreated": instance.created_at.isoformat() if instance.created_at else None,
        }
        if amount is not None:
            payload["amount"] = {
                "@type": "MonetaryAmount",
                "value": str(amount),
                "currency": instance.initiative.currency,
            }
        if instance.time_spent_minutes:
            payload["timeSpentMinutes"] = int(instance.time_spent_minutes)
        return payload


class ParticipationCreateSerializer(serializers.Serializer):
    description = serializers.CharField(min_length=1)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)

    def validate_description(self, value: str) -> str:
        return clean_html(value or "")

    def validate_amount(self, value: Decimal) -> Decimal:
        if value is not None:
            self.amount = int(Decimal(value) * 100)
        return value


class WalletRefillCreateSerializer(serializers.Serializer):
    """
    Entree pour recharger des tokens cadeau (TNF) sur la tirelire d'un user.
    / Input serializer for gift token wallet refill (API v2).

    LOCALISATION : api_v2/serializers.py

    Le montant est en unite brute (entier) : il est transmis tel quel a Fedow.
    / Amount is a raw integer unit, passed as-is to Fedow.
    """
    email = serializers.EmailField(required=True)
    asset = serializers.UUIDField(required=True)
    amount = serializers.IntegerField(required=True, min_value=1)


class MembershipStatusSerializer(serializers.Serializer):
    """
    Sortie minimale du statut d'adhesion pour LaBoutik.
    / Minimal membership status output for LaBoutik.
    """
    product_name = serializers.SerializerMethodField()
    price_name = serializers.SerializerMethodField()
    member_name = serializers.SerializerMethodField()
    is_valid = serializers.SerializerMethodField()
    deadline = serializers.DateTimeField()

    def get_product_name(self, obj):
        return obj.price.product.name if obj.price and obj.price.product else None

    def get_price_name(self, obj):
        return obj.price.name if obj.price else None

    def get_member_name(self, obj: Membership):
        return obj.member_name()

    def get_is_valid(self, obj):
        return obj.is_valid()


# ---------------------------------------------------------------------------
# App pages : Bloc <-> schema.org/WebPageElement
# / pages app: Bloc <-> schema.org/WebPageElement
# ---------------------------------------------------------------------------
from pages.models import Bloc, Page, valider_slug_non_reserve
from pages.blocs_catalogue import CHAMPS_BLOC_AUTORISES, CHAMPS_FICHIER, CHAMPS_IMAGE_URL

# Champs « standard » schema.org mappes a un champ modele (les autres passent
# par additionalProperty). / schema.org standard fields mapped to a model field.
MAPPING_STANDARD_VERS_CHAMP = {
    "headline": "titre",
    "alternativeHeadline": "sous_titre",
    "text": "texte",
}
# Champs modele dont la valeur est du texte riche a nettoyer (clean_html).
# / Model fields whose value is rich text to sanitize.
CHAMPS_TEXTE_RICHE = {"texte"}

# Champs lien neutralises contre les schemas dangereux (anti-XSS au clic).
# / Link fields neutralized against dangerous schemes (anti-XSS on click).
CHAMPS_URL_A_NEUTRALISER = ("bouton_url", "bouton2_url", "embed_url")


class BlocSchemaSerializer(serializers.Serializer):
    """Represente un Bloc en JSON-LD schema.org/WebPageElement (lecture seule).
    / Renders a Bloc as schema.org/WebPageElement JSON-LD (read-only)."""

    def to_representation(self, instance: "Bloc") -> Dict[str, Any]:
        # Image principale -> URL (vide si pas d'image). / Main image -> URL.
        image_url = None
        try:
            if instance.image:
                image_url = instance.image.url
        except Exception:
            image_url = None

        # GALERIE : on expose la liste d'images comme ImageObject[].
        # / GALLERY: expose the image list as ImageObject[].
        if instance.type_bloc == "GALERIE":
            image_sortie = [
                {"@type": "ImageObject", "contentUrl": ig.image.url,
                 "caption": ig.legende or None}
                for ig in instance.images_galerie.all().order_by("position")
                if ig.image
            ]
        else:
            image_sortie = image_url

        # additionalProperty : tous les champs du catalogue NON mappes en standard,
        # exposes sous {"@type":"PropertyValue","name":<champ>,"value":..}.
        # / additionalProperty: all catalogue fields not in the standard mapping.
        champs_standard = set(MAPPING_STANDARD_VERS_CHAMP.values()) | {"image"}
        props: List[Dict[str, Any]] = []
        for nom_champ in CHAMPS_BLOC_AUTORISES:
            if nom_champ in champs_standard:
                continue
            valeur = getattr(instance, nom_champ, None)
            # Les FileField/StdImage exposent .url ; on serialise en URL.
            # hasattr() ne convient pas : .url peut lever ValueError (pas AttributeError).
            # / FileField/StdImage expose .url; hasattr won't work — .url may raise ValueError.
            if isinstance(valeur, FieldFile):
                try:
                    valeur = valeur.url if valeur else None
                except Exception:
                    valeur = None
            if valeur in (None, "", [], {}):
                continue
            props.append({"@type": "PropertyValue", "name": nom_champ, "value": valeur})

        payload = {
            "@context": "https://schema.org",
            "@type": "WebPageElement",
            "identifier": str(instance.uuid),
            "additionalType": instance.type_bloc,
            "headline": instance.titre or None,
            "alternativeHeadline": instance.sous_titre or None,
            "text": instance.texte or None,
            "image": image_sortie or None,
            "position": instance.position,
            "additionalProperty": props or None,
        }
        return {k: v for k, v in payload.items() if v not in (None, "", [])}


class BlocCreateSerializer(serializers.Serializer):
    """Valide un WebPageElement entrant et cree un Bloc rattache a une Page.
    / Validates an incoming WebPageElement and creates a Bloc on a Page.

    Contexte requis : context={"page": <Page>}.
    """
    additionalType = serializers.CharField()  # type_bloc (pivot)
    headline = serializers.CharField(required=False, allow_blank=True)
    alternativeHeadline = serializers.CharField(required=False, allow_blank=True)
    text = serializers.CharField(required=False, allow_blank=True)
    # image accepte une URL (string) OU une liste d'ImageObject (GALERIE).
    # / image accepts a URL (string) OR a list of ImageObject (GALLERY).
    image = serializers.JSONField(required=False)
    position = serializers.IntegerField(required=False)
    additionalProperty = serializers.ListField(child=serializers.DictField(), required=False)

    def validate_additionalType(self, value: str) -> str:
        codes = {code for code, _ in Bloc.TYPE_BLOC_CHOICES}
        if value not in codes:
            raise serializers.ValidationError(
                _("Type de bloc inconnu : %(t)s") % {"t": value})
        return value

    def _pre_telecharger_images(self, validated_data: Dict[str, Any]) -> Dict[str, Any]:
        """Phase 1 (HORS transaction) : telecharge toutes les images distantes.
        / Phase 1 (OUTSIDE any transaction): download all remote images.

        Renvoie un dict de fichiers prets a persister. Leve ValidationError si une URL
        est invalide / dangereuse / interne (SSRF). AUCUNE ecriture DB ici.
        / Returns a dict of ready-to-persist files. Raises ValidationError on any
        invalid/dangerous/internal URL. NO DB write here.
        """
        type_bloc = validated_data["additionalType"]
        fichier_image = None
        fichiers_galerie = []          # liste de (ContentFile, legende, position)
        fichiers_additional = {}       # nom_champ -> ContentFile

        # Champs image passes en additionalProperty (image_secondaire, auteur_photo).
        # / Image fields passed via additionalProperty.
        for prop in (validated_data.get("additionalProperty") or []):
            nom = prop.get("name")
            valeur = prop.get("value")
            if (nom in CHAMPS_FICHIER and nom in CHAMPS_IMAGE_URL
                    and isinstance(valeur, str) and valeur):
                fichier = telecharger_et_valider_image(valeur)
                if fichier:
                    fichiers_additional[nom] = fichier

        # Champ image standard : URL string -> 1 image ; liste -> GALERIE.
        # / Standard image field: URL string -> 1 image; list -> GALLERY.
        valeur_image = validated_data.get("image")
        if isinstance(valeur_image, str) and valeur_image:
            fichier_image = telecharger_et_valider_image(valeur_image)
        elif isinstance(valeur_image, list) and type_bloc == "GALERIE":
            for index, img in enumerate(valeur_image):
                url = img.get("contentUrl") if isinstance(img, dict) else img
                fichier = telecharger_et_valider_image(url)
                if fichier:
                    legende = (img.get("caption") if isinstance(img, dict) else "") or ""
                    fichiers_galerie.append((fichier, legende, index))
        elif isinstance(valeur_image, list):
            # Une liste d'images n'est acceptee que pour le type GALERIE.
            # / A list of images is only accepted for the GALLERY type.
            raise serializers.ValidationError(
                {"image": _("Une liste d'images n'est acceptee que pour le bloc GALERIE.")})

        return {"image": fichier_image, "galerie": fichiers_galerie,
                "additional": fichiers_additional}

    def _persister(self, validated_data: Dict[str, Any], fichiers: Dict[str, Any],
                   page) -> "Bloc":
        """Phase 2 (DANS une transaction) : cree le bloc avec les fichiers deja
        telecharges. AUCUN I/O reseau ici. / Phase 2 (INSIDE a transaction): create the
        block with the already-downloaded files. NO network I/O here.
        """
        bloc = Bloc(page=page, type_bloc=validated_data["additionalType"])
        if "position" in validated_data:
            bloc.position = validated_data["position"]

        # Champs standard -> champs modele. / Standard fields -> model fields.
        for cle_std, nom_champ in MAPPING_STANDARD_VERS_CHAMP.items():
            if cle_std in validated_data:
                valeur = validated_data[cle_std]
                if nom_champ in CHAMPS_TEXTE_RICHE:
                    valeur = clean_html(valeur or "")
                setattr(bloc, nom_champ, valeur or "")

        # additionalProperty NON-fichier -> champs modele (whitelist stricte).
        # Les champs fichier sont geres via `fichiers` (pre-telecharges en phase 1).
        # / Non-file additionalProperty -> model fields; file fields come from `fichiers`.
        for prop in (validated_data.get("additionalProperty") or []):
            nom = prop.get("name")
            valeur = prop.get("value")
            if nom not in CHAMPS_BLOC_AUTORISES:
                continue
            if nom in ("points_gps", "contenu") and not isinstance(valeur, list):
                raise serializers.ValidationError(
                    {nom: _("Ce champ doit etre une liste.")})
            if nom in CHAMPS_FICHIER:
                continue  # gere en phase 1
            if nom in CHAMPS_TEXTE_RICHE:
                valeur = clean_html(valeur or "")
            setattr(bloc, nom, valeur)

        # Images fichier pre-telechargees (image_secondaire, auteur_photo).
        # / Pre-downloaded file images.
        for nom_champ, fichier in fichiers["additional"].items():
            setattr(bloc, nom_champ, fichier)

        # Securite : vide les champs lien a schema dangereux. / Empty dangerous-scheme links.
        for champ_url in CHAMPS_URL_A_NEUTRALISER:
            if url_a_schema_dangereux(getattr(bloc, champ_url, "")):
                setattr(bloc, champ_url, "")

        # Image standard pre-telechargee. / Pre-downloaded standard image.
        if fichiers["image"]:
            bloc.image = fichiers["image"]

        bloc.save()

        # Galerie pre-telechargee (FK : bloc deja persiste). / Pre-downloaded gallery.
        if fichiers["galerie"]:
            from pages.models import ImageGalerie
            for fichier, legende, position in fichiers["galerie"]:
                ImageGalerie.objects.create(
                    bloc=bloc, image=fichier, legende=legende, position=position)
        return bloc

    def create(self, validated_data: Dict[str, Any]) -> "Bloc":
        # Phase 1 : telechargements HORS transaction (I/O reseau).
        # Phase 2 : persistance en transaction courte (aucun reseau).
        # / Phase 1: downloads OUTSIDE any transaction. Phase 2: short DB transaction.
        page = self.context["page"]
        fichiers = self._pre_telecharger_images(validated_data)
        with transaction.atomic():
            bloc = self._persister(validated_data, fichiers, page)
        return bloc


# ---------------------------------------------------------------------------
# App pages : Page <-> schema.org/WebPage
# / pages app: Page <-> schema.org/WebPage
# ---------------------------------------------------------------------------
from django.core.exceptions import ValidationError as DjangoValidationError

# Champs meta de Page acceptes via additionalProperty (whitelist).
# / Page meta fields accepted via additionalProperty (whitelist).
CHAMPS_PAGE_AUTORISES = frozenset({
    "slug", "position", "publie", "est_accueil", "noindex",
    "meta_title", "meta_description",
})


def _resoudre_page(identifiant):
    """Trouve une Page par uuid OU slug. Renvoie None si introuvable/vide.
    / Finds a Page by uuid OR slug. Returns None if not found/empty."""
    import uuid as _uuid_mod
    if not identifiant:
        return None
    try:
        _uuid_mod.UUID(str(identifiant))
        page = Page.objects.filter(uuid=identifiant).first()
        if page:
            return page
    except (ValueError, TypeError):
        pass
    return Page.objects.filter(slug=identifiant).first()


class PageSchemaSerializer(serializers.Serializer):
    """Represente une Page en JSON-LD schema.org/WebPage (lecture seule).
    / Renders a Page as schema.org/WebPage JSON-LD (read-only)."""

    def to_representation(self, instance: "Page") -> Dict[str, Any]:
        blocs = [BlocSchemaSerializer(b).data
                 for b in instance.blocs.all().order_by("position")]
        props: List[Dict[str, Any]] = []
        for nom_champ in CHAMPS_PAGE_AUTORISES:
            if nom_champ == "meta_description":
                continue  # expose en `description`
            valeur = getattr(instance, nom_champ, None)
            if valeur in (None, "", [], {}):
                continue
            props.append({"@type": "PropertyValue", "name": nom_champ, "value": valeur})

        # Page parente (schema.org isPartOf). Null si page de premier niveau.
        # / Parent page (schema.org isPartOf). Null if top-level page.
        parent = getattr(instance, "parent", None)
        is_part_of = None
        if parent:
            is_part_of = {
                "@type": "WebPage",
                "identifier": str(parent.uuid),
                "url": f"/{parent.slug}/",
                "name": parent.titre,
            }

        payload = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "identifier": str(instance.uuid),
            "name": instance.titre,
            "url": f"/{instance.slug}/",
            "description": instance.meta_description or None,
            "isPartOf": is_part_of,
            "hasPart": blocs or None,
            "additionalProperty": props or None,
        }
        return {k: v for k, v in payload.items() if v not in (None, "", [])}


class PageCreateSerializer(serializers.Serializer):
    """Cree une Page et (option) ses blocs imbriques via hasPart.
    / Creates a Page and (optionally) its nested blocks via hasPart."""
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    # isPartOf : uuid ou slug de la page parente (schema.org). Vide = pas de parent.
    # / isPartOf: uuid or slug of the parent page (schema.org). Empty = no parent.
    isPartOf = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    additionalProperty = serializers.ListField(child=serializers.DictField(), required=False)
    hasPart = serializers.ListField(child=serializers.DictField(), required=False)

    def _meta_depuis_props(self, validated_data: Dict[str, Any]) -> Dict[str, Any]:
        # Deballe additionalProperty -> dict de champs meta autorises.
        # / Unpack additionalProperty -> dict of allowed meta fields.
        meta: Dict[str, Any] = {}
        for prop in (validated_data.get("additionalProperty") or []):
            nom = prop.get("name")
            if nom in CHAMPS_PAGE_AUTORISES:
                meta[nom] = prop.get("value")
        return meta

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        meta = self._meta_depuis_props(attrs)
        slug = meta.get("slug")
        # Slug obligatoire (sinon collision/SlugField unique) + anti-reserve.
        # / Slug required + reserved check.
        if not slug:
            raise serializers.ValidationError({"slug": _("Le slug est obligatoire.")})
        try:
            valider_slug_non_reserve(slug)
        except DjangoValidationError as e:
            raise serializers.ValidationError({"slug": e.messages})
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> "Page":
        # --- Phase 1 : validation + PRE-TELECHARGEMENT de tous les blocs (HORS transaction) ---
        # / Phase 1: validate + pre-download every block's images (OUTSIDE any transaction).
        meta = self._meta_depuis_props(validated_data)
        blocs_prepares = []  # liste de (bloc_ser, fichiers)
        for index, donnees_bloc in enumerate(validated_data.get("hasPart") or []):
            donnees_bloc.setdefault("position", index)
            bloc_ser = BlocCreateSerializer(data=donnees_bloc, context={"page": None})
            bloc_ser.is_valid(raise_exception=True)
            fichiers = bloc_ser._pre_telecharger_images(bloc_ser.validated_data)
            blocs_prepares.append((bloc_ser, fichiers))

        # --- Phase 2 : transaction courte, AUCUN I/O reseau ---
        # / Phase 2: short transaction, NO network I/O.
        with transaction.atomic():
            page = Page(titre=validated_data["name"])
            if validated_data.get("description"):
                page.meta_description = validated_data["description"]
            for nom_champ, valeur in meta.items():
                setattr(page, nom_champ, valeur)

            # Page parente (schema.org isPartOf) : uuid ou slug d'une autre page.
            # La validation de hierarchie (un seul niveau) est faite par page.full_clean() -> clean().
            # / Parent page (isPartOf): uuid or slug of another page. Hierarchy validation
            # (one level only) is enforced by page.full_clean() -> clean().
            identifiant_parent = validated_data.get("isPartOf")
            if identifiant_parent:
                parent = _resoudre_page(identifiant_parent)
                if not parent:
                    raise serializers.ValidationError(
                        {"isPartOf": _("Page parente introuvable : %(id)s") % {"id": identifiant_parent}})
                page.parent = parent

            try:
                page.full_clean(exclude=["uuid"])  # valide slug unique + reserves + hierarchie
            except DjangoValidationError as e:
                raise serializers.ValidationError(e.message_dict)
            page.save()
            for bloc_ser, fichiers in blocs_prepares:
                bloc_ser._persister(bloc_ser.validated_data, fichiers, page)
        return page
