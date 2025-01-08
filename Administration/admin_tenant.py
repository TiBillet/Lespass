import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.forms import ModelForm, TextInput, Form
from django.http import HttpResponse, HttpRequest
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from rest_framework_api_key.models import APIKey
from solo.admin import SingletonModelAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display, action
from unfold.sites import UnfoldAdminSite
from unfold.widgets import UnfoldAdminTextInputWidget, UnfoldAdminEmailInputWidget, UnfoldAdminSelectWidget

from ApiBillet.permissions import TenantAdminPermissionWithRequest
from AuthBillet.models import HumanUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Configuration, OptionGenerale, Product, Price, Paiement_stripe, Membership, Webhook, Tag, \
    LigneArticle, PaymentMethod, Reservation, ExternalApiKey, GhostConfig
from BaseBillet.tasks import create_membership_invoice_pdf, send_membership_invoice_to_email, webhook_reservation, \
    webhook_membership
from Customers.models import Client
from fedow_connect.utils import dround

logger = logging.getLogger(__name__)


class StaffAdminSite(UnfoldAdminSite):
    pass


staff_admin_site = StaffAdminSite(name='staff_admin')

""" Configuration UNFOLD """





@admin.register(ExternalApiKey, site=staff_admin_site)
class ExternalApiKeyAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    list_display = [
        'name',
        'user',
        'created',
        'event',
        'product',
        'reservation',
        'ticket',
        'wallet',
    ]

    fields = [
        'name',
        'ip',
        'created',
        # Les boutons de permissions :
        ('event', 'product',),
        ('reservation', 'ticket'),
        ('wallet', ),
        'user',
        'key',
    ]

    readonly_fields = [
        'created',
        'user',
        'key',
    ]

    def save_model(self, request: HttpRequest, obj: ExternalApiKey, form: Form, change: Any) -> None:
        if not obj.pk and not obj.key and obj.name:

            # On affiche la string Key sur l'admin de django en message
            # et django.message capitalize chaque message...
            # du coup on fait bien gaffe à ce que je la clée générée ai bien une majusculle au début ...
            api_key, key = APIKey.objects.create_key(name=obj.name)
            while key[0].isupper() == False:
                api_key, key = APIKey.objects.create_key(name=obj.name)
                if key[0].isupper() == False:
                    api_key.delete()

            messages.add_message(
                request,
                messages.SUCCESS,
                _(f"Copiez bien la clé suivante et mettez la en lieu sur ! Elle n'est pas enregistrée sur nos serveurs et ne sera affichée qu'une seule fois ici :")
            )
            messages.add_message(
                request,
                messages.WARNING,
                f"{key}"
            )
            obj.key = api_key
            obj.user = request.user
        super().save_model(request, obj, form, change)


