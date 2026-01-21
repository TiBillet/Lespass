from datetime import datetime
from random import randint

import requests
from django import template
from django.db import connection
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from Administration.management.commands.demo_data import logger
from fedow_connect.utils import dround as utils_dround

register = template.Library()

@register.filter
def strip_trailing_slash(value):
    """Supprime les / à la fin de la chaîne"""
    if isinstance(value, str):
        return value.rstrip('/')
    return value

@register.filter
def strip_leading_slash(value):
    """Supprime les / au début de la chaîne"""
    if isinstance(value, str):
        return value.lstrip('/')
    return value

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
def price_out_of_stock(value, event):
    price = value
    return price.out_of_stock(event=event)



@register.filter
def in_list(value:str, liste:list):
    logger.info(f"in_list {value} in {liste}")
    return value in liste

# @register.filter
# def in_list(value, liste):
#     value = str(value)
#     retour = value in liste.split(',')
#     return retour
#
# @register.filter
# def not_in_list(value, liste):
#     value = str(value)
#     retour = value not in liste.split(',')
#     return retour


@register.filter
def is_membership(user, membership_product) -> bool:
    # Recherche d'une adhésion valide chez l'utilisateur
    # import ipdb; ipdb.set_trace()
    return user.memberships.filter(price__product=membership_product, deadline__gte=timezone.now()).exists()


@register.filter
def can_admin(user):
    if user.is_anonymous:
        return False
    elif user.is_superuser:
        return True

    admin_this = False
    this_tenant = connection.tenant
    if user.is_tenant_admin(this_tenant):
        admin_this = True
    return all([user.email_valid, user.is_active, admin_this])

@register.filter
def can_create_event_tag(user):
    this_tenant = connection.tenant
    if user.is_anonymous:
        return False
    elif can_admin(user):
        return True
    elif user.can_create_event(this_tenant) :
        return True
    return False

@register.filter

def first_eight(value):
    return str(value)[:8]

@register.filter
def dround(value):
    return utils_dround(value)

@register.filter
def from_iso_to_date(value):
    return datetime.fromisoformat(value)

def get30randimg():
    list30 = []
    for i in range(30):
        rq = requests.get(f'https://picsum.photos/{randint(1680,1920)}/{randint(1050,1200)}', timeout=1)
        list30.append(rq.url)
    return list30

@register.filter
def randImg(value):
    if not value:
        return f"/static/images/404-{randint(1, 20)}.jpg"
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

@register.filter
def safe_join(value, sep=", "):
    """Join a list safely, otherwise return the value unchanged."""
    if type(value)==list:
        return sep.join(map(str, value))
    elif type(value)==bool:
        return _("Yes") if value else _("No")
    return value

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
    Convert a custom_form dict into Unfold Table component data.
    If a Membership, Reservation or Product is provided via `obj`, map field keys (slugs)
    to their user-friendly labels using ProductFormField for the related product(s).

    Returns a dict: {"headers": [...], "rows": [[label_or_key, formatted_value], ...]}
    """
    try:
        # Lazy import to avoid issues on startup
        try:
            from BaseBillet.models import ProductFormField, Product, Reservation
        except Exception:
            ProductFormField = None
            Product = None
            Reservation = None

        headers = _("Field"), _("Answer")
        rows = []

        # Build name->label map if possible
        name_to_label = {}

        products = []
        product = None
        if obj is not None:
            # If we received a Membership-like object
            price = getattr(obj, 'price', None)
            if price is not None:
                try:
                    product = getattr(price, 'product', None)
                except Exception:
                    product = None
            # If a Product instance was passed directly
            if product is None and Product is not None:
                try:
                    if isinstance(obj, Product):
                        product = obj
                except Exception:
                    pass
            # If a Reservation instance was passed: collect all related products from tickets
            if product is None and Reservation is not None:
                try:
                    if isinstance(obj, Reservation):
                        # Prefer prefetched relation if available
                        tickets = getattr(obj, 'tickets', None)
                        qs = getattr(tickets, 'select_related', None)
                        if callable(qs):
                            tqs = tickets.select_related('pricesold__price__product').all()
                            products = list({t.pricesold.price.product for t in tqs if getattr(t, 'pricesold', None) and getattr(t.pricesold, 'price', None) and getattr(t.pricesold.price, 'product', None)})
                        # Fallback to event products if no tickets found
                        if not products:
                            evt = getattr(obj, 'event', None)
                            if evt is not None:
                                try:
                                    products = list(getattr(evt, 'products').all())
                                except Exception:
                                    products = []
                except Exception:
                    pass

        # Build label map from either single product or multiple products
        if ProductFormField is not None:
            try:
                if product is not None:
                    # Use prefetched related if available, otherwise query
                    form_fields = getattr(product, 'form_fields', None)
                    if form_fields is not None:
                        qs = getattr(form_fields, 'all', lambda: [])()
                    else:
                        qs = []
                    if not qs:
                        qs = ProductFormField.objects.filter(product=product)
                    name_to_label.update({ff.name: ff.label for ff in qs})
                elif products:
                    # Aggregate all form fields for involved products
                    for prod in products:
                        try:
                            form_fields = getattr(prod, 'form_fields', None)
                            if form_fields is not None:
                                qs = getattr(form_fields, 'all', lambda: [])()
                            else:
                                qs = []
                            if not qs:
                                qs = ProductFormField.objects.filter(product=prod)
                            name_to_label.update({ff.name: ff.label for ff in qs})
                        except Exception:
                            continue
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
        return {"headers": list(headers), "rows": rows}
    except Exception:
        return {"headers": [_("Field"), _("Answer")], "rows": []}
