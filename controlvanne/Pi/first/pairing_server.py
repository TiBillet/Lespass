"""
pairing_server.py — Mini-serveur HTTP de premier appairage du Pi.
/ pairing_server.py — Minimal HTTP pairing server for first Pi boot.

LOCALISATION : controlvanne/Pi/first/pairing_server.py
"""

import os
import json
import requests
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs


ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
SERVER_URL = os.getenv("SERVER_URL", "https://lespass.handymaker.org").rstrip("/")
SSL_VERIFY = os.getenv("SSL_VERIFY", "True").lower() != "false"
PORT = 8080


HTML_FORM = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>TiBeer — Appairage</title>
    <style>
        body {{
            font-family: sans-serif;
            background: #1a1a2e;
            color: #eee;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }}
        .box {{
            background: #16213e;
            border-radius: 12px;
            padding: 40px;
            max-width: 420px;
            width: 100%;
            text-align: center;
        }}
        h1 {{ color: #e94560; margin-bottom: 8px; }}
        p {{ color: #aaa; font-size: 14px; margin-bottom: 24px; }}
        input[type=text] {{
            width: 100%;
            padding: 14px;
            font-size: 32px;
            letter-spacing: 10px;
            text-align: center;
            border: 2px solid #e94560;
            border-radius: 8px;
            background: #0f3460;
            color: #fff;
            box-sizing: border-box;
            margin-bottom: 16px;
        }}
        button {{
            width: 100%;
            padding: 14px;
            background: #e94560;
            color: #fff;
            border: none;
            border-radius: 8px;
            font-size: 18px;
            cursor: pointer;
        }}
        button:hover {{ background: #c73652; }}
        .server {{ margin-top: 24px; font-size: 12px; color: #555; word-break: break-all; }}
        .error {{ color: #e94560; margin-top: 16px; font-weight: bold; }}
        .success {{ color: #4caf50; margin-top: 16px; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="box">
        <h1>TiBeer — Appairage</h1>
        <p>Saisir le code PIN affiché dans l'admin Django<br>
           <em>Menu Tireuses &rarr; colonne PIN code</em></p>
        <form method="POST" action="/claim">
            <input type="text" name="pin_code" maxlength="6"
                   placeholder="000000" autofocus autocomplete="off"
                   inputmode="numeric" pattern="[0-9]{{6}}">
            <button type="submit">Appairer</button>
        </form>
        {message}
        <div class="server">Serveur : {server_url}</div>
    </div>
</body>
</html>"""


def _lire_env():
    env = {}
    if ENV_FILE.exists():
        for ligne in ENV_FILE.read_text().splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                cle, _, valeur = ligne.partition("=")
                env[cle.strip()] = valeur.strip()
    return env


def _ecrire_env(env_patch: dict):
    """Mets à jour uniquement les clés de env_patch dans .env (préserve le reste).
    / Update only env_patch keys in .env (preserve the rest)."""
    lignes_out = []
    cles_a_ecrire = set(env_patch.keys())
    if ENV_FILE.exists():
        for ligne in ENV_FILE.read_text().splitlines():
            stripped = ligne.strip()
            if not stripped or stripped.startswith("#"):
                lignes_out.append(ligne)
                continue
            cle = stripped.partition("=")[0].strip()
            if cle in cles_a_ecrire:
                lignes_out.append(f"{cle}={env_patch[cle]}")
                cles_a_ecrire.discard(cle)
            else:
                lignes_out.append(ligne)
    # Nouvelles clés absentes du fichier
    for cle in cles_a_ecrire:
        lignes_out.append(f"{cle}={env_patch[cle]}")
    ENV_FILE.write_text("\n".join(lignes_out) + "\n")


def _appeler_claim(pin_code: str) -> dict:
    url = f"{SERVER_URL}/api/discovery/claim/"
    reponse = requests.post(
        url,
        json={"pin_code": pin_code},
        timeout=10,
        verify=SSL_VERIFY,
    )
    reponse.raise_for_status()
    return reponse.json()


class PairingHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # Silencer les logs du serveur HTTP intégré

    def do_GET(self):
        self._send_html(HTML_FORM.format(message="", server_url=SERVER_URL))

    def do_POST(self):
        if self.path != "/claim":
            self.send_error(404)
            return

        longueur = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(longueur).decode()
        params = parse_qs(body)
        pin_code = params.get("pin_code", [""])[0].strip()

        if not pin_code or len(pin_code) != 6 or not pin_code.isdigit():
            msg = '<p class="error">PIN invalide — 6 chiffres requis.</p>'
            self._send_html(HTML_FORM.format(message=msg, server_url=SERVER_URL))
            return

        try:
            data = _appeler_claim(pin_code)
        except requests.HTTPError as e:
            msg = f'<p class="error">Erreur {e.response.status_code} — PIN incorrect ou déjà utilisé.</p>'
            self._send_html(HTML_FORM.format(message=msg, server_url=SERVER_URL))
            return
        except Exception as e:
            msg = f'<p class="error">Erreur réseau : {e}</p>'
            self._send_html(HTML_FORM.format(message=msg, server_url=SERVER_URL))
            return

        api_key = data.get("api_key")
        tireuse_uuid = data.get("tireuse_uuid")

        if not api_key or not tireuse_uuid:
            msg = f'<p class="error">Réponse inattendue : {data}</p>'
            self._send_html(HTML_FORM.format(message=msg, server_url=SERVER_URL))
            return

        _ecrire_env({"API_KEY": api_key, "TIREUSE_UUID": tireuse_uuid})

        msg = '<p class="success">✓ Appairage réussi ! Redémarrage...</p>'
        self._send_html(HTML_FORM.format(message=msg, server_url=SERVER_URL))

        import threading
        threading.Timer(2.0, lambda: os.system("sudo systemctl restart tibeer")).start()

    def _send_html(self, html: str):
        contenu = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(contenu)))
        self.end_headers()
        self.wfile.write(contenu)


def demarrer(logger=None):
    """Démarre le serveur d'appairage. Écrit l'URL dans /tmp/tibeer_kiosk_url
    pour que .xinitrc ouvre Chromium sur la page de pairing.
    / Start pairing server. Writes URL to /tmp/tibeer_kiosk_url
    so .xinitrc opens Chromium on the pairing page."""
    # Signaler à .xinitrc que Chromium peut démarrer sur la page de pairing
    # / Signal .xinitrc that Chromium can start on the pairing page
    try:
        with open("/tmp/tibeer_kiosk_url", "w") as f:
            f.write(f"http://localhost:{PORT}/")
        open("/tmp/tibeer_cookie_ready", "w").close()
    except Exception as e:
        if logger:
            logger.warning(f"Impossible d'ecrire tmp files: {e}")

    if logger:
        logger.info(f"MODE APPAIRAGE — http://localhost:{PORT}/")
        logger.info(f"Serveur cible : {SERVER_URL}")
    else:
        print(f"MODE APPAIRAGE — http://localhost:{PORT}/")

    serveur = HTTPServer(("0.0.0.0", PORT), PairingHandler)
    serveur.serve_forever()
