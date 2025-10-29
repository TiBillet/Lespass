from django import template
from ..models import Initiative

register = template.Library()

@register.simple_tag
def has_initiatives():
    """Return True if at least one Initiative exists."""
    try :
        return Initiative.objects.exists()
    except Exception:
        return False
