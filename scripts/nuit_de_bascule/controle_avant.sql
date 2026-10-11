-- =============================================================================
-- CONTRÔLE AVANT LES MIGRATIONS — nuit de la bascule, étape 4.
-- / CHECK BEFORE MIGRATIONS — cutover night, step 4.
--
-- LOCALISATION : scripts/nuit_de_bascule/controle_avant.sql
-- PROCÉDURE    : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-nuit-procedure.md
--
-- LECTURE SEULE : la transaction est en lecture seule, rien ne peut être écrit.
-- Aucune donnée personnelle : seulement des nombres.
-- / READ ONLY. Counts only.
--
-- LANCER (sur le serveur, base de `main` NON migrée) :
--   docker exec -i lespass_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < scripts/nuit_de_bascule/controle_avant.sql
--
-- CE QU'IL FAUT LIRE :
--   1. « lieux de production avec un drapeau V2 » doit valoir 0. Sinon STOP :
--      la migration BaseBillet 0227 passerait ces lieux en moteur v2.
--   2. « comptes hors plan par défaut de main » doit valoir 0. Sinon STOP :
--      comptabilite 0005 supprime ces tables sans recopie (fiche R §12, QO-11).
--   3. « anciennes clôtures » : NOTER ce nombre. L'export de l'étape 5 doit
--      annoncer exactement le même.
-- =============================================================================

SET default_transaction_read_only = on;

DO $$
DECLARE
    lieu record;
    nombre bigint;
    colonne text;
    un_drapeau_v2 boolean;
    lieux_de_production bigint := 0;
    lieux_de_production_avec_un_drapeau_v2 bigint := 0;
    comptes_hors_plan_par_defaut bigint := 0;
    lieux_avec_comptes_hors_plan bigint := 0;
    anciennes_clotures bigint := 0;
    lieux_avec_anciennes_clotures bigint := 0;
BEGIN
    FOR lieu IN
        SELECT schema_name, categorie FROM public."Customers_client" WHERE schema_name <> 'public'
    LOOP
        -- 1. Les drapeaux V2. Une colonne absente de la configuration (ex. module_kiosk
        -- sur `main`) compte comme « faux ».
        -- / V2 flags. A missing column counts as false.
        IF lieu.categorie <> 'W' THEN
            lieux_de_production := lieux_de_production + 1;
            un_drapeau_v2 := false;
            FOREACH colonne IN ARRAY ARRAY['module_caisse', 'module_monnaie_locale', 'module_kiosk', 'module_tireuse'] LOOP
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = lieu.schema_name
                      AND table_name = 'BaseBillet_configuration'
                      AND column_name = colonne
                ) THEN
                    EXECUTE format('SELECT count(*) FROM %I."BaseBillet_configuration" WHERE %I', lieu.schema_name, colonne) INTO nombre;
                    IF nombre > 0 THEN
                        un_drapeau_v2 := true;
                    END IF;
                END IF;
            END LOOP;
            IF un_drapeau_v2 THEN
                lieux_de_production_avec_un_drapeau_v2 := lieux_de_production_avec_un_drapeau_v2 + 1;
            END IF;
        END IF;

        -- 2. Le plan comptable : seuls les 9 comptes semés par main:comptabilite 0002.
        -- / Chart of accounts: only main's 9 seeded accounts.
        IF to_regclass(format('%I.comptabilite_comptecomptable', lieu.schema_name)) IS NOT NULL THEN
            EXECUTE format(
                'SELECT count(*) FROM %I.comptabilite_comptecomptable
                 WHERE numero NOT IN (''411000'', ''4457100'', ''4457200'', ''4457300'',
                                      ''511000'', ''512000'', ''530000'', ''706000'', ''756000'')',
                lieu.schema_name
            ) INTO nombre;
            comptes_hors_plan_par_defaut := comptes_hors_plan_par_defaut + nombre;
            IF nombre > 0 THEN
                lieux_avec_comptes_hors_plan := lieux_avec_comptes_hors_plan + 1;
            END IF;
        END IF;

        -- 3. Les anciennes clôtures, comptées ici indépendamment de la commande d'export.
        -- / Old closures, counted independently of the export command.
        IF to_regclass(format('%I.comptabilite_cloturecaisse', lieu.schema_name)) IS NOT NULL THEN
            EXECUTE format('SELECT count(*) FROM %I.comptabilite_cloturecaisse', lieu.schema_name) INTO nombre;
            anciennes_clotures := anciennes_clotures + nombre;
            IF nombre > 0 THEN
                lieux_avec_anciennes_clotures := lieux_avec_anciennes_clotures + 1;
            END IF;
        END IF;
    END LOOP;

    RAISE NOTICE 'lieux de production (hors pool W) : %', lieux_de_production;
    RAISE NOTICE '1. lieux de production avec un drapeau V2 : % (attendu : 0)', lieux_de_production_avec_un_drapeau_v2;
    RAISE NOTICE '2. comptes hors plan par défaut de main : % dans % lieux (attendu : 0)', comptes_hors_plan_par_defaut, lieux_avec_comptes_hors_plan;
    RAISE NOTICE '3. anciennes clôtures : % dans % lieux (à NOTER pour l''étape 5)', anciennes_clotures, lieux_avec_anciennes_clotures;
END $$;
