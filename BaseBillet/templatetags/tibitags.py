from datetime import datetime
from random import randint

from django import template
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

# TODO: fonctionnel, juste vérifier/simplifier le code si-dessous
@register.filter
def is_membership(membership, product_name) -> bool:
    retour = False
    if len(membership) == 0:
        return False
    # une list
    for adhesion in membership:
        # un dictionnaire ordonné
        for key, value in adhesion.items():
            if key == 'product_name' and value == str(product_name):
                retour = True
                break
    return retour

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
        return f"/static/images/404-{randint(1,9)}.jpg"
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
    '''Returns the given key from a dictionary.'''
    try :
        return d[k]
    except KeyError:
        return ""
