import logging

from django.contrib import messages
from django.db import models
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from unfold.sites import UnfoldAdminSite

from Administration.utils import clean_html
from ApiBillet.permissions import TenantAdminPermissionWithRequest

logger = logging.getLogger(__name__)


def sanitize_textfields(instance: models.Model) -> None:
    """Sanitize all TextField values on a model instance in-place using clean_html.
    Only string values are sanitized; None and non-string values are ignored.
    """
    # pass
    for field in instance._meta.get_fields():
        if isinstance(field, models.TextField):
            field_name = field.name
            if hasattr(instance, field_name):
                value = getattr(instance, field_name)
                if isinstance(value, str) and value:
                    setattr(instance, field_name, clean_html(value))


class StaffAdminSite(UnfoldAdminSite):
    def login(self, request, extra_context=None):
        """
        Redirect admin login to the root URL for better security.
        """
        messages.add_message(request, messages.WARNING, _("Please login to access this page."))
        return HttpResponseRedirect('/')

    def has_permission(self, request):
        return TenantAdminPermissionWithRequest(request)


staff_admin_site = StaffAdminSite(name='staff_admin')
