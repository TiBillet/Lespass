import json
import logging
import uuid
from datetime import datetime
from uuid import UUID, uuid4

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.signing import TimestampSigner
from django.db import connection
from django.utils import timezone
from django_tenants.postgresql_backend.base import FakeTenant

from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import Configuration, Membership, Product
from fedow_connect.models import FedowConfig
from fedow_connect.utils import sign_message, data_to_b64, verify_signature, rsa_decrypt_string
from fedow_connect.validators import WalletValidator, AssetValidator, TransactionValidator, \
    PaginatedTransactionValidator, CardValidator, QrCardValidator

logger = logging.getLogger(__name__)


### GENERIC GET AND POST ###
def _post(fedow_config: FedowConfig = None,
          user: TibilletUser = None,
          data: dict = None,
          path: str = None,
          apikey: str = None):
    fedow_domain = fedow_config.fedow_domain()
    now = f"{datetime.now().isoformat()}"

    # Pour la création, on prend la clé api de Root. On rempli apikey
    # Si vide, on prend la clé du lieu du tenant
    if apikey is None:
        # Pour la création, on prend la clé api de Root. apikey est donné en arguement.
        # Si vide, on prend la clé du lieu du tenant
        apikey = fedow_config.get_fedow_place_admin_apikey()
    headers = {
        "Date": f"{now}",
        'Authorization': f'Api-Key {apikey}',
        "Content-type": "application/json",
    }

    # Si un user est donné, on indique son wallet dans le header et on le signe avec now
    if user:
        # Signature de la requete
        signature = sign_message(
            data_to_b64(data),
            user.get_private_key(),
        ).decode('utf-8')

        # Ici, on s'autovérifie :
        # Assert volontaire. Si non effectué en prod, ce n'est pas grave.
        # logger.debug("_post verify_signature start")
        if not verify_signature(user.get_public_key(),
                                data_to_b64(data),
                                signature):
            raise Exception("Signature auto verification failed")

        headers.update({
            "Wallet": f"{user.wallet.uuid}" if user.wallet else "",
            "Signature": f"{signature}",
        })

    session = requests.Session()
    request_fedow = session.post(
        f"https://{fedow_domain}/{path}/",
        headers=headers,
        data=json.dumps(data),
        verify=bool(not settings.DEBUG),
    )

    # TODO: Vérifier la signature de FEDOW avec root_config.fedow_primary_pub_pem

    session.close()
    return request_fedow


def _get(fedow_config: FedowConfig = None,
         user: TibilletUser = None,
         path: str = None,
         apikey: str = None):
    fedow_domain = fedow_config.fedow_domain()
    now = f"{datetime.now().isoformat()}"

    if apikey is None:
        # Pour la création, on prend la clé api de Root. apikey est donné en arguement.
        # Si vide, on prend la clé du lieu du tenant
        apikey = fedow_config.get_fedow_place_admin_apikey()
    headers = {
        "Date": f"{now}",
        'Authorization': f'Api-Key {apikey}',
    }

    # Si un user est donné, on indique son wallet dans le header et on le signe avec now
    if user:
        # On signe le message
        message = f"{user.wallet.uuid}:{now}"
        signature = sign_message(
            message.encode('utf8'),
            user.get_private_key(),
        ).decode('utf-8')

        # Ici, on s'autovérifie :
        if not verify_signature(user.get_public_key(),
                                message.encode('utf8'),
                                signature):
            raise Exception("Signature auto verification failed")

        headers.update({
            "Wallet": f"{user.wallet.uuid}",
            "Signature": f"{signature}",
        })

    session = requests.Session()
    request_fedow = session.get(
        f"https://{fedow_domain}/{path}/",
        headers=headers,
        verify=bool(not settings.DEBUG),
    )
    session.close()

    # TODO: Vérifier la signature de réponse FEDOW
    return request_fedow


