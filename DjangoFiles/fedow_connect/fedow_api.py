import json
import logging

import requests
from django.conf import settings

from AuthBillet.models import RsaKey, TibilletUser
from BaseBillet.models import Configuration
from fedow_connect.models import FedowConfig
from fedow_connect.utils import sign_message, data_to_b64, verify_signature

logger = logging.getLogger(__name__)


### GENERIC GET AND POST ###
def _post(config, path, data):
    fedow_domain = config.fedow_domain
    fedow_place_admin_apikey = config.fedow_place_admin_apikey

    # Signature de la requete
    private_key = config.get_private_key()
    signature = sign_message(
        data_to_b64(data),
        private_key,
    ).decode('utf-8')

    # Ici, on s'autovérifie :
    # Assert volontaire. Si non effectué en prod, ce n'est pas grave.
    # logger.debug("_post verify_signature start")
    assert verify_signature(config.get_public_key(),
                            data_to_b64(data),
                            signature)
    # logger.debug("_post verify_signature end")

    session = requests.Session()
    request_fedow = session.post(
        f"https://{fedow_domain}/{path}/",
        headers={
            "Authorization": f"Api-Key {fedow_place_admin_apikey}",
            "Signature": f"{signature}",
            "Content-type": "application/json",
        },
        data=json.dumps(data),
        verify=bool(not settings.DEBUG),
    )
    # TODO: Vérifier la signature de FEDOW
    session.close()
    return request_fedow


def _get(config: FedowConfig, user: TibilletUser, path: str):
    fedow_domain = config.fedow_domain
    fedow_place_admin_apikey = config.fedow_place_admin_apikey

    # Signature de la requete : on signe le path
    private_key = user.get_private_key()
    # Signature de la requete : on signe la clé

    signature = sign_message(
        fedow_place_admin_apikey.encode('utf8'),
        private_key,
    ).decode('utf-8')

    # Ici, on s'autovérifie :
    # Assert volontaire. Si non effectué en prod, ce n'est pas grave.
    assert verify_signature(user.get_public_key(),
                            fedow_place_admin_apikey.encode('utf8'),
                            signature)

    session = requests.Session()
    request_fedow = session.get(
        f"https://{fedow_domain}/{path}/",
        headers={
            'Authorization': f'Api-Key {fedow_place_admin_apikey}',
            "Signature": f"{signature}",
        },
        verify=bool(not settings.DEBUG),
    )
    session.close()
    # TODO: Vérifier la signature de FEDOW
    return request_fedow


class WalletFedow():
    def __init__(self, config):
        config: FedowConfig = config
        if not config:
            config = FedowConfig.get_solo()

    def get_or_create(self, user: TibilletUser):
        email = user.email
        pub_key = user.get_public_key()


class FedowAPI():
    def __init__(self, config: FedowConfig = None):
        self.config = config
        if config is None:
            self.config = FedowConfig.get_solo()

        self.wallet = WalletFedow(self.config)
