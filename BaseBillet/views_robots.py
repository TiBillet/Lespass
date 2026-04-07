# DEPRECATED: Ce fichier est remplace par seo/views_common.py (robots_txt).
# Conserve temporairement pour reference.
# / DEPRECATED: This file is replaced by seo/views_common.py (robots_txt).
# Kept temporarily for reference.

from django.http import HttpResponse


# The robots.txt file is accessible at: https://yourdomain.com/robots.txt
# It automatically includes a reference to the sitemap at: https://yourdomain.com/sitemap.xml
def robots_txt(request):
    """
    Generate a dynamic robots.txt file with the correct sitemap URL.

    This view is mapped to /robots.txt in BaseBillet/urls.py and generates
    a robots.txt file that:
    1. Allows all search engines to access all content
    2. Includes a reference to the sitemap.xml file with the correct domain

    Access URL: https://yourdomain.com/robots.txt
    """
    # Try to get the domain from the current site
    domain = request.get_host()

    # If domain doesn't include protocol, add it
    if not domain.startswith('http'):
        domain = f"https://{domain}"

    robots_content = f"""User-agent: *
Allow: /

# Allow all robots to access all content
# Sitemap location
Sitemap: {domain}/sitemap.xml
"""
    return HttpResponse(robots_content, content_type="text/plain")
