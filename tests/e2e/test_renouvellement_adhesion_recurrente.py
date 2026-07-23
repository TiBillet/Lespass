"""
tests/e2e/test_renouvellement_adhesion_recurrente.py
Le renouvellement automatique d'une adhesion, sur un VRAI cycle Stripe.
/ Automatic membership renewal, on a REAL Stripe billing cycle.

LOCALISATION : tests/e2e/test_renouvellement_adhesion_recurrente.py

CE QUE CE FICHIER PROUVE / WHAT THIS FILE PROVES
--------------------------------------------------
Qu'un mois plus tard, sans que personne n'intervienne, l'echeance suivante :

1. est prelevee par Stripe ;
2. produit une `LigneArticle` de vente cote Lespass ;
3. **reverse la recompense en monnaie locale** au portefeuille de l'adherent ;
4. entre dans la cloture comptable en ligne, et pas dans le ticket de caisse.

Le point 3 est le seul qui ne va pas de soi. Une caisse de securite sociale
alimentaire promet un pouvoir d'achat **recurrent** : si la premiere cotisation
credite et pas les suivantes, l'adherent paie tous les mois pour ne recevoir
qu'une fois. Personne ne s'en apercevrait — ni erreur, ni ecran, ni alerte.

/ A food-security fund promises RECURRING purchasing power. If the first
contribution credits and the following ones do not, the member pays monthly and
receives once. Nothing anywhere would report it.

COMMENT ON FAIT PASSER UN MOIS / HOW A MONTH IS MADE TO PASS
--------------------------------------------------------------
Par une **horloge de test Stripe** (`stripe.test_helpers.TestClock`). Le client
Stripe est rattache a une horloge que le test avance de 32 jours ; Stripe emet
alors reellement l'echeance suivante, avec `billing_reason='subscription_cycle'`
— exactement l'evenement que `Webhook_stripe` attend (`ApiBillet/views.py`).

C'est la seule facon d'observer un renouvellement sans attendre un mois, et sans
fabriquer un faux webhook : la facture, le prelevement et l'evenement sont ceux
de Stripe.

/ A Stripe TEST CLOCK is advanced by 32 days, so Stripe really issues the next
invoice with billing_reason='subscription_cycle'. The invoice, the charge and the
event are Stripe's own — no hand-crafted webhook.

DEUX PIEGES PAYES EN ECRIVANT CE FICHIER / TWO TRAPS ALREADY PAID FOR
-----------------------------------------------------------------------
1. **Un client sans moyen de paiement fait echouer chaque echeance.** Stripe
   emet alors `invoice.payment_failed` en boucle, puis supprime l'abonnement.
   Il faut attacher une carte de test au client ET la designer comme moyen par
   defaut de facturation.
2. **La PREMIERE facture ne declenche rien.** Elle porte
   `billing_reason='subscription_create'`, que le webhook ignore volontairement
   (l'adhesion initiale est traitee par le retour de paiement, pas par le
   webhook). Seul le deuxieme cycle est un renouvellement. Conclure sur la
   premiere facture ferait croire a une regression inexistante.

CE QU'IL LAISSE DERRIERE LUI / WHAT IT LEAVES BEHIND
------------------------------------------------------
Une horloge de test, un client et un abonnement Stripe en mode test, une adhesion
reelle et un versement reel de monnaie locale. Le test supprime l'horloge de test
en fin de parcours (elle emporte le client et l'abonnement) ; le reste demeure.
/ The test deletes its test clock at the end (which takes the customer and the
subscription with it); the Lespass-side objects remain.

PREREQUIS / PREREQUISITES
--------------------------
- **`stripe listen` doit tourner** : sans lui, l'echeance est bien prelevee chez
  Stripe mais Lespass n'en sait rien. Ce test est ignore tant que
  `E2E_STRIPE_LISTEN=1` n'est pas pose — et l'oubli est signale bruyamment en fin
  de run (voir `tests/e2e/conftest.py`).
- Celery tourne : la recompense part par `.delay()`.
- le Fedow est joignable.

Lancement / Run:
    # 1. sur l'hote :
    stripe listen
    # 2. puis :
    docker exec -e E2E_STRIPE_LISTEN=1 lespass_django poetry run pytest \
        /DjangoFiles/tests/e2e/test_renouvellement_adhesion_recurrente.py -v
"""

