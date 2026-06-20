"""
Verifie l'integrite des transactions fedow_core.
Verifies fedow_core transaction integrity.

LOCALISATION : fedow_core/management/commands/verify_transactions.py

3 verifications :
  1. Sequence des IDs (trous = WARNING, normal apres rollback PostgreSQL)
  2. Soldes Token vs somme des transactions (ERROR si divergence)
  3. Coherence tenant/asset (ERROR si transaction avec asset non autorise)

3 checks:
  1. ID sequence (gaps = WARNING, normal after PostgreSQL rollback)
  2. Token balances vs transaction sums (ERROR if divergence)
  3. Tenant/asset coherence (ERROR if transaction with unauthorized asset)

FLUX :
  1. Resoudre le filtre --tenant si demande
  2. _verifier_sequence_ids() : scanner les IDs, detecter les trous
  3. _verifier_soldes() : pour chaque Token, recalculer le solde attendu
  4. _verifier_coherence_tenant_asset() : verifier asset autorise par tenant
  5. Si --fix-tokens : recalculer Token.value pour les tokens divergents

DEPENDENCIES :
  - fedow_core.models (Transaction, Token, Asset)
  - fedow_core.services (actions_sans_debit : FST, CRE)

Lancement / Run:
    docker exec lespass_django poetry run python manage.py verify_transactions
    docker exec lespass_django poetry run python manage.py verify_transactions --tenant lespass --verbose
    docker exec lespass_django poetry run python manage.py verify_transactions --fix-tokens --yes
"""

from django.core.management.base import BaseCommand
from django.db.models import Q, Sum

from Customers.models import Client
from fedow_core.models import Asset, Token, Transaction


