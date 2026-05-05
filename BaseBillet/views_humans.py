"""
Vue dynamique pour humans.txt
/ Dynamic view for humans.txt

LOCALISATION : BaseBillet/views_humans.py

Sert le fichier /humans.txt a la racine du site.
Le contenu est identique pour tous les tenants : il decrit l'equipe qui a fabrique
la plateforme (Cooperative Code Commun), pas le tenant qui l'utilise.

Standard suivi : https://humanstxt.org/Standard.html

Routage : voir BaseBillet/urls.py (path 'humans.txt').
"""
from datetime import date
from pathlib import Path

from django.http import HttpResponse


def _read_version_info() -> tuple[str, str]:
    """
    Lit la version et la date de derniere modification du fichier VERSION.
    / Reads version and last modification date from the VERSION file.

    Le fichier VERSION (a la racine du projet) contient des lignes au format
    cle=valeur, par exemple :
        VERSION=1.7.16
        MIGRATE=0

    La date de modification du fichier reflete le dernier bump de version,
    elle sert donc de "Last update" pour humans.txt.
    / The file mtime reflects the last version bump, used as "Last update".
    """
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    version = "unknown"
    with open(version_file, "r", encoding="utf-8") as f:
        for line in f:
            ligne_propre = line.strip()
            if ligne_propre.startswith("VERSION="):
                version = ligne_propre.split("=", 1)[1].strip()
                break
    last_update = date.fromtimestamp(version_file.stat().st_mtime).isoformat()
    return version, last_update


# Lecture unique au chargement du module pour eviter de relire le fichier a chaque requete
# / Read once at module load to avoid re-reading on every request
PROJECT_VERSION, PROJECT_LAST_UPDATE = _read_version_info()


def humans_txt(request):
    """
    Renvoie le fichier humans.txt au format standard.
    / Returns humans.txt in the standard format.

    Le contenu est statique (memes infos pour tous les tenants).
    / Content is static (same info for all tenants).

    URL : https://<n'importe-quel-tenant>/humans.txt
    """
    # L'@ est encode en "[at]" : convention humans.txt anti-spam
    # / "@" is encoded as "[at]": humans.txt anti-spam convention
    content = f"""/* TEAM */
    Développement: Coopérative Code Commun
    Site: https://codecommun.coop
    Contact: contact [at] tibillet.re
    Location: France

/* SITE */
    Last update: {PROJECT_LAST_UPDATE}
    Version: {PROJECT_VERSION}
    Software: Django, Python, HTMX
    Standards: HTML5, CSS3, JSON-LD
    Components: Bootstrap 5, HTMX, SweetAlert2
    Source: https://github.com/TiBillet/Lespass
"""
    return HttpResponse(content, content_type="text/plain; charset=utf-8")
