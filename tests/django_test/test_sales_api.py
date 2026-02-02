"""
Tests d'intégration — API des ventes (sales)

Objectif:
- Créer des lignes de vente pour 2 cas: produit de réservation avec TVA (20%) et adhésion sans TVA.
- Générer une clé API avec UNIQUEMENT le droit « sale » (associée à un superuser pour passer la permission admin tenant).
- Interroger l'API HTTP via python-requests (LIST et RETRIEVE) et vérifier la sortie sémantique schema.org.

Important:
- Ce test s'exécute directement DANS le même environnement Python que Django (dans le conteneur).
- AUCUN docker exec n'est utilisé par le test lui-même. Il importe Django, prépare les données via l'ORM,
  puis appelle l'API HTTP exposée par le service.

Variables d'environnement lues:
- API_BASE_URL (ex: https://lespass.tibillet.localhost)
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

import pytest
import requests


def _prepare_data_in_db(base_url: str) -> Dict[str, Any]:
    """Crée les données nécessaires directement via l'ORM Django (dans le conteneur).

    Retourne un dict avec:
      - api_key: la clé API claire (Api-Key ...) à utiliser
      - uuids: {
          "with_vat": <uuid VALID>,
          "no_vat": <uuid VALID>,
          "refunded": <uuid REFUNDED>,
          "created": <uuid CREATED>
        }
    """
    # Init Django si nécessaire
    import os as _os
    import sys as _sys
    from pathlib import Path as _Path

    # Assure que le répertoire projet (contenant TiBillet/) est sur sys.path
    _here = _Path(__file__).resolve()
    for _p in [_here] + list(_here.parents):
        if (_p / 'manage.py').exists() and (_p / 'TiBillet').exists():
            if str(_p) not in _sys.path:
                _sys.path.insert(0, str(_p))
            break

    if not _os.environ.get('DJANGO_SETTINGS_MODULE'):
        _os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')
    import django
    # Initialisation Django (toujours appeler setup une fois)
    try:
        django.setup()
    except RuntimeError:
        # Déjà initialisé
        pass

    # Imports après setup
    from django_tenants.utils import schema_context
    from Customers.models import Domain
    from BaseBillet.models import Tva, Product, Price, ProductSold, PriceSold, LigneArticle, ExternalApiKey
    from AuthBillet.models import TibilletUser
    from rest_framework_api_key.models import APIKey
    import uuid as _uuid

    # Résout le tenant par le host (extrait de l'URL)
    host = base_url.split('//', 1)[-1].split('/', 1)[0]
    domain = Domain.objects.filter(domain=host).first()
    if not domain:
        raise RuntimeError(f"Tenant introuvable pour le host: {host}")

    client = domain.tenant
    out: Dict[str, Any] = {}
    with schema_context(client.schema_name):
        # 1) Clé API (droit sale uniquement), liée à un superuser
        user, _ = TibilletUser.objects.get_or_create(
            username='sales_api_test_admin',
            defaults={'is_staff': True, 'is_active': True, 'is_superuser': True},
        )
        if not user.is_superuser:
            user.is_superuser = True
            user.is_staff = True
            user.is_active = True
            user.save()

        unique_name = f"sales-test-{_uuid.uuid4().hex[:8]}"
        api_key_obj, key = APIKey.objects.create_key(name=unique_name)
        ExternalApiKey.objects.create(
            name=unique_name,
            user=user,
            key=api_key_obj,
            sale=True,
        )
        out['api_key'] = key

        # 2) Produit avec TVA 20%
        tva20, _ = Tva.objects.get_or_create(tva_rate=20.00)
        _name_vat = f"Billet Test TVA 20% {_uuid.uuid4().hex[:8]}"
        prod_vat = Product.objects.create(name=_name_vat, tva=tva20, categorie_article=Product.BILLET)
        price_vat = Price.objects.create(product=prod_vat, name='Plein tarif', prix=10.00)
        psold_vat = ProductSold.objects.create(product=prod_vat, categorie_article=prod_vat.categorie_article)
        prsold_vat = PriceSold.objects.create(productsold=psold_vat, price=price_vat, prix=price_vat.prix)
        line_vat = LigneArticle.objects.create(pricesold=prsold_vat, qty=1, amount=1000)
        # Par défaut, la LIST renvoie uniquement les lignes VALID → on valide explicitement
        line_vat.status = LigneArticle.VALID
        line_vat.save(update_fields=["status"])

        # 3) Adhésion sans TVA
        _name_novat = f"Adhésion Test sans TVA {_uuid.uuid4().hex[:8]}"
        prod_novat = Product.objects.create(name=_name_novat, tva=None, categorie_article=Product.ADHESION)
        price_novat = Price.objects.create(product=prod_novat, name='Adhésion', prix=5.00)
        psold_novat = ProductSold.objects.create(product=prod_novat, categorie_article=prod_novat.categorie_article)
        prsold_novat = PriceSold.objects.create(productsold=psold_novat, price=price_novat, prix=price_novat.prix)
        line_novat = LigneArticle.objects.create(pricesold=prsold_novat, qty=2, amount=500)
        line_novat.status = LigneArticle.VALID
        line_novat.save(update_fields=["status"])

        # 4) Une ligne REMBOURSÉE (REFUNDED)
        _name_ref = f"Billet Remboursé {_uuid.uuid4().hex[:8]}"
        prod_ref = Product.objects.create(name=_name_ref, tva=tva20, categorie_article=Product.BILLET)
        price_ref = Price.objects.create(product=prod_ref, name='Tarif', prix=12.50)
        psold_ref = ProductSold.objects.create(product=prod_ref, categorie_article=prod_ref.categorie_article)
        prsold_ref = PriceSold.objects.create(productsold=psold_ref, price=price_ref, prix=price_ref.prix)
        line_ref = LigneArticle.objects.create(pricesold=prsold_ref, qty=1, amount=1250)
        line_ref.status = LigneArticle.REFUNDED
        line_ref.save(update_fields=["status"])

        # 5) Une ligne non envoyée en paiement (CREATED)
        _name_created = f"Billet Non envoyé {_uuid.uuid4().hex[:8]}"
        prod_created = Product.objects.create(name=_name_created, tva=tva20, categorie_article=Product.BILLET)
        price_created = Price.objects.create(product=prod_created, name='Tarif', prix=7.00)
        psold_created = ProductSold.objects.create(product=prod_created, categorie_article=prod_created.categorie_article)
        prsold_created = PriceSold.objects.create(productsold=psold_created, price=price_created, prix=price_created.prix)
        line_created = LigneArticle.objects.create(pricesold=prsold_created, qty=1, amount=700)
        line_created.status = LigneArticle.CREATED
        line_created.save(update_fields=["status"])

        out['uuids'] = {
            'with_vat': str(line_vat.uuid),
            'no_vat': str(line_novat.uuid),
            'refunded': str(line_ref.uuid),
            'created': str(line_created.uuid),
        }

    return out


@pytest.mark.integration
def test_sales_api_list_and_retrieve_semantic_and_status_filters():
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")

    # Prépare données et clé API directement via Django/ORM (dans le même conteneur)
    prep = _prepare_data_in_db(base_url)
    api_key = prep['api_key']
    uuid_with_vat = prep['uuids']['with_vat']
    uuid_no_vat = prep['uuids']['no_vat']
    uuid_refunded = prep['uuids']['refunded']
    uuid_created = prep['uuids']['created']

    headers = {"Authorization": f"Api-Key {api_key}"}

    # Fenêtre temporelle TZ-aware autour de maintenant (les lignes viennent d'être créées)
    start = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()

    # LIST — utiliser params pour encoder correctement le + de l'offset TZ
    list_url = f"{base_url}/api/v2/sales/"
    resp = requests.get(list_url, headers=headers, params={"start": start, "end": end}, timeout=10, verify=False)
    assert resp.status_code == 200, f"LIST failed ({resp.status_code}): {resp.text[:500]}"
    payload = resp.json()
    assert payload.get("@type") == "ItemList"
    items = payload.get("itemListElement") or []
    assert isinstance(items, list) and len(items) >= 2

    # Cherche nos 2 lignes via additionalProperty.sale_line_uuid
    def find_item(u):
        for it in items:
            if not isinstance(it, dict):
                continue
            if it.get("@type") != "Product":
                continue
            props = it.get("additionalProperty") or []
            for p in props:
                if p.get("name") == "sale_line_uuid" and p.get("value") == u:
                    return it
        return None

    item_vat = find_item(uuid_with_vat)
    item_novat = find_item(uuid_no_vat)
    item_refunded_in_valid = find_item(uuid_refunded)
    item_created_in_valid = find_item(uuid_created)
    assert item_vat and item_novat, "Les deux lignes (avec et sans TVA) doivent être dans la liste"
    # Vérifie que la liste par défaut (status=VALID) n'inclut NI les remboursés NI les non envoyés
    assert item_refunded_in_valid is None, "Les lignes REFUNDED ne doivent PAS apparaître par défaut (VALID seulement)"
    assert item_created_in_valid is None, "Les lignes CREATED (non envoyées en paiement) ne doivent PAS apparaître dans VALID"

    # Vérifie les TVA attendues dans additionalProperty
    def get_prop(it, name):
        for p in it.get("additionalProperty", []) or []:
            if p.get("name") == name:
                return p.get("value")
        return None

    assert get_prop(item_vat, "vat") in ("20.00", "20"), f"TVA 20% attendue: {item_vat}"
    assert get_prop(item_novat, "vat") in ("0.00", "0"), f"TVA 0% attendue: {item_novat}"

    # LIST — filtre explicite REFUNDED → on doit y trouver la ligne remboursée
    resp_ref = requests.get(
        list_url,
        headers=headers,
        params={"start": start, "end": end, "status": "REFUNDED"},
        timeout=10,
        verify=False,
    )
    assert resp_ref.status_code == 200, f"LIST REFUNDED failed ({resp_ref.status_code}): {resp_ref.text[:500]}"
    payload_ref = resp_ref.json()
    items_ref = payload_ref.get("itemListElement") or []
    def find_in_ref(u):
        for it in items_ref:
            if not isinstance(it, dict):
                continue
            if it.get("@type") != "Product":
                continue
            props = it.get("additionalProperty") or []
            for p in props:
                if p.get("name") == "sale_line_uuid" and p.get("value") == u:
                    return it
        return None
    assert find_in_ref(uuid_refunded) is not None, "La ligne REFUNDED doit apparaître quand status=REFUNDED"

    # RETRIEVE pour la ligne sans TVA (au hasard)
    detail_url = f"{base_url}/api/v2/sales/{uuid_no_vat}"
    dresp = requests.get(detail_url, headers=headers, timeout=10, verify=False)
    assert dresp.status_code == 200, f"DETAIL failed ({dresp.status_code}): {dresp.text[:500]}"
    detail = dresp.json()
    assert detail.get("@type") == "Product"
    props = detail.get("additionalProperty") or []
    values = {p.get('name'): p.get('value') for p in props if isinstance(p, dict)}
    assert values.get("sale_line_uuid") == uuid_no_vat
    assert values.get("vat") in ("0.00", "0")
