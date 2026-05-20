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
    list_help_text = ""
    list_help_url = ""

    changeform_help_text = ""
    changeform_help_url = ""
    change_form_template = 'admin/help/change_form_with_help.html'

    def check_configuration(self):
        if (not self.list_help_text or not self.list_help_url) and (not self.changeform_help_text or not self.changeform_help_url):
            raise Exception(f"L'aide a été mal configuré dans la classe : {self.__class__}. Quand vous implémentez 'HelpDisplayMixin', il faut définir 'list_help_text' et 'list_help_url' dans la classe parente.")


    def changelist_view(self, request, extra_context = None):
        if extra_context is None:
            extra_context = {}

        self.check_configuration()

        extra_context.update({
            "help_text":self.list_help_text,
            "help_url":self.list_help_url,
        })

        return super().changelist_view(request, extra_context=extra_context)

    def changeform_view(self, request, object_id= None, form_url = "",extra_context = None):
        if extra_context is None:
            extra_context = {}

        self.check_configuration()

        extra_context.update({
            "help_text":self.changeform_help_text,
            "help_url":self.changeform_help_url,
        })

        return super().changeform_view(request, object_id, form_url, extra_context=extra_context)
