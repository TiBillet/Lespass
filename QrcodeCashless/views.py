"""
import logging
from datetime import datetime
from decimal import Decimal

import dateutil.parser
import json
import requests
from django.contrib import messages
from django.db import connection
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from rest_framework import status
from rest_framework.generics import get_object_or_404

from ApiBillet.serializers import get_or_create_user, get_or_create_price_sold
from BaseBillet.models import Configuration, Product, LigneArticle, Price, Paiement_stripe, Membership
from PaiementStripe.views import CreationPaiementStripe
from QrcodeCashless.models import CarteCashless
from TiBillet import settings

logger = logging.getLogger(__name__)
"""

'''
def first_true(iterable, default=False, pred=None):
    """
    Returns the first true value in the iterable.
    If no true value is found, returns *default*

    If *pred* is not None, returns the first item
    for which pred(item) is true.

    ex :
    # Trouvez le premier élément vrai dans la liste
    first_true([False, False, True, False])  # retourne True

    # Utilisez un prédicat pour trouver le premier élément qui est supérieur à 2
    first_true([1, 2, 3, 4], pred=lambda x: x > 2)  # retourne 3

    # Utilisez une valeur par défaut si aucun élément n'est vrai
    first_true([False, False, False], default='No true values found')  # retourne 'No true values found'
    """
    return next(filter(pred, iterable), default)
'''

"""
def get_domain(request):
    absolute_uri = request.build_absolute_uri()
    for domain in request.tenant.domains.all():
        if domain.domain in absolute_uri:
            return domain.domain

    raise Http404
"""



"""
class gen_one_bisik(View):
    # Vue déclenchée lorsqu'on scanne un qrcode de la première génération Bisik avec m.tibllet et qsdf
    def get(self, request, numero_carte):
        logger.info(f"gen_one_bisik : {numero_carte} - tenant : {connection.tenant}")
        if connection.tenant.name != "m":
            raise Http404
        carte = get_object_or_404(CarteCashless, number=numero_carte)
        address = request.build_absolute_uri()
        return HttpResponseRedirect(
            address.replace("://m.", "://bisik.").replace(f"{carte.number}", f"qr/{carte.uuid}"))
"""


"""
def check_carte_local(uuid):
    # On vérifie que la carte existe bien en local
    # et que la requete vienne du domain du Client tenant.
    # :param uuid:
    # :return:
    carte = get_object_or_404(CarteCashless, uuid=uuid)
    logger.info(f"**1** check_carte_local : {carte}")
    return carte
"""
"""


def check_carte_serveur_cashless(config, uuid: str) -> dict or HttpResponse:
    # Avec uniquement l'uuid de la carte, on vérifie qu'elle existe coté serveur cashless
    # et on récupère les informations de l'utilisateur s'il existe.
    # 
    # :param config:
    # :param uuid:
    # :return:
    if not config.server_cashless:
        return HttpResponse(
            "L'adresse du serveur cashless n'est pas renseignée dans la configuration de la billetterie.")
    if not config.get_stripe_api():
        return HttpResponse(
            "Pas d'information de configuration pour paiement en ligne.")

    # on questionne le serveur cashless pour voir si la carte existe :
    sess = requests.Session()
    try:
        reponse = sess.post(
            f'{config.server_cashless}/api/billetterie_endpoint',
            headers={
                'Authorization': f'Api-Key {config.key_cashless}'
            },
            data={
                'uuid': f'{uuid}',
            },
            verify=bool(not settings.DEBUG),
            timeout=2,
        )

    except requests.exceptions.ConnectionError:
        reponse = HttpResponse("Serveur non disponible. Merci de revenir ultérieurement.",
                               status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except requests.exceptions.Timeout:
        reponse = HttpResponse("Serveur non disponible. Merci de revenir ultérieurement.",
                               status=status.HTTP_504_GATEWAY_TIMEOUT)


    sess.close()
    if reponse.status_code == 200:
        data_cashless = json.loads(reponse.json())
        logger.info(f"**2** check_carte_serveur_cashless : {data_cashless}")
        return data_cashless

    if reponse.status_code == 400:
        # Carte non trouvée
        logger.error(f"Erreur serveur cashless Carte inconnue : {reponse.status_code} - {reponse.content}")
        return HttpResponse('Carte inconnue', status=reponse.status_code)
    elif reponse.status_code == 403:
        # Clé api HS
        logger.error(f"Erreur serveur cashless Clé api HS Forbidden : {reponse.status_code} - {reponse.content}")
        return HttpResponse('Forbidden', status=reponse.status_code)
    else:
        logger.error(f"Erreur serveur cashless : {reponse.status_code} - {reponse.content}")
        return HttpResponse(f"Erreur serveur cashless : {reponse.status_code} - {reponse.content}",
                            status=reponse.status_code)
"""

