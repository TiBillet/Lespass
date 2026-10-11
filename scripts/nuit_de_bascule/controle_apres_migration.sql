-- =============================================================================
-- CONTRÔLE APRÈS LES MIGRATIONS — nuit de la bascule, étape 6.
-- / CHECK AFTER MIGRATIONS — cutover night, step 6.
--
-- LOCALISATION : scripts/nuit_de_bascule/controle_apres_migration.sql
-- PROCÉDURE    : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-nuit-procedure.md
--
-- LECTURE SEULE. Aucune donnée personnelle : seulement des nombres.
-- / READ ONLY. Counts only.
--
-- LANCER :
--   docker exec -i lespass_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < scripts/nuit_de_bascule/controle_apres_migration.sql
--
-- CE QU'IL FAUT LIRE :
--   - moteur de monnaie : `legacy` pour tous les lieux, sauf le pool `W` en `v2` ;
--   - ventes 0, règlements 0 (la reprise n'a pas encore tourné) ;
--   - lieux sans clé d'empreinte : 0 (laboutik 0002 la crée dans chaque lieu) ;
--   - anciennes clôtures : le même nombre qu'à l'étape 4 (supprimées à l'étape 7).
-- =============================================================================

SET default_transaction_read_only = on;

SELECT categorie, moteur_monnaie, count(*) AS lieux
FROM public."Customers_client"
WHERE schema_name <> 'public'
GROUP BY categorie, moteur_monnaie
ORDER BY categorie, moteur_monnaie;

DO $$
DECLARE
    lieu record;
    nombre bigint;
    ventes bigint := 0;
    reglements bigint := 0;
    lieux_sans_cle_d_empreinte bigint := 0;
    anciennes_clotures bigint := 0;
BEGIN
    FOR lieu IN SELECT schema_name FROM public."Customers_client" WHERE schema_name <> 'public' LOOP
        EXECUTE format('SELECT count(*) FROM %I."BaseBillet_vente"', lieu.schema_name) INTO nombre;
        ventes := ventes + nombre;
        EXECUTE format('SELECT count(*) FROM %I."BaseBillet_reglement"', lieu.schema_name) INTO nombre;
        reglements := reglements + nombre;
        EXECUTE format('SELECT count(*) FROM %I.laboutik_laboutikconfiguration WHERE coalesce(hmac_key, '''') <> ''''', lieu.schema_name) INTO nombre;
        IF nombre = 0 THEN
            lieux_sans_cle_d_empreinte := lieux_sans_cle_d_empreinte + 1;
        END IF;
        EXECUTE format('SELECT count(*) FROM %I.comptabilite_cloturecaisse', lieu.schema_name) INTO nombre;
        anciennes_clotures := anciennes_clotures + nombre;
    END LOOP;

    RAISE NOTICE 'ventes : % (attendu : 0)', ventes;
    RAISE NOTICE 'règlements : % (attendu : 0)', reglements;
    RAISE NOTICE 'lieux sans clé d''empreinte : % (attendu : 0)', lieux_sans_cle_d_empreinte;
    RAISE NOTICE 'anciennes clôtures : % (attendu : le nombre de l''étape 4)', anciennes_clotures;
END $$;