@admin.register(Webhook, site=staff_admin_site)
class WebhookAdmin(ModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True

    readonly_fields = ['last_response', ]
    fields = [
        "url",
        "event",
        "active",
        "last_response",
    ]

    list_display = [
        "url",
        "event",
        "active",
        "last_response",
    ]

    actions_detail = ["test_webhook"]

    @action(
        description=_("Test"),
        url_path="test_webhook",
        permissions=["custom_actions_detail"],
    )
    def test_webhook(self, request, object_id):
        # Lancement d'un test de webhook :
        webhook = Webhook.objects.get(pk=object_id)
        try:
            if webhook.event == Webhook.MEMBERSHIP:
                # On va chercher le membership le plus récent
                membership = Membership.objects.filter(contribution_value__isnull=False).first()
                webhook_membership(membership.pk, solo_webhook_pk=object_id)
                webhook.refresh_from_db()
            elif webhook.event == Webhook.RESERVATION_V:
                # On va chercher le membership le plus récent
                reservation = Reservation.objects.filter(status=Reservation.VALID).first()
                webhook_reservation(reservation.pk, solo_webhook_pk=object_id)
                webhook.refresh_from_db()

            messages.info(
                request,
                _(f"{webhook.last_response}"),
            )
            return redirect(request.META["HTTP_REFERER"])

        except Exception as e:
            messages.error(
                request,
                _(f"{e}"),
            )

    def has_custom_actions_detail_permission(self, request, object_id):
        return True


########################################################################
@admin.register(Configuration, site=staff_admin_site)
class ConfigurationAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    fieldsets = (
        (None, {
            'fields': (
                'organisation',
                'short_description',
                'long_description',
                'img',
                'logo',
                'adress',
                'phone',
                'email',
                'site_web',
                'fuseau_horaire',
                # 'map_img',
            )
        }),
        ('Stripe', {
            'fields': (
                # 'vat_taxe',
                'onboard_stripe',
                # 'stripe_mode_test',
            ),
        }),
        ('Fédération', {
            'fields': (
                'federated_with',
            ),
        }),
        # ('Options générales', {
        #     'fields': (
        #         'need_name',
        #         'jauge_max',
        #         'option_generale_radio',
        #         'option_generale_checkbox',
        #     ),
        # }),
    )
    readonly_fields = ['onboard_stripe', ]
    autocomplete_fields = ['federated_with', ]

    def save_model(self, request, obj, form, change):
        obj: Configuration
        if obj.server_cashless and obj.key_cashless:
            if obj.check_serveur_cashless():
                messages.add_message(request, messages.INFO, f"Cashless server ONLINE")
            else:
                messages.add_message(request, messages.ERROR, "Cashless server OFFLINE or BAD KEY")

        super().save_model(request, obj, form, change)


class TagForm(ModelForm):
    class Meta:
        model = Tag
        fields = '__all__'
        widgets = {
            'color': TextInput(attrs={'type': 'color'}),
        }


@admin.register(Tag, site=staff_admin_site)
class TagAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    form = TagForm
    fields = ("name", "color")
    list_display = [
        "name",
        "_color",
    ]
    readonly_fields = ['uuid', ]

    def _color(self, obj):
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; border: 1px solid #000;"></div>',
            obj.color, )

    _color.short_description = _("Couleur")

    # def has_view_or_change_permission(self, request, obj=None):
    #     return True
    #
    # def has_delete_permission(self, request, obj=None):
    # return False
    #
    # def has_add_permission(self, request):
    #     return False


@admin.register(OptionGenerale, site=staff_admin_site)
class OptionGeneraleAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    search_fields = ('name',)
    list_display = (
        'name',
        'poids',
    )


class ProductAdminCustomForm(ModelForm):
    class Meta:
        model = Product
        fields = (
            'name',
            'categorie_article',
            'nominative',
            'short_description',
            'long_description',
            'img',
            'poids',
            "option_generale_radio",
            "option_generale_checkbox",
            "legal_link",
            'publish',
            'archive',
        )

    def clean(self):
        cleaned_data = self.cleaned_data
        categorie = cleaned_data.get('categorie_article')
        if categorie == Product.NONE:
            raise forms.ValidationError(_("Merci de renseigner une catégorie pour cet article."))
        return cleaned_data


class PriceInline(TabularInline):
    model = Price
    fk_name = 'product'
    # hide_title = True
    fields = (
        'name',
        'product',
        'prix',
        # 'adhesion_obligatoire',
        'subscription_type',
        'recurring_payment',
        'publish',
    )

    # ordering_field = "weight"
    # max_num = 1
    extra = 0
    show_change_link = True
    tab = True


@admin.register(Product, site=staff_admin_site)
class ProductAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    inlines = [PriceInline, ]

    form = ProductAdminCustomForm
    list_display = (
        'name',
        'img',
        'poids',
        'categorie_article',
        'publish',
    )
    ordering = ("poids",)
    autocomplete_fields = [
        "option_generale_radio", "option_generale_checkbox",
    ]

    def get_queryset(self, request):
        # On retire les recharges cashless et l'article Don
        # Pas besoin de les afficher, ils se créent automatiquement.
        qs = super().get_queryset(request)
        return qs.exclude(categorie_article__in=[Product.RECHARGE_CASHLESS, Product.DON]).exclude(archive=True)


@admin.register(Price, site=staff_admin_site)
class PriceAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    fields = (
        'name',
        'product',
        'prix',
        'subscription_type',
        'recurring_payment',
        'publish',
        'adhesion_obligatoire',
    )

    # def has_view_or_change_permission(self, request, obj=None):
    #     return True
    #
    # def has_add_permission(self, request):
    #     return True

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Paiement_stripe, site=staff_admin_site)
class PaiementStripeAdmin(ModelAdmin):
    compressed_fields = True  # Default: False

    list_display = (
        'uuid_8',
        'user',
        'total',
        'order_date',
        'status',
        # 'traitement_en_cours',
        # 'source_traitement',
        'source',
        'articles',
    )
    readonly_fields = list_display
    ordering = ('-order_date',)

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True


