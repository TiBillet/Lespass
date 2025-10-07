from django import template
from decimal import *

register = template.Library()

@register.filter
def sel(value, arg):
	return value[arg]

@register.filter
def divide_by(value, arg):
	# 2 chiffre après la virgule
	return Decimal(value / arg).quantize(Decimal('.01'))