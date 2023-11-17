from django import template

register = template.Library()

@register.filter
def in_list(value, list):
    value = str(value)
    retour = value in list.split(',')
    return retour
