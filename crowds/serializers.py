from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from Administration.utils import clean_html


class BudgetItemProposalSerializer(serializers.Serializer):
    description = serializers.CharField(min_length=5, allow_blank=False, trim_whitespace=True)
    amount_eur = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_description(self, value: str) -> str:
        # Sanitize HTML to avoid script injections; allow basic formatting only
        return clean_html(value or "")

    def validate_amount_eur(self, value: Decimal) -> Decimal:
        try:
            if value is None or value <= Decimal("0"):
                raise serializers.ValidationError("Montant invalide")
        except InvalidOperation:
            raise serializers.ValidationError("Montant invalide")
        return value


class ContributionCreateSerializer(serializers.Serializer):
    contributor_name = serializers.CharField(allow_blank=False, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    amount = serializers.IntegerField(min_value=1)

    def validate_contributor_name(self, value: str) -> str:
        # Sanitize any HTML that could be injected (even if usually plain text)
        return clean_html(value or "")

    def validate_description(self, value: str) -> str:
        return clean_html(value or "")


class ParticipationCreateSerializer(serializers.Serializer):
    description = serializers.CharField(min_length=5, allow_blank=False, trim_whitespace=True)
    # Optionnel: peut être vide en cas de bénévolat
    requested_amount_cents = serializers.IntegerField(min_value=1, required=False, allow_null=True)

    def validate_description(self, value: str) -> str:
        return clean_html(value or "")


class ParticipationCompleteSerializer(serializers.Serializer):
    time_spent_minutes = serializers.IntegerField(min_value=1)
