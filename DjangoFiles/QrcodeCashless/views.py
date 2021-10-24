from datetime import datetime

import requests, json
from django.contrib import messages
from django.db import connection
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.shortcuts import render
from django.utils import timezone
from rest_framework.generics import get_object_or_404
from django.views import View
from rest_framework import status

from BaseBillet.models import Configuration, Product, LigneArticle
from PaiementStripe.models import Paiement_stripe
from PaiementStripe.views import creation_paiement_stripe
from QrcodeCashless.models import CarteCashless

from django.db.models.signals import pre_save
from django.dispatch import receiver

import logging
logger = logging.getLogger(__name__)


def get_domain(request):
    absolute_uri = request.build_absolute_uri()
    for domain in request.tenant.domains.all():
        if domain.domain in absolute_uri:
            return domain.domain

    raise Http404


def check_carte_local(uuid):
    carte = get_object_or_404(CarteCashless, uuid=uuid)
    # on vérifie toujours que la carte vienne bien du domain et Client tenant.
    if carte.detail.origine != connection.tenant:
        logger.error(f"{timezone.now()} "
                     f"check_carte_local {carte.uuid} : "
                     f"carte detail origine correspond pas : {carte.detail.origine} != {connection.tenant}")
        raise Http404

    return carte


class gen_one_bisik(View):
    def get(self, request, numero_carte):
        print(numero_carte)
        carte = get_object_or_404(CarteCashless, number=numero_carte)
        address = request.build_absolute_uri()
        return HttpResponseRedirect(
            address.replace("://m.", "://bisik.").replace(f"{carte.number}", f"qr/{carte.uuid}"))