"""
class GetArticleRechargeCashless():
    def __init__(self,
                 carte: CarteCashless = None,
                 montant_recharge: int = None,
                 config: Configuration = None):

        if not config:
            config = Configuration.get_solo()
        self.config = config

        self.montant_recharge = montant_recharge
        self.carte = carte
        self.product = self.get_product()
        self.price = self.get_price()

    def get_product(self):
        # TODO: Checker si l'image existe. Sinon erreur lorsqu'on change l'image ensuite ...
        carte = self.carte

        categorie = Product.RECHARGE_CASHLESS
        if self.config.federated_cashless:
            categorie = Product.RECHARGE_FEDERATED

        product, created = Product.objects.get_or_create(
            name=f"Recharge Carte {carte.detail.origine.name} v{carte.detail.generation}",
            categorie_article=categorie,
            img=carte.detail.img,
        )

        return product

    def get_price(self):
        product = self.product
        montant_recharge = self.montant_recharge

        price, created = Price.objects.get_or_create(
            product=product,
            name=f"{montant_recharge}€",
            prix=int(montant_recharge),
        )

        return price
"""

"""
class GetMembership():
    def __init__(self, user, config: Configuration = None, form_data: dict = None, cashless_card: CarteCashless = None):

        self.user = user
        self.cashless_card = cashless_card
        logger.info(f"**4** GetMembership : {user} - form_data : {form_data} - carte : {cashless_card}")

        self.form_data = form_data
        if form_data is None:
            self.form_data = {}

        self.config = config
        if config is None:
            self.config = Configuration.get_solo()

        # Il est censé n'y avoir qu'une seule adhésion envoyable en cashless
        self.product = Product.objects.get(send_to_cashless=True)

        self.data_cashless = self.data_check_cashless()
        self.membership = self._membership()

        # On vérifie les infos minimales de l'adhérent
        self.first_name = self._first_name()
        self.last_name = self._last_name()
        self.phone = self._phone()
        self.pseudo = self._pseudo()
        # Renvoie True si les tout est True
        self.detail_submitted = all([self.first_name, self.last_name, self.phone])

        self.a_jour_cotisation = self._a_jour_cotisation()

        self.reponse_sync_data = self.get_and_sync_user_data()

    def get_and_sync_user_data(self):
        # Synchronise les données de l'utilisateur avec celles du serveur cashless
        # et
        # Requete vers cashless pour savoir quel niveau d'information possède le serveur.
        # Suivant le code de statut de la réponse HTTP, on peut réclamer les informations manquantes
        # :param config:
        # :param data:
        # :return:

        # Si on cherche l'adhésion depuis un scan de carte, on aura l'info.
        # On vérifie les infos présentes dans le serveur cashless.
        # Et on les remplit si elles sont manquantes.
        # Utile lorsque la personne veut "payer avec un vrai humain", cela envoie l'info des input de la page avant le paiement,
        # pour pouvoir être retrouvé sur la page d'admin du cashless.

        if self.cashless_card and self.user:
            data = {
                'email': self.user.email,
                'prenom': self.first_name,
                'name': self.last_name,
                'tel': self.phone,
                'uuid_carte': self.cashless_card.uuid,
            }

            sess = requests.Session()

            response = sess.post(
                f'{self.config.server_cashless}/api/billetterie_qrcode_adhesion',
                headers={
                    'Authorization': f'Api-Key {self.config.key_cashless}'
                },
                data=data,
                verify=bool(not settings.DEBUG)
            )

            sess.close()
            logger.info(
                f"{timezone.now()} get_and_sync_user_data -> /api/billetterie_qrcode_adhesion : {response.status_code} - {response.content}")
            return response

        logger.info(f"**5** get_and_sync_user_data")
        return False

    def _first_name(self):
        if self.membership.first_name:
            return self.membership.first_name
        elif self.data_cashless.get('prenom'):
            self.membership.first_name = self.data_cashless.get('prenom')
            self.membership.save()
        elif self.form_data.get('prenom'):
            self.membership.first_name = self.form_data.get('prenom')
            self.membership.save()
        return self.membership.first_name

    def _last_name(self):
        if self.membership.last_name:
            return self.membership.last_name
        elif self.data_cashless.get('name'):
            self.membership.last_name = self.data_cashless.get('name')
            self.membership.save()
        elif self.form_data.get('name'):
            self.membership.last_name = self.form_data.get('name')
            self.membership.save()
        return self.membership.last_name

    def _pseudo(self):
        if self.membership.pseudo:
            return self.membership.pseudo
        elif self.data_cashless.get('pseudo'):
            self.membership.pseudo = self.data_cashless.get('pseudo')
            self.membership.save()
        elif self.form_data.get('pseudo'):
            self.membership.pseudo = self.form_data.get('pseudo')
            self.membership.save()
        return self.membership.pseudo

    def _phone(self):
        if self.membership.phone:
            return self.membership.phone
        elif self.data_cashless.get('tel'):
            self.membership.phone = self.data_cashless.get('tel')
            self.membership.save()
        elif self.form_data.get('tel'):
            self.membership.phone = self.form_data.get('tel')
            self.membership.save()
        return self.membership.phone

    def _a_jour_cotisation(self):
        if self.membership:
            if self.membership.is_valid():
                return True

        if self.data_cashless.get('a_jour_cotisation'):
            prices_adhesion = self.product.prices.all()
            data = self.data_cashless
            price: Price = prices_adhesion.filter(prix=Decimal(data.get('cotisation'))).first()
            if price:
                self.membership.price = price
            self.membership.date_added = dateutil.parser.parse(data.get('date_ajout'))
            self.membership.first_contribution = datetime.strptime(data.get('date_inscription'), '%Y-%m-%d').date()
            self.membership.last_contribution = datetime.strptime(data.get('date_derniere_cotisation'),
                                                                  '%Y-%m-%d').date()
            self.membership.contribution_value = float(data.get('cotisation'))

            self.membership.save()
            return True

        return False

    def _membership(self):
        membership = Membership.objects.filter(
            user=self.user,
            price__product=self.product
        ).first()

        # Si l'adhérent n'a pas de cotisation, on la crée
        # On ajoutera le prix lorsqu'il sera payé
        if not membership:
            logger.info("l'adhérent n'a pas de cotisation, on la crée. On ajoutera price lorsqu'il sera payé")
            membership, created = Membership.objects.get_or_create(
                user=self.user,
                price=None
            )
        return membership

    def data_check_cashless(self) -> dict or None:
        # Va chercher la carte membre dans le serveur cashless.
        # Renvoie le serialiser APIcashless.serializer.MembreSerializer
        # :param user:
        # :param config:
        # :return:
        data = None

        verify = True
        if settings.DEBUG:
            verify = False
        session = requests.session()

        response = session.post(
            f"{self.config.server_cashless}/api/membre_check",
            headers={"Authorization": f"Api-Key {self.config.key_cashless}"},
            data={"email": self.user.email},
            verify=verify)

        if response.status_code == 200:
            data = json.loads(response.content)

        session.close()

        logger.info(f"**5** data_check_cashless -> /api/membre_check : {response.status_code} - {response.content}")
        return data
"""

