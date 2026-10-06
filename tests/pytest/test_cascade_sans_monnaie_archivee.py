"""
La cascade de paiement ne débite jamais une monnaie archivée.
/ The payment cascade never debits an archived currency.

LOCALISATION : tests/pytest/test_cascade_sans_monnaie_archivee.py

RÈGLE MÉTIER TESTÉE
Brief TECH_DOC/SESSIONS/FEDOW_IMPORT/briefs/ter.md, point 1 (décision du mainteneur :
« l'exclure de la cascade »).
- Pour payer (caisse, tireuse), la cascade choisit, catégorie par catégorie (TNF, puis
  TLF, puis FED), la première monnaie de `AssetService.obtenir_assets_accessibles`, triée
  par nom. Une monnaie archivée n'est plus proposée au paiement : elle n'est jamais
  choisie, même quand son nom passe en premier et qu'elle est encore `active`.
- Les jetons qui restent sur une monnaie archivée ne sont pas perdus : la liste des
  soldes d'une carte les montre encore, et le vidage de la carte en caisse
  (`WalletService.rembourser_en_especes`) les rend en espèces.
/ The cascade skips archived currencies; their remaining tokens stay visible in the
balances and are still refunded when the card is emptied.

SIMULATIONS
- Tout se passe dans le lieu dédié `test_cascade_monnaie_archivee` (`FastTenantTestCase`,
  schéma cloné). Chaque test tourne dans une transaction annulée à la fin : les
  monnaies, portefeuilles, cartes, jetons et transactions disparaissent. Rien n'est
  écrit dans `lespass` ni dans un lieu de démo.
- La monnaie archivée garde `active=True` : c'est l'état laissé sur la base de dev par
  l'E2E de fédération (`tests/e2e/test_federation_asset_fedow_core.py`), cause de l'échec
  du test C1 de la tireuse.
- Aucun appel réseau : la carte a un portefeuille local (`wallet_ephemere`), le Fedow
  distant n'est jamais interrogé.
/ Dedicated test venue, rolled-back transaction per test, no network.

Lancer / Run : make test ARGS="tests/pytest/test_cascade_sans_monnaie_archivee.py"
"""

import uuid

from django.db import connection
from django.db import transaction as transaction_de_la_base
from django_tenants.test.cases import FastTenantTestCase

from AuthBillet.models import Wallet
from controlvanne.billing import obtenir_contexte_cashless
from fedow_core.models import Asset, Token
from fedow_core.services import AssetService, WalletService
from QrcodeCashless.models import CarteCashless