"""
USER
"""


class MembershipInline(TabularInline):
    model = Membership
    # form = MembershipInlineForm
    extra = 0
    # show_change_link = True
    can_delete = False
    tab = True

    fields = (
        'first_name',
        'last_name',
        'last_contribution',
        'price',
        'contribution_value',
        'deadline',
        'is_valid',
    )
    readonly_fields = fields

    def has_change_permission(self, request, obj=None):
        return False  # On interdit la modification

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False  # Autoriser l'ajout

    # def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
    #     if db_field.name == "price":  # Filtre sur le champ ForeignKey "prix"
    #         # Appliquez un filtre sur les objets accessibles via la ForeignKey
    #         kwargs["queryset"] = Price.objects.filter(product__categorie_article=Product.ADHESION,
    #                                                   publish=True)  # Exemple de filtre
    #     return super().formfield_for_foreignkey(db_field, request, **kwargs)
    #
    # # pour retirer les petits boutons add/edit a coté de la foreign key
    # def get_formset(self, request, obj=None, **kwargs):
    #     formset = super().get_formset(request, obj, **kwargs)
    #     price = formset.form.base_fields['price']
    #
    #     price.widget.can_add_related = False
    #     price.widget.can_delete_related = False
    #     price.widget.can_change_related = False
    #     price.widget.can_view_related = False
    #
    #     return formset