"""
class WalletValidator:
    def __init__(self,
                 uuid: str = None,
                 config: Configuration = None,
                 data_post: dict = None,
                 ):
        # CREATION DE L'OBJECT WALLET
        # en liaison avec le serveur cashless
        # Ceci peut etre une carte NFC cashless ou QrCode seul dans le futur
        # 
        # :param uuid:
        # :param config:
        # :param user:
        if config == None:
            config = Configuration.get_solo()
        self.config = config

        self.data_post = data_post
        if data_post == None:
            self.data_post = {}
        self.post_email = self.data_post.get('email')

        self.errors = []

        # Check carte coté serveur cashless
        self.carte_serveur_cashless: dict = check_carte_serveur_cashless(config, uuid)

        # Renvoi une carte cashless ou une erreur 404 si le tenant ne correspond pas à l'adresse
        self.carte_local: CarteCashless = check_carte_local(uuid)

        self.user = self._user()

        # self.fiche_membre = GetMembership(
        #     self.user,
        #     config,
        #     form_data=data_post,
        #     cashless_card=self.carte_local
        # ) if self.user else None

    def fiche_membre(self):
        if self.user:
            return GetMembership(
                self.user,
                self.config,
                form_data=self.data_post,
                cashless_card=self.carte_local
            )
        return None

    def _user(self):
        # On vérifie l'utilisateur.
        # On crée alors l'utilisateur s'il n'est pas dans le cashless et on le lie à la carte
        # On prend comme email le premier qui répond vrai (préférence pour le cashless)
        email_user = self.carte_local.user.email if self.carte_local.user else None
        email_cashless = self.carte_serveur_cashless.get('email')

        # Liste ordonnée des emails par ordre de confiance.
        # 1/ User a verifié son mail
        trusted_order = [email_cashless, email_user, self.post_email]
        # En cas de faute de frappe lors de la saisie de l'email à l'acceuil
        # TODO: Faire une verification des emails coté cashless pour ne pas avoir de faute de frappe
        if email_user and self.carte_local.user.is_active:
            trusted_order = [email_user, email_cashless, self.post_email]

        email = first_true(trusted_order)

        if email:
            user = get_or_create_user(email, send_mail=False)
            self.carte_local.user = user
            self.carte_local.save()

            # Première fois que le cashless à ce mail, on a la carte,
            # On lui indique pour qu'il la lie
            if not email_cashless:
                data = {
                    'uuid_carte': self.carte_local.uuid,
                    'email': user.email,
                }
                sess = requests.Session()
                reponse_cashless = sess.post(
                    f'{self.config.server_cashless}/api/billetterie_qrcode_adhesion',
                    headers={
                        'Authorization': f'Api-Key {self.config.key_cashless}'
                    },
                    verify=bool(not settings.DEBUG),
                    data=data)
                sess.close()

                logger.info(
                    f"{timezone.now()} envoi de l'email {user.email} vers le serveur cashless : "
                    f"{reponse_cashless.status_code} - {reponse_cashless.content}")

            logger.info(f"**3** WalletValidator ->  WalletValidator _user : {self.carte_local.user}")
            return self.carte_local.user

        logger.info(f"**3** WalletValidator ->  WalletValidator _user : {self.carte_local.user}")
        return None

    def is_valid(self):
        if len(self.errors) == 0:
            return True
        return False
"""


