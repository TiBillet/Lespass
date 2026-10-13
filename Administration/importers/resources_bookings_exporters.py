import json
from decimal import Decimal

from django.db.models import Sum
from django.core.exceptions import MultipleObjectsReturned
from django.utils.translation import gettext_lazy as _
from import_export import resources, fields
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget, ManyToManyWidget

from Administration.importers.reponses_formulaire_export import cles_des_reponses_a_exporter
from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Membership, Product, Price, OptionGenerale, Configuration
from booking.models import Booking

class BookingExportResource(resources.ModelResource):
    """
    Export lisible des réservations de ressources (Booking).
    / Human readable export of resource bookings.

    LOCALISATION : Administration/importers/resources_bookings_exporters.py

    Branché sur BookingAdmin (Administration/admin/resources.py) via resource_classes.
    Les dates sont converties à l'heure du lieu par les méthodes de Booking
    (booking/models.py : date_display, start_time_display, end_time_display).
    Le statut sort en libellé (« Payé par l'utilisateur »), pas en code (« PA »).
    / Wired on BookingAdmin. Dates in venue time, status as a label.

    FLUX : clic « Exporter » dans l'admin -> ExportMixin (django-import-export)
    -> before_export (lit le fuseau UNE fois) -> dehydrate_* pour chaque ligne.
    """

    date = Field(column_name=_("Date"))
    heure_de_debut = Field(column_name=_("Heure de début"))
    heure_de_fin = Field(column_name=_("Heure de fin"))
    duree = Field(column_name=_("Durée"))
    ressource = Field(attribute='resource__name', column_name=_("Ressource"))
    email = Field(attribute='user__email', column_name=_("Email"))
    prenom = Field(column_name=_("Prénom"))
    nom = Field(column_name=_("Nom"))
    statut = Field(attribute='get_status_display', column_name=_("Statut"))
    total_paye = Field(column_name=_("Total payé"))
    reserve_le = Field(column_name=_("Réservé le"))

    def before_export(self, queryset, *args, **kwargs):
        """
        Lit le fuseau du lieu une seule fois pour tout l'export.
        / Reads the venue timezone once for the whole export.

        Sans ça, chaque ligne ferait sa propre requête Configuration.get_solo().
        / Otherwise each row would run its own get_solo() query.
        """
        self._fuseau_du_lieu = Configuration.get_solo().get_tzinfo()

    def _fuseau(self):
        # None si before_export n'a pas tourné : Booking relit alors la Configuration.
        # / None if before_export did not run: Booking reads the Configuration itself.
        return getattr(self, '_fuseau_du_lieu', None)

    def dehydrate_date(self, booking):
        return booking.date_display(self._fuseau())

    def dehydrate_heure_de_debut(self, booking):
        return booking.start_time_display(self._fuseau())

    def dehydrate_heure_de_fin(self, booking):
        return booking.end_time_display(self._fuseau())

    def dehydrate_duree(self, booking):
        return booking.total_time()

    def dehydrate_prenom(self, booking):
        # Un prénom vide sort en case vide, pas en « None ».
        # / An empty first name is exported as an empty cell, not "None".
        return booking.first_name or ""

    def dehydrate_nom(self, booking):
        return booking.last_name or ""

    def dehydrate_total_paye(self, booking):
        """
        Le total payé en euros, lisible par un tableur français : « 12,50 ».
        / Total paid in euros, readable by a French spreadsheet.

        La somme vient de l'annotation `total_paye_en_centimes`, calculée en une seule
        requête par BookingAdmin.get_export_queryset (Administration/admin/resources.py).
        Sans annotation (export lancé hors de l'admin), on fait la somme pour cette
        réservation, avec les mêmes statuts que Booking.total_paid().
        / Reads the admin annotation; without it, sums this booking's lines.

        Toujours deux décimales et une virgule : « 0,00 », jamais « 0 ».
        Avec un point, Excel en français lit la case comme du texte et ne la somme pas.
        / Always two decimals and a comma: a dot makes French Excel read it as text.
        """
        total_en_centimes = getattr(booking, 'total_paye_en_centimes', None)
        if total_en_centimes is None:
            somme_des_lignes_payees = booking.lignearticles.filter(
                status__in=Booking.STATUTS_DES_LIGNES_PAYEES,
            ).aggregate(total=Sum('total_ttc'))
            total_en_centimes = somme_des_lignes_payees['total'] or 0

        total_en_euros = Decimal(total_en_centimes) / 100
        return f"{total_en_euros:.2f}".replace(".", ",")

    def dehydrate_reserve_le(self, booking):
        fuseau_du_lieu = self._fuseau()
        if fuseau_du_lieu is None:
            fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        return booking.booked_at.astimezone(fuseau_du_lieu).strftime('%d/%m/%Y %H:%M')

    class Meta:
        model = Booking
        fields = (
            'date',
            'heure_de_debut',
            'heure_de_fin',
            'duree',
            'ressource',
            'email',
            'prenom',
            'nom',
            'statut',
            'total_paye',
            'reserve_le',
        )
        export_order = fields
