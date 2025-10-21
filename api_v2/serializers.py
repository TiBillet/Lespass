from typing import Any, Dict

from rest_framework import serializers

from BaseBillet.models import Event, PostalAddress


class PostalAddressAsSchemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostalAddress
        fields = (
            "street_address",
            "address_locality",
            "address_region",
            "postal_code",
            "address_country",
            "latitude",
            "longitude",
        )

    def to_representation(self, instance: PostalAddress) -> Dict[str, Any]:
        data = super().to_representation(instance)
        # Map to schema.org/PostalAddress
        result: Dict[str, Any] = {
            "@type": "PostalAddress",
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
        return result


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

    def to_representation(self, instance: Event) -> Dict[str, Any]:
        data = super().to_representation(instance)

        # Choose the best description
        description = data.get("long_description") or data.get("short_description")

        # Build schema.org JSON-LD for Event
        payload: Dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Event",
            "identifier": str(data.get("uuid")) if data.get("uuid") else None,
            "name": data.get("name"),
            "description": description,
            "startDate": data.get("datetime"),
            "endDate": data.get("end_datetime"),
            # location may be a Place with address
            "location": None,
            "url": data.get("full_url"),
        }

        # Map location if available
        address = data.get("postal_address")
        if address:
            payload["location"] = {
                "@type": "Place",
                "address": address,
                # optional name of place if stored in address.name
            }

        # Remove nulls for cleanliness
        clean_payload = {k: v for k, v in payload.items() if v not in (None, "", [])}
        return clean_payload
