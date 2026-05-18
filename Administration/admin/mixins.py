import logging

from unfold.admin import ModelAdmin

logger = logging.getLogger(__name__)

class HelpDisplayMixin:
    """
    Display help before the templates.
    Must be placed before 'ModelAdmin' in the inheritance order.
    The template
    """

    #: template for change_list view
    # list_before_template = (
    #     "admin/help/help_display_before_template.html"
    # )
    help_text = ""
    help_url = ""

    def changelist_view(self, request, extra_context= None):
        if extra_context is None:
            extra_context = {}

        if not self.help_text or not self.help_url:
            raise Exception(f"L'aide a été mal configuré dans la classe : {self.__class__}. Quand vous implémentez 'HelpDisplayMixin', il faut définir 'help_url' et 'help_text' dans la classe parente.")

        extra_context.update({
            "help_text":self.help_text,
            "help_url":self.help_url,
        })

        return  super().changelist_view(request, extra_context=extra_context)