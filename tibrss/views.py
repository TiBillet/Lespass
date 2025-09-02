from django.db import connection
from django.shortcuts import render

# Create your views here.

from django.contrib.syndication.views import Feed
from django.urls import reverse
from django.utils import feedgenerator

from BaseBillet.models import Event, Configuration
from Customers.models import Client


class LatestEntriesEvent(Feed):
    description = "Derniers évènements créés"
    base_url = "https://www.tibilet.coop"

    def link(self):
        link = "/rss/latest/feed/"
        try:
            if connection.tenant:
                if connection.tenant.categorie != Client.ROOT:
                    link = f"https://{connection.tenant.get_primary_domain().domain}/rss/latest/feed/"
                    self.base_url = f"https://{connection.tenant.get_primary_domain().domain}"
        except AttributeError:
            link = "https://www.tibillet.coop/rss/latest/feed/"

        return link


    def title(self):
        name_orga = ""
        try:
            if connection.tenant:
                if connection.tenant.categorie != Client.ROOT:
                    config = Configuration.get_solo()
                    name_orga = f"{config.organisation}"
        except AttributeError:
            name_orga = ""

        return f"{name_orga} : Derniers évènements créés"

    def items(self):
        """

        :return: list
        """
        return Event.objects.order_by('-created')[:20]

    def item_title(self, item: Event):
        return f"{item.name} : {item.datetime.strftime('%D %R')}"

    def item_description(self, item: Event):
        import re

        # Function to remove control characters
        def remove_control_chars(text):
            if text:
                # Remove control characters (ASCII 0-8, 11-12, 14-31)
                return re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", text)
            return ""

        if item.short_description and item.long_description:
            return f"{remove_control_chars(item.short_description)} - {remove_control_chars(item.long_description)}"
        elif item.long_description:
            return remove_control_chars(item.long_description)
        elif item.short_description:
            return remove_control_chars(item.short_description)

        return ""

    # item_link is only needed if NewsItem has no get_absolute_url method.
    def item_link(self, item):
        # return reverse('show_event', args=[item.slug])
        return item.url()

    def item_pubdate(self, item: Event):
        return item.created

    def item_enclosures(self, item: Event):
        # Build an enclosure only if an image URL can be resolved without touching the filesystem.
        try:
            if not item.img:
                return ""

            # Prefer a resized/variant URL if available, else fallback to the original URL.
            url_path = None
            med = getattr(item.img, "med", None)
            if med and getattr(med, "url", None):
                url_path = med.url
            elif getattr(item.img, "url", None):
                url_path = item.img.url
            else:
                return ""

            # Ensure absolute URL based on base_url
            if url_path.startswith("/"):
                url_img = f"{self.base_url}{url_path}"
            else:
                url_img = f"{self.base_url}/{url_path}"

            # Determine a reasonable MIME type from the file extension without opening the file
            mime = "image/jpeg"
            lower_path = url_path.lower()
            if lower_path.endswith(".png"):
                mime = "image/png"
            elif lower_path.endswith(".gif"):
                mime = "image/gif"
            elif lower_path.endswith(".webp"):
                mime = "image/webp"

            # Do not call item.img.size to avoid filesystem access; RSS allows a length of 0
            return [feedgenerator.Enclosure(url_img, "0", mime)]
        except Exception:
            # In case of any problem (e.g., missing file), do not break the whole feed
            return ""
