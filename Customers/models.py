from django.utils import timezone

from django.db import connection, models
from django_tenants.models import TenantMixin, DomainMixin
from django_tenants.utils import get_public_schema_name
from django.utils.translation import gettext_lazy as _
import uuid

class Client(TenantMixin):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True, db_index=True)

    name = models.CharField(max_length=100, unique=True, db_index=True, verbose_name=_("Nom du lieu"))
    created_on = models.DateField(auto_now_add=True, verbose_name=_("Créé le"))

    paid_until =  models.DateField(default=timezone.now)
    on_trial = models.BooleanField(default=False)

    ARTISTE, SALLE_SPECTACLE, FESTIVAL, TOURNEUR, PRODUCTEUR, META, WAITING_CONFIG, ROOT = 'A', 'S', 'F', 'T', 'P', 'M', 'W', 'R'
    CATEGORIE_CHOICES = [
        (ARTISTE, _('Artist')),
        (SALLE_SPECTACLE, _("Scene")),
        (FESTIVAL, _('Festival')),
        (TOURNEUR, _('Tour operator')),
        (PRODUCTEUR, _('Producer')),
        (META, _('Event aggregator')),
        (WAITING_CONFIG, _('Waiting configuration')),
        (ROOT, _('Root public tenant')),
    ]

    categorie = models.CharField(max_length=3, choices=CATEGORIE_CHOICES, default=SALLE_SPECTACLE,
                                         verbose_name=_("Category"))

    # Moteur de monnaie du lieu. Un lieu LEGACY utilise l'ancien Fedow (fedow_connect) :
    # les modules V2 et l'admin fedow_core lui sont fermes. Un lieu V2 utilise fedow_core.
    # Le lieu ne change jamais cette valeur lui-meme : elle n'est dans aucun formulaire du lieu.
    # Pour la lire dans le code d'un lieu : lieu_en_moteur_legacy(), plus bas dans ce fichier.
    # / Venue currency engine. LEGACY = old Fedow; V2 modules and fedow_core admin closed.
    MOTEUR_LEGACY, MOTEUR_V2 = 'legacy', 'v2'
    MOTEUR_CHOICES = [
        (MOTEUR_LEGACY, _("Ancien Fedow")),
        (MOTEUR_V2, _("Moteur V2")),
    ]
    moteur_monnaie = models.CharField(
        max_length=6, choices=MOTEUR_CHOICES, default=MOTEUR_V2,
        verbose_name=_("Moteur de monnaie"),
    )

    # default true, schema will be automatically created and synced when it is saved
    auto_create_schema = True

    def __str__(self):
        return f"{self.name}"

class Domain(DomainMixin):
    pass


# Verrou de moteur (spec 15 §5.1) : les modules qui utilisent le moteur V2 (fedow_core).
# Un lieu legacy (ancien Fedow) ne peut pas les allumer. `module_inventaire` n'y est pas :
# le stock des articles ne deplace pas d'argent.
# Lus par module_toggle (Administration/admin_tenant.py) et par les cartes du tableau de
# bord (Administration/admin/dashboard.py).
# / Engine lock: the modules that use the V2 engine; a legacy venue cannot switch them on.
MODULES_V2_FERMES_AUX_LIEUX_LEGACY = [
    "module_caisse",
    "module_monnaie_locale",
    "module_kiosk",
    "module_tireuse",
]

# Message montre a un lieu legacy quand il touche a une fonction du moteur V2.
# Lu par module_toggle, les cartes du tableau de bord et les routes de l'admin fedow_core.
# / Message shown to a legacy venue when it reaches a V2 engine feature.
MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY = _(
    "Votre lieu utilise l'ancien moteur de monnaie (Fedow) : ce module V2 ne le concerne pas."
)

# Les deux phrases qui encadrent les raisons qui retiennent un lieu legacy sur l'ancien
# Fedow (spec 15 §5.8). Une seule source pour le message de refus de module_toggle, la
# fenetre de confirmation et la carte du tableau de bord.
# / The two sentences around the reasons that keep a legacy venue on the old Fedow.
INTRODUCTION_DES_RAISONS_DU_MOTEUR_LEGACY = _(
    "Ce module n'est pas encore disponible pour votre lieu :"
)
PHRASE_DE_FIN_DES_RAISONS_DU_MOTEUR_LEGACY = _(
    "Contactez l'équipe TiBillet pour lui indiquer que vous souhaitez faire une migration."
)


def lieu_en_moteur_legacy():
    """
    Dit si le lieu courant utilise l'ancien moteur de monnaie (Fedow distant).
    / Tells whether the current venue uses the old currency engine (remote Fedow).

    LOCALISATION : Customers/models.py

    Rend True quand le lieu est legacy : les modules V2 et l'admin fedow_core lui sont
    fermes. Rend False quand le lieu est V2 : tout est ouvert.

    Elle lit `connection.tenant`. En HTTP, en WebSocket et dans les taches Celery, c'est
    le vrai `Client` du lieu. Sous `schema_context()` (scripts, tests), c'est un
    `FakeTenant` sans champ `moteur_monnaie`. Un tenant dont on ne peut pas lire le
    moteur (`FakeTenant`, `None`) compte comme legacy : sans savoir, on garde le verrou
    ferme.
    / Unreadable engine (FakeTenant, None) counts as legacy: closed.

    Le schema public n'est pas un lieu : il est TOUJOURS ferme, quelle que soit la valeur
    de sa ligne `Client`. Sur une base neuve, cette ligne est creee apres la migration
    `Customers 0006`, donc en `v2` : on ne la lit pas.
    / The public schema is not a venue: always closed, whatever its Client row says.

    Elle vit ici, a cote de `Client`, parce que ce fichier n'importe que Django et
    django-tenants : les vues, l'admin et les permissions peuvent l'importer sans cycle.
    / Lives next to Client: this file only imports Django, so no import cycle.

    APPELEE PAR :
    - Administration/admin_tenant.py : `ConfigurationAdmin.module_toggle` ;
    - Administration/admin/dashboard.py : cartes du tableau de bord, menu lateral ;
    - fedow_core/admin.py : permissions et routes personnalisees de l'admin fedow_core ;
    - BaseBillet/permissions.py (`HasLaBoutikTerminalAccess`), kiosk/views.py
      (`IsKioskTerminal`), controlvanne/permissions.py (`HasTireuseAccess`) ;
    - BaseBillet/views.py : `get_distant_fedow_tokens`, `MyAccount.admin_my_cards` ;
    - ApiBillet/views.py : `Onboard_laboutik` (refuse un lieu v2).
    / Called by the engine lock, server side and on screen.

    :return: True si le lieu est legacy, inconnu ou public, False si le lieu est V2 (bool)
    """
    tenant_courant = getattr(connection, "tenant", None)

    schema_du_tenant = getattr(tenant_courant, "schema_name", None)
    if schema_du_tenant == get_public_schema_name():
        return True

    moteur_du_lieu = getattr(tenant_courant, "moteur_monnaie", None)

    lieu_en_moteur_v2 = moteur_du_lieu == Client.MOTEUR_V2
    if lieu_en_moteur_v2:
        return False
    return True
