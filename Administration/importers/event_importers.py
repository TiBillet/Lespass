import re
from datetime import datetime

import tablib
from django.template.defaultfilters import slugify
from django.utils.translation import gettext_lazy as _
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget

from BaseBillet.models import Event, PostalAddress


class PostalAddressForeignKeyWidget(ForeignKeyWidget):
    def clean(self, value, row=None, **kwargs):
        if not value:
            return None
        try:
            val = super().clean(value)
        except PostalAddress.DoesNotExist:
            # Create a new PostalAddress if it doesn't exist
            val = PostalAddress.objects.create(
                name=value,
                street_address=value,  # Using venue name as street address as a fallback
                address_locality="Montpellier",  # Default values, can be updated later
                postal_code="34000",
                address_country="France"
            )
        return val


# Le moteur d'importation pour les événements
class EventImportResource(resources.ModelResource):
    postal_address = fields.Field(
        column_name='LIEU',
        attribute='postal_address',
        widget=PostalAddressForeignKeyWidget(PostalAddress, field='name')
    )

    style = fields.Field(
        column_name='STYLE',
        attribute='short_description'
    )

    def import_data(self, dataset, dry_run=False, raise_errors=False, use_transactions=None, collect_failed_rows=False, **kwargs):
        """
        Override import_data to handle the special date format in the CSV file.
        Dates are in separate rows with format "Jeu 03/04" (day of week + day/month).
        """
        # Current date to use for events
        current_date = None
        current_year = datetime.now().year  # Default to current year

        # New dataset with only valid event rows
        new_dataset = tablib.Dataset(headers=dataset.headers)

        # Process each row
        for row in dataset:
            row_dict = dict(zip(dataset.headers, row))

            # Check if this is a date row (e.g., "Jeu 03/04")
            heure = row_dict.get('HEURE', '')
            if heure and re.match(r'^(Lun|Mar|Mer|Jeu|Ven|Sam|Dim)\s+\d{2}/\d{2}$', heure):
                # Extract date from format "Jeu 03/04"
                date_parts = heure.split(' ')[1].split('/')
                day = int(date_parts[0])
                month = int(date_parts[1])

                # Create a datetime object
                current_date = datetime(current_year, month, day)
                continue

            # If we have a valid event row with time and group
            if current_date and row_dict.get('HEURE') and row_dict.get('GROUPE'):
                # Add the row to the new dataset
                new_dataset.append(row)

        # Process the new dataset with the standard import_data method
        result = super().import_data(
            new_dataset, 
            dry_run=dry_run, 
            raise_errors=raise_errors, 
            use_transactions=use_transactions, 
            collect_failed_rows=collect_failed_rows,
            current_date=current_date,  # Pass the current date to before_import_row
            **kwargs
        )

        return result

    def before_import_row(self, row, **kwargs):
        # Get the current date from the dataset
        current_date = kwargs.get('current_date', None)

        # If we have a date and the row has time (HEURE)
        if current_date and row.get('HEURE'):
            # Parse the time (format: "12h30")
            time_str = row.get('HEURE')
            if time_str:
                hour, minute = time_str.replace('h', ':').split(':')

                # Create a datetime string in ISO format
                date_str = f"{current_date.year}-{current_date.month:02d}-{current_date.day:02d} {hour}:{minute}:00"
                row['datetime'] = date_str

                # Set the name from GROUPE
                row['name'] = row.get('GROUPE', '')

                # Set categorie based on STYLE
                style = row.get('STYLE', '')
                if 'Concert' in style or 'concert' in style:
                    row['categorie'] = Event.CONCERT
                elif 'Festival' in style or 'festival' in style:
                    row['categorie'] = Event.FESTIVAL
                elif 'Conférence' in style or 'conférence' in style:
                    row['categorie'] = Event.CONFERENCE
                else:
                    row['categorie'] = Event.CONCERT  # Default

                # Set published to True
                row['published'] = True

    def before_save_instance(self, instance, row, **kwargs):
        # Generate a slug if not present
        if not instance.slug:
            instance.slug = slugify(instance.name)

    class Meta:
        model = Event
        fields = (
            'name',
            'datetime',
            'postal_address',
            'short_description',
            'categorie',
            'published',
        )
        import_id_fields = ('name', 'datetime')