class AssetFedow():
    def __init__(self, fedow_config: FedowConfig or None = None):
        self.fedow_config: FedowConfig = fedow_config
        if fedow_config is None:
            self.fedow_config = FedowConfig.get_solo()

    # def list(self):
    #     response_asset = _get(self.config, ['asset', ])
    #     if response_asset.status_code == 200:
    #         serialized_assets = AssetValidator(data=response_asset.json(), many=True)
    #         if serialized_assets.is_valid():
    #             return serialized_assets.validated_data
    #         logger.error(serialized_assets.errors)
    #         raise Exception(f"{serialized_assets.errors}")

    def retrieve(self, uuid: uuid4 = None):
        response_asset = _get(self.fedow_config, path=f'asset/{UUID(uuid)}/retrieve_membership_asset')

        if response_asset.status_code == 200:
            serialized_assets = AssetValidator(data=response_asset.json(), many=False)
            if serialized_assets.is_valid():
                return serialized_assets.validated_data
            logger.error(serialized_assets.errors)
            raise Exception(f"{serialized_assets.errors}")
        logger.error(response_asset)
        raise Exception(f"{response_asset.status_code}")

    def get_or_create_asset(self, product: Product = None):
        try:
            asset_serialized = self.retrieve(uuid=f"{product.uuid}")
            return asset_serialized, False

        # Asset n'existe pas, on l'envoie
        except Exception as e:
            logger.info(f"Création de l'asset pour le produit {product.name}")
            config = Configuration.get_solo()
            asset = {
                "uuid": f"{product.pk}",
                "name": f"{product.name} {config.organisation}",
                "currency_code": f"{product.name[:2]}{product.categorie_article[1:]}".upper(),
                "category": f"{product.fedow_category()}",
                "created_at": timezone.now().isoformat()
            }
            response_asset = _post(self.fedow_config, path='asset/create_membership_asset', data=asset)
            if response_asset.status_code == 201:
                serialized_assets = AssetValidator(data=response_asset.json(), many=False)
                if serialized_assets.is_valid():
                    return serialized_assets.validated_data, True
                logger.error(serialized_assets.errors)
                raise Exception(f"{serialized_assets.errors}")
            logger.error(response_asset)
            raise Exception(f"{response_asset.status_code} {response_asset.content}")

    def archive_asset(self, product: Product):
        response_archive_asset = _get(self.fedow_config, path=f'asset/{product.uuid}/archive_asset')
        if response_archive_asset.status_code != 200:
            logger.error(f"archive_asset ERROR {response_archive_asset.status_code} {response_archive_asset.content}")
            raise Exception(
                f"archive_asset ERROR {response_archive_asset.status_code} {response_archive_asset.content}")
        logger.info("Asset archived")


class BadgeFedow():
    def __init__(self, fedow_config: FedowConfig or None = None):
        self.fedow_config: FedowConfig = fedow_config
        if not fedow_config:
            self.fedow_config = FedowConfig.get_solo()

    def badge_in(self, user, product):
        response_badge = _get(
            self.fedow_config,
            user=user,
            path=f'wallet/{product.uuid}/badge',
        )

        if not response_badge.status_code == 201:
            logger.error(f"badge_in ERRORS : {response_badge.status_code}")
            raise Exception(f"badge_in ERRORS : {response_badge.status_code}")

        transaction_serialized = TransactionValidator(data=response_badge.json())
        if transaction_serialized.is_valid():
            return transaction_serialized.validated_data
        else:
            logger.error(f"badge_in wallet_serialized transaction_serialized ERRORS : {transaction_serialized.errors}")
            raise Exception(f"badge_in transaction_serialized ERRORS : {transaction_serialized.errors}")


