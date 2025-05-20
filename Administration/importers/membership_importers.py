from django.core.exceptions import MultipleObjectsReturned
from django.utils.translation import gettext_lazy as _
from import_export import resources, fields
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget, ManyToManyWidget

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


class PriceForeignKeyWidget(ForeignKeyWidget):
    def clean(self, value, row=None, **kwargs):
        try:
            val = super().clean(value)
        except MultipleObjectsReturned:
            val = Price.objects.get(name=value, product__name=row.get('product_name'))
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


class MembershipExportResource(resources.ModelResource):
    email = Field(attribute='user__email', column_name='email')
    member_name = Field(attribute='member_name', column_name='member_name')
    price__product__name = Field(attribute='price__product__name', column_name='price__product__name')
    price__name = Field(attribute='price__name', column_name='price__name')
    payment_method_name = Field(attribute='payment_method_name', column_name='payment_method_name')
    options = Field(attribute='options', column_name='options')
    status_name = Field(attribute='status_name', column_name='status_name')

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
        widget=ForeignKeyWidget(Product, field='name'))  # renvoie une erreur si le produit n'existe pas

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