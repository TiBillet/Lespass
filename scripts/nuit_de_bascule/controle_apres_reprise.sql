-- =============================================================================
-- CONTRÔLE APRÈS LA REPRISE ET LA J « REPRISE » — nuit de la bascule, étapes 9 et 10.
-- / CHECK AFTER THE TAKEOVER AND THE "REPRISE" DAILY CLOSURE — steps 9 and 10.
--
-- LOCALISATION : scripts/nuit_de_bascule/controle_apres_reprise.sql
-- PROCÉDURE    : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-nuit-procedure.md
--
-- LECTURE SEULE. Aucune donnée personnelle : seulement des nombres.
-- / READ ONLY. Counts only.
--
-- LANCER :
--   docker exec -i lespass_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < scripts/nuit_de_bascule/controle_apres_reprise.sql
--
-- CE QU'IL FAUT LIRE (après l'étape 9) :
--   lignes sans vente 0 ; avoirs sans vente liée 0 ; ventes hors reprise 0 ;
--   paiements T sans vente 0 ; anciennes clôtures 0 (étape 7 faite).
-- APRÈS L'ÉTAPE 10, EN PLUS :
--   clôtures : une J par lieu qui a des ventes réglées, toutes marquées « reprise ».
-- =============================================================================

SET default_transaction_read_only = on;

DO $$
DECLARE
    lieu record;
    nombre bigint;
    lignes_sans_vente bigint := 0;
    avoirs_sans_vente_liee bigint := 0;
    ventes_hors_reprise bigint := 0;
    paiements_t_sans_vente bigint := 0;
    lieux_avec_ventes_reglees bigint := 0;
    clotures bigint := 0;
    j_reprise bigint := 0;
BEGIN
    FOR lieu IN SELECT schema_name FROM public."Customers_client" WHERE schema_name <> 'public' LOOP
        EXECUTE format('SELECT count(*) FROM %I."BaseBillet_lignearticle" WHERE vente_id IS NULL', lieu.schema_name) INTO nombre;
        lignes_sans_vente := lignes_sans_vente + nombre;
        EXECUTE format('SELECT count(*) FROM %I."BaseBillet_vente" WHERE nature = ''AVOIR'' AND vente_liee_id IS NULL', lieu.schema_name) INTO nombre;
        avoirs_sans_vente_liee := avoirs_sans_vente_liee + nombre;
        EXECUTE format('SELECT count(*) FROM %I."BaseBillet_vente" WHERE coalesce(idempotency_key, '''') NOT LIKE ''reprise-%%''', lieu.schema_name) INTO nombre;
        ventes_hors_reprise := ventes_hors_reprise + nombre;
        EXECUTE format('SELECT count(*) FROM %I."BaseBillet_paiement_stripe" WHERE source = ''T'' AND vente_id IS NULL', lieu.schema_name) INTO nombre;
        paiements_t_sans_vente := paiements_t_sans_vente + nombre;
        EXECUTE format('SELECT count(*) FROM %I."BaseBillet_vente" WHERE statut = ''REGLEE''', lieu.schema_name) INTO nombre;
        IF nombre > 0 THEN
            lieux_avec_ventes_reglees := lieux_avec_ventes_reglees + 1;
        END IF;
        EXECUTE format('SELECT count(*) FROM %I.comptabilite_cloturecaisse', lieu.schema_name) INTO nombre;
        clotures := clotures + nombre;
        EXECUTE format('SELECT count(*) FROM %I.comptabilite_cloturecaisse WHERE rapport_json -> ''en_tete'' ->> ''reprise'' = ''true''', lieu.schema_name) INTO nombre;
        j_reprise := j_reprise + nombre;
    END LOOP;

    RAISE NOTICE 'lignes sans vente : % (attendu : 0)', lignes_sans_vente;
    RAISE NOTICE 'avoirs sans vente liée : % (attendu : 0)', avoirs_sans_vente_liee;
    RAISE NOTICE 'ventes hors reprise : % (attendu : 0)', ventes_hors_reprise;
    RAISE NOTICE 'paiements T sans vente : % (attendu : 0)', paiements_t_sans_vente;
    RAISE NOTICE 'lieux avec des ventes réglées : %', lieux_avec_ventes_reglees;
    RAISE NOTICE 'clôtures : % dont J « reprise » : % (après l''étape 10, attendu : une J reprise par lieu avec des ventes réglées, aucune autre clôture)', clotures, j_reprise;
END $$;
