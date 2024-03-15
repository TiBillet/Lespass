from django.db import connection
from rest_framework import serializers

from ApiBillet.serializers import NewAdhesionValidator, get_or_create_price_sold
from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Price, Product, OptionGenerale, Membership, LigneArticle, Paiement_stripe
from PaiementStripe.views import CreationPaiementStripe


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


    def validate(self, attrs):
        email: str = attrs['email']
        price: Price = attrs['price']
        user: TibilletUser = get_or_create_user(email)

        # Vérification que l'user ne soit pas déja adhérant :
        if any([m.is_valid() for m in Membership.objects.filter(price__product=price.product, user=user)]):
            raise serializers.ValidationError('Vous avez déjà une adhésion ou un abonnement valide')

        ### CREATION DE LA FICHE MEMBRE

        membership, created = Membership.objects.get_or_create(
            user=user,
            price=price
        )

        membership.first_name = attrs['first_name']
        membership.last_name = attrs['last_name']
        membership.newsletter = attrs['newsletter']

        # Set remplace les options existantes, accepte les listes
        if 'options_checkbox' in attrs:
            membership.option_generale.set(attrs['options_checkbox'])
        # Add ajoute sans toucher aux précédentes
        if 'option_radio' in attrs:
            membership.option_generale.add(attrs['option_radio'])

        membership.save()
        self.membership = membership

        return attrs