class Command(BaseCommand):
    help = "Verifie l'integrite des transactions fedow_core."

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant',
            type=str,
            default=None,
            help='Filtrer par schema_name du tenant (ex: lespass)',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            default=False,
            help='Afficher chaque verification en detail',
        )
        parser.add_argument(
            '--fix-tokens',
            action='store_true',
            default=False,
            help='Recalculer Token.value depuis les transactions (DANGEREUX)',
        )
        parser.add_argument(
            '--yes',
            action='store_true',
            default=False,
            help='Pas de confirmation interactive pour --fix-tokens',
        )

    def handle(self, *args, **options):
        self.verbose = options['verbose']
        self.tenant_filter = None
        self.nb_warnings = 0
        self.nb_errors = 0
        self.soldes_divergents = []

        # Resoudre le filtre tenant si demande.
        # Resolve tenant filter if requested.
        if options['tenant']:
            try:
                self.tenant_filter = Client.objects.get(
                    schema_name=options['tenant'],
                )
            except Client.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(
                        f"Tenant '{options['tenant']}' introuvable."
                    )
                )
                return

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== Verification de l'integrite fedow_core ==="
        ))

        self._verifier_sequence_ids()
        self._verifier_soldes()
        self._verifier_coherence_tenant_asset()

        # Resume / Summary
        self.stdout.write('')
        if self.nb_errors == 0 and self.nb_warnings == 0:
            self.stdout.write(self.style.SUCCESS(
                'OK — 0 erreur, 0 warning.'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f'Resultat : {self.nb_errors} erreur(s), {self.nb_warnings} warning(s).'
            ))

        # Option --fix-tokens : recalculer les soldes divergents.
        # --fix-tokens option: recalculate divergent balances.
        if options['fix_tokens'] and self.soldes_divergents:
            self._fix_tokens(options['yes'])

    def _verifier_sequence_ids(self):
        """
        Verifie la continuite des IDs de Transaction.
        Checks Transaction ID continuity.

        Les trous sont normaux apres un rollback PostgreSQL
        (la sequence avance meme si INSERT echoue).
        Gaps are normal after a PostgreSQL rollback
        (the sequence advances even if INSERT fails).
        """
        self.stdout.write(self.style.MIGRATE_HEADING(
            '\n--- 1. Verification sequence IDs ---'
        ))

        queryset = Transaction.objects.all()
        if self.tenant_filter:
            queryset = queryset.filter(tenant=self.tenant_filter)

        # Recuperer tous les IDs tries.
        # Get all sorted IDs.
        tous_les_ids = list(
            queryset.order_by('id').values_list('id', flat=True)
        )

        if len(tous_les_ids) == 0:
            self.stdout.write('  Aucune transaction trouvee.')
            return

        if self.verbose:
            self.stdout.write(
                f'  {len(tous_les_ids)} transactions, '
                f'IDs de {tous_les_ids[0]} a {tous_les_ids[-1]}'
            )

        # Detecter les trous.
        # Detect gaps.
        trous = []
        for i in range(1, len(tous_les_ids)):
            id_precedent = tous_les_ids[i - 1]
            id_courant = tous_les_ids[i]
            if id_courant != id_precedent + 1:
                trous.append((id_precedent, id_courant))

        if trous:
            self.nb_warnings += len(trous)
            for id_avant, id_apres in trous:
                self.stdout.write(self.style.WARNING(
                    f'  WARNING : trou entre ID {id_avant} et {id_apres} '
                    f'({id_apres - id_avant - 1} ID(s) manquant(s))'
                ))
        else:
            self.stdout.write(self.style.SUCCESS(
                '  OK — sequence continue, aucun trou.'
            ))

    def _verifier_soldes(self):
        """
        Verifie que Token.value == somme des credits - somme des debits.
        Verifies that Token.value == sum of credits - sum of debits.

        Utilise des aggregates SQL (GROUP BY) pour la performance.
        Uses SQL aggregates (GROUP BY) for performance.
        """
        self.stdout.write(self.style.MIGRATE_HEADING(
            '\n--- 2. Verification soldes ---'
        ))

        # Filtrer les tokens si un tenant est specifie.
        # On filtre via l'asset.tenant_origin (le token n'a pas de champ tenant).
        # Filter tokens if a tenant is specified.
        # We filter via asset.tenant_origin (token has no tenant field).
        tokens_qs = Token.objects.select_related('wallet', 'asset').all()
        if self.tenant_filter:
            tokens_qs = tokens_qs.filter(
                asset__tenant_origin=self.tenant_filter,
            )

        # Construire le filtre de transactions pour le tenant.
        # Build the transaction filter for the tenant.
        tx_base_filter = Q()
        if self.tenant_filter:
            tx_base_filter = Q(tenant=self.tenant_filter)

        nb_tokens_verifies = 0
        nb_tokens_ok = 0

        # Actions qui ne debitent pas le sender (cf. services.py ligne 429).
        # Actions that don't debit the sender (see services.py line 429).
        actions_sans_debit = [Transaction.FIRST, Transaction.CREATION]

        for token in tokens_qs:
            wallet = token.wallet
            asset = token.asset

            # Credits : transactions ou ce wallet est receiver pour cet asset.
            # Credits: transactions where this wallet is receiver for this asset.
            total_credite = Transaction.objects.filter(
                tx_base_filter,
                receiver=wallet,
                asset=asset,
            ).aggregate(total=Sum('amount'))['total'] or 0

            # Debits : transactions ou ce wallet est sender pour cet asset,
            # SAUF actions sans debit (FST, CRE).
            # Debits: transactions where this wallet is sender for this asset,
            # EXCEPT no-debit actions (FST, CRE).
            total_debite = Transaction.objects.filter(
                tx_base_filter,
                sender=wallet,
                asset=asset,
            ).exclude(
                action__in=actions_sans_debit,
            ).aggregate(total=Sum('amount'))['total'] or 0

            solde_attendu = total_credite - total_debite

            nb_tokens_verifies += 1

            if token.value != solde_attendu:
                self.nb_errors += 1
                self.soldes_divergents.append({
                    'token_pk': token.pk,
                    'wallet_name': str(wallet),
                    'asset_name': str(asset),
                    'token_value': token.value,
                    'solde_attendu': solde_attendu,
                })
                self.stdout.write(self.style.ERROR(
                    f'  ERROR : Token {wallet}/{asset.name} : '
                    f'value={token.value}, attendu={solde_attendu} '
                    f'(ecart={token.value - solde_attendu})'
                ))
            else:
                nb_tokens_ok += 1
                if self.verbose:
                    self.stdout.write(
                        f'  OK : {wallet}/{asset.name} = {token.value}'
                    )

        self.stdout.write(
            f'  {nb_tokens_verifies} token(s) verifie(s), '
            f'{nb_tokens_ok} OK, {len(self.soldes_divergents)} divergent(s).'
        )

    def _verifier_coherence_tenant_asset(self):
        """
        Verifie que chaque Transaction utilise un asset autorise pour son tenant.
        Verifies that each Transaction uses an asset authorized for its tenant.

        Un asset est autorise si :
        - asset.tenant_origin == transaction.tenant (asset local)
        - OU transaction.tenant est dans asset.federated_with (asset federe)
        An asset is authorized if:
        - asset.tenant_origin == transaction.tenant (local asset)
        - OR transaction.tenant is in asset.federated_with (federated asset)
        """
        self.stdout.write(self.style.MIGRATE_HEADING(
            '\n--- 3. Verification coherence tenant/asset ---'
        ))

        queryset = Transaction.objects.select_related(
            'asset', 'tenant',
        ).all()
        if self.tenant_filter:
            queryset = queryset.filter(tenant=self.tenant_filter)

        # Cache des paires (asset_uuid, tenant_pk) valides.
        # Evite N+1 queries sur federated_with.
        # Cache of valid (asset_uuid, tenant_pk) pairs.
        # Avoids N+1 queries on federated_with.
        cache_paires_valides = set()

        nb_transactions_verifiees = 0
        nb_incoherences = 0

        for tx in queryset.iterator():
            cle_cache = (tx.asset_id, tx.tenant_id)

            if cle_cache in cache_paires_valides:
                nb_transactions_verifiees += 1
                continue

            # Verifier si l'asset est autorise pour ce tenant.
            # Check if the asset is authorized for this tenant.
            asset_est_local = (tx.asset.tenant_origin_id == tx.tenant_id)
            asset_est_federe = False

            if not asset_est_local:
                asset_est_federe = tx.asset.federated_with.filter(
                    pk=tx.tenant_id,
                ).exists()

            if asset_est_local or asset_est_federe:
                cache_paires_valides.add(cle_cache)
            else:
                nb_incoherences += 1
                self.nb_errors += 1
                self.stdout.write(self.style.ERROR(
                    f'  ERROR : Transaction #{tx.id} — '
                    f'asset "{tx.asset.name}" (tenant_origin={tx.asset.tenant_origin_id}) '
                    f'non autorise pour tenant {tx.tenant_id}'
                ))

            nb_transactions_verifiees += 1

        if nb_incoherences == 0:
            self.stdout.write(self.style.SUCCESS(
                f'  OK — {nb_transactions_verifiees} transaction(s) verifiee(s), '
                f'aucune incoherence.'
            ))
        else:
            self.stdout.write(
                f'  {nb_transactions_verifiees} transaction(s) verifiee(s), '
                f'{nb_incoherences} incoherence(s).'
            )

    def _fix_tokens(self, skip_confirmation):
        """
        Recalcule Token.value depuis les transactions pour les tokens divergents.
        Recalculates Token.value from transactions for divergent tokens.
        """
        self.stdout.write(self.style.WARNING(
            f'\n--- Correction de {len(self.soldes_divergents)} token(s) divergent(s) ---'
        ))

        if not skip_confirmation:
            self.stdout.write(self.style.WARNING(
                'ATTENTION : cette operation modifie les soldes en base.'
            ))
            reponse = input('Confirmer ? (oui/non) : ')
            if reponse.strip().lower() != 'oui':
                self.stdout.write('Annule.')
                return

        nb_corriges = 0
        for divergence in self.soldes_divergents:
            token = Token.objects.get(pk=divergence['token_pk'])
            ancienne_valeur = token.value
            nouvelle_valeur = divergence['solde_attendu']

            token.value = nouvelle_valeur
            token.save(update_fields=['value'])

            nb_corriges += 1
            self.stdout.write(self.style.SUCCESS(
                f'  Corrige : {divergence["wallet_name"]}/{divergence["asset_name"]} '
                f'{ancienne_valeur} → {nouvelle_valeur}'
            ))

        self.stdout.write(self.style.SUCCESS(
            f'{nb_corriges} token(s) corrige(s).'
        ))