class MembershipFedow():
    def __init__(self, fedow_config: FedowConfig or None = None):
        self.fedow_config: FedowConfig = fedow_config
        if not fedow_config:
            self.fedow_config = FedowConfig.get_solo()

    def create(self, membership: Membership = None):
        # Si Wallet est None, alors nous en créons ou allons chercher un wallet avec l'email
        membership.refresh_from_db()
        user = membership.user

        # TODO: le faire dans le get_or_create user et ajouter dans les test
        if user.wallet:
            receiver = user.wallet.uuid
        else:
            logger.info(f"Wallet not found for {user.email}")
            wallet_fedow = WalletFedow(self.fedow_config)
            wallet, created = wallet_fedow.get_or_create_wallet(membership.user)
            receiver = wallet.uuid

        # Vérification de l'uuid membership présent coté Fedow
        if not membership.asset_fedow and membership.price:
            fedow_asset = AssetFedow(fedow_config=self.fedow_config)
            serialized_asset, created = fedow_asset.get_or_create_asset(membership.price.product)
            asset_fedow = f"{serialized_asset['uuid']}"
            membership.asset_fedow = asset_fedow
        if not membership.asset_fedow:
            raise Exception("no asset_fedow nor price provided on membership")

        amount = membership.contribution_value
        sender = self.fedow_config.fedow_place_wallet_uuid
        subscription_start_datetime = membership.last_contribution

        subscription_data = {
            "amount": int(amount * 100),
            "sender": f"{sender}",
            "receiver": f"{receiver}",
            "asset": f"{membership.asset_fedow}",
            "subscription_start_datetime": subscription_start_datetime.isoformat(),
        }

        if membership.stripe_paiement.exists():
            subscription_data["metadata"] = {'checkout_session_id_stripe': membership.stripe_paiement.latest(
                'last_action').checkout_session_id_stripe}

        # TODO: Tester lorsqu'on a l'info de la carte
        # if user_card_firstTagId:
        #     subscription['user_card_firstTagId'] = f"{user_card_firstTagId}"
        # if primary_card_fisrtTagId:
        #     subscription['primary_card_fisrtTagId'] = f"{primary_card_fisrtTagId}"

        response_subscription = _post(
            fedow_config=self.fedow_config,
            user=user,
            data=subscription_data,
            path='transaction/create_membership',
        )

        if response_subscription.status_code == 201:
            serialized_transaction = TransactionValidator(data=response_subscription.json())
            if serialized_transaction.is_valid():
                fedow_transaction = serialized_transaction.fedow_transaction
                membership.fedow_transactions.add(fedow_transaction)
                membership.save()  # sauvegarde au cas ou membership.asset_fedow
                if membership.stripe_paiement.exists():
                    membership.stripe_paiement.latest('last_action').fedow_transactions.add(fedow_transaction)
                return serialized_transaction.validated_data

            logger.error(serialized_transaction.errors)
            return serialized_transaction.errors

        else:
            logger.error(response_subscription.json())
            return response_subscription.status_code

    # def retrieve(self, wallet: uuid4 = None):
    #     response_sub = _get(self.config, ['subscription', f"{UUID(wallet)}"])
    #     if response_sub.status_code == 200:
    #         return response_sub
    #
    #     raise Exception(f"{response_sub.status_code}")