import json
import time
import uuid as uuid_module

import pytest

# Le tarif du cas d'usage : recurrent mensuel ET porteur d'une recompense.
# / The use case price: monthly recurring AND carrying a reward.
NOM_DU_PRODUIT = "Caisse de sécurité sociale alimentaire"
NOM_DU_TARIF = "Souscription mensuelle"

# De combien on avance l'horloge pour provoquer l'echeance suivante. 32 jours
# depassent surement un cycle mensuel, quel que soit le mois de depart.
# / How far the clock is advanced: 32 days clears a monthly cycle in any month.
JOURS_JUSQU_A_L_ECHEANCE = 32


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def _lire_json_marque(sortie, marqueur):
    """Extrait le JSON imprime par le shell Django derriere un marqueur.
    / Extracts the JSON printed by the Django shell behind an explicit marker."""
    for ligne in sortie.splitlines():
        if ligne.startswith(marqueur):
            return json.loads(ligne[len(marqueur) :])
    pytest.fail(
        f"Le shell Django n'a rien imprime derriere '{marqueur}'. "
        f"Sortie : {sortie[-600:]}"
    )


def _etat_de_l_adhesion(django_shell, email, adhesion_pk):
    """Le solde Fedow de l'adherent et les lignes de vente de son adhesion.

    Le solde est relu SANS cache : c'est le versement qui vient (ou non) d'avoir
    lieu qu'on observe, pas la valeur memorisee avant lui.
    / Balance read WITHOUT cache: we observe the transfer that just happened.
    """
    sortie = django_shell(
        "import json\n"
        "from AuthBillet.models import TibilletUser\n"
        "from BaseBillet.models import LigneArticle, Membership\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        f"adhesion = Membership.objects.get(pk='{adhesion_pk}')\n"
        "lignes = LigneArticle.objects.filter(membership=adhesion).order_by('datetime')\n"
        "solde = FedowAPI().wallet.get_total_fiducial_and_all_federated_token(\n"
        "    user, use_cache=False)\n"
        "print('ETAT_JSON=' + json.dumps({\n"
        "    'solde': int(solde),\n"
        "    'lignes': [{\n"
        "        'uuid': str(l.uuid),\n"
        "        'origine': l.sale_origin,\n"
        "        'statut': l.status,\n"
        "        'montant': int(l.amount),\n"
        "        'moyen': l.payment_method,\n"
        "        'recompense': ((l.metadata or {}).get('fedow_reward') or {}).get('amount')\n"
        "                      if isinstance(l.metadata, dict) else None,\n"
        "    } for l in lignes],\n"
        "}))"
    )
    return _lire_json_marque(sortie, "ETAT_JSON=")


