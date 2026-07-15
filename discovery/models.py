import random
import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class PairingDevice(models.Model):
    """
    Appareil en attente d'appairage via code PIN.
    Device waiting to be paired via PIN code.

    Le PIN est généré côté admin (schéma tenant),
    et réclamé via la route publique /api/discovery/claim/.
    The PIN is generated from the tenant admin,
    and claimed via the public route /api/discovery/claim/.
    """

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        max_length=100,
        verbose_name=_("Device name"),
        help_text=_("Name of the device to pair, e.g. 'Cash register 1'"),
    )

    tenant = models.ForeignKey(
        'Customers.Client',
        on_delete=models.CASCADE,
        related_name='pairing_devices',
        verbose_name=_("Tenant"),
    )

    pin_code = models.PositiveIntegerField(
        unique=True,
        null=True,
        blank=True,
        verbose_name=_("PIN code"),
        help_text=_("6-digit pairing code, cleared after claim"),
    )

    # IMPORTANT : choices dupliqués volontairement — NE PAS importer depuis
    # AuthBillet.TibilletUser pour éviter l'import circulaire
    # discovery → AuthBillet → Customers → discovery.
    # La synchronisation des valeurs est vérifiée par
    # tests/pytest/test_terminal_role_choices_sync.py.
    # / IMPORTANT: choices duplicated on purpose — do NOT import from
    # AuthBillet.TibilletUser (circular import).
    # Sync is enforced by tests/pytest/test_terminal_role_choices_sync.py.
    terminal_role = models.CharField(
        max_length=2,
        choices=[
            ('LB', _('LaBoutik POS')),
            ('TI', _('Connected tap')),
            ('KI', _('Kiosk / self-service')),
        ],
        default='LB',
        verbose_name=_("Terminal role"),
        help_text=_("Type of hardware role being paired"),
    )

    # L'objet que cet appairage doit rattacher, quand il y en a un.
    #
    # Une tireuse est creee dans l'admin AVANT son Raspberry Pi. Le code PIN doit donc
    # savoir a quelle tireuse il correspond. Mais PairingDevice vit dans le schema public
    # et TireuseBec dans le schema du lieu : une cle etrangere est IMPOSSIBLE (PostgreSQL
    # ne saurait pas quelle table viser, la table des tireuses existant dans N schemas).
    #
    # On stocke donc un simple UUID, sans contrainte. Il ne vit QUE le temps de
    # l'appairage : le claim s'en sert pour retrouver la tireuse, pose une vraie cle
    # etrangere (TireuseBec.terminal), puis le vide — comme il vide le code PIN.
    #
    # Vide pour une caisse ou une borne : elles ne rattachent rien.
    # / The object this pairing must attach to, if any (a tap). A foreign key is impossible
    # here: PairingDevice lives in the public schema, TireuseBec in the venue's. So we store
    # a plain UUID, and it only lives for the duration of the pairing.
    cible_uuid = models.UUIDField(
        null=True,
        blank=True,
        verbose_name=_("Objet à rattacher"),
        help_text=_(
            "Identifiant de l'objet que cet appairage doit rattacher (une tireuse). "
            "Vide après l'appairage."
        ),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created at"),
    )

    claimed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Claimed at"),
        help_text=_("Set when a device claims this PIN"),
    )

    # Duree de vie d'un code PIN. Passe ce delai, il n'est plus reclamable.
    #
    # Une heure : le temps de monter un appareil et de le brancher, sans qu'un code
    # oublie dans l'admin ne reste une porte ouverte pour toujours. Le nombre de codes
    # est fini (900 000) et la route de reclamation est publique.
    # / A PIN's lifetime: one hour. Long enough to mount and plug a device, short enough
    # that a forgotten code does not stay an open door forever.
    DUREE_DE_VIE_DU_PIN = timedelta(hours=1)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("Pairing device")
        verbose_name_plural = _("Pairing devices")

    def __str__(self):
        if self.is_claimed:
            return f"{self.name} ({_('claimed')})"
        if self.pin_est_expire():
            return f"{self.name} ({_('expired PIN')})"
        return f"{self.name} - PIN {self.pin_code} ({_('available')})"

    @property
    def is_claimed(self):
        return self.claimed_at is not None

    def pin_est_expire(self):
        """
        Vrai si le code PIN est trop vieux pour etre encore reclame.
        / True if the PIN is too old to still be claimed.
        """
        if self.claimed_at is not None:
            return False
        date_limite = self.created_at + self.DUREE_DE_VIE_DU_PIN
        return timezone.now() > date_limite

    def regenerer_le_pin(self):
        """
        Refabrique un code PIN et remet le compteur de validite a zero.
        / Issues a fresh PIN and resets its validity countdown.

        Sert quand le code a expire avant que l'appareil n'ait pu etre appaire : plutot que
        de supprimer l'appairage et de tout recommencer, on redonne un code.

        INTERDIT SUR UN APPAIRAGE DEJA CONSOMME. Sans ce garde-fou, on rendrait un code a
        un appareil deja appaire : il apparaitrait de nouveau « en attente » dans l'admin,
        afficherait un code qui echouerait a chaque fois (le compte du terminal existe
        deja, et son email est unique), pendant que l'ancien terminal continue de tourner.
        Un appareil a re-appairer se recree, il ne se ressuscite pas.
        / FORBIDDEN on an already-claimed pairing: it would show a PIN that always fails,
        while the old terminal keeps running. A device to re-pair is re-created, not revived.

        :raises ValueError: si l'appairage a deja ete consomme
        """
        if self.is_claimed:
            raise ValueError(
                "Cet appairage a deja ete consomme : son code PIN ne peut pas etre "
                "regenere. Creer un nouvel appairage."
            )

        self.pin_code = self.generate_unique_pin()
        # created_at porte auto_now_add, qui n'agit qu'a la CREATION de la ligne.
        # Sur une mise a jour, la valeur posee ici est bien ecrite en base.
        # / auto_now_add only applies on INSERT; on UPDATE the value set here is written.
        self.created_at = timezone.now()
        self.save(update_fields=['pin_code', 'created_at'])

    def claim(self):
        """Marquer le PIN comme consommé et le vider (plus utile).
        Mark the PIN as consumed and clear it (no longer needed).

        On vide aussi cible_uuid : il n'a servi qu'a retrouver l'objet a rattacher pendant
        l'appairage. Le lien durable est desormais une vraie cle etrangere.
        / cible_uuid is cleared too: it only served to find the object during pairing.
        """
        self.claimed_at = timezone.now()
        self.pin_code = None
        self.cible_uuid = None
        self.save(update_fields=['claimed_at', 'pin_code', 'cible_uuid'])

    @staticmethod
    def generate_unique_pin():
        """
        Génère un PIN unique à 6 chiffres (100000-999999).
        Generate a unique 6-digit PIN (100000-999999).
        """
        max_attempts = 50
        for _attempt in range(max_attempts):
            random_pin = random.randint(100000, 999999)
            pin_already_exists = PairingDevice.objects.filter(pin_code=random_pin).exists()
            if not pin_already_exists:
                return random_pin
        raise RuntimeError("Unable to generate a unique PIN after multiple attempts")
