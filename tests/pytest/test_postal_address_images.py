"""
Test d'intégration — Upload d'images pour PostalAddress (img, sticker_img)

Envoie un POST multipart/form-data avec fichiers depuis tests/pytest/assets/
Vérifie que les URLs d'images sont renvoyées dans la représentation schema.org/PostalAddress.
"""
import os

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.mark.integration
def test_postal_address_create_with_images(api_client, auth_headers):
    # Assets
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    img_path = os.path.join(assets_dir, "event_main.jpg")
    sticker_path = os.path.join(assets_dir, "event_sticker.webp")
    if not (os.path.exists(img_path) and os.path.exists(sticker_path)):
        pytest.exit("Images de test manquantes dans tests/pytest/assets/")

    with open(img_path, "rb") as f:
        img_content = f.read()
    with open(sticker_path, "rb") as f:
        sticker_content = f.read()

    data = {
        "@type": "PostalAddress",
        "name": "Adresse avec images (pytest)",
        "streetAddress": "10 rue des Images",
        "addressLocality": "IconCity",
        "addressRegion": "IC",
        "postalCode": "10101",
        "addressCountry": "FR",
        "img": SimpleUploadedFile("event_main.jpg", img_content, content_type="image/jpeg"),
        "sticker_img": SimpleUploadedFile("event_sticker.webp", sticker_content, content_type="image/webp"),
    }
    resp = api_client.post('/api/v2/postal-addresses/', data=data, **auth_headers)

    assert resp.status_code == 201, f"Create with images failed: {resp.status_code} {resp.content.decode()[:300]}"
    body = resp.json()
    images = body.get("image") or []
    assert isinstance(images, list) and len(images) >= 1, f"image array expected, got {images}"