def _attendre_le_renouvellement(django_shell, email, adhesion_pk, secondes=90):
    """Attend qu'une ligne de vente apparaisse pour l'echeance, ou rend l'etat lu.

    L'echeance chemine par Stripe, puis le webhook, puis Celery : rien n'est
    synchrone. On interroge en boucle plutot que de parier sur un delai fixe.
    / The renewal travels through Stripe, then the webhook, then Celery: poll.
    """
    etat = _etat_de_l_adhesion(django_shell, email, adhesion_pk)
    for _tentative in range(secondes // 5):
        if etat["lignes"]:
            return etat
        time.sleep(5)
        etat = _etat_de_l_adhesion(django_shell, email, adhesion_pk)
    return etat


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tarif_recurrent_recompense(django_shell):
    """Le tarif du cas d'usage, tel qu'il est configure sur ce tenant.

    On ne le fabrique pas : c'est la configuration de production qu'on verifie.
    / Not fabricated: the production configuration is what we check.
    """
    sortie = django_shell(
        "import json\n"
        "from BaseBillet.models import Price\n"
        "tarif = Price.objects.filter(\n"
        f"    product__name='{NOM_DU_PRODUIT}', name='{NOM_DU_TARIF}'\n"
        ").select_related('product', 'fedow_reward_asset').first()\n"
        "print('TARIF_JSON=' + json.dumps({\n"
        "    'trouve': bool(tarif),\n"
        "    'uuid': str(tarif.uuid) if tarif else None,\n"
        "    'prix': float(tarif.prix) if tarif else None,\n"
        "    'recurrent': bool(tarif and tarif.recurring_payment),\n"
        "    'recompense_active': bool(tarif and tarif.fedow_reward_enabled),\n"
        "    'montant': float(tarif.fedow_reward_amount)\n"
        "               if (tarif and tarif.fedow_reward_amount) else None,\n"
        "}))"
    )
    donnees = _lire_json_marque(sortie, "TARIF_JSON=")

    if not donnees["trouve"]:
        pytest.fail(
            f"Le tarif '{NOM_DU_TARIF}' du produit '{NOM_DU_PRODUIT}' n'existe "
            "pas sur ce tenant. Reseeder : docker exec lespass_django poetry run "
            "python manage.py demo_data_v2"
        )
    if not donnees["recurrent"]:
        pytest.fail(
            f"Le tarif '{NOM_DU_TARIF}' n'est pas recurrent "
            "(`recurring_payment`) : il n'y a pas d'echeance a faire venir."
        )
    if not donnees["recompense_active"] or not donnees["montant"]:
        pytest.fail(
            f"Le tarif '{NOM_DU_TARIF}' ne verse aucune recompense. Ce fichier "
            f"verifie qu'elle est reversee A CHAQUE echeance. Lu : {donnees}"
        )

    donnees["montant_en_centimes"] = int(round(donnees["montant"] * 100))
    donnees["prix_en_centimes"] = int(round(donnees["prix"] * 100))
    return donnees


@pytest.fixture
def abonnement_stripe_sur_horloge_de_test(django_shell, tarif_recurrent_recompense):
    """Un adherent neuf, abonne chez Stripe, sur une horloge que l'on pourra avancer.

    L'abonnement est cree directement chez Stripe plutot que par le tunnel de
    paiement du site : c'est le seul moyen de rattacher le client a une horloge de
    test, et donc de faire venir une echeance. Les metadonnees reproduisent
    exactement celles que pose `MembershipValidator.get_checkout_stripe` — c'est
    par elles que le webhook retrouve le tenant, l'adhesion et le tarif.
    / Created directly at Stripe (the only way to attach a test clock), with the
    exact metadata get_checkout_stripe sets: that is how the webhook finds its way
    back to the tenant, the membership and the price.
    """
    adresse = f"e2e-renouv-{uuid_module.uuid4().hex[:8]}@tibillet.test"

    sortie = django_shell(
        "import json, time\n"
        "import stripe\n"
        "from django.db import connection\n"
        "from AuthBillet.utils import get_or_create_user\n"
        "from ApiBillet.serializers import get_or_create_price_sold\n"
        "from BaseBillet.models import Configuration, Membership, Price\n"
        "from fedow_connect.fedow_api import FedowAPI\n"
        "from root_billet.models import RootConfiguration\n"
        "stripe.api_key = RootConfiguration.get_solo().get_stripe_api()\n"
        "compte = Configuration.get_solo().get_stripe_connect_account()\n"
        "tenant = connection.tenant\n"
        f"tarif = Price.objects.get(uuid='{tarif_recurrent_recompense['uuid']}')\n"
        f"user = get_or_create_user('{adresse}', send_mail=False)\n"
        "user.email_valid = True\n"
        "user.save()\n"
        # Le portefeuille doit exister AVANT la premiere echeance.
        # / The wallet must exist BEFORE the first due date.
        "FedowAPI().wallet.get_or_create_wallet(user)\n"
        "user.refresh_from_db()\n"
        "adhesion = Membership.objects.create(\n"
        "    user=user, price=tarif, first_name='E2E', last_name='Renouvellement',\n"
        "    status=Membership.ONCE)\n"
        "horloge = stripe.test_helpers.TestClock.create(\n"
        "    frozen_time=int(time.time()), name='E2E renouvellement',\n"
        "    stripe_account=compte)\n"
        "client = stripe.Customer.create(\n"
        f"    email='{adresse}', test_clock=horloge.id, stripe_account=compte)\n"
        # Sans moyen de paiement par defaut, chaque echeance part en
        # `invoice.payment_failed` et Stripe finit par supprimer l'abonnement.
        # / Without a default payment method every due date fails and Stripe
        # eventually deletes the subscription.
        "moyen = stripe.PaymentMethod.attach(\n"
        "    'pm_card_visa', customer=client.id, stripe_account=compte)\n"
        "stripe.Customer.modify(\n"
        "    client.id, invoice_settings={'default_payment_method': moyen.id},\n"
        "    stripe_account=compte)\n"
        "id_prix = get_or_create_price_sold(\n"
        "    tarif, custom_amount=tarif.prix).get_id_price_stripe()\n"
        "abo = stripe.Subscription.create(\n"
        "    customer=client.id, items=[{'price': id_prix}],\n"
        "    metadata={'tenant': str(tenant.uuid), 'tenant_name': tenant.name,\n"
        "              'price_uuid': str(tarif.uuid),\n"
        "              'membership_uuid': str(adhesion.uuid),\n"
        f"              'user': '{adresse}'}},\n"
        "    stripe_account=compte)\n"
        "adhesion.stripe_id_subscription = abo.id\n"
        "adhesion.save()\n"
        "print('ABONNEMENT_JSON=' + json.dumps({\n"
        "    'email': user.email,\n"
        "    'adhesion_pk': str(adhesion.pk),\n"
        "    'horloge': horloge.id,\n"
        "    'abonnement': abo.id,\n"
        "    'statut_stripe': abo.status,\n"
        "    'wallet_uuid': str(user.wallet.uuid) if user.wallet else None,\n"
        "}))"
    )
    donnees = _lire_json_marque(sortie, "ABONNEMENT_JSON=")

    if not donnees["wallet_uuid"]:
        pytest.fail(
            "L'adherent n'a pas de portefeuille : le Fedow n'a pas repondu. "
            "La recompense n'aurait nulle part ou aller."
        )
    if donnees["statut_stripe"] not in ("active", "trialing"):
        pytest.fail(
            f"L'abonnement Stripe n'est pas actif ({donnees['statut_stripe']}) : "
            "aucune echeance ne viendra."
        )

    yield donnees

    # L'horloge de test emporte avec elle son client et son abonnement. Sans ce
    # nettoyage, chaque execution laisse un abonnement actif de plus dans le
    # compte Stripe de test.
    # / The test clock takes its customer and subscription with it.
    django_shell(
        "import stripe\n"
        "from BaseBillet.models import Configuration\n"
        "from root_billet.models import RootConfiguration\n"
        "stripe.api_key = RootConfiguration.get_solo().get_stripe_api()\n"
        "compte = Configuration.get_solo().get_stripe_connect_account()\n"
        "try:\n"
        f"    stripe.test_helpers.TestClock.delete('{donnees['horloge']}',\n"
        "                                          stripe_account=compte)\n"
        "except Exception as erreur:\n"
        "    print('NETTOYAGE_IMPOSSIBLE=' + str(erreur))"
    )


# ---------------------------------------------------------------------------
# Le parcours
# ---------------------------------------------------------------------------


@pytest.mark.stripe_listen
def test_chaque_echeance_reverse_la_recompense_et_entre_en_comptabilite(
    django_shell,
    instant_serveur,
    rapports_comptables,
    rapports_qui_voient_la_ligne,
    tarif_recurrent_recompense,
    abonnement_stripe_sur_horloge_de_test,
):
    """Faire venir l'echeance suivante, et verifier qu'elle credite ET se comptabilise.

    / Bring on the next due date, and check it both credits and is accounted for.
    """
    email = abonnement_stripe_sur_horloge_de_test["email"]
    adhesion_pk = abonnement_stripe_sur_horloge_de_test["adhesion_pk"]
    horloge = abonnement_stripe_sur_horloge_de_test["horloge"]
    recompense = tarif_recurrent_recompense["montant_en_centimes"]
    cotisation = tarif_recurrent_recompense["prix_en_centimes"]

    debut_de_la_mesure = instant_serveur()

    etat_initial = _etat_de_l_adhesion(django_shell, email, adhesion_pk)
    assert etat_initial["solde"] == 0, (
        f"L'adherent vient d'etre cree, son solde devrait etre nul : {etat_initial}"
    )
    assert etat_initial["lignes"] == [], (
        f"L'adhesion ne devrait porter aucune ligne de vente avant l'echeance : "
        f"{etat_initial}"
    )

    # --- 1. Un mois passe : Stripe emet l'echeance suivante ---
    #
    # `advance` est asynchrone chez Stripe : l'horloge repasse `ready` quand tous
    # les evenements du saut ont ete emis. Conclure avant, c'est conclure sur un
    # cycle qui n'a pas encore eu lieu.
    # / advance is asynchronous: the clock returns to `ready` once every event of
    # the jump has been emitted.
    sortie = django_shell(
        "import time\n"
        "import stripe\n"
        "from BaseBillet.models import Configuration\n"
        "from root_billet.models import RootConfiguration\n"
        "stripe.api_key = RootConfiguration.get_solo().get_stripe_api()\n"
        "compte = Configuration.get_solo().get_stripe_connect_account()\n"
        f"h = stripe.test_helpers.TestClock.retrieve('{horloge}', stripe_account=compte)\n"
        "stripe.test_helpers.TestClock.advance(\n"
        f"    '{horloge}',\n"
        f"    frozen_time=h.frozen_time + {JOURS_JUSQU_A_L_ECHEANCE} * 24 * 3600,\n"
        "    stripe_account=compte)\n"
        "for _essai in range(60):\n"
        "    time.sleep(3)\n"
        f"    h = stripe.test_helpers.TestClock.retrieve('{horloge}', stripe_account=compte)\n"
        "    if h.status == 'ready':\n"
        "        break\n"
        "print('HORLOGE_STATUT=' + h.status)"
    )
    assert "HORLOGE_STATUT=ready" in sortie, (
        f"L'horloge de test n'a pas fini d'avancer : {sortie[-300:]}. "
        "L'echeance n'a donc pas ete emise, et rien de ce qui suit n'a de sens."
    )

    # --- 2. Lespass a enregistre l'echeance comme une vente ---
    etat = _attendre_le_renouvellement(django_shell, email, adhesion_pk)

    assert etat["lignes"], (
        "L'echeance a ete prelevee chez Stripe, mais Lespass n'a enregistre "
        "aucune vente. Cause la plus probable : `stripe listen` ne tourne pas, "
        "donc le webhook `invoice.paid` n'est jamais arrive. Sinon, regarder les "
        "logs du serveur : le handler `subscription_cycle` avale ses erreurs."
    )
    assert len(etat["lignes"]) == 1, (
        f"L'echeance a produit {len(etat['lignes'])} lignes de vente au lieu "
        f"d'une seule : {etat['lignes']}. L'adherent serait facture plusieurs "
        "fois pour un seul prelevement."
    )

    ligne = etat["lignes"][0]
    assert ligne["origine"] == "WK", (
        f"La ligne du renouvellement ne porte pas l'origine WEBHOOK : {ligne}. "
        "Une autre origine la ferait basculer d'un rapport comptable a l'autre."
    )
    assert ligne["moyen"] == "SR", (
        f"La ligne ne porte pas le moyen de paiement « recurrent Stripe » : "
        f"{ligne}. La ventilation par moyen de paiement serait fausse."
    )
    assert ligne["statut"] == "V", (
        f"La ligne du renouvellement n'est pas validee : {ligne}. Restee a « P », "
        "elle signale que `trigger_A` s'est interrompu avant sa derniere "
        "instruction — l'exception est avalee, ce statut est le seul indice."
    )
    assert ligne["montant"] == cotisation, (
        f"La ligne ne porte pas le montant de la cotisation : {ligne}, "
        f"attendu {cotisation}."
    )

    # --- 3. LE FEDOW REEL a reverse la recompense ---
    #
    # Le coeur du fichier : la promesse d'un pouvoir d'achat RECURRENT.
    # / The heart of the file: the promise of RECURRING purchasing power.
    assert etat["solde"] == recompense, (
        f"L'echeance n'a pas reverse la recompense : solde {etat['solde']} au "
        f"lieu de {recompense}. L'adherent cotise tous les mois et n'est credite "
        "qu'une fois — sans qu'aucune erreur ne le signale nulle part."
    )
    assert ligne["recompense"] == recompense, (
        f"La ligne du renouvellement ne garde pas trace du versement : {ligne}. "
        "Sans cette trace, un rejeu du meme webhook reverserait la recompense."
    )

    # --- 4. La comptabilite classe l'echeance du bon cote ---
    #
    # Une vente a distance : elle entre dans la cloture comptable en ligne et
    # reste hors du ticket de caisse. Manquer les deux la rendrait invisible.
    # / A remote sale: it belongs to the online closure and stays out of the
    # register ticket. Missing both would make it invisible.
    # On situe LA ligne du renouvellement, plutot que d'asserter un total : les
    # lignes du rapport en ligne arrivent par webhook, donc de facon asynchrone,
    # et celui d'un test voisin peut tomber dans la meme fenetre. Un total exact
    # y est un piege (constate : 200 releve la ou 100 etait attendu).
    # / Locate THE line instead of asserting a total: online-report lines arrive
    # asynchronously by webhook, so a neighbouring test's webhook can land in the
    # same window (observed: 200 where 100 was expected).
    situation = rapports_qui_voient_la_ligne(ligne["uuid"], debut_de_la_mesure)

    assert situation["en_ligne"], (
        f"La ligne du renouvellement n'entre PAS dans la cloture comptable en "
        f"ligne : {ligne}. Une vente que ni le ticket de caisse ni la cloture en "
        "ligne ne voient n'existe pour aucun comptable."
    )
    assert not situation["caisse"], (
        f"La ligne du renouvellement entre AUSSI dans le ticket de caisse : "
        f"{ligne}. Le meme euro serait compte deux fois, et un prelevement a "
        "distance apparaitrait dans un tiroir ou aucun billet n'est entre."
    )

    # Le ticket de caisse, lui, n'a pas de source asynchrone : ses montants
    # peuvent etre asserted au centime. Le renouvellement ne doit rien y peser.
    # / The register report has no async source: its amounts can be asserted
    # exactly. The renewal must weigh nothing there.
    comptes = rapports_comptables(debut_de_la_mesure)
    assert comptes["caisse"]["especes"] == 0, (
        f"Le renouvellement est entre dans les especes du ticket de caisse : "
        f"{comptes['caisse']}. Aucun billet n'est pourtant entre dans le tiroir."
    )
    assert comptes["caisse"]["total_adhesions"] == 0, (
        f"Le renouvellement apparait dans la section adhesions du ticket de "
        f"caisse : {comptes['caisse']}. Il y ferait double emploi avec la "
        "cloture comptable en ligne."
    )

    # Le VERSEMENT, lui, ne laisse aucune ecriture — meme constat qu'au paiement
    # de la premiere cotisation (`test_adhesion_recompense_puis_qrcode.py`).
    # / The transfer itself leaves no entry, same as on the first contribution.
    sortie = django_shell(
        "from AuthBillet.models import TibilletUser\n"
        "from BaseBillet.models import LigneArticle, SaleOrigin\n"
        f"user = TibilletUser.objects.get(email='{email}')\n"
        "lignes = LigneArticle.objects.filter(\n"
        "    wallet=user.wallet).exclude(sale_origin=SaleOrigin.QRCODE_MA)\n"
        "print('LIGNES_HORS_QRCODE=' + str(lignes.count()))"
    )
    assert "LIGNES_HORS_QRCODE=0" in sortie, (
        f"Le versement de recompense a laisse une ecriture comptable : "
        f"{sortie[-200:]}. Ce fichier decrit l'inverse — si une contrepartie a "
        "ete ajoutee, il faut reecrire ce constat."
    )