class MembershipValid(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _("Adhésion valide")

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "membership_valid"

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return [
            ("Y", _("Oui")),
            ("N", _("Non")),
            ("B", _("Expire bientôt (2 semaines)")),
            ("O", _("Aucune adhésion prise")),

        ]

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value (either '80s' or '90s')
        # to decide how to filter the queryset.
        if self.value() == "Y":
            return queryset.filter(
                membership__deadline__gte=timezone.localtime(),
            ).distinct()
        if self.value() == "N":
            return queryset.filter(
                membership__deadline__lte=timezone.localtime(),
            ).distinct()
        if self.value() == "B":
            return queryset.filter(
                membership__deadline__lte=timezone.localtime() + timedelta(weeks=2),
                membership__deadline__gte=timezone.localtime(),
            ).distinct()
        if self.value() == 'O':
            return queryset.filter(membership__isnull=True).distinct()


# Tout les utilisateurs de type HUMAIN
@admin.register(HumanUser, site=staff_admin_site)
class HumanUserAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False
    inlines = [MembershipInline, ]

    list_display = [
        'email',
        'first_name',
        'last_name',
        'display_memberships_valid',
    ]

    search_fields = [
        'email',
        'first_name',
        'last_name',
    ]

    fieldsets = [
        ('Général', {
            'fields': [
                'email',
                'first_name',
                'last_name',
            ],
        }),
    ]

    list_filter = [
        "is_active",
        "email_error",
        MembershipValid,
        # "is_hidden",
        # ("salary", RangeNumericFilter),
        # ("status", ChoicesDropdownFilter),
        # ("created_at", RangeDateTimeFilter),
    ]

    # noinspection PyTypeChecker
    @display(description=_("Adhésions"), label={None: "danger", True: "success"})
    def display_memberships_valid(self, instance: HumanUser):
        count = instance.memberships_valid()
        if count > 0:
            return True, f"Valide : {count}"
        return None, _("Aucune")

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True


### ADHESION

class NewMembershipForm(ModelForm):
    # Un formulaire d'email qui va générer les action get_or_create_user
    email = forms.EmailField(
        required=True,
        widget=UnfoldAdminEmailInputWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label="Email",
    )

    # Uniquement les tarif Adhésion
    price = forms.ModelChoiceField(
        queryset=Price.objects.filter(product__categorie_article=Product.ADHESION),
        # Remplis le champ select avec les objets Price
        empty_label=_("Sélectionnez une adhésion"),  # Texte affiché par défaut
        required=True,
        widget=UnfoldAdminSelectWidget(),
        label=_("Adhésion")
    )

    # Fabrication au cas ou = 0
    contribution = forms.FloatField(
        required=False,
        widget=UnfoldAdminTextInputWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Cotisation"),
    )

    payment_method = forms.ChoiceField(
        required=False,
        choices=PaymentMethod.not_online(),  # on retire les choix stripe
        widget=UnfoldAdminSelectWidget(),  # attrs={"placeholder": "Entrez l'adresse email"}
        label=_("Moyen de paiement"),
    )

    class Meta:
        model = Membership
        fields = [
            'last_name',
            'first_name',
            'option_generale',
        ]

    def clean(self):
        # On vérifie que le moyen de paiement est bien entré si > 0
        cleaned_data = self.cleaned_data
        if cleaned_data.get("contribution"):
            if cleaned_data.get("contribution") > 0 and cleaned_data.get("payment_method") == PaymentMethod.FREE:
                raise forms.ValidationError(_("Merci de renseigner un moyen de paiement si la contribution est > 0"))

        if cleaned_data.get("payment_method") != PaymentMethod.FREE:
            if not cleaned_data.get("contribution"):
                raise forms.ValidationError(_("Merci de renseigner un montant."))
            if not cleaned_data.get("contribution") > 0:
                raise forms.ValidationError(_("Merci de renseigner un montant positif."))

        return cleaned_data

    def save(self, commit=True):
        self.instance: Membership
        # On indique que l'adhésion a été créé sur l'admin
        self.instance.status = Membership.ADMIN

        # Associez l'utilisateur au champ 'user' du formulaire
        email = self.cleaned_data.pop('email')
        user = get_or_create_user(email)
        self.instance.user = user

        # Flotant (FALC) vers Decimal
        contribution = self.cleaned_data.pop('contribution')
        self.instance.contribution_value = dround(Decimal(contribution)) if contribution else 0

        # Mise à jour des dates de contribution :
        self.instance.first_contribution = timezone.localtime()
        self.instance.last_contribution = timezone.localtime()

        # Le post save BaseBillet.signals.create_lignearticle_if_membership_created_on_admin s'executera
        # # Création de la ligne Article vendu qui envera à la caisse si besoin
        return super().save(commit=commit)


class MembershipForm(ModelForm):
    # Le formulaire pour changer une adhésion
    class Meta:
        model = Membership
        fields = (
            'last_name',
            'first_name',
            'option_generale',
            'commentaire',
        )

# Le petit badge route a droite du titre "adhésion"
def adhesion_badge_callback(request):
    # Recherche de la quantité de nouvelles adhésions ces 14 dernièrs jours
    return f"+ {Membership.objects.filter(last_contribution__gte=timezone.localtime() - timedelta(days=7)).count()}"

@admin.register(Membership, site=staff_admin_site)
class MembershipAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    # Formulaire de modification
    form = MembershipForm
    # Formulaire de création. A besoin de get_form pour fonctionner
    add_form = NewMembershipForm

    list_display = (
        'email',
        'first_name',
        'last_name',
        'price',
        'contribution_value',
        'options',
        'date_added',
        'deadline',
        'is_valid',
        'status',
        # 'commentaire',
    )

    ### FORMULAIRES
    autocomplete_fields = ['option_generale', ]

    def get_form(self, request, obj=None, **kwargs):
        """ Si c'est un add, on modifie un peu le formulaire pour avoir un champs email """
        defaults = {}
        if obj is None:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    ordering = ('-date_added',)
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'card_number')

    # Pour les bouton en haut de la vue change
    # chaque decorateur @action génère une nouvelle route
    actions_detail = ["send_invoice", "get_invoice"]

    @action(
        description=_("Envoyer une facture par mail"),
        url_path="send_invoice",
        permissions=["custom_actions_detail"],
    )
    def send_invoice(self, request, object_id):
        membership = Membership.objects.get(pk=object_id)
        send_membership_invoice_to_email(membership)
        messages.success(
            request,
            _(f"Facture envoyée sur {membership.user.email}"),
        )
        return redirect(request.META["HTTP_REFERER"])

    @action(
        description=_("Générer une facture"),
        url_path="get_invoice",
        permissions=["custom_actions_detail"],
    )
    def get_invoice(self, request, object_id):
        membership = Membership.objects.get(pk=object_id)
        pdf_binary = create_membership_invoice_pdf(membership)
        response = HttpResponse(pdf_binary, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="facture.pdf"'
        return response
        # messages.success(
        #     request,
        #     _(f"Facture générée"),
        # )
        # return redirect(request.META["HTTP_REFERER"])

    def has_custom_actions_detail_permission(self, request, object_id):
        return True

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False


### VENTES ###

@admin.register(LigneArticle, site=staff_admin_site)
class LigneArticleAdmin(ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    list_display = [
        'productsold',
        'datetime',
        'amount_decimal',
        'qty',
        'vat',
        'total_decimal',
        'display_status',
        'payment_method',
    ]
    # fields = "__all__"
    # readonly_fields = fields

    ordering = ('-datetime',)

    def get_queryset(self, request):
        # Utiliser select_related pour précharger pricesold et productsold
        queryset = super().get_queryset(request)
        return queryset.select_related('pricesold__productsold')

    @display(description=_("Montant"))
    def amount_decimal(self, obj):
        return dround(obj.amount)

    @display(description=_("Total"))
    def total_decimal(self, obj):
        return dround(obj.total())

    @display(description=_("Produit"))
    def productsold(self, obj):
        return f"{obj.pricesold.productsold} - {obj.pricesold}"

    # noinspection PyTypeChecker
    @display(description=_("Status"), label={None: "danger", True: "success"})
    def display_status(self, instance: LigneArticle):
        status = instance.status
        if status in [LigneArticle.VALID, LigneArticle.PAID, LigneArticle.FREERES]:
            return True, f"{instance.get_status_display()}"
        return None, f"{instance.get_status_display()}"

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


"""
class CustomEventForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        config = Configuration.get_solo()
        self.fields['jauge_max'].initial = config.jauge_max


class EventAdmin(admin.ModelAdmin):
    form = CustomEventForm
    fieldsets = (
        ('Nouvel évènement', {
            'fields': (
                'name',
                'datetime',
                'img',
                'short_description',
                'long_description',
                'published',
            )
        }),
        ('Articles', {
            'fields': (
                'products',
            )
        }),
        ('Options', {
            'fields': (
                'jauge_max',
                'max_per_user',
                'tag',
                'options_radio',
                'options_checkbox',
            )
        }),
        ('Recurence', {
            'fields': (
                'recurrent',
                'booking',
            )
        }),
        ('Cashless', {
            'fields': (
                # 'cashless',
                'minimum_cashless_required',
            )
        }),
    )

    list_display = [
        'name',
        'reservations',
        'datetime',
    ]
    readonly_fields = (
        'reservations',
    )
    search_fields = ['name']

    # pour selectionner uniquement les articles ventes et retour consigne
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        produits_non_affichables = [Product.RECHARGE_CASHLESS, Product.DON, Product.ADHESION]
        if db_field.name == "products":
            kwargs["queryset"] = Product.objects \
                .exclude(
                categorie_article__in=produits_non_affichables) \
                .exclude(archive=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        # On check si le cashless est opé.
        # if obj.recharge_cashless:
        #     config = Configuration.get_solo()
        #     if config.check_serveur_cashless():
        #         messages.add_message(request, messages.INFO, f"Cashless server ONLINE")
        #     else:
        #         obj.recharge_cashless = False
        #         messages.add_message(request, messages.ERROR, "Cashless server OFFLINE or BAD KEY")

        super().save_model(request, obj, form, change)

        # import ipdb; ipdb.set_trace()


staff_admin_site.register(Event, EventAdmin)





# class QuantitiesSoldAdmin(admin.ModelAdmin):
#     list_display = (
#         'price',
#         'event',
#         'qty',
#     )
# staff_admin_site.register(QuantitiesSold, QuantitiesSoldAdmin)


class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        'datetime',
        'user_commande',
        'event',
        'status',
        'total_paid',
    )
    # readonly_fields = list_display
    # search_fields = ['event']


# staff_admin_site.register(Reservation, ReservationAdmin)


class EventFilter(SimpleListFilter):
    title = _('Évènement')
    parameter_name = 'reservation__event__name'

    def lookups(self, request, model_admin):
        events = Event.objects.filter(
            datetime__gt=(datetime.datetime.now() - datetime.timedelta(days=2)).date(),
        )

        tuples_list = []
        for event in events:
            if event.reservation.count() > 0:
                t = (event.uuid, event.name.capitalize())
                tuples_list.append(t)
        return tuples_list

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        else:
            return queryset.filter(reservation__event__uuid=self.value())


def valider_ticket(modeladmin, request, queryset):
    queryset.update(status=Ticket.SCANNED)


valider_ticket.short_description = "Valider le/les tickets"


class TicketAdmin(admin.ModelAdmin):
    list_display = [
        'reservations',
        'first_name',
        'last_name',
        'event',
        'options',
        'state',
    ]

    # list_editable = ['status',]
    readonly_fields = list_display
    actions = [valider_ticket, ]
    ordering = ('-reservation__datetime',)

    # list_filter = [EventFilter, ]

    # list_filter = (
    #     EventFilter,
    # 'reservation__uuid'
    # )

    search_fields = (
        'first_name',
        'last_name',
        'reservation__user_commande__email'
    )

    def state(self, obj):
        if obj.status == Ticket.NOT_SCANNED:
            return format_html(
                f'<a  href="{reverse("staff_admin:ticket-scann", args=[obj.pk])}" class="button">Valider</a>&nbsp;',
            )
        elif obj.status == Ticket.SCANNED:
            return 'Validé'
        else:
            for choice in Reservation.TYPE_CHOICES:
                if choice[0] == obj.reservation.status:
                    return choice[1]

    state.short_description = 'Etat'
    state.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            re_path(
                r'^(?P<ticket_pk>.+)/scanner/$',
                self.admin_site.admin_view(self.scanner),
                name='ticket-scann',
            ),
        ]
        return custom_urls + urls

    def scanner(self, request, ticket_pk, *arg, **kwarg):
        print(ticket_pk)
        ticket = Ticket.objects.get(pk=ticket_pk)
        ticket.status = Ticket.SCANNED
        ticket.save()
        messages.add_message(
            request,
            messages.SUCCESS,
            f"Ticket validé. Statut scanné."
        )
        # context = self.admin_site.each_context(request)
        return HttpResponseRedirect(
            reverse("staff_admin:BaseBillet_ticket_changelist")
        )

    def reservations(self, obj):
        return format_html(
            '<a  '
            f'href="{reverse("staff_admin:BaseBillet_ticket_changelist")}?reservation__uuid={obj.reservation.pk}">'
            f'{obj.reservation}'
            f'</a>&nbsp;'
        )

    reservations.short_description = 'Reservations'
    reservations.allow_tags = True

    def has_delete_permission(self, request, obj=None):
        # return request.user.is_superuser
        return False

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        qs = super(TicketAdmin, self).get_queryset(request)
        future_events = qs.filter(
            reservation__event__datetime__gt=(datetime.datetime.now() - datetime.timedelta(days=2)).date(),
        )
        return future_events


staff_admin_site.register(Ticket, TicketAdmin)



# class ProductSoldAdmin(admin.ModelAdmin):
#     list_display = (
#         'product',
#         'event',
#         'img',
#         'id_product_stripe',
#     )
#
#
# staff_admin_site.register(ProductSold, ProductSoldAdmin)
#
#
# class PricesSoldAdmin(admin.ModelAdmin):
#     list_display = (
#         'productsold',
#         'price',
#         'qty_solded',
#         'id_price_stripe',
#     )
#
#
# staff_admin_site.register(PriceSold, PricesSoldAdmin)



staff_admin_site.register(Paiement_stripe, PaiementStripeAdmin)


# class LigneArticleAdmin(admin.ModelAdmin):
#     list_display = (
#         'datetime',
#         'pricesold',
#         'qty',
#         'carte',
#         'status',
#         'paiement_stripe',
#         'status_stripe'
#     )
#     ordering = ('-datetime',)
#
#
# staff_admin_site.register(LigneArticle, LigneArticleAdmin)


def send_invoice(modeladmin, request, queryset):
    pass

def send_to_ghost(modeladmin, request, queryset):
    pass
"""


@admin.register(Client, site=staff_admin_site)
class TenantAdmin(ModelAdmin):
    # Doit être référencé pour le champs autocomplete_fields federated_with de configuration
    # est en CRUD total false
    # Seul le search fields est utile :
    search_fields = ['name', ]

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



### Connect

@admin.register(GhostConfig, site=staff_admin_site)
class GhostConfigAdmin(SingletonModelAdmin, ModelAdmin):
    compressed_fields = True  # Default: False
    warn_unsaved_form = True  # Default: False

    fields = [
        "ghost_url",
        "ghost_key",
        "ghost_last_log",
    ]

    readonly_fields = ["ghost_last_log",]

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)