class TestCascadeSansMonnaieArchivee(FastTenantTestCase):
    """
    La cascade de paiement et les monnaies archivées, dans le lieu dédié.
    / The payment cascade and archived currencies, in the dedicated venue.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_cascade_monnaie_archivee"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-cascade-monnaie-archivee.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test cascade monnaie archivee"

    def setUp(self):
        # La transaction du test précédent a été annulée : on se replace sur le lieu.
        # / Back on the venue after the previous rolled-back test.
        connection.set_tenant(self.tenant)

        self.portefeuille_du_lieu = Wallet.objects.create(
            name=f"Portefeuille du lieu cascade {uuid.uuid4().hex[:8]}",
            origin=self.tenant,
        )

        # Deux monnaies locales (TLF) du lieu, toutes deux actives. Le nom de la monnaie
        # archivée commence par « 0 » : triée par nom, elle passe en PREMIER.
        # / Two local currencies, both active; the archived one sorts first by name.
        suffixe_unique = uuid.uuid4().hex[:8]
        self.monnaie_archivee = Asset.objects.create(
            name=f"0 Monnaie archivee {suffixe_unique}",
            currency_code="EUR",
            category=Asset.TLF,
            tenant_origin=self.tenant,
            wallet_origin=self.portefeuille_du_lieu,
            active=True,
            archive=True,
        )
        self.monnaie_en_service = Asset.objects.create(
            name=f"1 Monnaie en service {suffixe_unique}",
            currency_code="EUR",
            category=Asset.TLF,
            tenant_origin=self.tenant,
            wallet_origin=self.portefeuille_du_lieu,
            active=True,
            archive=False,
        )

    # ------------------------------------------------------------------ #
    #  Outils / Helpers                                                   #
    # ------------------------------------------------------------------ #

    def creer_une_carte_avec_des_jetons(self, monnaie, montant_en_centimes):
        """
        Une carte anonyme, avec un portefeuille local crédité sur la monnaie donnée.
        / An anonymous card whose local wallet is credited in the given currency.
        """
        identifiant_de_la_carte = uuid.uuid4().hex[:8].upper()
        portefeuille_de_la_carte = Wallet.objects.create(
            name=f"Portefeuille carte cascade {identifiant_de_la_carte}",
            origin=self.tenant,
        )
        carte = CarteCashless.objects.create(
            tag_id=identifiant_de_la_carte,
            number=identifiant_de_la_carte,
            wallet_ephemere=portefeuille_de_la_carte,
        )
        with transaction_de_la_base.atomic():
            WalletService.crediter(
                wallet=portefeuille_de_la_carte,
                asset=monnaie,
                montant_en_centimes=montant_en_centimes,
            )
        return carte

    # ------------------------------------------------------------------ #
    #  T1 — La cascade ne choisit jamais une monnaie archivée             #
    # ------------------------------------------------------------------ #

    def test_cascade_ignore_une_monnaie_archivee(self):
        """
        `AssetService.obtenir_assets_accessibles` ne rend pas la monnaie archivée ; la
        première monnaie TLF qu'elle rend (le choix de la caisse et de la tireuse) est la
        monnaie en service.
        / The archived currency is not returned; the first TLF is the one in service.
        """
        monnaies_accessibles = AssetService.obtenir_assets_accessibles(self.tenant)

        uuids_des_monnaies_accessibles = set(
            monnaies_accessibles.values_list("uuid", flat=True)
        )
        assert self.monnaie_archivee.uuid not in uuids_des_monnaies_accessibles, (
            "Une monnaie archivée ne doit plus être proposée au paiement."
        )
        assert self.monnaie_en_service.uuid in uuids_des_monnaies_accessibles

        monnaie_tlf_choisie = monnaies_accessibles.filter(category=Asset.TLF).first()
        assert monnaie_tlf_choisie == self.monnaie_en_service, (
            f"La cascade a choisi « {monnaie_tlf_choisie} » au lieu de la monnaie en "
            "service."
        )

    def test_cascade_de_la_tireuse_ignore_une_monnaie_archivee(self):
        """
        La cascade de la tireuse (`controlvanne.billing.obtenir_contexte_cashless`)
        contient la monnaie en service et jamais la monnaie archivée.
        / The tap cascade holds the currency in service, never the archived one.
        """
        carte = self.creer_une_carte_avec_des_jetons(
            self.monnaie_en_service, montant_en_centimes=1000
        )

        contexte_de_paiement = obtenir_contexte_cashless(carte)

        assert contexte_de_paiement is not None
        monnaies_de_la_cascade = contexte_de_paiement["cascade_assets"]
        assert self.monnaie_archivee not in monnaies_de_la_cascade, (
            "La tireuse ne doit jamais débiter une monnaie archivée."
        )
        assert self.monnaie_en_service in monnaies_de_la_cascade

    # ------------------------------------------------------------------ #
    #  T2 — Les jetons d'une monnaie archivée restent visibles et rendus  #
    # ------------------------------------------------------------------ #

    def test_vidage_et_soldes_voient_encore_une_monnaie_archivee(self):
        """
        Une carte a 7,00 € sur la monnaie archivée du lieu :
        - la liste des soldes de la carte (`WalletService.obtenir_tous_les_soldes`) montre
          ce jeton ;
        - le vidage de la carte (`WalletService.rembourser_en_especes`) le rend en
          espèces : 700 centimes de monnaie locale, solde à 0 ensuite.
        / A token on an archived currency is still listed and refunded in cash.
        """
        carte = self.creer_une_carte_avec_des_jetons(
            self.monnaie_archivee, montant_en_centimes=700
        )
        portefeuille_de_la_carte = carte.wallet_ephemere

        monnaies_des_soldes = []
        for jeton in WalletService.obtenir_tous_les_soldes(portefeuille_de_la_carte):
            monnaies_des_soldes.append(jeton.asset)
        assert self.monnaie_archivee in monnaies_des_soldes, (
            "Le solde sur une monnaie archivée doit rester visible."
        )

        resultat_du_vidage = WalletService.rembourser_en_especes(
            carte=carte,
            tenant=self.tenant,
            receiver_wallet=self.portefeuille_du_lieu,
            ip="127.0.0.1",
            vider_carte=False,
        )

        assert resultat_du_vidage["total_tlf_centimes"] == 700
        assert resultat_du_vidage["total_centimes"] == 700
        solde_apres_le_vidage = Token.objects.get(
            wallet=portefeuille_de_la_carte, asset=self.monnaie_archivee
        ).value
        assert solde_apres_le_vidage == 0
