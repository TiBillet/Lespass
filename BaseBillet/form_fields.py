"""
Helpers de validation pour les form fields personnalisés.
/ Validation helpers for custom form fields.

LOCALISATION: BaseBillet/form_fields.py

Pour le widget carte adresse : `AdresseGeolocaliseeField` extrait et
valide les coordonnées (latitude/longitude) + l'adresse formatée
depuis un `request.POST` ou `request.data`. Les noms de champs sont
préfixés par l'`identifiant_widget` du widget (ex: `place_latitude`).

Pas un `forms.Field` Django : le projet utilise des DRF Serializers
(cf. djc skill). C'est un helper statique consommé par les serializers.

/ For the address map widget: `AdresseGeolocaliseeField` extracts and
validates lat/lng + formatted address from `request.POST` or
`request.data`. Field names are prefixed by the widget's
`identifiant_widget` (e.g. `place_latitude`). Not a Django `forms.Field`
because the project uses DRF Serializers — this is a static helper
consumed by the serializers.
"""

from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError


class AdresseGeolocaliseeField:
    """
    Helper statique. Pas d'instance — uniquement la méthode `extraire_depuis`.
    """

    LATITUDE_MIN = -90
    LATITUDE_MAX = 90
    LONGITUDE_MIN = -180
    LONGITUDE_MAX = 180

    @staticmethod
    def extraire_depuis(post_data, identifiant_widget, obligatoire=False):
        """
        Lit les 3 champs `<identifiant>_latitude/longitude/adresse` dans
        `post_data` (dict-like : `request.POST`, `request.data`, dict).

        Renvoie :
          - dict `{"latitude": float, "longitude": float, "adresse": str}` si OK.
          - `None` si tous les champs sont absents/vides ET `obligatoire=False`.
          - Lève `ValidationError` si :
              * `obligatoire=True` ET coords absentes/vides ;
              * coords présentes mais hors range WGS84 ;
              * coords présentes mais non castables en float.

        :param post_data: request.POST / request.data / dict.
        :param identifiant_widget: str — préfixe des champs (ex: "place").
        :param obligatoire: bool — True force la présence des coords.

        / Reads the 3 fields `<id>_latitude/longitude/adresse` from
        `post_data`. Returns a validated dict, or None if all empty and
        not required, or raises ValidationError on invalid coords.
        """
        cle_latitude = f"{identifiant_widget}_latitude"
        cle_longitude = f"{identifiant_widget}_longitude"
        cle_adresse = f"{identifiant_widget}_adresse"

        valeur_latitude = post_data.get(cle_latitude, "")
        valeur_longitude = post_data.get(cle_longitude, "")
        valeur_adresse = post_data.get(cle_adresse, "")

        # Strip uniquement si c'est une string (request.POST = QueryDict
        # de strings, request.data peut contenir des floats deja castes).
        # / Strip only on strings (request.POST = QueryDict of strings,
        # request.data may already contain casted floats).
        if isinstance(valeur_latitude, str):
            valeur_latitude = valeur_latitude.strip()
        if isinstance(valeur_longitude, str):
            valeur_longitude = valeur_longitude.strip()

        coords_absentes = (not valeur_latitude) and (not valeur_longitude)

        if coords_absentes:
            if obligatoire:
                raise ValidationError(_(
                    "Veuillez sélectionner une adresse sur la carte."
                ))
            return None

        # Cast en float — raise ValidationError si non castable.
        # / Cast to float — raise ValidationError if not castable.
        try:
            latitude = float(valeur_latitude)
            longitude = float(valeur_longitude)
        except (TypeError, ValueError):
            raise ValidationError(_("Coordonnées invalides (format)."))

        if not (AdresseGeolocaliseeField.LATITUDE_MIN
                <= latitude
                <= AdresseGeolocaliseeField.LATITUDE_MAX):
            raise ValidationError(_("Latitude hors range WGS84 (-90 à 90)."))

        if not (AdresseGeolocaliseeField.LONGITUDE_MIN
                <= longitude
                <= AdresseGeolocaliseeField.LONGITUDE_MAX):
            raise ValidationError(_("Longitude hors range WGS84 (-180 à 180)."))

        return {
            "latitude": latitude,
            "longitude": longitude,
            "adresse": valeur_adresse or "",
        }
