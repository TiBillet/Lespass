import os

import stripe
from django.db import connection
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import tenant_context, schema_context
from rest_framework import serializers

from ApiBillet.serializers import get_or_create_price_sold
from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Price, Product, OptionGenerale, Membership, Paiement_stripe, LigneArticle
from Customers.models import Client, Domain
from MetaBillet.models import WaitingConfiguration
from PaiementStripe.views import CreationPaiementStripe
from root_billet.models import RootConfiguration


class LinkQrCodeValidator(serializers.Serializer):
    email = serializers.EmailField(required=True, allow_null=False)
    firstname = serializers.CharField(max_length=500, required=False, allow_blank=True)
    lastname = serializers.CharField(max_length=500, required=False, allow_blank=True)
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

    def validate_email(self, email):
        self.user = get_or_create_user(email)
        return email

    def validate_price(self, price):
        self.price = price
        return price


    def checkout_stripe(self):
        # Fiche membre créée, si price payant, on crée le checkout stripe :
        membership: Membership = self.membership
        price: Price = membership.price
        user: TibilletUser = membership.user
        tenant = connection.tenant

        metadata = {
            'tenant': f'{tenant.uuid}',
            'price': f"{price.pk}",
            'membership': f"{membership.pk}",
            'user': f"{user.pk}",
        }
        ligne_article_adhesion = LigneArticle.objects.create(
            pricesold=get_or_create_price_sold(price),
            membership=membership,
            amount=int(price.prix*100),
            qty=1,
        )

        # Création de l'objet paiement stripe en base de donnée
        new_paiement_stripe = CreationPaiementStripe(
            user=user,
            liste_ligne_article=[ligne_article_adhesion, ],
            metadata=metadata,
            reservation=None,
            source=Paiement_stripe.FRONT_BILLETTERIE,
            success_url=f"stripe_return/",
            cancel_url=f"stripe_return/",
            absolute_domain=f"https://{tenant.get_primary_domain()}/memberships/",
        )

        # Passage du status en UNPAID
        if not new_paiement_stripe.is_valid():
            raise serializers.ValidationError(new_paiement_stripe.errors)

        paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
        paiement_stripe.lignearticles.all().update(status=LigneArticle.UNPAID)

        # On ajoute le paiement dans l'objet membership
        membership.stripe_paiement.add(paiement_stripe)

        # Retour de l'url vers qui rediriger
        checkout_stripe_url = new_paiement_stripe.checkout_session.url
        return checkout_stripe_url

    def validate(self, attrs):
        ### CREATION DE LA FICHE MEMBRE
        # Il peut y avoir plusieurs adhésions pour le même user (ex : parent/enfant)
        membership = Membership.objects.create(
            user=self.user,
            price=self.price
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
        # Création du lien de paiement
        self.checkout_stripe_url = self.checkout_stripe()

        return attrs


class TenantCreateValidator(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=200)
    laboutik = serializers.BooleanField(required=True)
    cgu = serializers.BooleanField(required=True)
    dns_choice = serializers.ChoiceField(choices=["tibillet.coop", "tibillet.re"])

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
    def create_tenant(waiting_config: WaitingConfiguration):
        name = waiting_config.organisation
        admin_email = waiting_config.email.lower()

        with schema_context('public'):
            slug = slugify(name)
            domain = os.getenv("DOMAIN")
            tenant, created = Client.objects.get_or_create(
                schema_name=slug,
                name=name,
                on_trial=False,
                categorie=Client.SALLE_SPECTACLE,
            )
            Domain.objects.create(
                domain=f'{slug}.{waiting_config.dns_choice}',
                tenant=tenant,
                is_primary=True
            )

        with tenant_context(tenant):
            ## Création du premier admin:
            from django.contrib.auth.models import Group
            staff_group, created = Group.objects.get_or_create(name="staff")

            # Sans envoie d'email pour l'instant, on l'envoie quand tout sera bien terminé
            user: TibilletUser = get_or_create_user(admin_email, send_mail=False)
            user.client_admin.add(tenant)
            user.is_staff = True
            user.groups.add(staff_group)
            user.save()

            from BaseBillet.models import Configuration
            config = Configuration.get_solo()
            config.organisation = name
            config.slug = slugify(name)
            config.email = user.email

            rootConf = RootConfiguration.get_solo()
            config.stripe_mode_test = rootConf.stripe_mode_test

            if waiting_config.id_acc_connect:
                info_stripe = stripe.Account.retrieve(waiting_config.id_acc_connect)
                config.site_web = info_stripe.business_profile.url
                config.phone = info_stripe.business_profile.support_phone
                if rootConf.stripe_mode_test:
                    config.stripe_connect_account_test = info_stripe.id
                else:
                    config.stripe_connect_account = info_stripe.id

            config.save()

            # Liaison / création du lieu coté Fedow :
            from fedow_connect.fedow_api import FedowAPI
            from fedow_connect.models import FedowConfig
            FedowAPI()
            if not FedowConfig.get_solo().can_fedow():
                raise Exception('Erreur on install : can_fedow = False')

            # Envoie du mail de connection et validation
            get_or_create_user(admin_email, force_mail=True)

        return tenant
