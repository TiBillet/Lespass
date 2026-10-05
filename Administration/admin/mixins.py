import logging

# ModelAdmin vient de Administration/admin/base.py : c'est le ModelAdmin
# d'Unfold plus le placeholder de recherche tire de search_fields.
# / Project ModelAdmin: Unfold's, plus the search placeholder.
from Administration.admin.base import ModelAdmin

logger = logging.getLogger(__name__)


# Formats texte qui recoivent un BOM a l'export.
# / Text formats that get a BOM on export.
EXTENSIONS_EXPORTEES_AVEC_BOM = ("csv", "tsv")


class ExportCsvLisibleParExcelMixin:
    """
    Ajoute un BOM au debut des exports CSV et TSV.
    / Adds a BOM at the start of CSV and TSV exports.

    LOCALISATION : Administration/admin/mixins.py

    Le BOM est un petit caractere invisible (U+FEFF) en tete de fichier.
    Il dit au tableur : « ce fichier est en UTF-8 ».
    Sans lui, Excel lit le fichier en Windows-1252.
    Les accents sont alors casses : « é » devient « Ã© ».
    LibreOffice et Google Sheets lisent le fichier correctement, avec ou sans BOM.

    Pourquoi pas l'attribut `to_encoding = "utf-8-sig"` de django-import-export :
    il s'applique a TOUS les formats texte, y compris JSON et YAML.
    Or un JSON ne doit pas commencer par un BOM : JSON.parse() refuse le fichier.
    Les formats binaires (XLSX, XLS, ODS) ne sont pas concernes.

    UTILISATION : placer ce mixin AVANT ImportExportModelAdmin / ExportActionModelAdmin
    dans l'heritage, sinon sa methode get_export_data n'est jamais appelee.

    FLUX : clic « Exporter » -> ExportMixin._do_file_export (django-import-export)
    -> CETTE METHODE -> ExportMixin.get_export_data -> encode le texte en bytes.
    """

    def get_export_data(self, file_format, request, queryset, **kwargs):
        # Un CSV ou un TSV est encode en UTF-8 avec BOM.
        # Les autres formats gardent l'encodage choisi par django-import-export.
        # / CSV and TSV are encoded as UTF-8 with BOM, other formats are unchanged.
        extension_du_format = file_format.get_extension()
        if extension_du_format in EXTENSIONS_EXPORTEES_AVEC_BOM:
            kwargs["encoding"] = "utf-8-sig"

        return super().get_export_data(file_format, request, queryset, **kwargs)


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
