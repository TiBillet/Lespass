from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone
from datetime import datetime, timedelta

from BaseBillet.models import Event, Configuration, Reservation, FederatedPlace, Tag
from Customers.models import Client

class ICalInvitationTest(TestCase):
    def setUp(self):
        # Créer un client pour les tests
        self.client = Client()
        
        # Créer un tenant
        self.tenant = Client.objects.create(
            name='test_tenant',
            categorie=Client.SALLE_SPECTACLE,
            schema_name='test_schema'
        )
        
        # Créer un tenant
        self.tenant2 = Client.objects.create(
            name='test_tenant2',
            categorie=Client.SALLE_SPECTACLE,
            schema_name='test_schema2'
        )
        
        # Créer une configuration
        self.config = Configuration.objects.create(
            organisation='Test Organization',
            tenant=self.tenant
        )
        
        # Créer un utilisateur admin associé au tenant
        User = get_user_model()
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='admin123',
            client_source=self.tenant
        )
        
        # Créer des tags pour les tests
        self.tag1 = Tag.objects.create(name='Concert')
        self.tag2 = Tag.objects.create(name='Festival')
        
        # Créer un événement
        self.event = Event.objects.create(
            name='Test Event',
            datetime=timezone.now() + timedelta(days=7),
            end_datetime=timezone.now() + timedelta(days=7, hours=2),
            short_description='Test Short Description',
            long_description='Test Long Description',
            published=True,
            tenant=self.tenant
        )
        self.event.tags.add(self.tag1)
        
        # Créer un autre tenant pour les tests de séparation
        self.other_tenant = Client.objects.create(
            name='Other Organization',
            categorie=Client.SALLE_SPECTACLE,
            schema_name='test_schema3'
        )
        
        # Créer une configuration pour l'autre tenant
        self.other_config = Configuration.objects.create(
            organisation='Other Organization',
            tenant=self.other_tenant
        )
        
        # Créer un événement pour l'autre tenant
        self.other_event = Event.objects.create(
            name='Other Event',
            datetime=timezone.now() + timedelta(days=7),
            end_datetime=timezone.now() + timedelta(days=7, hours=2),
            short_description='Other Short Description',
            long_description='Other Long Description',
            published=True,
            tenant=self.other_tenant
        )
        self.other_event.tags.add(self.tag2)
        
        # Créer une fédération entre les tenants
        self.federation = FederatedPlace.objects.create(
            tenant=self.tenant2
        )
        self.federation.tag_filter.add(self.tag1)
        
        # Se connecter en tant qu'admin
        self.client.login(username='admin', password='admin123')
    
    def test_send_invitation(self):
        """Test l'envoi d'une invitation"""
        # URL pour envoyer l'invitation
        url = reverse('admin:event-send-invitation', args=[self.event.uuid])
        
        # Données du formulaire
        data = {
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User'
        }
        
        # Envoyer l'invitation
        response = self.client.post(url, data)
        
        # Vérifier la réponse
        self.assertEqual(response.status_code, 302)  # Redirection après succès
        
        # Vérifier que l'utilisateur a été créé avec le bon client_source
        User = get_user_model()
        user = User.objects.get(email='test@example.com')
        self.assertEqual(user.client_source, self.tenant)
        
        # Vérifier que la réservation a été créée avec le bon tenant
        self.assertTrue(Reservation.objects.filter(
            event=self.event,
            user_commande=user,
            tenant=self.tenant
        ).exists())
        
        # Vérifier que l'email a été envoyé
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['test@example.com'])
        self.assertIn('Invitation à l\'événement', mail.outbox[0].subject)
    
    def test_accept_invitation(self):
        """Test l'acceptation d'une invitation"""
        # Créer un utilisateur et une réservation
        User = get_user_model()
        user = User.objects.create_user(
            email='test@example.com',
            first_name='Test',
            last_name='User',
            client_source=self.tenant
        )
        
        reservation = Reservation.objects.create(
            event=self.event,
            user_commande=user,
            status=Reservation.CREATED,
            ical_sequence=0,
            tenant=self.tenant
        )
        
        # URL pour accepter l'invitation
        url = reverse('accept_invitation', args=[self.event.uuid, reservation.uuid])
        
        # Accepter l'invitation
        response = self.client.get(url)
        
        # Vérifier la réponse
        self.assertEqual(response.status_code, 200)
        
        # Vérifier que le statut de la réservation a été mis à jour
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.VALID)
        self.assertEqual(reservation.ical_sequence, 1)
        self.assertEqual(reservation.tenant, self.tenant)
        
        # Vérifier que l'email de confirmation a été envoyé
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['test@example.com'])
        self.assertIn('Confirmation de participation', mail.outbox[0].subject)
    
    def test_decline_invitation(self):
        """Test le refus d'une invitation"""
        # Créer un utilisateur et une réservation
        User = get_user_model()
        user = User.objects.create_user(
            email='test@example.com',
            first_name='Test',
            last_name='User',
            client_source=self.tenant
        )
        
        reservation = Reservation.objects.create(
            event=self.event,
            user_commande=user,
            status=Reservation.CREATED,
            ical_sequence=0,
            tenant=self.tenant
        )
        
        # URL pour refuser l'invitation
        url = reverse('decline_invitation', args=[self.event.uuid, reservation.uuid])
        
        # Refuser l'invitation
        response = self.client.get(url)
        
        # Vérifier la réponse
        self.assertEqual(response.status_code, 200)
        
        # Vérifier que le statut de la réservation a été mis à jour
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.CANCELED)
        self.assertEqual(reservation.ical_sequence, 1)
        self.assertEqual(reservation.tenant, self.tenant)
        
        # Vérifier que l'email de confirmation a été envoyé
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['test@example.com'])
        self.assertIn('Confirmation de non-participation', mail.outbox[0].subject)
    
    def test_complete_flow(self):
        """Test le flux complet d'invitation"""
        # 1. Envoyer l'invitation
        url = reverse('admin:event-send-invitation', args=[self.event.uuid])
        data = {
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Vérifier que l'utilisateur et la réservation ont été créés
        User = get_user_model()
        user = User.objects.get(email='test@example.com')
        self.assertEqual(user.client_source, self.tenant)
        
        reservation = Reservation.objects.get(
            event=self.event,
            user_commande=user,
            tenant=self.tenant
        )
        
        # 2. Accepter l'invitation
        url = reverse('accept_invitation', args=[self.event.uuid, reservation.uuid])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Vérifier le statut final
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.VALID)
        self.assertEqual(reservation.tenant, self.tenant)
        
        # Vérifier les emails envoyés
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ['test@example.com'])
        self.assertEqual(mail.outbox[1].to, ['test@example.com'])
    
    def test_tenant_separation(self):
        """Test la séparation des tenants"""
        # Créer une réservation pour le premier tenant
        User = get_user_model()
        user = User.objects.create_user(
            email='test@example.com',
            first_name='Test',
            last_name='User',
            client_source=self.tenant
        )
        
        reservation1 = Reservation.objects.create(
            event=self.event,
            user_commande=user,
            status=Reservation.CREATED,
            ical_sequence=0,
            tenant=self.tenant
        )
        
        # Créer une réservation pour l'autre tenant
        reservation2 = Reservation.objects.create(
            event=self.other_event,
            user_commande=user,
            status=Reservation.CREATED,
            ical_sequence=0,
            tenant=self.other_tenant
        )
        
        # Vérifier que les réservations sont bien séparées
        self.assertEqual(reservation1.tenant, self.tenant)
        self.assertEqual(reservation2.tenant, self.other_tenant)
        
        # Vérifier que les URLs d'acceptation sont différentes
        url1 = reverse('accept_invitation', args=[self.event.uuid, reservation1.uuid])
        url2 = reverse('accept_invitation', args=[self.other_event.uuid, reservation2.uuid])
        self.assertNotEqual(url1, url2)
        
        # Accepter la première réservation
        response = self.client.get(url1)
        self.assertEqual(response.status_code, 200)
        
        # Vérifier que seule la première réservation a été mise à jour
        reservation1.refresh_from_db()
        reservation2.refresh_from_db()
        self.assertEqual(reservation1.status, Reservation.VALID)
        self.assertEqual(reservation2.status, Reservation.CREATED)
    
    def test_federation_with_tags(self):
        """Test la fédération avec filtrage par tags"""
        # Créer un nouvel événement avec le tag1 pour le tenant principal
        event_with_tag1 = Event.objects.create(
            name='Event with Tag1',
            datetime=timezone.now() + timedelta(days=7),
            end_datetime=timezone.now() + timedelta(days=7, hours=2),
            published=True,
            tenant=self.tenant
        )
        event_with_tag1.tags.add(self.tag1)

        # Créer un événement avec le tag2 pour le tenant principal
        event_with_tag2 = Event.objects.create(
            name='Event with Tag2',
            datetime=timezone.now() + timedelta(days=7),
            end_datetime=timezone.now() + timedelta(days=7, hours=2),
            published=True,
            tenant=self.tenant
        )
        event_with_tag2.tags.add(self.tag2)

        # Vérifier que seul l'événement avec tag1 est visible via la fédération
        federated_events = Event.objects.filter(
            tags__in=self.federation.tag_filter.all(),
            tenant=self.tenant
        ).distinct()

        self.assertIn(event_with_tag1, federated_events)
        self.assertNotIn(event_with_tag2, federated_events)

        # Ajouter un tag à exclure
        self.federation.tag_exclude.add(self.tag1)

        # Vérifier que l'événement avec tag1 n'est plus visible
        federated_events = Event.objects.filter(
            tags__in=self.federation.tag_filter.all(),
            tenant=self.tenant
        ).exclude(
            tags__in=self.federation.tag_exclude.all()
        ).distinct()

        self.assertNotIn(event_with_tag1, federated_events)
        self.assertNotIn(event_with_tag2, federated_events) 