class index_scan(View):
    template_name = "html5up-dimension/index.html"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.carte = None
        self.adhesion = None

    def check_carte_serveur_cashless(self, uuid):
        configuration = Configuration.get_solo()
        # on questionne le serveur cashless pour voir si la carte existe :

        sess = requests.Session()
        try:
            reponse = sess.post(
                f'{configuration.server_cashless}/api/billetterie_endpoint',
                headers={
                    'Authorization': f'Api-Key {configuration.key_cashless}'
                },
                data={
                    'uuid': f'{uuid}',
                })
        except requests.exceptions.ConnectionError:
            reponse = HttpResponse("Serveur non disponible. Merci de revenir ultérieurement.",
                                   status=status.HTTP_503_SERVICE_UNAVAILABLE)

        sess.close()
        return reponse

    def get(self, request, uuid):
        carte = check_carte_local(uuid)
        # dette technique ...
        # pour rediriger les premières générations de qrcode
        # m.tibillet.re et raffinerie
        address = request.build_absolute_uri()
        host = address.partition('://')[2]
        sub_addr = host.partition('.')[0]
        if sub_addr == "m":
            return HttpResponseRedirect(address.replace("://m.", "://raffinerie."))

        configuration = Configuration.get_solo()
        if not configuration.server_cashless:
            return HttpResponse(
                "L'adress du serveur cashless n'est pas renseignée dans la configuration de la billetterie.")
        if not configuration.stripe_api_key or not configuration.stripe_test_api_key:
            return HttpResponse(
                "Pas d'information de configuration pour paiement en ligne.")

        reponse_server_cashless = self.check_carte_serveur_cashless(carte.uuid)
        if reponse_server_cashless.status_code == 200:
            json_reponse = json.loads(reponse_server_cashless.json())
            email = json_reponse.get('email')
            a_jour_cotisation = json_reponse.get('a_jour_cotisation')

            if json_reponse.get('history'):
                for his in json_reponse.get('history'):
                    his['date'] = datetime.fromisoformat(his['date'])

            return render(
                request,
                self.template_name,
                {
                    'tarifs_adhesion': Product.objects.filter(categorie_article=Product.ADHESION).order_by('-prix'),
                    'adhesion_obligatoire': configuration.adhesion_obligatoire,
                    'history': json_reponse.get('history'),
                    'carte_resto': configuration.carte_restaurant,
                    'site_web': configuration.site_web,
                    'image_carte': carte.detail.img,
                    'numero_carte': carte.number,
                    'client_name': carte.detail.origine.name,
                    'domain': sub_addr,
                    # 'informations_carte': reponse_server_cashless.text,
                    'total_monnaie': json_reponse.get('total_monnaie'),
                    'assets': json_reponse.get('assets'),
                    'a_jour_cotisation': a_jour_cotisation,
                    # 'liste_assets': liste_assets,
                    'email': email,
                    'billetterie_bool': configuration.activer_billetterie,
                }
            )


        elif reponse_server_cashless.status_code == 400:
            # Carte non trouvée
            return HttpResponse('Carte inconnue', status=status.HTTP_400_BAD_REQUEST)
        elif reponse_server_cashless.status_code == 403:
            # Clé api HS
            logger.error(reponse_server_cashless)
            return HttpResponse('Forbidden', status=status.HTTP_403_FORBIDDEN)
        else:
            return HttpResponse("Serveur non disponible. Merci de revenir ultérieurement.",
                                   status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def post(self, request, uuid):
        carte = check_carte_local(uuid)
        if carte.detail.origine != connection.tenant:
            raise Http404

        data = request.POST
        print(data)
        # montant_adhesion = data.get('montant_adhesion')
        pk_adhesion = data.get('pk_adhesion')
        montant_recharge = data.get('montant_recharge')

        # c'est un paiement
        if ( pk_adhesion or montant_recharge ) and data.get('email'):
            # montant_recharge = data.get('montant_recharge')
            ligne_articles = []
            metadata = {}
            metadata['recharge_carte_uuid'] = str(carte.uuid)
            if montant_recharge:
                art, created = Product.objects.get_or_create(
                    name="Recharge Carte",
                    prix=1,
                    categorie_article=Product.RECHARGE_CASHLESS,
                )

                ligne_article_recharge = LigneArticle.objects.create(
                    article=art,
                    qty=montant_recharge,
                    carte=carte,
                )
                ligne_articles.append(ligne_article_recharge)


                metadata['recharge_carte_montant'] = str(montant_recharge)

            if pk_adhesion:
                art_adhesion = Product.objects.get(pk=data.get('pk_adhesion'))
                ligne_article_recharge = LigneArticle.objects.create(
                    article=art_adhesion,
                    qty=1,
                    carte=carte,
                )
                ligne_articles.append(ligne_article_recharge)
                metadata['pk_adhesion'] = str(art_adhesion.pk)

            if len(ligne_articles) > 0:
                new_paiement_stripe = creation_paiement_stripe(
                    email_paiement=data.get('email'),
                    liste_ligne_article=ligne_articles,
                    metadata=metadata,
                    absolute_domain=request.build_absolute_uri().partition('/qr')[0],
                )

                if new_paiement_stripe.is_valid():
                    print(new_paiement_stripe.checkout_session.stripe_id)
                    return new_paiement_stripe.redirect_to_stripe()


        # Email seul sans montant, c'est une adhésion
        elif data.get('email'):

            sess = requests.Session()
            configuration = Configuration.get_solo()
            r = sess.post(
                f'{configuration.server_cashless}/api/billetterie_qrcode_adhesion',
                headers={
                    'Authorization': f'Api-Key {configuration.key_cashless}'
                },
                data={
                    'prenom': data.get('prenom'),
                    'name': data.get('name'),
                    'email': data.get('email'),
                    'tel': data.get('tel'),
                    'uuid_carte': carte.uuid,
                })

            sess.close()

            # nouveau membre crée avec uniquement l'email on demande la suite.
            # HTTP_202_ACCEPTED
            # HTTP_201_CREATED
            if r.status_code in (201, 204):
                messages.success(request, f"{data.get('email')}", extra_tags='email')
                return HttpResponseRedirect(f'#demande_nom_prenom_tel')

            # partial information :
            elif r.status_code == 206:
                partial = json.loads(r.text)
                messages.success(request, f"{data.get('email')}", extra_tags='email')
                if partial.get('name'):
                    messages.success(request, f"Email déja connu. Name déja connu", extra_tags='name')
                if partial.get('prenom'):
                    messages.success(request, f"Email déja connu. prenom déja connu", extra_tags='prenom')
                if partial.get('tel'):
                    messages.success(request, f"Email déja connu. tel déja connu", extra_tags='tel')
                return HttpResponseRedirect(f'#demande_nom_prenom_tel')

            # nouveau membre crée, on demande la suite.
            elif r.status_code == 202:
                messages.success(request, f"Carte liée au membre {data.get('email')}")
                return HttpResponseRedirect(f'#adhesionsuccess')

            else:
                messages.error(request, f'Erreur {r.status_code} {r.text}')
                return HttpResponseRedirect(f'#erreur')


@receiver(pre_save, sender=Paiement_stripe)
def changement_paid_to_valid(sender, instance: Paiement_stripe, update_fields=None, **kwargs):
    # si l'instance vient d'être créé, ne rien faire :
    if instance.pk is None:
        pass
    else:
        paiementStripe = instance
        if paiementStripe.status == Paiement_stripe.PAID:
            data_pour_serveur_cashless = {'uuid_commande': paiementStripe.uuid}

            for ligne_article in paiementStripe.lignearticle_set.all():
                if ligne_article.carte :
                    data_pour_serveur_cashless['uuid'] = ligne_article.carte.uuid

                if ligne_article.product.categorie_article == Product.RECHARGE_CASHLESS :
                    data_pour_serveur_cashless['recharge_qty'] = float(ligne_article.qty)

                if ligne_article.product.categorie_article == Product.ADHESION :
                    data_pour_serveur_cashless['tarif_adhesion'] = ligne_article.product.prix

            # si il y a autre chose que uuid_commande :
            if len(data_pour_serveur_cashless) > 1 :
                sess = requests.Session()
                configuration = Configuration.get_solo()
                r = sess.post(
                    f'{configuration.server_cashless}/api/billetterie_endpoint',
                    headers={
                        'Authorization': f'Api-Key {configuration.key_cashless}'
                    },
                    data=data_pour_serveur_cashless,
                )

                sess.close()
                print(
                    f"{timezone.now()} demande au serveur cashless pour un rechargement. réponse : {r.status_code} ")

                if r.status_code == 200:
                    # la commande a été envoyé au serveur cashless et validé.
                    paiementStripe.status = Paiement_stripe.VALID