class WalletFedow():
    def __init__(self, fedow_config):
        self.fedow_config: FedowConfig = fedow_config
        if not fedow_config:
            self.fedow_config = FedowConfig.get_solo()

    def cached_retrieve_by_signature(self, user):
        if not user.wallet:
            wallet = self.get_or_create_wallet(user)
        try:
            # get_or_set va toujours faire la fonction callable avant de vérifier le cache.
            # Solution : soit retirer les () dans le callable, soit utiliser cache.lambda
            serialized_wallet = cache.get_or_set(f"wallet_user_{user.wallet.uuid}",
                                                 lambda: self.retrieve_by_signature(user), 10)
        except KeyError as e:
            # Exception soulevé parfois : AttributeError: 'NoneType' object has no attribute 'recv'
            # A investiguer, peut être que l'écriture du cache est en concurence avec une autre écriture
            # réalisée en même temps, avec les requetes async
            logger.warning(f"cached_retrieve_by_signature : {e} - fetch from fedow without cache.")
            serialized_wallet = self.retrieve_by_signature(user)
        except Exception as e:
            logger.error(f"cached_retrieve_by_signature : {e}")
            raise e

        return serialized_wallet

    def retrieve_by_signature(self, user):
        response_link = _get(
            self.fedow_config,
            user=user,
            path=f'wallet/retrieve_by_signature',
        )

        if not response_link.status_code == 200:
            logger.error(f"retrieve_by_signature ERRORS : {response_link.status_code}")
            raise Exception(f"retrieve_by_signature ERRORS : {response_link.status_code}")

        wallet_serialized = WalletValidator(data=response_link.json())
        if wallet_serialized.is_valid():
            return wallet_serialized
        else:
            logger.error(f"retrieve_by_signature wallet_serialized ERRORS : {wallet_serialized.errors}")
            raise Exception(f"retrieve_by_signature wallet_serialized ERRORS : {wallet_serialized.errors}")

    def get_or_create_wallet(self, user: TibilletUser):
        email = user.email.lower()
        response_link = _post(self.fedow_config, user=user, path='wallet/get_or_create', data={
            "email": email,
            "public_pem": user.get_public_pem(),
        })

        if response_link.status_code in [200, 201]:
            # Création du wallet dans la base de donnée s'il n'existe pas
            if not user.wallet:
                user.wallet = Wallet.objects.get_or_create(uuid=UUID(response_link.json()))[0]
                user.save()
                logger.info(f"user {user} tout neuf, on ajoute le wallet : {user.wallet}")

            # Wallet existe déja et est lié à l'user, on compare avec celui envoyé par Fedow
            elif user.wallet.uuid != UUID(response_link.json()):
                raise Exception("Wallet and member mismatch")

            # Si c'est 201, c'est created :
            created = False if response_link.status_code == 200 else True
            return user.wallet, created

        raise Exception(f"Wallet FedowAPI create_from_email response : {response_link.status_code}")

    def get_federated_token_refill_checkout(self, user: TibilletUser):
        # Pour que le retour Fedow soit vérifié par un élément de signature créé lors de la demande
        signer = TimestampSigner()
        signed_data = signer.sign({
            "origin_request_wallet": f"{user.wallet.uuid}"
        })
        response_checkout = _post(
            self.fedow_config,
            user=user,
            path=f'wallet/get_federated_token_refill_checkout',
            data={"lespass_signed_data": signed_data},
        )

        if response_checkout.status_code == 417:
            logger.warning("get_federated_token_refill_checkout. RETURN FEDOW : No stripe key provided on .env -> 417")
            return None

        if response_checkout.status_code != 202:
            logger.error(response_checkout.json())
            raise Exception(response_checkout.json())

        stripe_checkout_url = response_checkout.json()
        return stripe_checkout_url

    def retrieve_from_refill_checkout(self, user: TibilletUser, pk: uuid4):
        # Vérifie que le paiement stripe a bien été validé coté Fedow.
        response_checkout = _get(
            self.fedow_config,
            user=user,
            path=f'wallet/{pk}/retrieve_from_refill_checkout'
        )

        if response_checkout.status_code == 402:
            logger.warning(
                f"retrieve_from_refill_checkout - Checkout Stripe non paid : 402 - {response_checkout.json()}")
            return None

        if not response_checkout.status_code == 200:
            logger.error(
                f"retrieve_from_refill_checkout ERRORS : {response_checkout.status_code} - {response_checkout.json()}")
            raise Exception(
                f"retrieve_from_refill_checkout ERRORS : {response_checkout.status_code} - {response_checkout.json()}")

        wallet_serialized = WalletValidator(data=response_checkout.json())
        if not wallet_serialized.is_valid():
            logger.error(f"retrieve_by_signature wallet_serialized ERRORS : {wallet_serialized.errors}")
            raise Exception(f"retrieve_by_signature wallet_serialized ERRORS : {wallet_serialized.errors}")

        return wallet_serialized