"""
class index_scan(View):
    # Vue pour les scans de QrCode des cartes cashless
    # En modèle MVT standard, en attendant un full vue.js du front
    template_name = "html5up-dimension/index.html"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configuration = Configuration.get_solo()

    def get(self, request, uuid):
        config = self.configuration

        # Dette technique…
        # Pour rediriger les premières générations de qrcode
        # m.tibillet.re de la raffinerie
        address = request.build_absolute_uri()
        host = address.partition('://')[2]
        sub_addr = host.partition('.')[0]
        if sub_addr == "m":
            logger.warning(f"m_tenant Check : {address}")
            return HttpResponseRedirect(address.replace("://m.", "://raffinerie."))


        if not config.check_serveur_cashless():
            return HttpResponse("<h1>Serveur non joignable, merci de revenir ultérieurement.<h1>")


        wallet = WalletValidator(uuid=uuid, config=config)

        carte = wallet.carte_local
        if not carte.detail.origine:
            return HttpResponse("<h1>Carte non lié à une instance. Merci de contacter l'administrateur.</h1>")

        reponse_carte_dict = wallet.carte_serveur_cashless
        email = wallet.user.email if wallet.user else None

        if reponse_carte_dict.get('history'):
            for his in reponse_carte_dict.get('history'):
                his['date'] = datetime.fromisoformat(his['date'])

        template_data = {
            'tarifs_adhesion': Price.objects.filter(
                product__categorie_article=Product.ADHESION,
                product__send_to_cashless=True,
            ).order_by('recurring_payment'),

            'history': reponse_carte_dict.get('history'),
            'total_monnaie': reponse_carte_dict.get('total_monnaie'),
            'assets': reponse_carte_dict.get('assets'),
            'a_jour_cotisation': reponse_carte_dict.get('a_jour_cotisation'),

            'image_carte': carte.detail.img,
            'numero_carte': carte.number,
            'client_name': carte.detail.origine.name,

            'carte_resto': config.carte_restaurant,
            'site_web': config.site_web,

            'email': email,
        }

        return render(request, self.template_name, template_data)

    def post(self, request, uuid):
        # carte = check_carte_local(uuid)
        config = self.configuration
        if not config.check_serveur_cashless():
            return HttpResponse("Serveur non joignable, merci de revenir ultérieurement.")

        # On récupère les données du formulaire
        data = request.POST
        pk_adhesion = data.get('pk_adhesion')
        montant_recharge = data.get('montant_recharge')

        wallet = WalletValidator(uuid=uuid, config=config, data_post=data)
        carte = wallet.carte_local
        user = wallet.user
        email = wallet.user.email

        if not wallet.is_valid():
            for error in wallet.errors:
                messages.error(request, error)

        # c'est une demande de paiement
        if (pk_adhesion or montant_recharge) and email:
            ligne_articles = []
            metadata = {
                'tenant': f'{connection.tenant.uuid}',
                'recharge_carte_uuid': f"{carte.uuid}"
            }

            if montant_recharge:
                recharge = GetArticleRechargeCashless(
                    montant_recharge=montant_recharge,
                    carte=carte,
                    config=config,
                )
                price = recharge.price
                # import ipdb; ipdb.set_trace()

                # noinspection PyTypeChecker
                ligne_article_recharge = LigneArticle.objects.create(
                    pricesold=get_or_create_price_sold(price, None),
                    qty=1,
                    carte=carte,
                )

                ligne_articles.append(ligne_article_recharge)
                metadata['recharge_carte_montant'] = str(montant_recharge)

            price_adhesion = None
            if pk_adhesion:
                price_adhesion = Price.objects.get(pk=data.get('pk_adhesion'))

                if data.get('gift') == "on" and price_adhesion.recurring_payment:
                    price_sold = get_or_create_price_sold(price_adhesion, None, gift=1)
                    metadata['gift'] = 'True'
                else:
                    price_sold = get_or_create_price_sold(price_adhesion, None)

                ligne = {
                    "pricesold": price_sold,
                    "qty": 1,
                    "carte": carte,
                }

                # noinspection PyTypeChecker
                ligne_article_adhesion = LigneArticle.objects.create(**ligne)

                ligne_articles.append(ligne_article_adhesion)
                metadata['pk_adhesion'] = str(price_adhesion.pk)

            if data.get('gift') == 'on' and not getattr(price_adhesion, 'recurring_payment', None):
                metadata['gift'] = 'True'

                gift_product, created = Product.objects.get_or_create(categorie_article=Product.DON,
                                                                      name="Don pour la coopérative")
                gift_price, created = Price.objects.get_or_create(product=gift_product, prix=1,
                                                                  name="1 euros")
                ligne_article_gift = LigneArticle.objects.create(
                    pricesold=get_or_create_price_sold(gift_price, None),
                    qty=1,
                )
                ligne_articles.append(ligne_article_gift)

            if len(ligne_articles) > 0:
                new_paiement_stripe = CreationPaiementStripe(
                    user=user,
                    liste_ligne_article=ligne_articles,
                    metadata=metadata,
                    reservation=None,
                    source=Paiement_stripe.QRCODE,
                    absolute_domain=request.build_absolute_uri().partition('/qr')[0],
                )

                if new_paiement_stripe.is_valid():
                    paiement_stripe: Paiement_stripe = new_paiement_stripe.paiement_stripe_db
                    paiement_stripe.lignearticles.all().update(status=LigneArticle.UNPAID)
                    return new_paiement_stripe.redirect_to_stripe()

        # Ce n'est pas une demande de paiement
        # On vérifie et construit la fiche d'adhésion
        fiche_membre = wallet.fiche_membre()
        if fiche_membre:
            messages.success(request, f"{data.get('email')}", extra_tags='email')
            # partial information :
            if not fiche_membre.detail_submitted:
                if fiche_membre.first_name:
                    messages.success(request, f"Email déja connu. prenom déja connu", extra_tags='prenom')
                if fiche_membre.last_name:
                    messages.success(request, f"Email déja connu. Name déja connu", extra_tags='name')
                if fiche_membre.phone:
                    messages.success(request, f"Email déja connu. Téléphone déja connu", extra_tags='phone')
                return HttpResponseRedirect(f'#demande_nom_prenom_tel')

            # messages.success(request, f"Carte liée au membre {data.get('email')}")
            return HttpResponseRedirect(f'#adhesionsuccess')

        messages.error(request,
                       f'erreur fin de fichier')
        return HttpResponseRedirect(f'#erreur')

        # return HttpResponseRedirect(f'#adhesionsuccess')
"""