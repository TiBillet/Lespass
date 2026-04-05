from django import forms
from decimal import Decimal
from .models import TireuseBec


class SeuilClField(forms.DecimalField):
    """Champ seuil saisi en cl par l'admin, stocké en ml en base."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label", "Seuil mini (cl)")
        kwargs.setdefault("min_value", Decimal("0"))
        super().__init__(*args, **kwargs)

    def prepare_value(self, value):
        # Convertit ml → cl pour l'affichage dans le formulaire
        if value is not None and value != "":
            try:
                return (Decimal(str(value)) / 10).quantize(Decimal("1"))
            except Exception:
                pass
        return value

    def to_python(self, value):
        # Convertit cl → ml avant de sauvegarder
        cl = super().to_python(value)
        if cl is None:
            return Decimal("0.00")
        return (cl * 10).quantize(Decimal("0.01"))


class TireuseBecForm(forms.ModelForm):
    seuil_mini_ml = SeuilClField(required=False)

    class Meta:
        model = TireuseBec
        fields = [
            "nom_tireuse", "monnaie",
            "prix_litre_override",
            "seuil_mini_ml", "appliquer_reserve",
            "enabled", "notes",
        ]