class PlaceFedow():
    def __init__(self, fedow_config, admin=None):
        self.fedow_config: FedowConfig = fedow_config
        if not fedow_config:
            self.fedow_config = FedowConfig.get_solo()

        if not fedow_config.can_fedow():
            # Premier contact entre une nouvelle place (nouveau tenant) et Fedow
            self.create_place(admin=admin)

    def link_cashless_to_place(self, admin):
        link_response = _get(fedow_config=self.fedow_config,
                             user=admin,
                             path='place/link_cashless_to_place')

        if not link_response.status_code == 201:
            logger.error(f"link_cashless_to_place ERRORS : {link_response.status_code}")
            raise Exception(f"link_cashless_to_place ERRORS : {link_response.status_code}")

        rsa_cypher_message = link_response.json()['rsa_cypher_message']
        temp_key = rsa_decrypt_string(utf8_enc_string=rsa_cypher_message, private_key=admin.get_private_key())
        return temp_key

    def create_place(self, admin: TibilletUser = None, place_name=None):
        # Premier contact entre une nouvelle place (nouveau tenant) et Fedow
        # Se lance automatiquement si can_fedow() is false

        if any([
            self.fedow_config.fedow_place_uuid,
            self.fedow_config.fedow_place_wallet_uuid,
            self.fedow_config.fedow_place_admin_apikey,
        ]):
            raise Exception("Place already created")

        tenant = connection.tenant
        tenant_config = Configuration.get_solo()

        # Si on est en mode test/debug :
        if type(tenant) == FakeTenant and settings.DEBUG:
            logger.warning("FakeTenant in DEBUG mode")
            from Customers.models import Client
            tenant = Client.objects.get(schema_name='meta')
            tenant_domain = "test.tibillet.localhost"
        else:
            tenant_domain = tenant_config.domain()

        if place_name is None:
            place_name = tenant_config.organisation

        if admin is None:
            # Un seul admin lors de la création du lieu est présent.
            User: TibilletUser = get_user_model()
            admin = User.objects.get(client_admin=tenant)

        # Pour la création, on prend la clé "create_place_apikey" de Root
        apikey = self.fedow_config.get_fedow_create_place_apikey()
        data = {
            'place_name': place_name,
            'place_domain': tenant_domain,
            'admin_email': admin.email,
            'admin_pub_pem': admin.get_public_pem(),
        }

        request_for_new_place = _post(fedow_config=self.fedow_config,
                                      user=admin,
                                      path='place',
                                      data=data, apikey=apikey)

        if request_for_new_place.status_code != 201:
            raise Exception(
                f"PlaceFedow Create : {request_for_new_place.status_code} : {request_for_new_place.content}")

        new_place_data = request_for_new_place.json()

        wallet = Wallet.objects.create(
            # display_name=tenant_config.organisation,
            uuid=new_place_data['wallet']
        )

        self.fedow_config.wallet = wallet
        self.fedow_config.fedow_place_uuid = new_place_data['uuid']
        self.fedow_config.fedow_place_wallet_uuid = new_place_data['wallet']
        self.fedow_config.set_fedow_place_admin_apikey(new_place_data['key'])
        self.fedow_config.save()

        logger.info(f"Place and Fedow linked : wallet {new_place_data['wallet']}")


class NFCcardFedow():
    def __init__(self, fedow_config: FedowConfig or None = None):
        self.fedow_config: FedowConfig = fedow_config
        if fedow_config is None:
            self.config = FedowConfig.get_solo()

    def retrieve_card_by_signature(self, user: TibilletUser):
        response_get_card = _get(
            self.fedow_config,
            user=user,
            path=f'card/retrieve_card_by_signature',
        )

        if not response_get_card.status_code == 200:
            logger.error(f"retrieve_by_signature ERRORS : {response_get_card.status_code}")
            raise Exception(f"retrieve_by_signature ERRORS : {response_get_card.status_code}")

        card_serialized = CardValidator(data=response_get_card.json(), many=True)
        if card_serialized.is_valid():
            return card_serialized.validated_data
        else:
            logger.error(f"retrieve_by_signature card_serialized ERRORS : {card_serialized.errors}")
            raise Exception(f"retrieve_by_signature card_serialized ERRORS : {card_serialized.errors}")

    def lost_my_card_by_signature(self, user, number_printed):
        response_lost_my_card = _post(
            self.fedow_config,
            user=user,
            path=f'card/lost_my_card_by_signature',
            data={'number_printed': number_printed}
        )

        if not response_lost_my_card.status_code == 200:
            logger.error(f"retrieve_by_signature ERRORS : {response_lost_my_card.status_code}")
            raise Exception(f"retrieve_by_signature ERRORS : {response_lost_my_card.status_code}")
        return True

    def qr_retrieve(self, qrcode_uuid: uuid4):
        # On vérifie que l'uuid soit bien un uuid :
        checked_uuid = uuid.UUID(str(qrcode_uuid))
        response_qr = _get(self.fedow_config, path=f'card/{checked_uuid}/qr_retrieve')
        if not response_qr.status_code == 200:
            return None

        serialized_card = QrCardValidator(data=response_qr.json())
        if not serialized_card.is_valid():
            logger.error(serialized_card.errors)
            raise Exception(serialized_card.errors)

        return serialized_card.validated_data

    def linkwallet_cardqrcode(self, user: TibilletUser = None, qrcode_uuid: uuid4 = None):
        checked_uuid = uuid.UUID(str(qrcode_uuid))

        response_link = _post(
            fedow_config=self.fedow_config,
            user=user,
            data={
                "wallet": f"{user.wallet.uuid}",
                "card_qrcode_uuid": f"{checked_uuid}",
            },
            path='wallet/linkwallet_cardqrcode',
        )

        if response_link.status_code != 200:
            logger.error(f"linkwallet_cardqrcode : {response_link.status_code} {response_link.json()}")
            return False

        validated_card = CardValidator(data=response_link.json())
        if not validated_card.is_valid():
            logger.error(validated_card.errors)
            return False

        return validated_card.validated_data


