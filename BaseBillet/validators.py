import os

from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import tenant_context, schema_context
from rest_framework import serializers

from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Price, Product, OptionGenerale, Membership
from Customers.models import Client, Domain


class LinkQrCodeValidator(serializers.Serializer):
    email = serializers.EmailField(required=True, allow_null=False)
    # data=request.POST.dict() in the controler for boolean
    cgu = serializers.BooleanField(required=True, allow_null=False)
    qrcode_uuid = serializers.UUIDField()


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

        # Sur le form, on coche pour NE PAS recevoir la news
        membership.newsletter = not attrs['newsletter']

        # Set remplace les options existantes, accepte les listes
        if 'options_checkbox' in attrs:
            membership.option_generale.set(attrs['options_checkbox'])
        # Add ajoute sans toucher aux précédentes
        if 'option_radio' in attrs:
            membership.option_generale.add(attrs['option_radio'])

        membership.save()
        self.membership = membership

        return attrs


class TenantCreateValidator(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=200)
    laboutik = serializers.BooleanField(required=True)
    cgu = serializers.BooleanField(required=True)

    def validate_cgu(self, value):
        if not value:
            raise serializers.ValidationError(_('Please accept terms and conditions.'))
        return value

    def validate_name(self, value):
        try:
            Client.objects.get(schema_name=slugify(value))
            raise serializers.ValidationError(_('Tenant name exist'))
        except Client.DoesNotExist:
            return value

    @staticmethod
    def create_tenant(validated_data):
        name = validated_data['name']
        admin_email = validated_data['email']

        with schema_context('public'):
            tenant, created = Client.objects.get_or_create(
                schema_name=slugify(name),
                name=slugify(name),
                on_trial=False,
                categorie=Client.SALLE_SPECTACLE,
            )
            Domain.objects.create(
                domain=f'{slugify(name)}.{os.getenv("DOMAIN")}',
                tenant=tenant,
                is_primary=True
            )

        with tenant_context(tenant):
            ## Création du premier admin:
            from django.contrib.auth.models import Group
            staff_group, created = Group.objects.get_or_create(name="staff")

            user: TibilletUser = get_or_create_user(admin_email)
            user.client_admin.add(tenant)
            user.is_staff = True
            user.groups.add(staff_group)
            user.save()

            from BaseBillet.models import Configuration
            config = Configuration.get_solo()
            config.organisation = name.capitalize()
            config.save()

            # Liaison / création du lieu coté Fedow :
            from fedow_connect.fedow_api import FedowAPI
            from fedow_connect.models import FedowConfig
            FedowAPI()
            if not FedowConfig.get_solo().can_fedow():
                raise Exception('Erreur on install : can_fedow = False')

        return tenant