from typing import Any, Dict, List, Optional
import random
import string

from rest_framework import serializers
from django.utils.text import slugify

from BaseBillet.models import Event, PostalAddress, Tag, OptionGenerale

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
        event = Event.objects.create(
            name=name,
            slug=slug_value,
            datetime=start,
            end_datetime=end,
            full_url=full_url,
            is_external=is_external,
            jauge_max=max_cap if max_cap is not None else Event.jauge_max.field.default,
            short_description=short_desc,
            long_description=long_desc,
            published=published,
            private=private,
            max_per_user=max_per_user if max_per_user is not None else Event.max_per_user.field.default,
            refund_deadline=refund_days if refund_days is not None else Event.refund_deadline.field.default,
            categorie=cat_code,
            parent=parent_obj,
        )

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
                    event.options_radio.add(opt)
                except OptionGenerale.DoesNotExist:
                    continue

        checkbox_names = _extract_values("optionsCheckbox")
        if checkbox_names:
            for opt_name in checkbox_names:
                try:
                    opt = OptionGenerale.objects.get(name=opt_name)
                    event.options_checkbox.add(opt)
                except OptionGenerale.DoesNotExist:
                    continue

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
