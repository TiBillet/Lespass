"""
Test d'intégration — Upload d'images pour PostalAddress (img, sticker_img)

Envoie un POST multipart/form-data avec fichiers depuis tests/pytest/assets/
Vérifie que les URLs d'images sont renvoyées dans la représentation schema.org/PostalAddress.
"""
import os
import pytest
import requests


@pytest.mark.integration
def test_postal_address_create_with_images():
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY")
    if not api_key:
        pytest.exit("API key not set")

    headers = {"Authorization": f"Api-Key {api_key}"}

    # Assets
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    img_path = os.path.join(assets_dir, "event_main.jpg")
    sticker_path = os.path.join(assets_dir, "event_sticker.webp")
    if not (os.path.exists(img_path) and os.path.exists(sticker_path)):
        pytest.exit("Images de test manquantes dans tests/pytest/assets/")

    data = {
        "@type": "PostalAddress",
        "name": "Adresse avec images (pytest)",
        "streetAddress": "10 rue des Images",
        "addressLocality": "IconCity",
        "addressRegion": "IC",
        "postalCode": "10101",
        "addressCountry": "FR",
    }

    files = {
        "img": (os.path.basename(img_path), open(img_path, "rb"), "image/jpeg"),
        "sticker_img": (os.path.basename(sticker_path), open(sticker_path, "rb"), "image/jpeg"),
    }

    url = f"{base_url}/api/v2/postal-addresses/"
    resp = requests.post(url, headers=headers, data=data, files=files, timeout=20, verify=False)

    # Close files
    for f in files.values():
        try:
            f[1].close()
        except Exception:
            pass

    assert resp.status_code == 201, f"Create with images failed: {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    images = body.get("image") or []
    assert isinstance(images, list) and len(images) >= 1, f"image array expected, got {images}"
