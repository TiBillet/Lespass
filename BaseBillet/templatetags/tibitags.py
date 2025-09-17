from datetime import datetime
from itertools import product
from random import randint

from django import template
from django.db import connection
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from Administration.management.commands.demo_data import logger
from fedow_connect.utils import dround as utils_dround

register = template.Library()

@register.filter
def modulo(num, val):
    return num % val

@register.filter
def range_by(events: list, val: int):
    list_ranged = []
    iteration = 0
    count_list = -1
    for event in events:
        if iteration % val == 0:
            count_list += 1
            list_ranged.append([event,])
        else :
            list_ranged[count_list].append(event)
        iteration += 1

    return list_ranged


@register.filter
def in_list(value, list):
    value = str(value)
    retour = value in list.split(',')
    return retour

@register.filter
def not_in_list(value, list):
    value = str(value)
    retour = value not in list.split(',')
    return retour


@register.filter
def is_membership(user, membership_product) -> bool:
    # Recherche d'une adhésion valide chez l'utilisateur
    # import ipdb; ipdb.set_trace()
    return user.memberships.filter(price__product=membership_product, deadline__gte=timezone.now()).exists()


@register.filter
def can_admin(user):
    if user.is_superuser:
        return True

    admin_this = False
    this_tenant = connection.tenant
    if user.is_tenant_admin(this_tenant):
        admin_this = True
    return all([user.email_valid, user.is_active, admin_this])

@register.filter
def first_eight(value):
    return str(value)[:8]

@register.filter
def dround(value):
    return utils_dround(value)

@register.filter
def from_iso_to_date(value):
    return datetime.fromisoformat(value)

@register.filter
def randImg(value):
    if not value :
        return f"/static/images/404-{randint(1,12)}.jpg"
    return value

@register.filter
def randCardImg(value):
    if not value :
        return f"/static/images/404-Card-1.jpg"
    return value
# @register.filter
# def wallet_name(wallet):
#     return wallet.uuid

@register.filter(name='dict_key')
def dict_key(d, k):
    logger.info(d, k)
    '''Returns the given key from a dictionary.'''
    try :
        return d[k]
    except KeyError:
        return ""

@register.filter(name='get_choice_string')
def get_choice_string(value: str, choice: tuple):
    # Le dictionnaire des choix : {clé: libellé}
    choice_dict = dict(choice)
    # Retourner le libellé s’il existe, sinon la valeur brute
    return choice_dict.get(value, value)

@register.filter(name='brightness')
def brightness(color):
    # dans le template : {% if tag.color|brightness < 128 %}white{% else %}black{% endif %}
    if not color:
        return 0
    # Remove '#' if present
    color = color.lstrip('#')

    # Convert hex to RGB
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)

    # Calculate brightness using perceived luminance formula
    # Source: https://www.w3.org/TR/AERT/#color-contrast
    return ((r * 299) + (g * 587) + (b * 114)) / 1000


@register.filter(name='format_answer')
def format_answer(value):
    """
    Render a value coming from JSON (Membership.custom_form) safely:
    - lists/tuples => comma-separated string
    - dicts => "key: value" pairs joined by comma
    - others => returned as-is for Django to render
    """
    try:
        # List or tuple: join with comma and space
        if isinstance(value, (list, tuple)):
            return ", ".join([str(v) for v in value])
        # Dict: render as key: value pairs
        if isinstance(value, dict):
            return ", ".join([f"{k}: {v}" for k, v in value.items()])
        # Booleans/ints/floats/strings: let Django render normally
        return value
    except Exception:
        return value


@register.filter(name='custom_form_table')
def custom_form_table(custom_form, obj=None):
    """
    Convert a membership custom_form dict into Unfold Table component data.
    If a Membership or Product is provided via `obj`, map field keys (slugs)
    to their user-friendly labels using ProductFormField for the related product.

    Returns a dict: {"headers": [...], "rows": [[label_or_key, formatted_value], ...]}
    """
    try:
        # Lazy import to avoid issues on startup
        try:
            from BaseBillet.models import ProductFormField, Product
        except Exception:
            ProductFormField = None
            Product = None

        headers = [_("Field"), _("Answer")]
        rows = []

        # Build name->label map if possible
        name_to_label = {}
        product = None
        if obj is not None:
            # If we received a Membership-like object
            price = getattr(obj, 'price', None)
            if price is not None:
                try:
                    product = getattr(price, 'product', None)
                except Exception:
                    product = None
            # Or if a Product instance was passed directly
            if product is None and Product is not None:
                try:
                    if isinstance(obj, Product):
                        product = obj
                except Exception:
                    pass

        if product is not None and ProductFormField is not None:
            try:
                # Use prefetched related if available, otherwise query
                form_fields = getattr(product, 'form_fields', None)
                if form_fields is not None:
                    qs = getattr(form_fields, 'all', lambda: [])()
                else:
                    qs = []
                if not qs and ProductFormField is not None:
                    qs = ProductFormField.objects.filter(product=product)
                name_to_label = {ff.name: ff.label for ff in qs}
            except Exception:
                name_to_label = {}

        # Iterate entries
        if isinstance(custom_form, dict):
            items = custom_form.items()
        else:
            try:
                items = list(custom_form.items())
            except Exception:
                items = []

        for key, value in items:
            label = name_to_label.get(key, key)
            rows.append([label, format_answer(value)])
        return {"headers": headers, "rows": rows}
    except Exception:
        return {"headers": [_("Field"), _("Answer")], "rows": []}
