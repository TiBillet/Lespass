from django import template

register = template.Library()

@register.filter
def sel(value, arg):
    return value[arg]