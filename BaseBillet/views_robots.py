from django.http import HttpResponse

from TiBillet.seo_indexing import should_noindex


# The robots.txt file is accessible at: https://yourdomain.com/robots.txt
# It automatically includes a reference to the sitemap at: https://yourdomain.com/sitemap.xml
def robots_txt(request):
    """
    Genere un robots.txt dynamique pour le tenant courant.
    / Generate a dynamic robots.txt for the current tenant.

    LOCALISATION : BaseBillet/views_robots.py

    Si l'instance est marquee noindex (au moins un flag d'env
    DEBUG/TEST/DEMO/STRIPE_TEST a 1), on sert `Disallow: /` pour
    bloquer le crawl. Sinon : `Allow: /` + sitemap.
    Voir TiBillet/seo_indexing.py pour la regle complete.
    / If the instance is marked noindex (at least one env flag
    DEBUG/TEST/DEMO/STRIPE_TEST is 1), we serve `Disallow: /`.
    Otherwise: `Allow: /` + sitemap reference.

    Access URL: https://yourdomain.com/robots.txt
    """
    if should_noindex():
        # Instance non indexable : on bloque le crawl entier.
        # / Non-indexable instance: block all crawling.
        return HttpResponse(
            "User-agent: *\nDisallow: /\n",
            content_type="text/plain",
        )

    # Instance prod : crawl autorise + reference du sitemap
    # / Prod instance: crawling allowed + sitemap reference
    domain = request.get_host()
    if not domain.startswith('http'):
        domain = f"https://{domain}"

    robots_content = f"""User-agent: *
Allow: /

# Allow all robots to access all content
# Sitemap location
Sitemap: {domain}/sitemap.xml
"""
    return HttpResponse(robots_content, content_type="text/plain")