class TransactionFedow():
    def __init__(self, fedow_config: FedowConfig or None = None):
        self.fedow_config: FedowConfig = fedow_config
        if fedow_config is None:
            self.config = FedowConfig.get_solo()


    def retrieve(self, uuid):
        response = _get(self.fedow_config, path=f'transaction/{uuid}')
        if response.status_code == 200:
            serialized_transaction = TransactionValidator(data=response.json())
            if serialized_transaction.is_valid():
                validated_data = serialized_transaction.validated_data
                return validated_data
            logger.error(serialized_transaction.errors)
            return serialized_transaction.errors
        else:
            logger.error(response.json())
            return response.status_code


    def get_from_hash(self, hash_fedow: str = None):
        response_hash = _get(self.fedow_config, path=f'transaction/{hash_fedow}/get_from_hash')
        if response_hash.status_code == 200:
            serialized_transaction = TransactionValidator(data=response_hash.json())
            if serialized_transaction.is_valid():
                validated_data = serialized_transaction.validated_data
                return validated_data
            logger.error(serialized_transaction.errors)
            return serialized_transaction.errors

        else:
            logger.error(response_hash.json())
            return response_hash.status_code

    def paginated_list_by_wallet_signature(self, user):
        response_link = _get(
            self.fedow_config,
            user=user,
            path=f'transaction/paginated_list_by_wallet_signature'
        )

        if not response_link.status_code == 200:
            logger.error(f"paginated_list_by_wallet_signature ERRORS : {response_link.status_code}")
            raise Exception(f"paginated_list_by_wallet_signature ERRORS : {response_link.status_code}")

        paginated_transactions_serialized = PaginatedTransactionValidator(data=response_link.json())

        if paginated_transactions_serialized.is_valid():
            return paginated_transactions_serialized
        else:
            logger.error(f"retrieve_by_signature wallet_serialized ERRORS : {paginated_transactions_serialized.errors}")
            raise Exception(
                f"retrieve_by_signature wallet_serialized ERRORS : {paginated_transactions_serialized.errors}")




# from fedow_connect.fedow_api import FedowAPI
class FedowAPI():
    def __init__(self, fedow_config: FedowConfig = None, admin=None):
        self.fedow_config = fedow_config
        if fedow_config is None:
            self.fedow_config = FedowConfig.get_solo()

        self.wallet = WalletFedow(fedow_config=self.fedow_config)
        self.place = PlaceFedow(fedow_config=self.fedow_config, admin=admin)
        self.membership = MembershipFedow(fedow_config=self.fedow_config)
        self.asset = AssetFedow(fedow_config=self.fedow_config)
        self.transaction = TransactionFedow(fedow_config=self.fedow_config)
        self.NFCcard = NFCcardFedow(fedow_config=self.fedow_config)
        self.badge = BadgeFedow(fedow_config=self.fedow_config)

    def handshake(self):
        pass
