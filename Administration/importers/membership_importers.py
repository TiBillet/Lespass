import json
from django.core.exceptions import MultipleObjectsReturned
from django.utils.translation import gettext_lazy as _
from import_export import resources, fields
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget, ManyToManyWidget

from Administration.importers.reponses_formulaire_export import cles_des_reponses_a_exporter
from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Membership, Product, Price, OptionGenerale


class EmailUserForeignKeyWidget(ForeignKeyWidget):
    def clean(self, value, row=None, **kwargs):
        try:
            val = super().clean(value)
        except TibilletUser.DoesNotExist:
            val = get_or_create_user(value, send_mail=False)
        return val


class ProductNonArchiveForeignKeyWidget(ForeignKeyWidget):
    def get_queryset(self, value, row, *args, **kwargs):
        # Un produit archivé peut porter le même nom qu'un produit actif.
        # L'import cherche le produit par son nom : on ne garde que les produits non archivés.
        # / An archived product may share its name with an active one: import on active only.
        return Product.objects.filter(archive=False)


class PriceForeignKeyWidget(ForeignKeyWidget):
    def get_queryset(self, value, row, *args, **kwargs):
        # Un tarif archivé (« supprimé ») ne peut pas recevoir de nouvelle adhésion importée.
        # / An archived ("deleted") price cannot receive a newly imported membership.
        return Price.objects.filter(archived=False)

    def clean(self, value, row=None, **kwargs):
        try:
            val = super().clean(value)
        except MultipleObjectsReturned:
            val = Price.objects.get(
                name=value,
                product__name=row.get('product_name'),
                product__archive=False,
                archived=False,
            )
        except Exception as err:
            raise err
        return val


class OptionsManyToManyWidgetWidget(ManyToManyWidget):
    def clean(self, value, row=None, **kwargs):
        if not value:
            return self.model.objects.none()
        else:
            objs = []
            names = value.split(self.separator)
            for name in names:
                if name.rstrip().lstrip():  # on supprime les espace avants et après
                    try:
                        option = OptionGenerale.objects.get(name=name)
                        objs.append(option)
                    except OptionGenerale.DoesNotExist:
                        option = OptionGenerale.objects.create(name=name)
                        objs.append(option)
            return objs


class JSONKeyField(Field):
    """A Field that exports a value from Membership.custom_form for a given key."""
    def __init__(self, key: str, column_name: str = None):
        # attribute isn't used for value extraction; keep None
        super().__init__(column_name=column_name or key)
        self.key = key

    def get_value(self, obj):
        data = getattr(obj, 'custom_form', None)
        if isinstance(data, dict):
            value = data.get(self.key)
            # Apply safe_join-like behavior for CSV readability
            if isinstance(value, list):
                return ", ".join(map(str, value))
            if isinstance(value, bool):
                return _("Yes") if value else _("No")
            if isinstance(value, dict):
                return json.dumps(value, ensure_ascii=False)
            return value
        return None


class MembershipExportResource(resources.ModelResource):
    email = Field(attribute='user__email', column_name='email')
    member_name = Field(attribute='member_name', column_name='member_name')
    price__product__name = Field(attribute='price__product__name', column_name='price__product__name')
    price__name = Field(attribute='price__name', column_name='price__name')
    payment_method_name = Field(attribute='payment_method_name', column_name='payment_method_name')
    options = Field(attribute='options', column_name='options')
    status_name = Field(attribute='status_name', column_name='status_name')

    def before_export(self, queryset, *args, **kwargs):
        """
        Prépare les colonnes des réponses au formulaire personnalisé.
        / Prepares the custom form answer columns.

        On lit les clés des réponses des adhésions exportées, et leurs produits.
        cles_des_reponses_a_exporter (reponses_formulaire_export.py) trie les
        colonnes dans l'ordre d'affichage des questions. Issue #290.
        / Keys and products of the exported memberships; ordering is done by
        cles_des_reponses_a_exporter.
        """
        keys = set()
        uuids_des_produits = set()
        for obj in queryset:
            data = getattr(obj, 'custom_form', None)
            if isinstance(data, dict):
                for k in data.keys():
                    if k is not None:
                        keys.add(str(k))

        # Les produits des adhésions, en UNE requête (pas une par adhésion).
        # / The memberships' products, in ONE query.
        if hasattr(queryset, 'values_list'):
            for uuid_du_produit in queryset.values_list('price__product_id', flat=True).distinct():
                if uuid_du_produit is not None:
                    uuids_des_produits.add(uuid_du_produit)
        self._custom_form_keys = cles_des_reponses_a_exporter(keys, uuids_des_produits)

    def get_export_fields(self, *args, **kwargs):
        base_fields = super().get_export_fields(*args, **kwargs)
        # Avoid duplicates by column name
        existing = set()
        for f in base_fields:
            name = getattr(f, 'column_name', None) or getattr(f, 'attribute', None)
            if name:
                existing.add(str(name))
        dynamic_fields = []
        for key in getattr(self, '_custom_form_keys', []):
            if key not in existing:
                dynamic_fields.append(JSONKeyField(key=key, column_name=key))
        return base_fields + dynamic_fields

    def get_export_headers(self, selected_fields=None, *args, **kwargs):
        # Build headers directly from field column names to support dynamic fields
        fields = selected_fields or self.get_export_fields(*args, **kwargs)
        return [f.column_name for f in fields]

    def get_field_name(self, field):
        # Gracefully handle dynamically generated JSONKeyField instances
        if isinstance(field, JSONKeyField):
            # Use the column_name as the header/name for JSON dynamic fields
            return field.column_name
        return super().get_field_name(field)

    class Meta:
        model = Membership
        fields = (
            'last_contribution',
            'email',
            'member_name',
            'price__product__name',
            'price__name',
            'contribution_value',
            'payment_method_name',
            'options',
            'is_valid',
            'deadline',
            'status_name',
        )
        export_order = ('last_contribution',)


# Le moteur d'importation pour les adhésions
class MembershipImportResource(resources.ModelResource):
    product_name = fields.Field(
        column_name='product_name',
        attribute='product_name',
        widget=ProductNonArchiveForeignKeyWidget(Product, field='name'))  # renvoie une erreur si le produit n'existe pas

    price_name = fields.Field(
        column_name='price_name',
        attribute='price',
        widget=PriceForeignKeyWidget(Price, field='name'))  # Vérfie que le price correspond bien au product

    email = fields.Field(
        column_name='email',
        attribute='user',
        widget=EmailUserForeignKeyWidget(TibilletUser, field='email'))  # si l'user n'existe pas, va le créer

    option_generale = fields.Field(
        column_name='option_generale',
        attribute='option_generale',
        widget=OptionsManyToManyWidgetWidget(OptionGenerale, field='name', separator=';')
    )

    def before_save_instance(self, instance, row, **kwargs):
        instance.status = Membership.IMPORT

    class Meta:
        model = Membership
        fields = (
            'email',
            'first_name',
            'last_name',
            'last_contribution',
            'contribution_value',
            'product_name',
            'price_name',
            'option_generale',
            'commentaire',
        )
        import_id_fields = ('email',)

        widgets = {
            'last_contribution': {'format': '%d/%m/%Y'},
        }