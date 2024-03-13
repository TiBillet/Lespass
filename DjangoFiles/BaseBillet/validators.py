from rest_framework import serializers

from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Price, Product, OptionGenerale, Membership


class LoginEmailValidator(serializers.Serializer):
    email = serializers.EmailField()


class MembershipValidator(serializers.Serializer):
    acknowledge = serializers.BooleanField()
    price = serializers.PrimaryKeyRelatedField(
        queryset=Price.objects.filter(product__categorie_article=Product.ADHESION)
    )

    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=200)
    last_name = serializers.CharField(max_length=200)

    options_checkbox = serializers.PrimaryKeyRelatedField(queryset=OptionGenerale.objects.all(), many=True,
                                                          allow_null=True, required=False)

    option_radio = serializers.PrimaryKeyRelatedField(queryset=OptionGenerale.objects.all(),
                                                      allow_null=True, required=False)

    newsletter = serializers.BooleanField()

    def validate_email(self, value):
        user: TibilletUser = get_or_create_user(value)
        self.user = user

        self.fiche_membre, created = Membership.objects.get_or_create(
            user=user,
            price=self.price,
        )
