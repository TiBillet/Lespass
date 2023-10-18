--
-- PostgreSQL database cluster dump
--

SET default_transaction_read_only = off;

SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

--
-- Roles
--

CREATE ROLE ticket_postgres_user;
ALTER ROLE ticket_postgres_user WITH SUPERUSER INHERIT CREATEROLE CREATEDB LOGIN REPLICATION BYPASSRLS PASSWORD 'md5c8aeb777cf7353e851dfc6d7d771f98d';






--
-- Databases
--

--
-- Database "template1" dump
--

\connect template1

--
-- PostgreSQL database dump
--

-- Dumped from database version 11.5
-- Dumped by pg_dump version 13.9 (Debian 13.9-0+deb11u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- PostgreSQL database dump complete
--

--
-- Database "postgres" dump
--

\connect postgres

--
-- PostgreSQL database dump
--

-- Dumped from database version 11.5
-- Dumped by pg_dump version 13.9 (Debian 13.9-0+deb11u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- PostgreSQL database dump complete
--

--
-- Database "tibillet" dump
--

--
-- PostgreSQL database dump
--

-- Dumped from database version 11.5
-- Dumped by pg_dump version 13.9 (Debian 13.9-0+deb11u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: tibillet; Type: DATABASE; Schema: -; Owner: ticket_postgres_user
--

CREATE DATABASE tibillet WITH TEMPLATE = template0 ENCODING = 'UTF8' LOCALE = 'en_US.utf8';


ALTER DATABASE tibillet OWNER TO ticket_postgres_user;

\connect tibillet

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: balaphonik-sound-system; Type: SCHEMA; Schema: -; Owner: ticket_postgres_user
--

CREATE SCHEMA "balaphonik-sound-system";


ALTER SCHEMA "balaphonik-sound-system" OWNER TO ticket_postgres_user;

--
-- Name: billetistan; Type: SCHEMA; Schema: -; Owner: ticket_postgres_user
--

CREATE SCHEMA billetistan;


ALTER SCHEMA billetistan OWNER TO ticket_postgres_user;

--
-- Name: demo; Type: SCHEMA; Schema: -; Owner: ticket_postgres_user
--

CREATE SCHEMA demo;


ALTER SCHEMA demo OWNER TO ticket_postgres_user;

--
-- Name: meta; Type: SCHEMA; Schema: -; Owner: ticket_postgres_user
--

CREATE SCHEMA meta;


ALTER SCHEMA meta OWNER TO ticket_postgres_user;

--
-- Name: ziskakan; Type: SCHEMA; Schema: -; Owner: ticket_postgres_user
--

CREATE SCHEMA ziskakan;


ALTER SCHEMA ziskakan OWNER TO ticket_postgres_user;

SET default_tablespace = '';

--
-- Name: BaseBillet_externalapikey; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_externalapikey" (
    id integer NOT NULL,
    ip inet NOT NULL,
    revoquer_apikey boolean NOT NULL,
    created timestamp with time zone NOT NULL,
    name character varying(30) NOT NULL,
    event boolean NOT NULL,
    product boolean NOT NULL,
    artist boolean NOT NULL,
    place boolean NOT NULL,
    user_id uuid,
    reservation boolean NOT NULL,
    ticket boolean NOT NULL,
    key_id character varying(150)
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_externalapikey" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_apikey_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_apikey_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_apikey_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_externalapikey".id;


--
-- Name: BaseBillet_artist_on_event; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_artist_on_event" (
    id integer NOT NULL,
    datetime timestamp with time zone NOT NULL,
    artist_id uuid NOT NULL,
    event_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_artist_on_event" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_artist_on_event_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_artist_on_event_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_artist_on_event_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_artist_on_event".id;


--
-- Name: BaseBillet_configuration; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_configuration" (
    id integer NOT NULL,
    organisation character varying(50) NOT NULL,
    short_description character varying(250),
    long_description text,
    adress character varying(250),
    postal_code integer,
    city character varying(250),
    phone character varying(20) NOT NULL,
    email character varying(254) NOT NULL,
    site_web character varying(200),
    twitter character varying(200),
    facebook character varying(200),
    instagram character varying(200),
    map_img character varying(100),
    carte_restaurant character varying(100),
    img character varying(100),
    fuseau_horaire character varying(50) NOT NULL,
    logo character varying(100),
    stripe_api_key character varying(110),
    stripe_test_api_key character varying(110),
    stripe_mode_test boolean NOT NULL,
    jauge_max smallint NOT NULL,
    server_cashless character varying(300),
    key_cashless character varying(41),
    template_billetterie character varying(250),
    template_meta character varying(250),
    activate_mailjet boolean NOT NULL,
    email_confirm_template integer NOT NULL,
    slug character varying(50) NOT NULL,
    legal_documents character varying(200),
    stripe_connect_account character varying(21),
    stripe_connect_account_test character varying(21),
    stripe_payouts_enabled boolean NOT NULL,
    federated_cashless boolean NOT NULL,
    ghost_key character varying(200),
    ghost_last_log text,
    ghost_url character varying(200),
    key_fedow character varying(41),
    server_fedow character varying(300),
    CONSTRAINT "BaseBillet_configuration_jauge_max_check" CHECK ((jauge_max >= 0))
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_configuration" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_configuration_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_configuration_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_configuration_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_configuration".id;


--
-- Name: BaseBillet_configuration_option_generale_checkbox; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox" (
    id integer NOT NULL,
    configuration_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox".id;


--
-- Name: BaseBillet_configuration_option_generale_radio; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio" (
    id integer NOT NULL,
    configuration_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio".id;


--
-- Name: BaseBillet_event; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_event" (
    uuid uuid NOT NULL,
    name character varying(200) NOT NULL,
    slug character varying(250),
    datetime timestamp with time zone NOT NULL,
    created timestamp with time zone NOT NULL,
    short_description character varying(250),
    long_description text,
    url_external character varying(200),
    published boolean NOT NULL,
    img character varying(100),
    categorie character varying(3) NOT NULL,
    jauge_max smallint NOT NULL,
    minimum_cashless_required smallint NOT NULL,
    max_per_user smallint NOT NULL,
    is_external boolean NOT NULL,
    booking boolean NOT NULL,
    CONSTRAINT "BaseBillet_event_jauge_max_check" CHECK ((jauge_max >= 0)),
    CONSTRAINT "BaseBillet_event_max_per_user_check" CHECK ((max_per_user >= 0))
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_event" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_event_options_checkbox" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_event_options_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_event_options_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_event_options_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_event_options_checkbox_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_event_options_checkbox".id;


--
-- Name: BaseBillet_event_options_radio; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_event_options_radio" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_event_options_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_event_options_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_event_options_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_event_options_radio_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_event_options_radio".id;


--
-- Name: BaseBillet_event_products; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_event_products" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    product_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_event_products" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_event_products_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_event_products_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_event_products_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_event_products".id;


--
-- Name: BaseBillet_event_recurrent; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_event_recurrent" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    weekday_id integer NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_event_recurrent" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_event_recurrent_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_event_recurrent_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_event_recurrent_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_event_recurrent".id;


--
-- Name: BaseBillet_event_tag; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_event_tag" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    tag_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_event_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_event_tag_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_event_tag_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_event_tag_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_event_tag".id;


--
-- Name: BaseBillet_lignearticle; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_lignearticle" (
    uuid uuid NOT NULL,
    datetime timestamp with time zone NOT NULL,
    qty smallint NOT NULL,
    status character varying(3) NOT NULL,
    carte_id integer,
    paiement_stripe_id uuid,
    pricesold_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_lignearticle" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_membership" (
    id integer NOT NULL,
    date_added timestamp with time zone NOT NULL,
    first_contribution date,
    last_contribution date,
    contribution_value double precision,
    last_action timestamp with time zone NOT NULL,
    first_name character varying(200),
    last_name character varying(200),
    pseudo character varying(50),
    newsletter boolean NOT NULL,
    postal_code integer,
    birth_date date,
    phone character varying(20),
    commentaire text,
    user_id uuid NOT NULL,
    price_id uuid,
    stripe_id_subscription character varying(28),
    last_stripe_invoice character varying(278),
    status character varying(1) NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_membership" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_membership_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_membership_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_membership_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_membership".id;


--
-- Name: BaseBillet_membership_option_generale; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_membership_option_generale" (
    id integer NOT NULL,
    membership_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_membership_option_generale" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_membership_option_generale_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_membership_option_generale_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_membership_option_generale_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_membership_option_generale".id;


--
-- Name: BaseBillet_optiongenerale; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_optiongenerale" (
    uuid uuid NOT NULL,
    name character varying(30) NOT NULL,
    poids smallint NOT NULL,
    description character varying(250),
    CONSTRAINT "BaseBillet_optiongenerale_poids_check" CHECK ((poids >= 0))
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_optiongenerale" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_paiement_stripe; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_paiement_stripe" (
    uuid uuid NOT NULL,
    detail character varying(50),
    datetime timestamp with time zone NOT NULL,
    checkout_session_id_stripe character varying(80),
    payment_intent_id character varying(80),
    metadata_stripe jsonb,
    order_date timestamp with time zone NOT NULL,
    last_action timestamp with time zone NOT NULL,
    status character varying(1) NOT NULL,
    traitement_en_cours boolean NOT NULL,
    source_traitement character varying(1) NOT NULL,
    source character varying(1) NOT NULL,
    total double precision NOT NULL,
    reservation_id uuid,
    user_id uuid,
    customer_stripe character varying(20),
    invoice_stripe character varying(27),
    subscription character varying(28)
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_paiement_stripe" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_price; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_price" (
    uuid uuid NOT NULL,
    name character varying(50) NOT NULL,
    prix numeric(6,2) NOT NULL,
    vat character varying(2) NOT NULL,
    stock smallint,
    max_per_user smallint NOT NULL,
    product_id uuid NOT NULL,
    adhesion_obligatoire_id uuid,
    long_description text,
    short_description character varying(250),
    subscription_type character varying(1) NOT NULL,
    recurring_payment boolean NOT NULL,
    CONSTRAINT "BaseBillet_price_max_per_user_check" CHECK ((max_per_user >= 0))
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_price" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_pricesold; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_pricesold" (
    uuid uuid NOT NULL,
    id_price_stripe character varying(30),
    qty_solded smallint NOT NULL,
    prix numeric(6,2) NOT NULL,
    price_id uuid NOT NULL,
    productsold_id uuid NOT NULL,
    gift numeric(6,2)
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_pricesold" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_product" (
    uuid uuid NOT NULL,
    name character varying(500) NOT NULL,
    publish boolean NOT NULL,
    img character varying(100),
    categorie_article character varying(3) NOT NULL,
    long_description text,
    short_description character varying(250),
    terms_and_conditions_document character varying(200),
    send_to_cashless boolean NOT NULL,
    poids smallint NOT NULL,
    archive boolean NOT NULL,
    legal_link character varying(200),
    nominative boolean NOT NULL,
    CONSTRAINT "BaseBillet_product_poids_check" CHECK ((poids >= 0))
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_product" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox".id;


--
-- Name: BaseBillet_product_option_generale_radio; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_product_option_generale_radio" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_product_option_generale_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_product_option_generale_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_product_option_generale_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_product_option_generale_radio_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_product_option_generale_radio".id;


--
-- Name: BaseBillet_product_tag; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_product_tag" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    tag_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_product_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_product_tag_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_product_tag_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_product_tag_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_product_tag".id;


--
-- Name: BaseBillet_productsold; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_productsold" (
    uuid uuid NOT NULL,
    id_product_stripe character varying(30),
    event_id uuid,
    product_id uuid NOT NULL,
    categorie_article character varying(3) NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_productsold" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_reservation" (
    uuid uuid NOT NULL,
    datetime timestamp with time zone NOT NULL,
    status character varying(3) NOT NULL,
    to_mail boolean NOT NULL,
    mail_send boolean NOT NULL,
    mail_error boolean NOT NULL,
    event_id uuid NOT NULL,
    user_commande_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_reservation" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_reservation_options" (
    id integer NOT NULL,
    reservation_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_reservation_options" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_reservation_options_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_reservation_options_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_reservation_options_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_reservation_options".id;


--
-- Name: BaseBillet_tag; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_tag" (
    uuid uuid NOT NULL,
    name character varying(50) NOT NULL,
    color character varying(7) NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_ticket; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_ticket" (
    uuid uuid NOT NULL,
    first_name character varying(200) NOT NULL,
    last_name character varying(200) NOT NULL,
    status character varying(1) NOT NULL,
    seat character varying(20) NOT NULL,
    pricesold_id uuid NOT NULL,
    reservation_id uuid NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_ticket" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_webhook" (
    id integer NOT NULL,
    url character varying(200) NOT NULL,
    event character varying(2) NOT NULL,
    active boolean NOT NULL,
    last_response text
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_webhook" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_webhook_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_webhook_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_webhook_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_webhook".id;


--
-- Name: BaseBillet_weekday; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system"."BaseBillet_weekday" (
    id integer NOT NULL,
    day integer NOT NULL
);


ALTER TABLE "balaphonik-sound-system"."BaseBillet_weekday" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system"."BaseBillet_weekday_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system"."BaseBillet_weekday_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system"."BaseBillet_weekday_id_seq" OWNED BY "balaphonik-sound-system"."BaseBillet_weekday".id;


--
-- Name: django_content_type; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system".django_content_type (
    id integer NOT NULL,
    app_label character varying(100) NOT NULL,
    model character varying(100) NOT NULL
);


ALTER TABLE "balaphonik-sound-system".django_content_type OWNER TO ticket_postgres_user;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system".django_content_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system".django_content_type_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system".django_content_type_id_seq OWNED BY "balaphonik-sound-system".django_content_type.id;


--
-- Name: django_migrations; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system".django_migrations (
    id integer NOT NULL,
    app character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    applied timestamp with time zone NOT NULL
);


ALTER TABLE "balaphonik-sound-system".django_migrations OWNER TO ticket_postgres_user;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE SEQUENCE "balaphonik-sound-system".django_migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "balaphonik-sound-system".django_migrations_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER SEQUENCE "balaphonik-sound-system".django_migrations_id_seq OWNED BY "balaphonik-sound-system".django_migrations.id;


--
-- Name: rest_framework_api_key_apikey; Type: TABLE; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE TABLE "balaphonik-sound-system".rest_framework_api_key_apikey (
    id character varying(150) NOT NULL,
    created timestamp with time zone NOT NULL,
    name character varying(50) NOT NULL,
    revoked boolean NOT NULL,
    expiry_date timestamp with time zone,
    hashed_key character varying(150) NOT NULL,
    prefix character varying(8) NOT NULL
);


ALTER TABLE "balaphonik-sound-system".rest_framework_api_key_apikey OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_externalapikey; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_externalapikey" (
    id integer NOT NULL,
    ip inet NOT NULL,
    revoquer_apikey boolean NOT NULL,
    created timestamp with time zone NOT NULL,
    name character varying(30) NOT NULL,
    event boolean NOT NULL,
    product boolean NOT NULL,
    artist boolean NOT NULL,
    place boolean NOT NULL,
    user_id uuid,
    reservation boolean NOT NULL,
    ticket boolean NOT NULL,
    key_id character varying(150)
);


ALTER TABLE billetistan."BaseBillet_externalapikey" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_apikey_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_apikey_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_apikey_id_seq" OWNED BY billetistan."BaseBillet_externalapikey".id;


--
-- Name: BaseBillet_artist_on_event; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_artist_on_event" (
    id integer NOT NULL,
    datetime timestamp with time zone NOT NULL,
    artist_id uuid NOT NULL,
    event_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_artist_on_event" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_artist_on_event_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_artist_on_event_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_artist_on_event_id_seq" OWNED BY billetistan."BaseBillet_artist_on_event".id;


--
-- Name: BaseBillet_configuration; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_configuration" (
    id integer NOT NULL,
    organisation character varying(50) NOT NULL,
    short_description character varying(250),
    long_description text,
    adress character varying(250),
    postal_code integer,
    city character varying(250),
    phone character varying(20) NOT NULL,
    email character varying(254) NOT NULL,
    site_web character varying(200),
    twitter character varying(200),
    facebook character varying(200),
    instagram character varying(200),
    map_img character varying(100),
    carte_restaurant character varying(100),
    img character varying(100),
    fuseau_horaire character varying(50) NOT NULL,
    logo character varying(100),
    stripe_api_key character varying(110),
    stripe_test_api_key character varying(110),
    stripe_mode_test boolean NOT NULL,
    jauge_max smallint NOT NULL,
    server_cashless character varying(300),
    key_cashless character varying(41),
    template_billetterie character varying(250),
    template_meta character varying(250),
    activate_mailjet boolean NOT NULL,
    email_confirm_template integer NOT NULL,
    slug character varying(50) NOT NULL,
    legal_documents character varying(200),
    stripe_connect_account character varying(21),
    stripe_connect_account_test character varying(21),
    stripe_payouts_enabled boolean NOT NULL,
    federated_cashless boolean NOT NULL,
    ghost_key character varying(200),
    ghost_last_log text,
    ghost_url character varying(200),
    key_fedow character varying(41),
    server_fedow character varying(300),
    CONSTRAINT "BaseBillet_configuration_jauge_max_check" CHECK ((jauge_max >= 0))
);


ALTER TABLE billetistan."BaseBillet_configuration" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_configuration_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_configuration_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_configuration_id_seq" OWNED BY billetistan."BaseBillet_configuration".id;


--
-- Name: BaseBillet_configuration_option_generale_checkbox; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_configuration_option_generale_checkbox" (
    id integer NOT NULL,
    configuration_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_configuration_option_generale_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_configuration_option_generale_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_configuration_option_generale_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_configuration_option_generale_checkbox_id_seq" OWNED BY billetistan."BaseBillet_configuration_option_generale_checkbox".id;


--
-- Name: BaseBillet_configuration_option_generale_radio; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_configuration_option_generale_radio" (
    id integer NOT NULL,
    configuration_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_configuration_option_generale_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_configuration_option_generale_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_configuration_option_generale_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_configuration_option_generale_radio_id_seq" OWNED BY billetistan."BaseBillet_configuration_option_generale_radio".id;


--
-- Name: BaseBillet_event; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_event" (
    uuid uuid NOT NULL,
    name character varying(200) NOT NULL,
    slug character varying(250),
    datetime timestamp with time zone NOT NULL,
    created timestamp with time zone NOT NULL,
    short_description character varying(250),
    long_description text,
    url_external character varying(200),
    published boolean NOT NULL,
    img character varying(100),
    categorie character varying(3) NOT NULL,
    jauge_max smallint NOT NULL,
    minimum_cashless_required smallint NOT NULL,
    max_per_user smallint NOT NULL,
    is_external boolean NOT NULL,
    booking boolean NOT NULL,
    CONSTRAINT "BaseBillet_event_jauge_max_check" CHECK ((jauge_max >= 0)),
    CONSTRAINT "BaseBillet_event_max_per_user_check" CHECK ((max_per_user >= 0))
);


ALTER TABLE billetistan."BaseBillet_event" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_event_options_checkbox" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_event_options_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_event_options_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_event_options_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_event_options_checkbox_id_seq" OWNED BY billetistan."BaseBillet_event_options_checkbox".id;


--
-- Name: BaseBillet_event_options_radio; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_event_options_radio" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_event_options_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_event_options_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_event_options_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_event_options_radio_id_seq" OWNED BY billetistan."BaseBillet_event_options_radio".id;


--
-- Name: BaseBillet_event_products; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_event_products" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    product_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_event_products" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_event_products_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_event_products_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_event_products_id_seq" OWNED BY billetistan."BaseBillet_event_products".id;


--
-- Name: BaseBillet_event_recurrent; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_event_recurrent" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    weekday_id integer NOT NULL
);


ALTER TABLE billetistan."BaseBillet_event_recurrent" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_event_recurrent_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_event_recurrent_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_event_recurrent_id_seq" OWNED BY billetistan."BaseBillet_event_recurrent".id;


--
-- Name: BaseBillet_event_tag; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_event_tag" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    tag_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_event_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_event_tag_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_event_tag_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_event_tag_id_seq" OWNED BY billetistan."BaseBillet_event_tag".id;


--
-- Name: BaseBillet_lignearticle; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_lignearticle" (
    uuid uuid NOT NULL,
    datetime timestamp with time zone NOT NULL,
    qty smallint NOT NULL,
    status character varying(3) NOT NULL,
    carte_id integer,
    paiement_stripe_id uuid,
    pricesold_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_lignearticle" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_membership" (
    id integer NOT NULL,
    date_added timestamp with time zone NOT NULL,
    first_contribution date,
    last_contribution date,
    contribution_value double precision,
    last_action timestamp with time zone NOT NULL,
    first_name character varying(200),
    last_name character varying(200),
    pseudo character varying(50),
    newsletter boolean NOT NULL,
    postal_code integer,
    birth_date date,
    phone character varying(20),
    commentaire text,
    user_id uuid NOT NULL,
    price_id uuid,
    stripe_id_subscription character varying(28),
    last_stripe_invoice character varying(278),
    status character varying(1) NOT NULL
);


ALTER TABLE billetistan."BaseBillet_membership" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_membership_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_membership_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_membership_id_seq" OWNED BY billetistan."BaseBillet_membership".id;


--
-- Name: BaseBillet_membership_option_generale; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_membership_option_generale" (
    id integer NOT NULL,
    membership_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_membership_option_generale" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_membership_option_generale_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_membership_option_generale_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_membership_option_generale_id_seq" OWNED BY billetistan."BaseBillet_membership_option_generale".id;


--
-- Name: BaseBillet_optiongenerale; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_optiongenerale" (
    uuid uuid NOT NULL,
    name character varying(30) NOT NULL,
    poids smallint NOT NULL,
    description character varying(250),
    CONSTRAINT "BaseBillet_optiongenerale_poids_check" CHECK ((poids >= 0))
);


ALTER TABLE billetistan."BaseBillet_optiongenerale" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_paiement_stripe; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_paiement_stripe" (
    uuid uuid NOT NULL,
    detail character varying(50),
    datetime timestamp with time zone NOT NULL,
    checkout_session_id_stripe character varying(80),
    payment_intent_id character varying(80),
    metadata_stripe jsonb,
    order_date timestamp with time zone NOT NULL,
    last_action timestamp with time zone NOT NULL,
    status character varying(1) NOT NULL,
    traitement_en_cours boolean NOT NULL,
    source_traitement character varying(1) NOT NULL,
    source character varying(1) NOT NULL,
    total double precision NOT NULL,
    reservation_id uuid,
    user_id uuid,
    customer_stripe character varying(20),
    invoice_stripe character varying(27),
    subscription character varying(28)
);


ALTER TABLE billetistan."BaseBillet_paiement_stripe" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_price; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_price" (
    uuid uuid NOT NULL,
    name character varying(50) NOT NULL,
    prix numeric(6,2) NOT NULL,
    vat character varying(2) NOT NULL,
    stock smallint,
    max_per_user smallint NOT NULL,
    product_id uuid NOT NULL,
    adhesion_obligatoire_id uuid,
    long_description text,
    short_description character varying(250),
    subscription_type character varying(1) NOT NULL,
    recurring_payment boolean NOT NULL,
    CONSTRAINT "BaseBillet_price_max_per_user_check" CHECK ((max_per_user >= 0))
);


ALTER TABLE billetistan."BaseBillet_price" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_pricesold; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_pricesold" (
    uuid uuid NOT NULL,
    id_price_stripe character varying(30),
    qty_solded smallint NOT NULL,
    prix numeric(6,2) NOT NULL,
    price_id uuid NOT NULL,
    productsold_id uuid NOT NULL,
    gift numeric(6,2)
);


ALTER TABLE billetistan."BaseBillet_pricesold" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_product" (
    uuid uuid NOT NULL,
    name character varying(500) NOT NULL,
    publish boolean NOT NULL,
    img character varying(100),
    categorie_article character varying(3) NOT NULL,
    long_description text,
    short_description character varying(250),
    terms_and_conditions_document character varying(200),
    send_to_cashless boolean NOT NULL,
    poids smallint NOT NULL,
    archive boolean NOT NULL,
    legal_link character varying(200),
    nominative boolean NOT NULL,
    CONSTRAINT "BaseBillet_product_poids_check" CHECK ((poids >= 0))
);


ALTER TABLE billetistan."BaseBillet_product" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_product_option_generale_checkbox" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_product_option_generale_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_product_option_generale_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_product_option_generale_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_product_option_generale_checkbox_id_seq" OWNED BY billetistan."BaseBillet_product_option_generale_checkbox".id;


--
-- Name: BaseBillet_product_option_generale_radio; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_product_option_generale_radio" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_product_option_generale_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_product_option_generale_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_product_option_generale_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_product_option_generale_radio_id_seq" OWNED BY billetistan."BaseBillet_product_option_generale_radio".id;


--
-- Name: BaseBillet_product_tag; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_product_tag" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    tag_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_product_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_product_tag_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_product_tag_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_product_tag_id_seq" OWNED BY billetistan."BaseBillet_product_tag".id;


--
-- Name: BaseBillet_productsold; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_productsold" (
    uuid uuid NOT NULL,
    id_product_stripe character varying(30),
    event_id uuid,
    product_id uuid NOT NULL,
    categorie_article character varying(3) NOT NULL
);


ALTER TABLE billetistan."BaseBillet_productsold" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_reservation" (
    uuid uuid NOT NULL,
    datetime timestamp with time zone NOT NULL,
    status character varying(3) NOT NULL,
    to_mail boolean NOT NULL,
    mail_send boolean NOT NULL,
    mail_error boolean NOT NULL,
    event_id uuid NOT NULL,
    user_commande_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_reservation" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_reservation_options" (
    id integer NOT NULL,
    reservation_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_reservation_options" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_reservation_options_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_reservation_options_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_reservation_options_id_seq" OWNED BY billetistan."BaseBillet_reservation_options".id;


--
-- Name: BaseBillet_tag; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_tag" (
    uuid uuid NOT NULL,
    name character varying(50) NOT NULL,
    color character varying(7) NOT NULL
);


ALTER TABLE billetistan."BaseBillet_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_ticket; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_ticket" (
    uuid uuid NOT NULL,
    first_name character varying(200) NOT NULL,
    last_name character varying(200) NOT NULL,
    status character varying(1) NOT NULL,
    seat character varying(20) NOT NULL,
    pricesold_id uuid NOT NULL,
    reservation_id uuid NOT NULL
);


ALTER TABLE billetistan."BaseBillet_ticket" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_webhook" (
    id integer NOT NULL,
    url character varying(200) NOT NULL,
    event character varying(2) NOT NULL,
    active boolean NOT NULL,
    last_response text
);


ALTER TABLE billetistan."BaseBillet_webhook" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_webhook_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_webhook_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_webhook_id_seq" OWNED BY billetistan."BaseBillet_webhook".id;


--
-- Name: BaseBillet_weekday; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan."BaseBillet_weekday" (
    id integer NOT NULL,
    day integer NOT NULL
);


ALTER TABLE billetistan."BaseBillet_weekday" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan."BaseBillet_weekday_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan."BaseBillet_weekday_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan."BaseBillet_weekday_id_seq" OWNED BY billetistan."BaseBillet_weekday".id;


--
-- Name: django_content_type; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan.django_content_type (
    id integer NOT NULL,
    app_label character varying(100) NOT NULL,
    model character varying(100) NOT NULL
);


ALTER TABLE billetistan.django_content_type OWNER TO ticket_postgres_user;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan.django_content_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan.django_content_type_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan.django_content_type_id_seq OWNED BY billetistan.django_content_type.id;


--
-- Name: django_migrations; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan.django_migrations (
    id integer NOT NULL,
    app character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    applied timestamp with time zone NOT NULL
);


ALTER TABLE billetistan.django_migrations OWNER TO ticket_postgres_user;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE SEQUENCE billetistan.django_migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE billetistan.django_migrations_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER SEQUENCE billetistan.django_migrations_id_seq OWNED BY billetistan.django_migrations.id;


--
-- Name: rest_framework_api_key_apikey; Type: TABLE; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE TABLE billetistan.rest_framework_api_key_apikey (
    id character varying(150) NOT NULL,
    created timestamp with time zone NOT NULL,
    name character varying(50) NOT NULL,
    revoked boolean NOT NULL,
    expiry_date timestamp with time zone,
    hashed_key character varying(150) NOT NULL,
    prefix character varying(8) NOT NULL
);


ALTER TABLE billetistan.rest_framework_api_key_apikey OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_externalapikey; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_externalapikey" (
    id integer NOT NULL,
    ip inet NOT NULL,
    revoquer_apikey boolean NOT NULL,
    created timestamp with time zone NOT NULL,
    name character varying(30) NOT NULL,
    event boolean NOT NULL,
    product boolean NOT NULL,
    artist boolean NOT NULL,
    place boolean NOT NULL,
    user_id uuid,
    reservation boolean NOT NULL,
    ticket boolean NOT NULL,
    key_id character varying(150)
);


ALTER TABLE demo."BaseBillet_externalapikey" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_apikey_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_apikey_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_apikey_id_seq" OWNED BY demo."BaseBillet_externalapikey".id;


--
-- Name: BaseBillet_artist_on_event; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_artist_on_event" (
    id integer NOT NULL,
    datetime timestamp with time zone NOT NULL,
    artist_id uuid NOT NULL,
    event_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_artist_on_event" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_artist_on_event_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_artist_on_event_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_artist_on_event_id_seq" OWNED BY demo."BaseBillet_artist_on_event".id;


--
-- Name: BaseBillet_configuration; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_configuration" (
    id integer NOT NULL,
    organisation character varying(50) NOT NULL,
    short_description character varying(250),
    long_description text,
    adress character varying(250),
    postal_code integer,
    city character varying(250),
    phone character varying(20) NOT NULL,
    email character varying(254) NOT NULL,
    site_web character varying(200),
    twitter character varying(200),
    facebook character varying(200),
    instagram character varying(200),
    map_img character varying(100),
    carte_restaurant character varying(100),
    img character varying(100),
    fuseau_horaire character varying(50) NOT NULL,
    logo character varying(100),
    stripe_api_key character varying(110),
    stripe_test_api_key character varying(110),
    stripe_mode_test boolean NOT NULL,
    jauge_max smallint NOT NULL,
    server_cashless character varying(300),
    key_cashless character varying(41),
    template_billetterie character varying(250),
    template_meta character varying(250),
    activate_mailjet boolean NOT NULL,
    email_confirm_template integer NOT NULL,
    slug character varying(50) NOT NULL,
    legal_documents character varying(200),
    stripe_connect_account character varying(21),
    stripe_connect_account_test character varying(21),
    stripe_payouts_enabled boolean NOT NULL,
    federated_cashless boolean NOT NULL,
    ghost_key character varying(200),
    ghost_last_log text,
    ghost_url character varying(200),
    key_fedow character varying(41),
    server_fedow character varying(300),
    CONSTRAINT "BaseBillet_configuration_jauge_max_check" CHECK ((jauge_max >= 0))
);


ALTER TABLE demo."BaseBillet_configuration" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_configuration_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_configuration_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_configuration_id_seq" OWNED BY demo."BaseBillet_configuration".id;


--
-- Name: BaseBillet_configuration_option_generale_checkbox; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_configuration_option_generale_checkbox" (
    id integer NOT NULL,
    configuration_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_configuration_option_generale_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_configuration_option_generale_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_configuration_option_generale_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_configuration_option_generale_checkbox_id_seq" OWNED BY demo."BaseBillet_configuration_option_generale_checkbox".id;


--
-- Name: BaseBillet_configuration_option_generale_radio; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_configuration_option_generale_radio" (
    id integer NOT NULL,
    configuration_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_configuration_option_generale_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_configuration_option_generale_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_configuration_option_generale_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_configuration_option_generale_radio_id_seq" OWNED BY demo."BaseBillet_configuration_option_generale_radio".id;


--
-- Name: BaseBillet_event; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_event" (
    uuid uuid NOT NULL,
    name character varying(200) NOT NULL,
    slug character varying(250),
    datetime timestamp with time zone NOT NULL,
    created timestamp with time zone NOT NULL,
    short_description character varying(250),
    long_description text,
    url_external character varying(200),
    published boolean NOT NULL,
    img character varying(100),
    categorie character varying(3) NOT NULL,
    jauge_max smallint NOT NULL,
    minimum_cashless_required smallint NOT NULL,
    max_per_user smallint NOT NULL,
    is_external boolean NOT NULL,
    booking boolean NOT NULL,
    CONSTRAINT "BaseBillet_event_jauge_max_check" CHECK ((jauge_max >= 0)),
    CONSTRAINT "BaseBillet_event_max_per_user_check" CHECK ((max_per_user >= 0))
);


ALTER TABLE demo."BaseBillet_event" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_event_options_checkbox" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_event_options_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_event_options_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_event_options_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_event_options_checkbox_id_seq" OWNED BY demo."BaseBillet_event_options_checkbox".id;


--
-- Name: BaseBillet_event_options_radio; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_event_options_radio" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_event_options_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_event_options_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_event_options_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_event_options_radio_id_seq" OWNED BY demo."BaseBillet_event_options_radio".id;


--
-- Name: BaseBillet_event_products; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_event_products" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    product_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_event_products" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_event_products_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_event_products_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_event_products_id_seq" OWNED BY demo."BaseBillet_event_products".id;


--
-- Name: BaseBillet_event_recurrent; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_event_recurrent" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    weekday_id integer NOT NULL
);


ALTER TABLE demo."BaseBillet_event_recurrent" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_event_recurrent_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_event_recurrent_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_event_recurrent_id_seq" OWNED BY demo."BaseBillet_event_recurrent".id;


--
-- Name: BaseBillet_event_tag; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_event_tag" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    tag_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_event_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_event_tag_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_event_tag_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_event_tag_id_seq" OWNED BY demo."BaseBillet_event_tag".id;


--
-- Name: BaseBillet_lignearticle; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_lignearticle" (
    uuid uuid NOT NULL,
    datetime timestamp with time zone NOT NULL,
    qty smallint NOT NULL,
    status character varying(3) NOT NULL,
    carte_id integer,
    paiement_stripe_id uuid,
    pricesold_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_lignearticle" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_membership" (
    id integer NOT NULL,
    date_added timestamp with time zone NOT NULL,
    first_contribution date,
    last_contribution date,
    contribution_value double precision,
    last_action timestamp with time zone NOT NULL,
    first_name character varying(200),
    last_name character varying(200),
    pseudo character varying(50),
    newsletter boolean NOT NULL,
    postal_code integer,
    birth_date date,
    phone character varying(20),
    commentaire text,
    user_id uuid NOT NULL,
    price_id uuid,
    stripe_id_subscription character varying(28),
    last_stripe_invoice character varying(278),
    status character varying(1) NOT NULL
);


ALTER TABLE demo."BaseBillet_membership" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_membership_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_membership_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_membership_id_seq" OWNED BY demo."BaseBillet_membership".id;


--
-- Name: BaseBillet_membership_option_generale; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_membership_option_generale" (
    id integer NOT NULL,
    membership_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_membership_option_generale" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_membership_option_generale_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_membership_option_generale_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_membership_option_generale_id_seq" OWNED BY demo."BaseBillet_membership_option_generale".id;


--
-- Name: BaseBillet_optiongenerale; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_optiongenerale" (
    uuid uuid NOT NULL,
    name character varying(30) NOT NULL,
    poids smallint NOT NULL,
    description character varying(250),
    CONSTRAINT "BaseBillet_optiongenerale_poids_check" CHECK ((poids >= 0))
);


ALTER TABLE demo."BaseBillet_optiongenerale" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_paiement_stripe; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_paiement_stripe" (
    uuid uuid NOT NULL,
    detail character varying(50),
    datetime timestamp with time zone NOT NULL,
    checkout_session_id_stripe character varying(80),
    payment_intent_id character varying(80),
    metadata_stripe jsonb,
    order_date timestamp with time zone NOT NULL,
    last_action timestamp with time zone NOT NULL,
    status character varying(1) NOT NULL,
    traitement_en_cours boolean NOT NULL,
    source_traitement character varying(1) NOT NULL,
    source character varying(1) NOT NULL,
    total double precision NOT NULL,
    reservation_id uuid,
    user_id uuid,
    customer_stripe character varying(20),
    invoice_stripe character varying(27),
    subscription character varying(28)
);


ALTER TABLE demo."BaseBillet_paiement_stripe" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_price; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_price" (
    uuid uuid NOT NULL,
    name character varying(50) NOT NULL,
    prix numeric(6,2) NOT NULL,
    vat character varying(2) NOT NULL,
    stock smallint,
    max_per_user smallint NOT NULL,
    product_id uuid NOT NULL,
    adhesion_obligatoire_id uuid,
    long_description text,
    short_description character varying(250),
    subscription_type character varying(1) NOT NULL,
    recurring_payment boolean NOT NULL,
    CONSTRAINT "BaseBillet_price_max_per_user_check" CHECK ((max_per_user >= 0))
);


ALTER TABLE demo."BaseBillet_price" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_pricesold; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_pricesold" (
    uuid uuid NOT NULL,
    id_price_stripe character varying(30),
    qty_solded smallint NOT NULL,
    prix numeric(6,2) NOT NULL,
    price_id uuid NOT NULL,
    productsold_id uuid NOT NULL,
    gift numeric(6,2)
);


ALTER TABLE demo."BaseBillet_pricesold" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_product" (
    uuid uuid NOT NULL,
    name character varying(500) NOT NULL,
    publish boolean NOT NULL,
    img character varying(100),
    categorie_article character varying(3) NOT NULL,
    long_description text,
    short_description character varying(250),
    terms_and_conditions_document character varying(200),
    send_to_cashless boolean NOT NULL,
    poids smallint NOT NULL,
    archive boolean NOT NULL,
    legal_link character varying(200),
    nominative boolean NOT NULL,
    CONSTRAINT "BaseBillet_product_poids_check" CHECK ((poids >= 0))
);


ALTER TABLE demo."BaseBillet_product" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_product_option_generale_checkbox" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_product_option_generale_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_product_option_generale_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_product_option_generale_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_product_option_generale_checkbox_id_seq" OWNED BY demo."BaseBillet_product_option_generale_checkbox".id;


--
-- Name: BaseBillet_product_option_generale_radio; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_product_option_generale_radio" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_product_option_generale_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_product_option_generale_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_product_option_generale_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_product_option_generale_radio_id_seq" OWNED BY demo."BaseBillet_product_option_generale_radio".id;


--
-- Name: BaseBillet_product_tag; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_product_tag" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    tag_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_product_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_product_tag_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_product_tag_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_product_tag_id_seq" OWNED BY demo."BaseBillet_product_tag".id;


--
-- Name: BaseBillet_productsold; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_productsold" (
    uuid uuid NOT NULL,
    id_product_stripe character varying(30),
    event_id uuid,
    product_id uuid NOT NULL,
    categorie_article character varying(3) NOT NULL
);


ALTER TABLE demo."BaseBillet_productsold" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_reservation" (
    uuid uuid NOT NULL,
    datetime timestamp with time zone NOT NULL,
    status character varying(3) NOT NULL,
    to_mail boolean NOT NULL,
    mail_send boolean NOT NULL,
    mail_error boolean NOT NULL,
    event_id uuid NOT NULL,
    user_commande_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_reservation" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_reservation_options" (
    id integer NOT NULL,
    reservation_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_reservation_options" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_reservation_options_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_reservation_options_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_reservation_options_id_seq" OWNED BY demo."BaseBillet_reservation_options".id;


--
-- Name: BaseBillet_tag; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_tag" (
    uuid uuid NOT NULL,
    name character varying(50) NOT NULL,
    color character varying(7) NOT NULL
);


ALTER TABLE demo."BaseBillet_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_ticket; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_ticket" (
    uuid uuid NOT NULL,
    first_name character varying(200) NOT NULL,
    last_name character varying(200) NOT NULL,
    status character varying(1) NOT NULL,
    seat character varying(20) NOT NULL,
    pricesold_id uuid NOT NULL,
    reservation_id uuid NOT NULL
);


ALTER TABLE demo."BaseBillet_ticket" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_webhook" (
    id integer NOT NULL,
    url character varying(200) NOT NULL,
    event character varying(2) NOT NULL,
    active boolean NOT NULL,
    last_response text
);


ALTER TABLE demo."BaseBillet_webhook" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_webhook_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_webhook_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_webhook_id_seq" OWNED BY demo."BaseBillet_webhook".id;


--
-- Name: BaseBillet_weekday; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo."BaseBillet_weekday" (
    id integer NOT NULL,
    day integer NOT NULL
);


ALTER TABLE demo."BaseBillet_weekday" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo."BaseBillet_weekday_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo."BaseBillet_weekday_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo."BaseBillet_weekday_id_seq" OWNED BY demo."BaseBillet_weekday".id;


--
-- Name: django_content_type; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo.django_content_type (
    id integer NOT NULL,
    app_label character varying(100) NOT NULL,
    model character varying(100) NOT NULL
);


ALTER TABLE demo.django_content_type OWNER TO ticket_postgres_user;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo.django_content_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo.django_content_type_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo.django_content_type_id_seq OWNED BY demo.django_content_type.id;


--
-- Name: django_migrations; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo.django_migrations (
    id integer NOT NULL,
    app character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    applied timestamp with time zone NOT NULL
);


ALTER TABLE demo.django_migrations OWNER TO ticket_postgres_user;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE; Schema: demo; Owner: ticket_postgres_user
--

CREATE SEQUENCE demo.django_migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE demo.django_migrations_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: demo; Owner: ticket_postgres_user
--

ALTER SEQUENCE demo.django_migrations_id_seq OWNED BY demo.django_migrations.id;


--
-- Name: rest_framework_api_key_apikey; Type: TABLE; Schema: demo; Owner: ticket_postgres_user
--

CREATE TABLE demo.rest_framework_api_key_apikey (
    id character varying(150) NOT NULL,
    created timestamp with time zone NOT NULL,
    name character varying(50) NOT NULL,
    revoked boolean NOT NULL,
    expiry_date timestamp with time zone,
    hashed_key character varying(150) NOT NULL,
    prefix character varying(8) NOT NULL
);


ALTER TABLE demo.rest_framework_api_key_apikey OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_externalapikey; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_externalapikey" (
    id integer NOT NULL,
    ip inet NOT NULL,
    revoquer_apikey boolean NOT NULL,
    created timestamp with time zone NOT NULL,
    name character varying(30) NOT NULL,
    event boolean NOT NULL,
    product boolean NOT NULL,
    artist boolean NOT NULL,
    place boolean NOT NULL,
    user_id uuid,
    reservation boolean NOT NULL,
    ticket boolean NOT NULL,
    key_id character varying(150)
);


ALTER TABLE meta."BaseBillet_externalapikey" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_apikey_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_apikey_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_apikey_id_seq" OWNED BY meta."BaseBillet_externalapikey".id;


--
-- Name: BaseBillet_artist_on_event; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_artist_on_event" (
    id integer NOT NULL,
    datetime timestamp with time zone NOT NULL,
    artist_id uuid NOT NULL,
    event_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_artist_on_event" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_artist_on_event_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_artist_on_event_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_artist_on_event_id_seq" OWNED BY meta."BaseBillet_artist_on_event".id;


--
-- Name: BaseBillet_configuration; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_configuration" (
    id integer NOT NULL,
    organisation character varying(50) NOT NULL,
    short_description character varying(250),
    long_description text,
    adress character varying(250),
    postal_code integer,
    city character varying(250),
    phone character varying(20) NOT NULL,
    email character varying(254) NOT NULL,
    site_web character varying(200),
    twitter character varying(200),
    facebook character varying(200),
    instagram character varying(200),
    map_img character varying(100),
    carte_restaurant character varying(100),
    img character varying(100),
    fuseau_horaire character varying(50) NOT NULL,
    logo character varying(100),
    stripe_api_key character varying(110),
    stripe_test_api_key character varying(110),
    stripe_mode_test boolean NOT NULL,
    jauge_max smallint NOT NULL,
    server_cashless character varying(300),
    key_cashless character varying(41),
    template_billetterie character varying(250),
    template_meta character varying(250),
    activate_mailjet boolean NOT NULL,
    email_confirm_template integer NOT NULL,
    slug character varying(50) NOT NULL,
    legal_documents character varying(200),
    stripe_connect_account character varying(21),
    stripe_connect_account_test character varying(21),
    stripe_payouts_enabled boolean NOT NULL,
    federated_cashless boolean NOT NULL,
    ghost_key character varying(200),
    ghost_last_log text,
    ghost_url character varying(200),
    key_fedow character varying(41),
    server_fedow character varying(300),
    CONSTRAINT "BaseBillet_configuration_jauge_max_check" CHECK ((jauge_max >= 0))
);


ALTER TABLE meta."BaseBillet_configuration" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_configuration_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_configuration_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_configuration_id_seq" OWNED BY meta."BaseBillet_configuration".id;


--
-- Name: BaseBillet_configuration_option_generale_checkbox; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_configuration_option_generale_checkbox" (
    id integer NOT NULL,
    configuration_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_configuration_option_generale_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_configuration_option_generale_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_configuration_option_generale_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_configuration_option_generale_checkbox_id_seq" OWNED BY meta."BaseBillet_configuration_option_generale_checkbox".id;


--
-- Name: BaseBillet_configuration_option_generale_radio; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_configuration_option_generale_radio" (
    id integer NOT NULL,
    configuration_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_configuration_option_generale_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_configuration_option_generale_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_configuration_option_generale_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_configuration_option_generale_radio_id_seq" OWNED BY meta."BaseBillet_configuration_option_generale_radio".id;


--
-- Name: BaseBillet_event; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_event" (
    uuid uuid NOT NULL,
    name character varying(200) NOT NULL,
    slug character varying(250),
    datetime timestamp with time zone NOT NULL,
    created timestamp with time zone NOT NULL,
    short_description character varying(250),
    long_description text,
    url_external character varying(200),
    published boolean NOT NULL,
    img character varying(100),
    categorie character varying(3) NOT NULL,
    jauge_max smallint NOT NULL,
    minimum_cashless_required smallint NOT NULL,
    max_per_user smallint NOT NULL,
    is_external boolean NOT NULL,
    booking boolean NOT NULL,
    CONSTRAINT "BaseBillet_event_jauge_max_check" CHECK ((jauge_max >= 0)),
    CONSTRAINT "BaseBillet_event_max_per_user_check" CHECK ((max_per_user >= 0))
);


ALTER TABLE meta."BaseBillet_event" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_event_options_checkbox" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_event_options_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_event_options_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_event_options_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_event_options_checkbox_id_seq" OWNED BY meta."BaseBillet_event_options_checkbox".id;


--
-- Name: BaseBillet_event_options_radio; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_event_options_radio" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_event_options_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_event_options_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_event_options_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_event_options_radio_id_seq" OWNED BY meta."BaseBillet_event_options_radio".id;


--
-- Name: BaseBillet_event_products; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_event_products" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    product_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_event_products" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_event_products_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_event_products_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_event_products_id_seq" OWNED BY meta."BaseBillet_event_products".id;


--
-- Name: BaseBillet_event_recurrent; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_event_recurrent" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    weekday_id integer NOT NULL
);


ALTER TABLE meta."BaseBillet_event_recurrent" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_event_recurrent_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_event_recurrent_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_event_recurrent_id_seq" OWNED BY meta."BaseBillet_event_recurrent".id;


--
-- Name: BaseBillet_event_tag; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_event_tag" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    tag_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_event_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_event_tag_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_event_tag_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_event_tag_id_seq" OWNED BY meta."BaseBillet_event_tag".id;


--
-- Name: BaseBillet_lignearticle; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_lignearticle" (
    uuid uuid NOT NULL,
    datetime timestamp with time zone NOT NULL,
    qty smallint NOT NULL,
    status character varying(3) NOT NULL,
    carte_id integer,
    paiement_stripe_id uuid,
    pricesold_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_lignearticle" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_membership" (
    id integer NOT NULL,
    date_added timestamp with time zone NOT NULL,
    first_contribution date,
    last_contribution date,
    contribution_value double precision,
    last_action timestamp with time zone NOT NULL,
    first_name character varying(200),
    last_name character varying(200),
    pseudo character varying(50),
    newsletter boolean NOT NULL,
    postal_code integer,
    birth_date date,
    phone character varying(20),
    commentaire text,
    user_id uuid NOT NULL,
    price_id uuid,
    stripe_id_subscription character varying(28),
    last_stripe_invoice character varying(278),
    status character varying(1) NOT NULL
);


ALTER TABLE meta."BaseBillet_membership" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_membership_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_membership_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_membership_id_seq" OWNED BY meta."BaseBillet_membership".id;


--
-- Name: BaseBillet_membership_option_generale; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_membership_option_generale" (
    id integer NOT NULL,
    membership_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_membership_option_generale" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_membership_option_generale_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_membership_option_generale_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_membership_option_generale_id_seq" OWNED BY meta."BaseBillet_membership_option_generale".id;


--
-- Name: BaseBillet_optiongenerale; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_optiongenerale" (
    uuid uuid NOT NULL,
    name character varying(30) NOT NULL,
    poids smallint NOT NULL,
    description character varying(250),
    CONSTRAINT "BaseBillet_optiongenerale_poids_check" CHECK ((poids >= 0))
);


ALTER TABLE meta."BaseBillet_optiongenerale" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_paiement_stripe; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_paiement_stripe" (
    uuid uuid NOT NULL,
    detail character varying(50),
    datetime timestamp with time zone NOT NULL,
    checkout_session_id_stripe character varying(80),
    payment_intent_id character varying(80),
    metadata_stripe jsonb,
    order_date timestamp with time zone NOT NULL,
    last_action timestamp with time zone NOT NULL,
    status character varying(1) NOT NULL,
    traitement_en_cours boolean NOT NULL,
    source_traitement character varying(1) NOT NULL,
    source character varying(1) NOT NULL,
    total double precision NOT NULL,
    reservation_id uuid,
    user_id uuid,
    customer_stripe character varying(20),
    invoice_stripe character varying(27),
    subscription character varying(28)
);


ALTER TABLE meta."BaseBillet_paiement_stripe" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_price; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_price" (
    uuid uuid NOT NULL,
    name character varying(50) NOT NULL,
    prix numeric(6,2) NOT NULL,
    vat character varying(2) NOT NULL,
    stock smallint,
    max_per_user smallint NOT NULL,
    product_id uuid NOT NULL,
    adhesion_obligatoire_id uuid,
    long_description text,
    short_description character varying(250),
    subscription_type character varying(1) NOT NULL,
    recurring_payment boolean NOT NULL,
    CONSTRAINT "BaseBillet_price_max_per_user_check" CHECK ((max_per_user >= 0))
);


ALTER TABLE meta."BaseBillet_price" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_pricesold; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_pricesold" (
    uuid uuid NOT NULL,
    id_price_stripe character varying(30),
    qty_solded smallint NOT NULL,
    prix numeric(6,2) NOT NULL,
    price_id uuid NOT NULL,
    productsold_id uuid NOT NULL,
    gift numeric(6,2)
);


ALTER TABLE meta."BaseBillet_pricesold" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_product" (
    uuid uuid NOT NULL,
    name character varying(500) NOT NULL,
    publish boolean NOT NULL,
    img character varying(100),
    categorie_article character varying(3) NOT NULL,
    long_description text,
    short_description character varying(250),
    terms_and_conditions_document character varying(200),
    send_to_cashless boolean NOT NULL,
    poids smallint NOT NULL,
    archive boolean NOT NULL,
    legal_link character varying(200),
    nominative boolean NOT NULL,
    CONSTRAINT "BaseBillet_product_poids_check" CHECK ((poids >= 0))
);


ALTER TABLE meta."BaseBillet_product" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_product_option_generale_checkbox" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_product_option_generale_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_product_option_generale_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_product_option_generale_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_product_option_generale_checkbox_id_seq" OWNED BY meta."BaseBillet_product_option_generale_checkbox".id;


--
-- Name: BaseBillet_product_option_generale_radio; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_product_option_generale_radio" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_product_option_generale_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_product_option_generale_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_product_option_generale_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_product_option_generale_radio_id_seq" OWNED BY meta."BaseBillet_product_option_generale_radio".id;


--
-- Name: BaseBillet_product_tag; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_product_tag" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    tag_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_product_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_product_tag_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_product_tag_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_product_tag_id_seq" OWNED BY meta."BaseBillet_product_tag".id;


--
-- Name: BaseBillet_productsold; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_productsold" (
    uuid uuid NOT NULL,
    id_product_stripe character varying(30),
    event_id uuid,
    product_id uuid NOT NULL,
    categorie_article character varying(3) NOT NULL
);


ALTER TABLE meta."BaseBillet_productsold" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_reservation" (
    uuid uuid NOT NULL,
    datetime timestamp with time zone NOT NULL,
    status character varying(3) NOT NULL,
    to_mail boolean NOT NULL,
    mail_send boolean NOT NULL,
    mail_error boolean NOT NULL,
    event_id uuid NOT NULL,
    user_commande_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_reservation" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_reservation_options" (
    id integer NOT NULL,
    reservation_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_reservation_options" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_reservation_options_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_reservation_options_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_reservation_options_id_seq" OWNED BY meta."BaseBillet_reservation_options".id;


--
-- Name: BaseBillet_tag; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_tag" (
    uuid uuid NOT NULL,
    name character varying(50) NOT NULL,
    color character varying(7) NOT NULL
);


ALTER TABLE meta."BaseBillet_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_ticket; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_ticket" (
    uuid uuid NOT NULL,
    first_name character varying(200) NOT NULL,
    last_name character varying(200) NOT NULL,
    status character varying(1) NOT NULL,
    seat character varying(20) NOT NULL,
    pricesold_id uuid NOT NULL,
    reservation_id uuid NOT NULL
);


ALTER TABLE meta."BaseBillet_ticket" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_webhook" (
    id integer NOT NULL,
    url character varying(200) NOT NULL,
    event character varying(2) NOT NULL,
    active boolean NOT NULL,
    last_response text
);


ALTER TABLE meta."BaseBillet_webhook" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_webhook_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_webhook_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_webhook_id_seq" OWNED BY meta."BaseBillet_webhook".id;


--
-- Name: BaseBillet_weekday; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta."BaseBillet_weekday" (
    id integer NOT NULL,
    day integer NOT NULL
);


ALTER TABLE meta."BaseBillet_weekday" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta."BaseBillet_weekday_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta."BaseBillet_weekday_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta."BaseBillet_weekday_id_seq" OWNED BY meta."BaseBillet_weekday".id;


--
-- Name: django_content_type; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta.django_content_type (
    id integer NOT NULL,
    app_label character varying(100) NOT NULL,
    model character varying(100) NOT NULL
);


ALTER TABLE meta.django_content_type OWNER TO ticket_postgres_user;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta.django_content_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta.django_content_type_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta.django_content_type_id_seq OWNED BY meta.django_content_type.id;


--
-- Name: django_migrations; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta.django_migrations (
    id integer NOT NULL,
    app character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    applied timestamp with time zone NOT NULL
);


ALTER TABLE meta.django_migrations OWNER TO ticket_postgres_user;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE; Schema: meta; Owner: ticket_postgres_user
--

CREATE SEQUENCE meta.django_migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE meta.django_migrations_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: meta; Owner: ticket_postgres_user
--

ALTER SEQUENCE meta.django_migrations_id_seq OWNED BY meta.django_migrations.id;


--
-- Name: rest_framework_api_key_apikey; Type: TABLE; Schema: meta; Owner: ticket_postgres_user
--

CREATE TABLE meta.rest_framework_api_key_apikey (
    id character varying(150) NOT NULL,
    created timestamp with time zone NOT NULL,
    name character varying(50) NOT NULL,
    revoked boolean NOT NULL,
    expiry_date timestamp with time zone,
    hashed_key character varying(150) NOT NULL,
    prefix character varying(8) NOT NULL
);


ALTER TABLE meta.rest_framework_api_key_apikey OWNER TO ticket_postgres_user;

--
-- Name: AuthBillet_terminalpairingtoken; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."AuthBillet_terminalpairingtoken" (
    id integer NOT NULL,
    datetime timestamp with time zone NOT NULL,
    token integer NOT NULL,
    user_id uuid NOT NULL,
    used boolean NOT NULL,
    CONSTRAINT "AuthBillet_terminalpairingtoken_token_e5ae3cf7_check" CHECK ((token >= 0))
);


ALTER TABLE public."AuthBillet_terminalpairingtoken" OWNER TO ticket_postgres_user;

--
-- Name: AuthBillet_terminalpairingtoken_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public."AuthBillet_terminalpairingtoken_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public."AuthBillet_terminalpairingtoken_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: AuthBillet_terminalpairingtoken_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public."AuthBillet_terminalpairingtoken_id_seq" OWNED BY public."AuthBillet_terminalpairingtoken".id;


--
-- Name: AuthBillet_tibilletuser; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."AuthBillet_tibilletuser" (
    password character varying(128) NOT NULL,
    last_login timestamp with time zone,
    is_superuser boolean NOT NULL,
    is_staff boolean NOT NULL,
    is_active boolean NOT NULL,
    date_joined timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    email character varying(254) NOT NULL,
    email_error boolean NOT NULL,
    username character varying(200) NOT NULL,
    first_name character varying(200),
    last_name character varying(200),
    phone character varying(20),
    last_see timestamp with time zone NOT NULL,
    accept_newsletter boolean NOT NULL,
    postal_code integer,
    birth_date date,
    can_create_tenant boolean NOT NULL,
    espece character varying(2) NOT NULL,
    offre character varying(2) NOT NULL,
    client_source_id uuid,
    user_parent_pk uuid,
    local_ip_sended inet,
    mac_adress_sended character varying(17),
    terminal_uuid character varying(200)
);


ALTER TABLE public."AuthBillet_tibilletuser" OWNER TO ticket_postgres_user;

--
-- Name: AuthBillet_tibilletuser_client_achat; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."AuthBillet_tibilletuser_client_achat" (
    id integer NOT NULL,
    tibilletuser_id uuid NOT NULL,
    client_id uuid NOT NULL
);


ALTER TABLE public."AuthBillet_tibilletuser_client_achat" OWNER TO ticket_postgres_user;

--
-- Name: AuthBillet_tibilletuser_client_achat_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public."AuthBillet_tibilletuser_client_achat_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public."AuthBillet_tibilletuser_client_achat_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: AuthBillet_tibilletuser_client_achat_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public."AuthBillet_tibilletuser_client_achat_id_seq" OWNED BY public."AuthBillet_tibilletuser_client_achat".id;


--
-- Name: AuthBillet_tibilletuser_client_admin; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."AuthBillet_tibilletuser_client_admin" (
    id integer NOT NULL,
    tibilletuser_id uuid NOT NULL,
    client_id uuid NOT NULL
);


ALTER TABLE public."AuthBillet_tibilletuser_client_admin" OWNER TO ticket_postgres_user;

--
-- Name: AuthBillet_tibilletuser_client_admin_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public."AuthBillet_tibilletuser_client_admin_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public."AuthBillet_tibilletuser_client_admin_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: AuthBillet_tibilletuser_client_admin_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public."AuthBillet_tibilletuser_client_admin_id_seq" OWNED BY public."AuthBillet_tibilletuser_client_admin".id;


--
-- Name: AuthBillet_tibilletuser_groups; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."AuthBillet_tibilletuser_groups" (
    id integer NOT NULL,
    tibilletuser_id uuid NOT NULL,
    group_id integer NOT NULL
);


ALTER TABLE public."AuthBillet_tibilletuser_groups" OWNER TO ticket_postgres_user;

--
-- Name: AuthBillet_tibilletuser_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public."AuthBillet_tibilletuser_groups_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public."AuthBillet_tibilletuser_groups_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: AuthBillet_tibilletuser_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public."AuthBillet_tibilletuser_groups_id_seq" OWNED BY public."AuthBillet_tibilletuser_groups".id;


--
-- Name: AuthBillet_tibilletuser_user_permissions; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."AuthBillet_tibilletuser_user_permissions" (
    id integer NOT NULL,
    tibilletuser_id uuid NOT NULL,
    permission_id integer NOT NULL
);


ALTER TABLE public."AuthBillet_tibilletuser_user_permissions" OWNER TO ticket_postgres_user;

--
-- Name: AuthBillet_tibilletuser_user_permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public."AuthBillet_tibilletuser_user_permissions_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public."AuthBillet_tibilletuser_user_permissions_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: AuthBillet_tibilletuser_user_permissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public."AuthBillet_tibilletuser_user_permissions_id_seq" OWNED BY public."AuthBillet_tibilletuser_user_permissions".id;


--
-- Name: Customers_client; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."Customers_client" (
    schema_name character varying(63) NOT NULL,
    uuid uuid NOT NULL,
    name character varying(100) NOT NULL,
    paid_until date NOT NULL,
    on_trial boolean NOT NULL,
    created_on date NOT NULL,
    categorie character varying(3) NOT NULL
);


ALTER TABLE public."Customers_client" OWNER TO ticket_postgres_user;

--
-- Name: Customers_domain; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."Customers_domain" (
    id integer NOT NULL,
    domain character varying(253) NOT NULL,
    is_primary boolean NOT NULL,
    tenant_id uuid NOT NULL
);


ALTER TABLE public."Customers_domain" OWNER TO ticket_postgres_user;

--
-- Name: Customers_domain_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public."Customers_domain_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public."Customers_domain_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: Customers_domain_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public."Customers_domain_id_seq" OWNED BY public."Customers_domain".id;


--
-- Name: MetaBillet_eventdirectory; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."MetaBillet_eventdirectory" (
    id integer NOT NULL,
    datetime timestamp with time zone NOT NULL,
    event_uuid uuid NOT NULL,
    artist_id uuid NOT NULL,
    place_id uuid NOT NULL
);


ALTER TABLE public."MetaBillet_eventdirectory" OWNER TO ticket_postgres_user;

--
-- Name: MetaBillet_eventdirectory_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public."MetaBillet_eventdirectory_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public."MetaBillet_eventdirectory_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: MetaBillet_eventdirectory_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public."MetaBillet_eventdirectory_id_seq" OWNED BY public."MetaBillet_eventdirectory".id;


--
-- Name: MetaBillet_productdirectory; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."MetaBillet_productdirectory" (
    id integer NOT NULL,
    product_sold_stripe_id character varying(30),
    place_id uuid NOT NULL
);


ALTER TABLE public."MetaBillet_productdirectory" OWNER TO ticket_postgres_user;

--
-- Name: MetaBillet_productdirectory_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public."MetaBillet_productdirectory_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public."MetaBillet_productdirectory_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: MetaBillet_productdirectory_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public."MetaBillet_productdirectory_id_seq" OWNED BY public."MetaBillet_productdirectory".id;


--
-- Name: QrcodeCashless_asset; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."QrcodeCashless_asset" (
    id uuid NOT NULL,
    name character varying(50) NOT NULL,
    is_federated boolean NOT NULL,
    origin_id uuid NOT NULL,
    categorie character varying(2) NOT NULL
);


ALTER TABLE public."QrcodeCashless_asset" OWNER TO ticket_postgres_user;

--
-- Name: QrcodeCashless_cartecashless; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."QrcodeCashless_cartecashless" (
    id integer NOT NULL,
    tag_id character varying(8) NOT NULL,
    uuid uuid,
    number character varying(8) NOT NULL,
    detail_id integer,
    user_id uuid
);


ALTER TABLE public."QrcodeCashless_cartecashless" OWNER TO ticket_postgres_user;

--
-- Name: QrcodeCashless_cartecashless_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public."QrcodeCashless_cartecashless_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public."QrcodeCashless_cartecashless_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: QrcodeCashless_cartecashless_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public."QrcodeCashless_cartecashless_id_seq" OWNED BY public."QrcodeCashless_cartecashless".id;


--
-- Name: QrcodeCashless_detail; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."QrcodeCashless_detail" (
    id integer NOT NULL,
    img character varying(100),
    img_url character varying(200),
    base_url character varying(60),
    generation smallint NOT NULL,
    origine_id uuid,
    uuid uuid NOT NULL,
    slug character varying(50)
);


ALTER TABLE public."QrcodeCashless_detail" OWNER TO ticket_postgres_user;

--
-- Name: QrcodeCashless_detail_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public."QrcodeCashless_detail_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public."QrcodeCashless_detail_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: QrcodeCashless_detail_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public."QrcodeCashless_detail_id_seq" OWNED BY public."QrcodeCashless_detail".id;


--
-- Name: QrcodeCashless_federatedcashless; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."QrcodeCashless_federatedcashless" (
    id uuid NOT NULL,
    server_cashless character varying(200),
    key_cashless character varying(50),
    asset_id uuid NOT NULL,
    client_id uuid NOT NULL
);


ALTER TABLE public."QrcodeCashless_federatedcashless" OWNER TO ticket_postgres_user;

--
-- Name: QrcodeCashless_syncfederatedlog; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."QrcodeCashless_syncfederatedlog" (
    id integer NOT NULL,
    uuid uuid NOT NULL,
    date timestamp with time zone NOT NULL,
    etat_client_sync jsonb,
    card_id integer,
    client_source_id uuid,
    new_qty numeric(10,2) NOT NULL,
    old_qty numeric(10,2) NOT NULL,
    categorie character varying(3) NOT NULL,
    wallet_id uuid
);


ALTER TABLE public."QrcodeCashless_syncfederatedlog" OWNER TO ticket_postgres_user;

--
-- Name: QrcodeCashless_syncfederatedlog_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public."QrcodeCashless_syncfederatedlog_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public."QrcodeCashless_syncfederatedlog_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: QrcodeCashless_syncfederatedlog_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public."QrcodeCashless_syncfederatedlog_id_seq" OWNED BY public."QrcodeCashless_syncfederatedlog".id;


--
-- Name: QrcodeCashless_wallet; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public."QrcodeCashless_wallet" (
    id uuid NOT NULL,
    qty numeric(10,2) NOT NULL,
    last_date_used timestamp with time zone NOT NULL,
    sync jsonb,
    asset_id uuid NOT NULL,
    user_id uuid,
    card_id integer
);


ALTER TABLE public."QrcodeCashless_wallet" OWNER TO ticket_postgres_user;

--
-- Name: auth_group; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public.auth_group (
    id integer NOT NULL,
    name character varying(150) NOT NULL
);


ALTER TABLE public.auth_group OWNER TO ticket_postgres_user;

--
-- Name: auth_group_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public.auth_group_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.auth_group_id_seq OWNER TO ticket_postgres_user;

--
-- Name: auth_group_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public.auth_group_id_seq OWNED BY public.auth_group.id;


--
-- Name: auth_group_permissions; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public.auth_group_permissions (
    id integer NOT NULL,
    group_id integer NOT NULL,
    permission_id integer NOT NULL
);


ALTER TABLE public.auth_group_permissions OWNER TO ticket_postgres_user;

--
-- Name: auth_group_permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public.auth_group_permissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.auth_group_permissions_id_seq OWNER TO ticket_postgres_user;

--
-- Name: auth_group_permissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public.auth_group_permissions_id_seq OWNED BY public.auth_group_permissions.id;


--
-- Name: auth_permission; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public.auth_permission (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    content_type_id integer NOT NULL,
    codename character varying(100) NOT NULL
);


ALTER TABLE public.auth_permission OWNER TO ticket_postgres_user;

--
-- Name: auth_permission_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public.auth_permission_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.auth_permission_id_seq OWNER TO ticket_postgres_user;

--
-- Name: auth_permission_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public.auth_permission_id_seq OWNED BY public.auth_permission.id;


--
-- Name: authtoken_token; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public.authtoken_token (
    key character varying(40) NOT NULL,
    created timestamp with time zone NOT NULL,
    user_id uuid NOT NULL
);


ALTER TABLE public.authtoken_token OWNER TO ticket_postgres_user;

--
-- Name: django_admin_log; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public.django_admin_log (
    id integer NOT NULL,
    action_time timestamp with time zone NOT NULL,
    object_id text,
    object_repr character varying(200) NOT NULL,
    action_flag smallint NOT NULL,
    change_message text NOT NULL,
    content_type_id integer,
    user_id uuid NOT NULL,
    CONSTRAINT django_admin_log_action_flag_check CHECK ((action_flag >= 0))
);


ALTER TABLE public.django_admin_log OWNER TO ticket_postgres_user;

--
-- Name: django_admin_log_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public.django_admin_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.django_admin_log_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_admin_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public.django_admin_log_id_seq OWNED BY public.django_admin_log.id;


--
-- Name: django_content_type; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public.django_content_type (
    id integer NOT NULL,
    app_label character varying(100) NOT NULL,
    model character varying(100) NOT NULL
);


ALTER TABLE public.django_content_type OWNER TO ticket_postgres_user;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public.django_content_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.django_content_type_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public.django_content_type_id_seq OWNED BY public.django_content_type.id;


--
-- Name: django_migrations; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public.django_migrations (
    id integer NOT NULL,
    app character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    applied timestamp with time zone NOT NULL
);


ALTER TABLE public.django_migrations OWNER TO ticket_postgres_user;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public.django_migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.django_migrations_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public.django_migrations_id_seq OWNED BY public.django_migrations.id;


--
-- Name: django_session; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public.django_session (
    session_key character varying(40) NOT NULL,
    session_data text NOT NULL,
    expire_date timestamp with time zone NOT NULL
);


ALTER TABLE public.django_session OWNER TO ticket_postgres_user;

--
-- Name: django_site; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public.django_site (
    id integer NOT NULL,
    domain character varying(100) NOT NULL,
    name character varying(50) NOT NULL
);


ALTER TABLE public.django_site OWNER TO ticket_postgres_user;

--
-- Name: django_site_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public.django_site_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.django_site_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_site_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public.django_site_id_seq OWNED BY public.django_site.id;


--
-- Name: root_billet_rootconfiguration; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public.root_billet_rootconfiguration (
    id bigint NOT NULL,
    fuseau_horaire character varying(50) NOT NULL,
    stripe_api_key character varying(110),
    stripe_test_api_key character varying(110),
    stripe_mode_test boolean NOT NULL
);


ALTER TABLE public.root_billet_rootconfiguration OWNER TO ticket_postgres_user;

--
-- Name: root_billet_rootconfiguration_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public.root_billet_rootconfiguration_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.root_billet_rootconfiguration_id_seq OWNER TO ticket_postgres_user;

--
-- Name: root_billet_rootconfiguration_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public.root_billet_rootconfiguration_id_seq OWNED BY public.root_billet_rootconfiguration.id;


--
-- Name: token_blacklist_blacklistedtoken; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public.token_blacklist_blacklistedtoken (
    id bigint NOT NULL,
    blacklisted_at timestamp with time zone NOT NULL,
    token_id bigint NOT NULL
);


ALTER TABLE public.token_blacklist_blacklistedtoken OWNER TO ticket_postgres_user;

--
-- Name: token_blacklist_blacklistedtoken_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public.token_blacklist_blacklistedtoken_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.token_blacklist_blacklistedtoken_id_seq OWNER TO ticket_postgres_user;

--
-- Name: token_blacklist_blacklistedtoken_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public.token_blacklist_blacklistedtoken_id_seq OWNED BY public.token_blacklist_blacklistedtoken.id;


--
-- Name: token_blacklist_outstandingtoken; Type: TABLE; Schema: public; Owner: ticket_postgres_user
--

CREATE TABLE public.token_blacklist_outstandingtoken (
    id bigint NOT NULL,
    token text NOT NULL,
    created_at timestamp with time zone,
    expires_at timestamp with time zone NOT NULL,
    user_id uuid,
    jti character varying(255) NOT NULL
);


ALTER TABLE public.token_blacklist_outstandingtoken OWNER TO ticket_postgres_user;

--
-- Name: token_blacklist_outstandingtoken_id_seq; Type: SEQUENCE; Schema: public; Owner: ticket_postgres_user
--

CREATE SEQUENCE public.token_blacklist_outstandingtoken_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.token_blacklist_outstandingtoken_id_seq OWNER TO ticket_postgres_user;

--
-- Name: token_blacklist_outstandingtoken_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: ticket_postgres_user
--

ALTER SEQUENCE public.token_blacklist_outstandingtoken_id_seq OWNED BY public.token_blacklist_outstandingtoken.id;


--
-- Name: BaseBillet_externalapikey; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_externalapikey" (
    id integer NOT NULL,
    ip inet NOT NULL,
    revoquer_apikey boolean NOT NULL,
    created timestamp with time zone NOT NULL,
    name character varying(30) NOT NULL,
    event boolean NOT NULL,
    product boolean NOT NULL,
    artist boolean NOT NULL,
    place boolean NOT NULL,
    user_id uuid,
    reservation boolean NOT NULL,
    ticket boolean NOT NULL,
    key_id character varying(150)
);


ALTER TABLE ziskakan."BaseBillet_externalapikey" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_apikey_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_apikey_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_apikey_id_seq" OWNED BY ziskakan."BaseBillet_externalapikey".id;


--
-- Name: BaseBillet_artist_on_event; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_artist_on_event" (
    id integer NOT NULL,
    datetime timestamp with time zone NOT NULL,
    artist_id uuid NOT NULL,
    event_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_artist_on_event" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_artist_on_event_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_artist_on_event_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_artist_on_event_id_seq" OWNED BY ziskakan."BaseBillet_artist_on_event".id;


--
-- Name: BaseBillet_configuration; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_configuration" (
    id integer NOT NULL,
    organisation character varying(50) NOT NULL,
    short_description character varying(250),
    long_description text,
    adress character varying(250),
    postal_code integer,
    city character varying(250),
    phone character varying(20) NOT NULL,
    email character varying(254) NOT NULL,
    site_web character varying(200),
    twitter character varying(200),
    facebook character varying(200),
    instagram character varying(200),
    map_img character varying(100),
    carte_restaurant character varying(100),
    img character varying(100),
    fuseau_horaire character varying(50) NOT NULL,
    logo character varying(100),
    stripe_api_key character varying(110),
    stripe_test_api_key character varying(110),
    stripe_mode_test boolean NOT NULL,
    jauge_max smallint NOT NULL,
    server_cashless character varying(300),
    key_cashless character varying(41),
    template_billetterie character varying(250),
    template_meta character varying(250),
    activate_mailjet boolean NOT NULL,
    email_confirm_template integer NOT NULL,
    slug character varying(50) NOT NULL,
    legal_documents character varying(200),
    stripe_connect_account character varying(21),
    stripe_connect_account_test character varying(21),
    stripe_payouts_enabled boolean NOT NULL,
    federated_cashless boolean NOT NULL,
    ghost_key character varying(200),
    ghost_last_log text,
    ghost_url character varying(200),
    key_fedow character varying(41),
    server_fedow character varying(300),
    CONSTRAINT "BaseBillet_configuration_jauge_max_check" CHECK ((jauge_max >= 0))
);


ALTER TABLE ziskakan."BaseBillet_configuration" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_configuration_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_configuration_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_configuration_id_seq" OWNED BY ziskakan."BaseBillet_configuration".id;


--
-- Name: BaseBillet_configuration_option_generale_checkbox; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_configuration_option_generale_checkbox" (
    id integer NOT NULL,
    configuration_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_configuration_option_generale_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_configuration_option_generale_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_configuration_option_generale_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_configuration_option_generale_checkbox_id_seq" OWNED BY ziskakan."BaseBillet_configuration_option_generale_checkbox".id;


--
-- Name: BaseBillet_configuration_option_generale_radio; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_configuration_option_generale_radio" (
    id integer NOT NULL,
    configuration_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_configuration_option_generale_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_configuration_option_generale_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_configuration_option_generale_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_configuration_option_generale_radio_id_seq" OWNED BY ziskakan."BaseBillet_configuration_option_generale_radio".id;


--
-- Name: BaseBillet_event; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_event" (
    uuid uuid NOT NULL,
    name character varying(200) NOT NULL,
    slug character varying(250),
    datetime timestamp with time zone NOT NULL,
    created timestamp with time zone NOT NULL,
    short_description character varying(250),
    long_description text,
    url_external character varying(200),
    published boolean NOT NULL,
    img character varying(100),
    categorie character varying(3) NOT NULL,
    jauge_max smallint NOT NULL,
    minimum_cashless_required smallint NOT NULL,
    max_per_user smallint NOT NULL,
    is_external boolean NOT NULL,
    booking boolean NOT NULL,
    CONSTRAINT "BaseBillet_event_jauge_max_check" CHECK ((jauge_max >= 0)),
    CONSTRAINT "BaseBillet_event_max_per_user_check" CHECK ((max_per_user >= 0))
);


ALTER TABLE ziskakan."BaseBillet_event" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_event_options_checkbox" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_event_options_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_event_options_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_event_options_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_event_options_checkbox_id_seq" OWNED BY ziskakan."BaseBillet_event_options_checkbox".id;


--
-- Name: BaseBillet_event_options_radio; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_event_options_radio" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_event_options_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_event_options_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_event_options_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_event_options_radio_id_seq" OWNED BY ziskakan."BaseBillet_event_options_radio".id;


--
-- Name: BaseBillet_event_products; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_event_products" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    product_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_event_products" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_event_products_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_event_products_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_event_products_id_seq" OWNED BY ziskakan."BaseBillet_event_products".id;


--
-- Name: BaseBillet_event_recurrent; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_event_recurrent" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    weekday_id integer NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_event_recurrent" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_event_recurrent_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_event_recurrent_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_event_recurrent_id_seq" OWNED BY ziskakan."BaseBillet_event_recurrent".id;


--
-- Name: BaseBillet_event_tag; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_event_tag" (
    id integer NOT NULL,
    event_id uuid NOT NULL,
    tag_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_event_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_event_tag_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_event_tag_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_event_tag_id_seq" OWNED BY ziskakan."BaseBillet_event_tag".id;


--
-- Name: BaseBillet_lignearticle; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_lignearticle" (
    uuid uuid NOT NULL,
    datetime timestamp with time zone NOT NULL,
    qty smallint NOT NULL,
    status character varying(3) NOT NULL,
    carte_id integer,
    paiement_stripe_id uuid,
    pricesold_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_lignearticle" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_membership" (
    id integer NOT NULL,
    date_added timestamp with time zone NOT NULL,
    first_contribution date,
    last_contribution date,
    contribution_value double precision,
    last_action timestamp with time zone NOT NULL,
    first_name character varying(200),
    last_name character varying(200),
    pseudo character varying(50),
    newsletter boolean NOT NULL,
    postal_code integer,
    birth_date date,
    phone character varying(20),
    commentaire text,
    user_id uuid NOT NULL,
    price_id uuid,
    stripe_id_subscription character varying(28),
    last_stripe_invoice character varying(278),
    status character varying(1) NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_membership" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_membership_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_membership_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_membership_id_seq" OWNED BY ziskakan."BaseBillet_membership".id;


--
-- Name: BaseBillet_membership_option_generale; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_membership_option_generale" (
    id integer NOT NULL,
    membership_id integer NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_membership_option_generale" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_membership_option_generale_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_membership_option_generale_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_membership_option_generale_id_seq" OWNED BY ziskakan."BaseBillet_membership_option_generale".id;


--
-- Name: BaseBillet_optiongenerale; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_optiongenerale" (
    uuid uuid NOT NULL,
    name character varying(30) NOT NULL,
    poids smallint NOT NULL,
    description character varying(250),
    CONSTRAINT "BaseBillet_optiongenerale_poids_check" CHECK ((poids >= 0))
);


ALTER TABLE ziskakan."BaseBillet_optiongenerale" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_paiement_stripe; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_paiement_stripe" (
    uuid uuid NOT NULL,
    detail character varying(50),
    datetime timestamp with time zone NOT NULL,
    checkout_session_id_stripe character varying(80),
    payment_intent_id character varying(80),
    metadata_stripe jsonb,
    order_date timestamp with time zone NOT NULL,
    last_action timestamp with time zone NOT NULL,
    status character varying(1) NOT NULL,
    traitement_en_cours boolean NOT NULL,
    source_traitement character varying(1) NOT NULL,
    source character varying(1) NOT NULL,
    total double precision NOT NULL,
    reservation_id uuid,
    user_id uuid,
    customer_stripe character varying(20),
    invoice_stripe character varying(27),
    subscription character varying(28)
);


ALTER TABLE ziskakan."BaseBillet_paiement_stripe" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_price; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_price" (
    uuid uuid NOT NULL,
    name character varying(50) NOT NULL,
    prix numeric(6,2) NOT NULL,
    vat character varying(2) NOT NULL,
    stock smallint,
    max_per_user smallint NOT NULL,
    product_id uuid NOT NULL,
    adhesion_obligatoire_id uuid,
    long_description text,
    short_description character varying(250),
    subscription_type character varying(1) NOT NULL,
    recurring_payment boolean NOT NULL,
    CONSTRAINT "BaseBillet_price_max_per_user_check" CHECK ((max_per_user >= 0))
);


ALTER TABLE ziskakan."BaseBillet_price" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_pricesold; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_pricesold" (
    uuid uuid NOT NULL,
    id_price_stripe character varying(30),
    qty_solded smallint NOT NULL,
    prix numeric(6,2) NOT NULL,
    price_id uuid NOT NULL,
    productsold_id uuid NOT NULL,
    gift numeric(6,2)
);


ALTER TABLE ziskakan."BaseBillet_pricesold" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_product" (
    uuid uuid NOT NULL,
    name character varying(500) NOT NULL,
    publish boolean NOT NULL,
    img character varying(100),
    categorie_article character varying(3) NOT NULL,
    long_description text,
    short_description character varying(250),
    terms_and_conditions_document character varying(200),
    send_to_cashless boolean NOT NULL,
    poids smallint NOT NULL,
    archive boolean NOT NULL,
    legal_link character varying(200),
    nominative boolean NOT NULL,
    CONSTRAINT "BaseBillet_product_poids_check" CHECK ((poids >= 0))
);


ALTER TABLE ziskakan."BaseBillet_product" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_product_option_generale_checkbox" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_product_option_generale_checkbox" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_product_option_generale_checkbox_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_product_option_generale_checkbox_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_product_option_generale_checkbox_id_seq" OWNED BY ziskakan."BaseBillet_product_option_generale_checkbox".id;


--
-- Name: BaseBillet_product_option_generale_radio; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_product_option_generale_radio" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_product_option_generale_radio" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_product_option_generale_radio_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_product_option_generale_radio_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_product_option_generale_radio_id_seq" OWNED BY ziskakan."BaseBillet_product_option_generale_radio".id;


--
-- Name: BaseBillet_product_tag; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_product_tag" (
    id integer NOT NULL,
    product_id uuid NOT NULL,
    tag_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_product_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_product_tag_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_product_tag_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_product_tag_id_seq" OWNED BY ziskakan."BaseBillet_product_tag".id;


--
-- Name: BaseBillet_productsold; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_productsold" (
    uuid uuid NOT NULL,
    id_product_stripe character varying(30),
    event_id uuid,
    product_id uuid NOT NULL,
    categorie_article character varying(3) NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_productsold" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_reservation" (
    uuid uuid NOT NULL,
    datetime timestamp with time zone NOT NULL,
    status character varying(3) NOT NULL,
    to_mail boolean NOT NULL,
    mail_send boolean NOT NULL,
    mail_error boolean NOT NULL,
    event_id uuid NOT NULL,
    user_commande_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_reservation" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_reservation_options" (
    id integer NOT NULL,
    reservation_id uuid NOT NULL,
    optiongenerale_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_reservation_options" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_reservation_options_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_reservation_options_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_reservation_options_id_seq" OWNED BY ziskakan."BaseBillet_reservation_options".id;


--
-- Name: BaseBillet_tag; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_tag" (
    uuid uuid NOT NULL,
    name character varying(50) NOT NULL,
    color character varying(7) NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_tag" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_ticket; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_ticket" (
    uuid uuid NOT NULL,
    first_name character varying(200) NOT NULL,
    last_name character varying(200) NOT NULL,
    status character varying(1) NOT NULL,
    seat character varying(20) NOT NULL,
    pricesold_id uuid NOT NULL,
    reservation_id uuid NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_ticket" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_webhook" (
    id integer NOT NULL,
    url character varying(200) NOT NULL,
    event character varying(2) NOT NULL,
    active boolean NOT NULL,
    last_response text
);


ALTER TABLE ziskakan."BaseBillet_webhook" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_webhook_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_webhook_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_webhook_id_seq" OWNED BY ziskakan."BaseBillet_webhook".id;


--
-- Name: BaseBillet_weekday; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan."BaseBillet_weekday" (
    id integer NOT NULL,
    day integer NOT NULL
);


ALTER TABLE ziskakan."BaseBillet_weekday" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan."BaseBillet_weekday_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan."BaseBillet_weekday_id_seq" OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan."BaseBillet_weekday_id_seq" OWNED BY ziskakan."BaseBillet_weekday".id;


--
-- Name: django_content_type; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan.django_content_type (
    id integer NOT NULL,
    app_label character varying(100) NOT NULL,
    model character varying(100) NOT NULL
);


ALTER TABLE ziskakan.django_content_type OWNER TO ticket_postgres_user;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan.django_content_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan.django_content_type_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan.django_content_type_id_seq OWNED BY ziskakan.django_content_type.id;


--
-- Name: django_migrations; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan.django_migrations (
    id integer NOT NULL,
    app character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    applied timestamp with time zone NOT NULL
);


ALTER TABLE ziskakan.django_migrations OWNER TO ticket_postgres_user;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE SEQUENCE ziskakan.django_migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE ziskakan.django_migrations_id_seq OWNER TO ticket_postgres_user;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER SEQUENCE ziskakan.django_migrations_id_seq OWNED BY ziskakan.django_migrations.id;


--
-- Name: rest_framework_api_key_apikey; Type: TABLE; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE TABLE ziskakan.rest_framework_api_key_apikey (
    id character varying(150) NOT NULL,
    created timestamp with time zone NOT NULL,
    name character varying(50) NOT NULL,
    revoked boolean NOT NULL,
    expiry_date timestamp with time zone,
    hashed_key character varying(150) NOT NULL,
    prefix character varying(8) NOT NULL
);


ALTER TABLE ziskakan.rest_framework_api_key_apikey OWNER TO ticket_postgres_user;

--
-- Name: BaseBillet_artist_on_event id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_artist_on_event" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_artist_on_event_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_configuration" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_configuration_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration_option_generale_checkbox id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration_option_generale_radio id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_event_options_checkbox id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_options_checkbox" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_event_options_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_event_options_radio id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_options_radio" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_event_options_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_event_products id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_products" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_event_products_id_seq"'::regclass);


--
-- Name: BaseBillet_event_recurrent id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_recurrent" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_event_recurrent_id_seq"'::regclass);


--
-- Name: BaseBillet_event_tag id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_tag" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_event_tag_id_seq"'::regclass);


--
-- Name: BaseBillet_externalapikey id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_externalapikey" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_apikey_id_seq"'::regclass);


--
-- Name: BaseBillet_membership id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_membership" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_membership_id_seq"'::regclass);


--
-- Name: BaseBillet_membership_option_generale id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_membership_option_generale" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_membership_option_generale_id_seq"'::regclass);


--
-- Name: BaseBillet_product_option_generale_checkbox id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_product_option_generale_radio id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_option_generale_radio" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_product_option_generale_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_product_tag id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_tag" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_product_tag_id_seq"'::regclass);


--
-- Name: BaseBillet_reservation_options id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_reservation_options" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_reservation_options_id_seq"'::regclass);


--
-- Name: BaseBillet_webhook id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_webhook" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_webhook_id_seq"'::regclass);


--
-- Name: BaseBillet_weekday id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_weekday" ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system"."BaseBillet_weekday_id_seq"'::regclass);


--
-- Name: django_content_type id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system".django_content_type ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system".django_content_type_id_seq'::regclass);


--
-- Name: django_migrations id; Type: DEFAULT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system".django_migrations ALTER COLUMN id SET DEFAULT nextval('"balaphonik-sound-system".django_migrations_id_seq'::regclass);


--
-- Name: BaseBillet_artist_on_event id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_artist_on_event" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_artist_on_event_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_configuration" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_configuration_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration_option_generale_checkbox id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_configuration_option_generale_checkbox" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_configuration_option_generale_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration_option_generale_radio id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_configuration_option_generale_radio" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_configuration_option_generale_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_event_options_checkbox id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_options_checkbox" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_event_options_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_event_options_radio id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_options_radio" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_event_options_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_event_products id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_products" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_event_products_id_seq"'::regclass);


--
-- Name: BaseBillet_event_recurrent id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_recurrent" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_event_recurrent_id_seq"'::regclass);


--
-- Name: BaseBillet_event_tag id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_tag" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_event_tag_id_seq"'::regclass);


--
-- Name: BaseBillet_externalapikey id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_externalapikey" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_apikey_id_seq"'::regclass);


--
-- Name: BaseBillet_membership id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_membership" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_membership_id_seq"'::regclass);


--
-- Name: BaseBillet_membership_option_generale id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_membership_option_generale" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_membership_option_generale_id_seq"'::regclass);


--
-- Name: BaseBillet_product_option_generale_checkbox id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_option_generale_checkbox" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_product_option_generale_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_product_option_generale_radio id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_option_generale_radio" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_product_option_generale_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_product_tag id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_tag" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_product_tag_id_seq"'::regclass);


--
-- Name: BaseBillet_reservation_options id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_reservation_options" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_reservation_options_id_seq"'::regclass);


--
-- Name: BaseBillet_webhook id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_webhook" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_webhook_id_seq"'::regclass);


--
-- Name: BaseBillet_weekday id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_weekday" ALTER COLUMN id SET DEFAULT nextval('billetistan."BaseBillet_weekday_id_seq"'::regclass);


--
-- Name: django_content_type id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan.django_content_type ALTER COLUMN id SET DEFAULT nextval('billetistan.django_content_type_id_seq'::regclass);


--
-- Name: django_migrations id; Type: DEFAULT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan.django_migrations ALTER COLUMN id SET DEFAULT nextval('billetistan.django_migrations_id_seq'::regclass);


--
-- Name: BaseBillet_artist_on_event id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_artist_on_event" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_artist_on_event_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_configuration" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_configuration_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration_option_generale_checkbox id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_configuration_option_generale_checkbox" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_configuration_option_generale_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration_option_generale_radio id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_configuration_option_generale_radio" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_configuration_option_generale_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_event_options_checkbox id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_options_checkbox" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_event_options_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_event_options_radio id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_options_radio" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_event_options_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_event_products id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_products" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_event_products_id_seq"'::regclass);


--
-- Name: BaseBillet_event_recurrent id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_recurrent" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_event_recurrent_id_seq"'::regclass);


--
-- Name: BaseBillet_event_tag id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_tag" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_event_tag_id_seq"'::regclass);


--
-- Name: BaseBillet_externalapikey id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_externalapikey" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_apikey_id_seq"'::regclass);


--
-- Name: BaseBillet_membership id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_membership" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_membership_id_seq"'::regclass);


--
-- Name: BaseBillet_membership_option_generale id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_membership_option_generale" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_membership_option_generale_id_seq"'::regclass);


--
-- Name: BaseBillet_product_option_generale_checkbox id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_option_generale_checkbox" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_product_option_generale_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_product_option_generale_radio id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_option_generale_radio" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_product_option_generale_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_product_tag id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_tag" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_product_tag_id_seq"'::regclass);


--
-- Name: BaseBillet_reservation_options id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_reservation_options" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_reservation_options_id_seq"'::regclass);


--
-- Name: BaseBillet_webhook id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_webhook" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_webhook_id_seq"'::regclass);


--
-- Name: BaseBillet_weekday id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_weekday" ALTER COLUMN id SET DEFAULT nextval('demo."BaseBillet_weekday_id_seq"'::regclass);


--
-- Name: django_content_type id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo.django_content_type ALTER COLUMN id SET DEFAULT nextval('demo.django_content_type_id_seq'::regclass);


--
-- Name: django_migrations id; Type: DEFAULT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo.django_migrations ALTER COLUMN id SET DEFAULT nextval('demo.django_migrations_id_seq'::regclass);


--
-- Name: BaseBillet_artist_on_event id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_artist_on_event" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_artist_on_event_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_configuration" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_configuration_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration_option_generale_checkbox id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_configuration_option_generale_checkbox" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_configuration_option_generale_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration_option_generale_radio id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_configuration_option_generale_radio" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_configuration_option_generale_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_event_options_checkbox id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_options_checkbox" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_event_options_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_event_options_radio id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_options_radio" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_event_options_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_event_products id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_products" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_event_products_id_seq"'::regclass);


--
-- Name: BaseBillet_event_recurrent id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_recurrent" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_event_recurrent_id_seq"'::regclass);


--
-- Name: BaseBillet_event_tag id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_tag" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_event_tag_id_seq"'::regclass);


--
-- Name: BaseBillet_externalapikey id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_externalapikey" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_apikey_id_seq"'::regclass);


--
-- Name: BaseBillet_membership id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_membership" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_membership_id_seq"'::regclass);


--
-- Name: BaseBillet_membership_option_generale id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_membership_option_generale" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_membership_option_generale_id_seq"'::regclass);


--
-- Name: BaseBillet_product_option_generale_checkbox id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_option_generale_checkbox" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_product_option_generale_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_product_option_generale_radio id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_option_generale_radio" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_product_option_generale_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_product_tag id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_tag" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_product_tag_id_seq"'::regclass);


--
-- Name: BaseBillet_reservation_options id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_reservation_options" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_reservation_options_id_seq"'::regclass);


--
-- Name: BaseBillet_webhook id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_webhook" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_webhook_id_seq"'::regclass);


--
-- Name: BaseBillet_weekday id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_weekday" ALTER COLUMN id SET DEFAULT nextval('meta."BaseBillet_weekday_id_seq"'::regclass);


--
-- Name: django_content_type id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta.django_content_type ALTER COLUMN id SET DEFAULT nextval('meta.django_content_type_id_seq'::regclass);


--
-- Name: django_migrations id; Type: DEFAULT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta.django_migrations ALTER COLUMN id SET DEFAULT nextval('meta.django_migrations_id_seq'::regclass);


--
-- Name: AuthBillet_terminalpairingtoken id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_terminalpairingtoken" ALTER COLUMN id SET DEFAULT nextval('public."AuthBillet_terminalpairingtoken_id_seq"'::regclass);


--
-- Name: AuthBillet_tibilletuser_client_achat id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_client_achat" ALTER COLUMN id SET DEFAULT nextval('public."AuthBillet_tibilletuser_client_achat_id_seq"'::regclass);


--
-- Name: AuthBillet_tibilletuser_client_admin id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_client_admin" ALTER COLUMN id SET DEFAULT nextval('public."AuthBillet_tibilletuser_client_admin_id_seq"'::regclass);


--
-- Name: AuthBillet_tibilletuser_groups id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_groups" ALTER COLUMN id SET DEFAULT nextval('public."AuthBillet_tibilletuser_groups_id_seq"'::regclass);


--
-- Name: AuthBillet_tibilletuser_user_permissions id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_user_permissions" ALTER COLUMN id SET DEFAULT nextval('public."AuthBillet_tibilletuser_user_permissions_id_seq"'::regclass);


--
-- Name: Customers_domain id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."Customers_domain" ALTER COLUMN id SET DEFAULT nextval('public."Customers_domain_id_seq"'::regclass);


--
-- Name: MetaBillet_eventdirectory id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."MetaBillet_eventdirectory" ALTER COLUMN id SET DEFAULT nextval('public."MetaBillet_eventdirectory_id_seq"'::regclass);


--
-- Name: MetaBillet_productdirectory id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."MetaBillet_productdirectory" ALTER COLUMN id SET DEFAULT nextval('public."MetaBillet_productdirectory_id_seq"'::regclass);


--
-- Name: QrcodeCashless_cartecashless id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_cartecashless" ALTER COLUMN id SET DEFAULT nextval('public."QrcodeCashless_cartecashless_id_seq"'::regclass);


--
-- Name: QrcodeCashless_detail id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_detail" ALTER COLUMN id SET DEFAULT nextval('public."QrcodeCashless_detail_id_seq"'::regclass);


--
-- Name: QrcodeCashless_syncfederatedlog id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_syncfederatedlog" ALTER COLUMN id SET DEFAULT nextval('public."QrcodeCashless_syncfederatedlog_id_seq"'::regclass);


--
-- Name: auth_group id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.auth_group ALTER COLUMN id SET DEFAULT nextval('public.auth_group_id_seq'::regclass);


--
-- Name: auth_group_permissions id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.auth_group_permissions ALTER COLUMN id SET DEFAULT nextval('public.auth_group_permissions_id_seq'::regclass);


--
-- Name: auth_permission id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.auth_permission ALTER COLUMN id SET DEFAULT nextval('public.auth_permission_id_seq'::regclass);


--
-- Name: django_admin_log id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.django_admin_log ALTER COLUMN id SET DEFAULT nextval('public.django_admin_log_id_seq'::regclass);


--
-- Name: django_content_type id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.django_content_type ALTER COLUMN id SET DEFAULT nextval('public.django_content_type_id_seq'::regclass);


--
-- Name: django_migrations id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.django_migrations ALTER COLUMN id SET DEFAULT nextval('public.django_migrations_id_seq'::regclass);


--
-- Name: django_site id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.django_site ALTER COLUMN id SET DEFAULT nextval('public.django_site_id_seq'::regclass);


--
-- Name: root_billet_rootconfiguration id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.root_billet_rootconfiguration ALTER COLUMN id SET DEFAULT nextval('public.root_billet_rootconfiguration_id_seq'::regclass);


--
-- Name: token_blacklist_blacklistedtoken id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.token_blacklist_blacklistedtoken ALTER COLUMN id SET DEFAULT nextval('public.token_blacklist_blacklistedtoken_id_seq'::regclass);


--
-- Name: token_blacklist_outstandingtoken id; Type: DEFAULT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.token_blacklist_outstandingtoken ALTER COLUMN id SET DEFAULT nextval('public.token_blacklist_outstandingtoken_id_seq'::regclass);


--
-- Name: BaseBillet_artist_on_event id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_artist_on_event" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_artist_on_event_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_configuration" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_configuration_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration_option_generale_checkbox id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_configuration_option_generale_checkbox" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_configuration_option_generale_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_configuration_option_generale_radio id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_configuration_option_generale_radio" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_configuration_option_generale_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_event_options_checkbox id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_options_checkbox" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_event_options_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_event_options_radio id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_options_radio" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_event_options_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_event_products id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_products" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_event_products_id_seq"'::regclass);


--
-- Name: BaseBillet_event_recurrent id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_recurrent" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_event_recurrent_id_seq"'::regclass);


--
-- Name: BaseBillet_event_tag id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_tag" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_event_tag_id_seq"'::regclass);


--
-- Name: BaseBillet_externalapikey id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_externalapikey" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_apikey_id_seq"'::regclass);


--
-- Name: BaseBillet_membership id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_membership" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_membership_id_seq"'::regclass);


--
-- Name: BaseBillet_membership_option_generale id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_membership_option_generale" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_membership_option_generale_id_seq"'::regclass);


--
-- Name: BaseBillet_product_option_generale_checkbox id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_option_generale_checkbox" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_product_option_generale_checkbox_id_seq"'::regclass);


--
-- Name: BaseBillet_product_option_generale_radio id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_option_generale_radio" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_product_option_generale_radio_id_seq"'::regclass);


--
-- Name: BaseBillet_product_tag id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_tag" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_product_tag_id_seq"'::regclass);


--
-- Name: BaseBillet_reservation_options id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_reservation_options" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_reservation_options_id_seq"'::regclass);


--
-- Name: BaseBillet_webhook id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_webhook" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_webhook_id_seq"'::regclass);


--
-- Name: BaseBillet_weekday id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_weekday" ALTER COLUMN id SET DEFAULT nextval('ziskakan."BaseBillet_weekday_id_seq"'::regclass);


--
-- Name: django_content_type id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan.django_content_type ALTER COLUMN id SET DEFAULT nextval('ziskakan.django_content_type_id_seq'::regclass);


--
-- Name: django_migrations id; Type: DEFAULT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan.django_migrations ALTER COLUMN id SET DEFAULT nextval('ziskakan.django_migrations_id_seq'::regclass);


--
-- Data for Name: BaseBillet_artist_on_event; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_artist_on_event" (id, datetime, artist_id, event_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_configuration; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_configuration" (id, organisation, short_description, long_description, adress, postal_code, city, phone, email, site_web, twitter, facebook, instagram, map_img, carte_restaurant, img, fuseau_horaire, logo, stripe_api_key, stripe_test_api_key, stripe_mode_test, jauge_max, server_cashless, key_cashless, template_billetterie, template_meta, activate_mailjet, email_confirm_template, slug, legal_documents, stripe_connect_account, stripe_connect_account_test, stripe_payouts_enabled, federated_cashless, ghost_key, ghost_last_log, ghost_url, key_fedow, server_fedow) FROM stdin;
1	Balaphonik Sound System	Balaphonik Sound System	Multi-instrumentiste, Alex a participé à des projets musicaux variés.	\N	\N	\N		root@root.root	\N	\N	\N	\N			images/1080_fvvZlc1	Indian/Reunion	images/540_Z7DCInP	\N	\N	t	50	\N	\N	arnaud_mvc	html5up-masseively	f	3898061	balaphonik-sound-system	\N	acct_1M7YYOE0J1b3jXbW	\N	f	f	\N	\N	\N	\N	\N
\.


--
-- Data for Name: BaseBillet_configuration_option_generale_checkbox; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox" (id, configuration_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_configuration_option_generale_radio; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio" (id, configuration_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_event" (uuid, name, slug, datetime, created, short_description, long_description, url_external, published, img, categorie, jauge_max, minimum_cashless_required, max_per_user, is_external, booking) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_options_checkbox; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_event_options_checkbox" (id, event_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_options_radio; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_event_options_radio" (id, event_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_products; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_event_products" (id, event_id, product_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_recurrent; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_event_recurrent" (id, event_id, weekday_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_tag; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_event_tag" (id, event_id, tag_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_externalapikey; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_externalapikey" (id, ip, revoquer_apikey, created, name, event, product, artist, place, user_id, reservation, ticket, key_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_lignearticle; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_lignearticle" (uuid, datetime, qty, status, carte_id, paiement_stripe_id, pricesold_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_membership; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_membership" (id, date_added, first_contribution, last_contribution, contribution_value, last_action, first_name, last_name, pseudo, newsletter, postal_code, birth_date, phone, commentaire, user_id, price_id, stripe_id_subscription, last_stripe_invoice, status) FROM stdin;
\.


--
-- Data for Name: BaseBillet_membership_option_generale; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_membership_option_generale" (id, membership_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_optiongenerale; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_optiongenerale" (uuid, name, poids, description) FROM stdin;
\.


--
-- Data for Name: BaseBillet_paiement_stripe; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_paiement_stripe" (uuid, detail, datetime, checkout_session_id_stripe, payment_intent_id, metadata_stripe, order_date, last_action, status, traitement_en_cours, source_traitement, source, total, reservation_id, user_id, customer_stripe, invoice_stripe, subscription) FROM stdin;
\.


--
-- Data for Name: BaseBillet_price; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_price" (uuid, name, prix, vat, stock, max_per_user, product_id, adhesion_obligatoire_id, long_description, short_description, subscription_type, recurring_payment) FROM stdin;
\.


--
-- Data for Name: BaseBillet_pricesold; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_pricesold" (uuid, id_price_stripe, qty_solded, prix, price_id, productsold_id, gift) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_product" (uuid, name, publish, img, categorie_article, long_description, short_description, terms_and_conditions_document, send_to_cashless, poids, archive, legal_link, nominative) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product_option_generale_checkbox; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox" (id, product_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product_option_generale_radio; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_product_option_generale_radio" (id, product_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product_tag; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_product_tag" (id, product_id, tag_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_productsold; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_productsold" (uuid, id_product_stripe, event_id, product_id, categorie_article) FROM stdin;
\.


--
-- Data for Name: BaseBillet_reservation; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_reservation" (uuid, datetime, status, to_mail, mail_send, mail_error, event_id, user_commande_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_reservation_options; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_reservation_options" (id, reservation_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_tag; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_tag" (uuid, name, color) FROM stdin;
\.


--
-- Data for Name: BaseBillet_ticket; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_ticket" (uuid, first_name, last_name, status, seat, pricesold_id, reservation_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_webhook; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_webhook" (id, url, event, active, last_response) FROM stdin;
\.


--
-- Data for Name: BaseBillet_weekday; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system"."BaseBillet_weekday" (id, day) FROM stdin;
1	0
2	1
3	2
4	3
5	4
6	5
7	6
\.


--
-- Data for Name: django_content_type; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system".django_content_type (id, app_label, model) FROM stdin;
1	Customers	client
2	Customers	domain
3	contenttypes	contenttype
4	auth	permission
5	auth	group
6	AuthBillet	tibilletuser
7	AuthBillet	humanuser
8	AuthBillet	superhumanuser
9	AuthBillet	termuser
10	AuthBillet	terminalpairingtoken
11	QrcodeCashless	detail
12	QrcodeCashless	cartecashless
13	QrcodeCashless	asset
14	QrcodeCashless	wallet
15	QrcodeCashless	syncfederatedlog
16	QrcodeCashless	federatedcashless
17	authtoken	token
18	authtoken	tokenproxy
19	token_blacklist	blacklistedtoken
20	token_blacklist	outstandingtoken
21	sessions	session
22	sites	site
23	admin	logentry
24	MetaBillet	eventdirectory
25	MetaBillet	productdirectory
26	root_billet	rootconfiguration
27	rest_framework_api_key	apikey
28	BaseBillet	event
29	BaseBillet	optiongenerale
30	BaseBillet	price
31	BaseBillet	pricesold
32	BaseBillet	product
33	BaseBillet	reservation
34	BaseBillet	ticket
35	BaseBillet	productsold
36	BaseBillet	paiement_stripe
37	BaseBillet	membership
38	BaseBillet	lignearticle
39	BaseBillet	configuration
40	BaseBillet	artist_on_event
41	BaseBillet	webhook
42	BaseBillet	externalapikey
43	BaseBillet	tag
44	BaseBillet	weekday
\.


--
-- Data for Name: django_migrations; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system".django_migrations (id, app, name, applied) FROM stdin;
1	contenttypes	0001_initial	2023-10-18 17:19:15.882988+04
2	contenttypes	0002_remove_content_type_name	2023-10-18 17:19:15.891732+04
3	auth	0001_initial	2023-10-18 17:19:15.90365+04
4	auth	0002_alter_permission_name_max_length	2023-10-18 17:19:15.909946+04
5	auth	0003_alter_user_email_max_length	2023-10-18 17:19:15.916217+04
6	auth	0004_alter_user_username_opts	2023-10-18 17:19:15.923125+04
7	auth	0005_alter_user_last_login_null	2023-10-18 17:19:15.929212+04
8	auth	0006_require_contenttypes_0002	2023-10-18 17:19:15.931825+04
9	auth	0007_alter_validators_add_error_messages	2023-10-18 17:19:15.937454+04
10	auth	0008_alter_user_username_max_length	2023-10-18 17:19:15.943734+04
11	auth	0009_alter_user_last_name_max_length	2023-10-18 17:19:15.954232+04
12	auth	0010_alter_group_name_max_length	2023-10-18 17:19:15.960908+04
13	auth	0011_update_proxy_permissions	2023-10-18 17:19:15.964562+04
14	auth	0012_alter_user_first_name_max_length	2023-10-18 17:19:15.970917+04
15	Customers	0001_initial	2023-10-18 17:19:15.976037+04
16	AuthBillet	0001_initial	2023-10-18 17:19:15.987695+04
17	AuthBillet	0002_alter_tibilletuser_is_active	2023-10-18 17:19:15.998024+04
18	AuthBillet	0003_tibilletuser_user_parent_pk	2023-10-18 17:19:16.008313+04
19	AuthBillet	0004_terminalpairingtoken	2023-10-18 17:19:16.022115+04
20	AuthBillet	0005_auto_20220422_1601	2023-10-18 17:19:16.056237+04
21	AuthBillet	0006_terminalpairingtoken_used	2023-10-18 17:19:16.067406+04
22	AuthBillet	0007_alter_terminalpairingtoken_datetime	2023-10-18 17:19:16.078815+04
23	AuthBillet	0008_alter_terminalpairingtoken_datetime	2023-10-18 17:19:16.089882+04
24	AuthBillet	0009_alter_tibilletuser_is_active	2023-10-18 17:19:16.100614+04
25	rest_framework_api_key	0001_initial	2023-10-18 17:19:16.12258+04
26	rest_framework_api_key	0002_auto_20190529_2243	2023-10-18 17:19:16.136606+04
27	rest_framework_api_key	0003_auto_20190623_1952	2023-10-18 17:19:16.142285+04
28	rest_framework_api_key	0004_prefix_hashed_key	2023-10-18 17:19:16.174286+04
29	rest_framework_api_key	0005_auto_20220110_1102	2023-10-18 17:19:16.248834+04
30	QrcodeCashless	0001_initial	2023-10-18 17:19:16.266557+04
31	BaseBillet	0001_initial	2023-10-18 17:19:16.947296+04
32	BaseBillet	0002_alter_ticket_seat	2023-10-18 17:19:16.986293+04
33	BaseBillet	0003_alter_reservation_user_commande	2023-10-18 17:19:17.018039+04
34	BaseBillet	0004_auto_20220421_1129	2023-10-18 17:19:17.052096+04
35	BaseBillet	0005_alter_reservation_status	2023-10-18 17:19:17.074702+04
36	BaseBillet	0006_auto_20220428_1533	2023-10-18 17:19:17.10081+04
37	BaseBillet	0007_alter_configuration_img	2023-10-18 17:19:17.114804+04
38	BaseBillet	0008_auto_20220505_1520	2023-10-18 17:19:17.205164+04
39	BaseBillet	0009_configuration_slug	2023-10-18 17:19:17.225139+04
40	BaseBillet	0010_auto_20220531_0920	2023-10-18 17:19:17.276158+04
41	BaseBillet	0011_membership_price	2023-10-18 17:19:17.305502+04
42	BaseBillet	0012_configuration_legal_documents	2023-10-18 17:19:17.31788+04
43	BaseBillet	0013_auto_20220602_1013	2023-10-18 17:19:17.421084+04
44	BaseBillet	0014_product_terms_and_conditions_document	2023-10-18 17:19:17.429922+04
45	BaseBillet	0015_price_subscription_type	2023-10-18 17:19:17.440005+04
46	BaseBillet	0016_alter_membership_unique_together	2023-10-18 17:19:17.459945+04
47	BaseBillet	0017_product_send_to_cashless	2023-10-18 17:19:17.472897+04
48	BaseBillet	0018_auto_20220608_1607	2023-10-18 17:19:17.497242+04
49	BaseBillet	0019_auto_20220624_0726	2023-10-18 17:19:17.529592+04
50	BaseBillet	0020_membership_stripe_id_subscription	2023-10-18 17:19:17.547988+04
51	BaseBillet	0021_paiement_stripe_invoice_stripe	2023-10-18 17:19:17.570132+04
52	BaseBillet	0022_paiement_stripe_subscription	2023-10-18 17:19:17.588765+04
53	BaseBillet	0023_membership_last_stripe_invoice	2023-10-18 17:19:17.610074+04
54	BaseBillet	0024_auto_20220626_1257	2023-10-18 17:19:17.663632+04
55	BaseBillet	0025_auto_20220810_1245	2023-10-18 17:19:17.690625+04
56	BaseBillet	0026_alter_configuration_slug	2023-10-18 17:19:17.778689+04
57	BaseBillet	0027_product_poids	2023-10-18 17:19:17.790543+04
58	BaseBillet	0028_auto_20220826_1559	2023-10-18 17:19:17.951768+04
59	BaseBillet	0029_remove_configuration_activer_billetterie	2023-10-18 17:19:17.962723+04
60	BaseBillet	0030_auto_20220927_1855	2023-10-18 17:19:18.006251+04
61	BaseBillet	0031_apikey	2023-10-18 17:19:18.031808+04
62	BaseBillet	0032_apikey_created	2023-10-18 17:19:18.038543+04
63	BaseBillet	0033_apikey_name	2023-10-18 17:19:18.060621+04
64	BaseBillet	0034_apikey_auth	2023-10-18 17:19:18.066666+04
65	BaseBillet	0035_alter_apikey_auth	2023-10-18 17:19:18.074726+04
66	BaseBillet	0036_remove_apikey_auth	2023-10-18 17:19:18.080639+04
67	BaseBillet	0037_auto_20221017_1320	2023-10-18 17:19:18.093477+04
68	BaseBillet	0038_apikey_product	2023-10-18 17:19:18.100159+04
69	BaseBillet	0039_auto_20221017_1402	2023-10-18 17:19:18.115186+04
70	BaseBillet	0040_apikey_user	2023-10-18 17:19:18.153348+04
71	BaseBillet	0041_auto_20221018_0932	2023-10-18 17:19:18.18714+04
72	BaseBillet	0042_webhook	2023-10-18 17:19:18.198248+04
73	BaseBillet	0043_webhook_active	2023-10-18 17:19:18.204028+04
74	BaseBillet	0044_webhook_last_response	2023-10-18 17:19:18.215463+04
75	BaseBillet	0045_auto_20221021_1031	2023-10-18 17:19:18.237776+04
76	BaseBillet	0046_alter_product_categorie_article	2023-10-18 17:19:18.266532+04
77	BaseBillet	0047_auto_20221121_1256	2023-10-18 17:19:18.287574+04
78	BaseBillet	0048_configuration_stripe_payouts_enabled	2023-10-18 17:19:18.302343+04
79	BaseBillet	0049_rename_apikey_externalapikey	2023-10-18 17:19:18.420892+04
80	BaseBillet	0050_alter_externalapikey_options	2023-10-18 17:19:18.436864+04
81	BaseBillet	0051_auto_20221125_1847	2023-10-18 17:19:18.481097+04
82	BaseBillet	0052_externalapikey_key	2023-10-18 17:19:18.517286+04
83	BaseBillet	0053_alter_externalapikey_options	2023-10-18 17:19:18.534411+04
84	BaseBillet	0054_price_recurring_payment	2023-10-18 17:19:18.549611+04
85	BaseBillet	0055_auto_20221215_1922	2023-10-18 17:19:18.607199+04
86	BaseBillet	0056_pricesold_gift	2023-10-18 17:19:18.623122+04
87	BaseBillet	0057_auto_20230102_1847	2023-10-18 17:19:18.685224+04
88	BaseBillet	0058_alter_paiement_stripe_status	2023-10-18 17:19:18.704668+04
89	BaseBillet	0059_event_cashless	2023-10-18 17:19:18.71899+04
90	BaseBillet	0060_event_minimum_cashless_required	2023-10-18 17:19:18.737191+04
91	BaseBillet	0061_configuration_federated_cashless	2023-10-18 17:19:18.752837+04
92	BaseBillet	0062_remove_configuration_mollie_api_key	2023-10-18 17:19:18.76811+04
93	BaseBillet	0063_auto_20230427_1105	2023-10-18 17:19:18.944086+04
94	BaseBillet	0064_auto_20230427_1146	2023-10-18 17:19:19.01648+04
95	BaseBillet	0065_auto_20230427_1248	2023-10-18 17:19:19.191906+04
96	BaseBillet	0066_optiongenerale_description	2023-10-18 17:19:19.207054+04
97	BaseBillet	0067_auto_20230427_1410	2023-10-18 17:19:19.318205+04
98	BaseBillet	0068_auto_20230427_1826	2023-10-18 17:19:19.382372+04
99	BaseBillet	0069_alter_optiongenerale_options	2023-10-18 17:19:19.397401+04
100	BaseBillet	0070_alter_configuration_short_description	2023-10-18 17:19:19.413462+04
101	BaseBillet	0071_event_tag	2023-10-18 17:19:19.478184+04
102	BaseBillet	0072_auto_20230522_1614	2023-10-18 17:19:19.529911+04
103	BaseBillet	0073_auto_20230523_1411	2023-10-18 17:19:19.560458+04
104	BaseBillet	0074_auto_20230523_1548	2023-10-18 17:19:19.803336+04
105	BaseBillet	0075_auto_20230524_1706	2023-10-18 17:19:19.864237+04
106	BaseBillet	0076_auto_20230525_1315	2023-10-18 17:19:19.888618+04
107	BaseBillet	0077_auto_20230525_1409	2023-10-18 17:19:19.927065+04
108	BaseBillet	0078_auto_20230602_1441	2023-10-18 17:19:19.959153+04
109	BaseBillet	0079_auto_20230822_0932	2023-10-18 17:19:20.010822+04
110	BaseBillet	0080_productsold_categorie_article	2023-10-18 17:19:20.027566+04
111	BaseBillet	0081_auto_20230822_1459	2023-10-18 17:19:20.060217+04
112	BaseBillet	0082_auto_20230906_1231	2023-10-18 17:19:20.195591+04
113	BaseBillet	0083_auto_20230906_1237	2023-10-18 17:19:20.237244+04
114	BaseBillet	0084_auto_20230906_1243	2023-10-18 17:19:20.282541+04
115	BaseBillet	0085_auto_20230908_1409	2023-10-18 17:19:20.364842+04
116	BaseBillet	0086_auto_20230908_1410	2023-10-18 17:19:20.398116+04
117	Customers	0002_alter_client_categorie	2023-10-18 17:19:20.432478+04
118	MetaBillet	0001_initial	2023-10-18 17:19:20.437056+04
119	MetaBillet	0002_auto_20220519_0904	2023-10-18 17:19:20.47169+04
120	MetaBillet	0003_productdirectory	2023-10-18 17:19:20.507016+04
121	QrcodeCashless	0002_alter_detail_img	2023-10-18 17:19:20.522056+04
122	QrcodeCashless	0003_auto_20221101_1820	2023-10-18 17:19:20.69079+04
123	QrcodeCashless	0004_detail_uuid	2023-10-18 17:19:20.701883+04
124	QrcodeCashless	0005_auto_20230103_1240	2023-10-18 17:19:20.777752+04
125	QrcodeCashless	0006_alter_wallet_unique_together	2023-10-18 17:19:20.797535+04
126	QrcodeCashless	0007_alter_wallet_unique_together	2023-10-18 17:19:20.81749+04
127	QrcodeCashless	0008_alter_cartecashless_uuid	2023-10-18 17:19:20.837532+04
128	QrcodeCashless	0009_federatedcashless_syncfederatedlog	2023-10-18 17:19:20.902858+04
129	QrcodeCashless	0010_auto_20230111_0701	2023-10-18 17:19:20.946219+04
130	QrcodeCashless	0011_auto_20230125_1445	2023-10-18 17:19:20.973507+04
131	QrcodeCashless	0012_syncfederatedlog_categorie	2023-10-18 17:19:20.989572+04
132	QrcodeCashless	0013_auto_20230125_1802	2023-10-18 17:19:21.056509+04
133	QrcodeCashless	0014_asset_categorie	2023-10-18 17:19:21.069015+04
134	QrcodeCashless	0015_alter_asset_unique_together	2023-10-18 17:19:21.082404+04
135	QrcodeCashless	0016_detail_slug	2023-10-18 17:19:21.178312+04
136	admin	0001_initial	2023-10-18 17:19:21.212535+04
137	admin	0002_logentry_remove_auto_add	2023-10-18 17:19:21.231404+04
138	admin	0003_logentry_add_action_flag_choices	2023-10-18 17:19:21.249323+04
139	authtoken	0001_initial	2023-10-18 17:19:21.286387+04
140	authtoken	0002_auto_20160226_1747	2023-10-18 17:19:21.366905+04
141	authtoken	0003_tokenproxy	2023-10-18 17:19:21.371101+04
142	root_billet	0001_initial	2023-10-18 17:19:21.375269+04
143	sessions	0001_initial	2023-10-18 17:19:21.380543+04
144	sites	0001_initial	2023-10-18 17:19:21.386791+04
145	sites	0002_alter_domain_unique	2023-10-18 17:19:21.392341+04
146	token_blacklist	0001_initial	2023-10-18 17:19:21.464846+04
147	token_blacklist	0002_outstandingtoken_jti_hex	2023-10-18 17:19:21.48181+04
148	token_blacklist	0003_auto_20171017_2007	2023-10-18 17:19:21.485583+04
149	token_blacklist	0004_auto_20171017_2013	2023-10-18 17:19:21.504887+04
150	token_blacklist	0005_remove_outstandingtoken_jti	2023-10-18 17:19:21.52396+04
151	token_blacklist	0006_auto_20171017_2113	2023-10-18 17:19:21.546601+04
152	token_blacklist	0007_auto_20171017_2214	2023-10-18 17:19:21.606098+04
153	token_blacklist	0008_migrate_to_bigautofield	2023-10-18 17:19:21.71801+04
154	token_blacklist	0010_fix_migrate_to_bigautofield	2023-10-18 17:19:21.772202+04
155	token_blacklist	0011_linearizes_history	2023-10-18 17:19:21.775183+04
156	token_blacklist	0012_alter_outstandingtoken_user	2023-10-18 17:19:21.815628+04
\.


--
-- Data for Name: rest_framework_api_key_apikey; Type: TABLE DATA; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

COPY "balaphonik-sound-system".rest_framework_api_key_apikey (id, created, name, revoked, expiry_date, hashed_key, prefix) FROM stdin;
\.


--
-- Data for Name: BaseBillet_artist_on_event; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_artist_on_event" (id, datetime, artist_id, event_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_configuration; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_configuration" (id, organisation, short_description, long_description, adress, postal_code, city, phone, email, site_web, twitter, facebook, instagram, map_img, carte_restaurant, img, fuseau_horaire, logo, stripe_api_key, stripe_test_api_key, stripe_mode_test, jauge_max, server_cashless, key_cashless, template_billetterie, template_meta, activate_mailjet, email_confirm_template, slug, legal_documents, stripe_connect_account, stripe_connect_account_test, stripe_payouts_enabled, federated_cashless, ghost_key, ghost_last_log, ghost_url, key_fedow, server_fedow) FROM stdin;
1	Billetistan	Grande scène du Billetistan	\N	\N	\N	\N		root@root.root	\N	\N	\N	\N			images/1080_WHSHYcK	Indian/Reunion	images/540_HjExeIz	\N	\N	t	50	https://cashless2.filaos.re	Mdz6ibyR.sthkYUzpEypuVjltDY68PIDy2n50HFjE	arnaud_mvc	html5up-masseively	f	3898061	billetistan	\N	acct_1M7YYOE0J1b3jXbW	\N	f	f	\N	\N	\N	\N	\N
\.


--
-- Data for Name: BaseBillet_configuration_option_generale_checkbox; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_configuration_option_generale_checkbox" (id, configuration_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_configuration_option_generale_radio; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_configuration_option_generale_radio" (id, configuration_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_event" (uuid, name, slug, datetime, created, short_description, long_description, url_external, published, img, categorie, jauge_max, minimum_cashless_required, max_per_user, is_external, booking) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_options_checkbox; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_event_options_checkbox" (id, event_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_options_radio; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_event_options_radio" (id, event_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_products; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_event_products" (id, event_id, product_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_recurrent; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_event_recurrent" (id, event_id, weekday_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_tag; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_event_tag" (id, event_id, tag_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_externalapikey; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_externalapikey" (id, ip, revoquer_apikey, created, name, event, product, artist, place, user_id, reservation, ticket, key_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_lignearticle; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_lignearticle" (uuid, datetime, qty, status, carte_id, paiement_stripe_id, pricesold_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_membership; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_membership" (id, date_added, first_contribution, last_contribution, contribution_value, last_action, first_name, last_name, pseudo, newsletter, postal_code, birth_date, phone, commentaire, user_id, price_id, stripe_id_subscription, last_stripe_invoice, status) FROM stdin;
\.


--
-- Data for Name: BaseBillet_membership_option_generale; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_membership_option_generale" (id, membership_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_optiongenerale; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_optiongenerale" (uuid, name, poids, description) FROM stdin;
\.


--
-- Data for Name: BaseBillet_paiement_stripe; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_paiement_stripe" (uuid, detail, datetime, checkout_session_id_stripe, payment_intent_id, metadata_stripe, order_date, last_action, status, traitement_en_cours, source_traitement, source, total, reservation_id, user_id, customer_stripe, invoice_stripe, subscription) FROM stdin;
\.


--
-- Data for Name: BaseBillet_price; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_price" (uuid, name, prix, vat, stock, max_per_user, product_id, adhesion_obligatoire_id, long_description, short_description, subscription_type, recurring_payment) FROM stdin;
\.


--
-- Data for Name: BaseBillet_pricesold; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_pricesold" (uuid, id_price_stripe, qty_solded, prix, price_id, productsold_id, gift) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_product" (uuid, name, publish, img, categorie_article, long_description, short_description, terms_and_conditions_document, send_to_cashless, poids, archive, legal_link, nominative) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product_option_generale_checkbox; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_product_option_generale_checkbox" (id, product_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product_option_generale_radio; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_product_option_generale_radio" (id, product_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product_tag; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_product_tag" (id, product_id, tag_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_productsold; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_productsold" (uuid, id_product_stripe, event_id, product_id, categorie_article) FROM stdin;
\.


--
-- Data for Name: BaseBillet_reservation; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_reservation" (uuid, datetime, status, to_mail, mail_send, mail_error, event_id, user_commande_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_reservation_options; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_reservation_options" (id, reservation_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_tag; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_tag" (uuid, name, color) FROM stdin;
\.


--
-- Data for Name: BaseBillet_ticket; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_ticket" (uuid, first_name, last_name, status, seat, pricesold_id, reservation_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_webhook; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_webhook" (id, url, event, active, last_response) FROM stdin;
\.


--
-- Data for Name: BaseBillet_weekday; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan."BaseBillet_weekday" (id, day) FROM stdin;
1	0
2	1
3	2
4	3
5	4
6	5
7	6
\.


--
-- Data for Name: django_content_type; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan.django_content_type (id, app_label, model) FROM stdin;
1	Customers	client
2	Customers	domain
3	contenttypes	contenttype
4	auth	permission
5	auth	group
6	AuthBillet	tibilletuser
7	AuthBillet	humanuser
8	AuthBillet	superhumanuser
9	AuthBillet	termuser
10	AuthBillet	terminalpairingtoken
11	QrcodeCashless	detail
12	QrcodeCashless	cartecashless
13	QrcodeCashless	asset
14	QrcodeCashless	wallet
15	QrcodeCashless	syncfederatedlog
16	QrcodeCashless	federatedcashless
17	authtoken	token
18	authtoken	tokenproxy
19	token_blacklist	blacklistedtoken
20	token_blacklist	outstandingtoken
21	sessions	session
22	sites	site
23	admin	logentry
24	MetaBillet	eventdirectory
25	MetaBillet	productdirectory
26	root_billet	rootconfiguration
27	rest_framework_api_key	apikey
28	BaseBillet	event
29	BaseBillet	optiongenerale
30	BaseBillet	price
31	BaseBillet	pricesold
32	BaseBillet	product
33	BaseBillet	reservation
34	BaseBillet	ticket
35	BaseBillet	productsold
36	BaseBillet	paiement_stripe
37	BaseBillet	membership
38	BaseBillet	lignearticle
39	BaseBillet	configuration
40	BaseBillet	artist_on_event
41	BaseBillet	webhook
42	BaseBillet	externalapikey
43	BaseBillet	tag
44	BaseBillet	weekday
\.


--
-- Data for Name: django_migrations; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan.django_migrations (id, app, name, applied) FROM stdin;
1	contenttypes	0001_initial	2023-10-18 17:18:53.173473+04
2	contenttypes	0002_remove_content_type_name	2023-10-18 17:18:53.192306+04
3	auth	0001_initial	2023-10-18 17:18:53.212461+04
4	auth	0002_alter_permission_name_max_length	2023-10-18 17:18:53.221819+04
5	auth	0003_alter_user_email_max_length	2023-10-18 17:18:53.233137+04
6	auth	0004_alter_user_username_opts	2023-10-18 17:18:53.243835+04
7	auth	0005_alter_user_last_login_null	2023-10-18 17:18:53.252356+04
8	auth	0006_require_contenttypes_0002	2023-10-18 17:18:53.255118+04
9	auth	0007_alter_validators_add_error_messages	2023-10-18 17:18:53.264822+04
10	auth	0008_alter_user_username_max_length	2023-10-18 17:18:53.272203+04
11	auth	0009_alter_user_last_name_max_length	2023-10-18 17:18:53.27984+04
12	auth	0010_alter_group_name_max_length	2023-10-18 17:18:53.28514+04
13	auth	0011_update_proxy_permissions	2023-10-18 17:18:53.287864+04
14	auth	0012_alter_user_first_name_max_length	2023-10-18 17:18:53.295001+04
15	Customers	0001_initial	2023-10-18 17:18:53.299907+04
16	AuthBillet	0001_initial	2023-10-18 17:18:53.311889+04
17	AuthBillet	0002_alter_tibilletuser_is_active	2023-10-18 17:18:53.32328+04
18	AuthBillet	0003_tibilletuser_user_parent_pk	2023-10-18 17:18:53.333228+04
19	AuthBillet	0004_terminalpairingtoken	2023-10-18 17:18:53.3465+04
20	AuthBillet	0005_auto_20220422_1601	2023-10-18 17:18:53.382571+04
21	AuthBillet	0006_terminalpairingtoken_used	2023-10-18 17:18:53.393486+04
22	AuthBillet	0007_alter_terminalpairingtoken_datetime	2023-10-18 17:18:53.403443+04
23	AuthBillet	0008_alter_terminalpairingtoken_datetime	2023-10-18 17:18:53.413473+04
24	AuthBillet	0009_alter_tibilletuser_is_active	2023-10-18 17:18:53.425011+04
25	rest_framework_api_key	0001_initial	2023-10-18 17:18:53.444509+04
26	rest_framework_api_key	0002_auto_20190529_2243	2023-10-18 17:18:53.452583+04
27	rest_framework_api_key	0003_auto_20190623_1952	2023-10-18 17:18:53.456867+04
28	rest_framework_api_key	0004_prefix_hashed_key	2023-10-18 17:18:53.489994+04
29	rest_framework_api_key	0005_auto_20220110_1102	2023-10-18 17:18:53.497851+04
30	QrcodeCashless	0001_initial	2023-10-18 17:18:53.517554+04
31	BaseBillet	0001_initial	2023-10-18 17:18:54.375602+04
32	BaseBillet	0002_alter_ticket_seat	2023-10-18 17:18:54.414553+04
33	BaseBillet	0003_alter_reservation_user_commande	2023-10-18 17:18:54.442237+04
34	BaseBillet	0004_auto_20220421_1129	2023-10-18 17:18:54.477288+04
35	BaseBillet	0005_alter_reservation_status	2023-10-18 17:18:54.502371+04
36	BaseBillet	0006_auto_20220428_1533	2023-10-18 17:18:54.529744+04
37	BaseBillet	0007_alter_configuration_img	2023-10-18 17:18:54.542652+04
38	BaseBillet	0008_auto_20220505_1520	2023-10-18 17:18:54.567526+04
39	BaseBillet	0009_configuration_slug	2023-10-18 17:18:54.591411+04
40	BaseBillet	0010_auto_20220531_0920	2023-10-18 17:18:54.65195+04
41	BaseBillet	0011_membership_price	2023-10-18 17:18:54.688493+04
42	BaseBillet	0012_configuration_legal_documents	2023-10-18 17:18:54.699548+04
43	BaseBillet	0013_auto_20220602_1013	2023-10-18 17:18:54.820134+04
44	BaseBillet	0014_product_terms_and_conditions_document	2023-10-18 17:18:54.828138+04
45	BaseBillet	0015_price_subscription_type	2023-10-18 17:18:54.841941+04
46	BaseBillet	0016_alter_membership_unique_together	2023-10-18 17:18:54.867268+04
47	BaseBillet	0017_product_send_to_cashless	2023-10-18 17:18:54.947912+04
48	BaseBillet	0018_auto_20220608_1607	2023-10-18 17:18:54.967844+04
49	BaseBillet	0019_auto_20220624_0726	2023-10-18 17:18:55.000155+04
50	BaseBillet	0020_membership_stripe_id_subscription	2023-10-18 17:18:55.016951+04
51	BaseBillet	0021_paiement_stripe_invoice_stripe	2023-10-18 17:18:55.041595+04
52	BaseBillet	0022_paiement_stripe_subscription	2023-10-18 17:18:55.062101+04
53	BaseBillet	0023_membership_last_stripe_invoice	2023-10-18 17:18:55.081078+04
54	BaseBillet	0024_auto_20220626_1257	2023-10-18 17:18:55.133087+04
55	BaseBillet	0025_auto_20220810_1245	2023-10-18 17:18:55.155368+04
56	BaseBillet	0026_alter_configuration_slug	2023-10-18 17:18:55.168727+04
57	BaseBillet	0027_product_poids	2023-10-18 17:18:55.179529+04
58	BaseBillet	0028_auto_20220826_1559	2023-10-18 17:18:55.341742+04
59	BaseBillet	0029_remove_configuration_activer_billetterie	2023-10-18 17:18:55.35251+04
60	BaseBillet	0030_auto_20220927_1855	2023-10-18 17:18:55.463356+04
61	BaseBillet	0031_apikey	2023-10-18 17:18:55.489947+04
62	BaseBillet	0032_apikey_created	2023-10-18 17:18:55.499043+04
63	BaseBillet	0033_apikey_name	2023-10-18 17:18:55.516959+04
64	BaseBillet	0034_apikey_auth	2023-10-18 17:18:55.523788+04
65	BaseBillet	0035_alter_apikey_auth	2023-10-18 17:18:55.530577+04
66	BaseBillet	0036_remove_apikey_auth	2023-10-18 17:18:55.536588+04
67	BaseBillet	0037_auto_20221017_1320	2023-10-18 17:18:55.547832+04
68	BaseBillet	0038_apikey_product	2023-10-18 17:18:55.553958+04
69	BaseBillet	0039_auto_20221017_1402	2023-10-18 17:18:55.568267+04
70	BaseBillet	0040_apikey_user	2023-10-18 17:18:55.603711+04
71	BaseBillet	0041_auto_20221018_0932	2023-10-18 17:18:55.635658+04
72	BaseBillet	0042_webhook	2023-10-18 17:18:55.64762+04
73	BaseBillet	0043_webhook_active	2023-10-18 17:18:55.655919+04
74	BaseBillet	0044_webhook_last_response	2023-10-18 17:18:55.667242+04
75	BaseBillet	0045_auto_20221021_1031	2023-10-18 17:18:55.694615+04
76	BaseBillet	0046_alter_product_categorie_article	2023-10-18 17:18:55.746626+04
77	BaseBillet	0047_auto_20221121_1256	2023-10-18 17:18:55.782153+04
78	BaseBillet	0048_configuration_stripe_payouts_enabled	2023-10-18 17:18:55.794685+04
79	BaseBillet	0049_rename_apikey_externalapikey	2023-10-18 17:18:55.860497+04
80	BaseBillet	0050_alter_externalapikey_options	2023-10-18 17:18:55.88209+04
81	BaseBillet	0051_auto_20221125_1847	2023-10-18 17:18:55.940354+04
82	BaseBillet	0052_externalapikey_key	2023-10-18 17:18:55.98668+04
83	BaseBillet	0053_alter_externalapikey_options	2023-10-18 17:18:56.005717+04
84	BaseBillet	0054_price_recurring_payment	2023-10-18 17:18:56.019295+04
85	BaseBillet	0055_auto_20221215_1922	2023-10-18 17:18:56.104799+04
86	BaseBillet	0056_pricesold_gift	2023-10-18 17:18:56.123455+04
87	BaseBillet	0057_auto_20230102_1847	2023-10-18 17:18:56.172843+04
88	BaseBillet	0058_alter_paiement_stripe_status	2023-10-18 17:18:56.198116+04
89	BaseBillet	0059_event_cashless	2023-10-18 17:18:56.223927+04
90	BaseBillet	0060_event_minimum_cashless_required	2023-10-18 17:18:56.342661+04
91	BaseBillet	0061_configuration_federated_cashless	2023-10-18 17:18:56.356183+04
92	BaseBillet	0062_remove_configuration_mollie_api_key	2023-10-18 17:18:56.367278+04
93	BaseBillet	0063_auto_20230427_1105	2023-10-18 17:18:56.52448+04
94	BaseBillet	0064_auto_20230427_1146	2023-10-18 17:18:56.613878+04
95	BaseBillet	0065_auto_20230427_1248	2023-10-18 17:18:56.758999+04
96	BaseBillet	0066_optiongenerale_description	2023-10-18 17:18:56.778495+04
97	BaseBillet	0067_auto_20230427_1410	2023-10-18 17:18:56.890591+04
98	BaseBillet	0068_auto_20230427_1826	2023-10-18 17:18:56.931347+04
99	BaseBillet	0069_alter_optiongenerale_options	2023-10-18 17:18:56.950343+04
100	BaseBillet	0070_alter_configuration_short_description	2023-10-18 17:18:56.969046+04
101	BaseBillet	0071_event_tag	2023-10-18 17:18:57.115222+04
102	BaseBillet	0072_auto_20230522_1614	2023-10-18 17:18:57.16722+04
103	BaseBillet	0073_auto_20230523_1411	2023-10-18 17:18:57.195527+04
104	BaseBillet	0074_auto_20230523_1548	2023-10-18 17:18:57.375826+04
105	BaseBillet	0075_auto_20230524_1706	2023-10-18 17:18:57.437939+04
106	BaseBillet	0076_auto_20230525_1315	2023-10-18 17:18:57.462025+04
107	BaseBillet	0077_auto_20230525_1409	2023-10-18 17:18:57.565538+04
108	BaseBillet	0078_auto_20230602_1441	2023-10-18 17:18:57.601532+04
109	BaseBillet	0079_auto_20230822_0932	2023-10-18 17:18:57.657834+04
110	BaseBillet	0080_productsold_categorie_article	2023-10-18 17:18:57.67175+04
111	BaseBillet	0081_auto_20230822_1459	2023-10-18 17:18:57.715578+04
112	BaseBillet	0082_auto_20230906_1231	2023-10-18 17:18:57.80284+04
113	BaseBillet	0083_auto_20230906_1237	2023-10-18 17:18:57.844469+04
114	BaseBillet	0084_auto_20230906_1243	2023-10-18 17:18:57.895724+04
115	BaseBillet	0085_auto_20230908_1409	2023-10-18 17:18:57.99585+04
116	BaseBillet	0086_auto_20230908_1410	2023-10-18 17:18:58.037741+04
117	Customers	0002_alter_client_categorie	2023-10-18 17:18:58.176587+04
118	MetaBillet	0001_initial	2023-10-18 17:18:58.182664+04
119	MetaBillet	0002_auto_20220519_0904	2023-10-18 17:18:58.218707+04
120	MetaBillet	0003_productdirectory	2023-10-18 17:18:58.259242+04
121	QrcodeCashless	0002_alter_detail_img	2023-10-18 17:18:58.275004+04
122	QrcodeCashless	0003_auto_20221101_1820	2023-10-18 17:18:58.390039+04
123	QrcodeCashless	0004_detail_uuid	2023-10-18 17:18:58.401407+04
124	QrcodeCashless	0005_auto_20230103_1240	2023-10-18 17:18:58.470185+04
125	QrcodeCashless	0006_alter_wallet_unique_together	2023-10-18 17:18:58.488952+04
126	QrcodeCashless	0007_alter_wallet_unique_together	2023-10-18 17:18:58.50846+04
127	QrcodeCashless	0008_alter_cartecashless_uuid	2023-10-18 17:18:58.527137+04
128	QrcodeCashless	0009_federatedcashless_syncfederatedlog	2023-10-18 17:18:58.607872+04
129	QrcodeCashless	0010_auto_20230111_0701	2023-10-18 17:18:58.735949+04
130	QrcodeCashless	0011_auto_20230125_1445	2023-10-18 17:18:58.764866+04
131	QrcodeCashless	0012_syncfederatedlog_categorie	2023-10-18 17:18:58.784373+04
132	QrcodeCashless	0013_auto_20230125_1802	2023-10-18 17:18:58.853931+04
133	QrcodeCashless	0014_asset_categorie	2023-10-18 17:18:58.86648+04
134	QrcodeCashless	0015_alter_asset_unique_together	2023-10-18 17:18:58.882331+04
135	QrcodeCashless	0016_detail_slug	2023-10-18 17:18:58.897797+04
136	admin	0001_initial	2023-10-18 17:18:58.941648+04
137	admin	0002_logentry_remove_auto_add	2023-10-18 17:18:58.958816+04
138	admin	0003_logentry_add_action_flag_choices	2023-10-18 17:18:58.978837+04
139	authtoken	0001_initial	2023-10-18 17:18:59.024567+04
140	authtoken	0002_auto_20160226_1747	2023-10-18 17:18:59.107633+04
141	authtoken	0003_tokenproxy	2023-10-18 17:18:59.11368+04
142	root_billet	0001_initial	2023-10-18 17:18:59.117641+04
143	sessions	0001_initial	2023-10-18 17:18:59.122881+04
144	sites	0001_initial	2023-10-18 17:18:59.127032+04
145	sites	0002_alter_domain_unique	2023-10-18 17:18:59.131945+04
146	token_blacklist	0001_initial	2023-10-18 17:18:59.260974+04
147	token_blacklist	0002_outstandingtoken_jti_hex	2023-10-18 17:18:59.277247+04
148	token_blacklist	0003_auto_20171017_2007	2023-10-18 17:18:59.281851+04
149	token_blacklist	0004_auto_20171017_2013	2023-10-18 17:18:59.302753+04
150	token_blacklist	0005_remove_outstandingtoken_jti	2023-10-18 17:18:59.323607+04
151	token_blacklist	0006_auto_20171017_2113	2023-10-18 17:18:59.347319+04
152	token_blacklist	0007_auto_20171017_2214	2023-10-18 17:18:59.410313+04
153	token_blacklist	0008_migrate_to_bigautofield	2023-10-18 17:18:59.45183+04
154	token_blacklist	0010_fix_migrate_to_bigautofield	2023-10-18 17:18:59.500133+04
155	token_blacklist	0011_linearizes_history	2023-10-18 17:18:59.502266+04
156	token_blacklist	0012_alter_outstandingtoken_user	2023-10-18 17:18:59.538979+04
\.


--
-- Data for Name: rest_framework_api_key_apikey; Type: TABLE DATA; Schema: billetistan; Owner: ticket_postgres_user
--

COPY billetistan.rest_framework_api_key_apikey (id, created, name, revoked, expiry_date, hashed_key, prefix) FROM stdin;
\.


--
-- Data for Name: BaseBillet_artist_on_event; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_artist_on_event" (id, datetime, artist_id, event_id) FROM stdin;
1	2024-07-20 17:19:39.023+04	9cfbb542-ccd0-4b41-bb46-8c627a0a7fb9	fec06317-878c-4c6d-9f87-52f1f59831c7
2	2023-12-27 17:19:41.205+04	64d8bfb6-8acb-4ab9-a46d-d2cb7fb6745f	1a8eb214-faab-4cb3-b8a8-ece9b8286fdc
\.


--
-- Data for Name: BaseBillet_configuration; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_configuration" (id, organisation, short_description, long_description, adress, postal_code, city, phone, email, site_web, twitter, facebook, instagram, map_img, carte_restaurant, img, fuseau_horaire, logo, stripe_api_key, stripe_test_api_key, stripe_mode_test, jauge_max, server_cashless, key_cashless, template_billetterie, template_meta, activate_mailjet, email_confirm_template, slug, legal_documents, stripe_connect_account, stripe_connect_account_test, stripe_payouts_enabled, federated_cashless, ghost_key, ghost_last_log, ghost_url, key_fedow, server_fedow) FROM stdin;
1	Demo	Les scènes oniriques du Billetistan	Ah ben ça alors ! Un nouveau lieu dans un espace virtuel !	\N	\N	\N		root@root.root	\N	\N	\N	\N			images/1080_RIUslBa	Indian/Reunion	images/540_SFfRnv6	\N	\N	t	50	https://cashless.filaos.re	LV7OXOpB.PUhWuGQPHt9EmPnKTUeXHZ45lgZPWh6b	arnaud_mvc	html5up-masseively	f	3898061	demo	\N	acct_1M7YYOE0J1b3jXbW	\N	f	f	\N	\N	\N	\N	\N
\.


--
-- Data for Name: BaseBillet_configuration_option_generale_checkbox; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_configuration_option_generale_checkbox" (id, configuration_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_configuration_option_generale_radio; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_configuration_option_generale_radio" (id, configuration_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_event" (uuid, name, slug, datetime, created, short_description, long_description, url_external, published, img, categorie, jauge_max, minimum_cashless_required, max_per_user, is_external, booking) FROM stdin;
fec06317-878c-4c6d-9f87-52f1f59831c7	Réservation non nominative	reservation-non-nominative-240303-1719	2024-03-03 17:19:39.013+04	2023-10-18 17:19:39.088714+04	Lorem ipsum dolor	Lorem ipsum dolor sit amet, consectetur adipiscing elit. Donec ipsum lectus, ultrices vel placerat et, finibus ultricies dolor. Integer facilisis fermentum placerat. Nam malesuada fermentum nunc ac consectetur. Donec velit tortor, feugiat in euismod eu, semper blandit lacus. Nunc ultricies lorem sed libero bibendum, id vestibulum massa lacinia. In hac habitasse platea dictumst. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam interdum lacinia metus, nec rutrum diam congue ut. Phasellus accumsan at leo ac eleifend. Phasellus cursus vitae tortor vestibulum faucibus. Pellentesque dictum libero ut tellus tristique condimentum.	\N	t		LIV	50	0	10	f	f
0f60248a-70b8-4e1d-9d4a-53955b2b3b0c	Mon resto	mon-resto-240723-1719	2024-07-23 17:19:39.207+04	2023-10-18 17:19:40.853465+04	Le plus gouteux des restaurants ;0)	Lorem ipsum dolor sit amet, consectetur adipiscing elit. Donec ipsum lectus, ultrices vel placerat et, finibus ultricies dolor. Integer facilisis fermentum placerat. Nam malesuada fermentum nunc ac consectetur. Donec velit tortor, feugiat in euismod eu, semper blandit lacus. Nunc ultricies lorem sed libero bibendum, id vestibulum massa lacinia. In hac habitasse platea dictumst. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam interdum lacinia metus, nec rutrum diam congue ut. Phasellus accumsan at leo ac eleifend. Phasellus cursus vitae tortor vestibulum faucibus. Pellentesque dictum libero ut tellus tristique condimentum.	\N	t	images/1080_FpBrpRF	LIV	50	0	10	f	f
1a8eb214-faab-4cb3-b8a8-ece9b8286fdc	Balaphonik Sound System	balaphonik-sound-system-240503-1719	2024-05-03 17:19:41.205+04	2023-10-18 17:19:41.257641+04	Courte description	Lorem ipsum dolor sit amet, consectetur adipiscing elit. Donec ipsum lectus, ultrices vel placerat et, finibus ultricies dolor. Integer facilisis fermentum placerat. Nam malesuada fermentum nunc ac consectetur. Donec velit tortor, feugiat in euismod eu, semper blandit lacus. Nunc ultricies lorem sed libero bibendum, id vestibulum massa lacinia. In hac habitasse platea dictumst. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam interdum lacinia metus, nec rutrum diam congue ut. Phasellus accumsan at leo ac eleifend. Phasellus cursus vitae tortor vestibulum faucibus. Pellentesque dictum libero ut tellus tristique condimentum.	\N	t		LIV	50	0	10	f	f
2ff701f8-ece7-4b30-aa15-b4ec444a6a73	Scène ouverte 1	scene-ouverte-1-231209-1719	2023-12-09 17:19:41.399+04	2023-10-18 17:19:43.535213+04	Viens jouer avec tes potes !	Lorem ipsum dolor sit amet, consectetur adipiscing elit. Donec ipsum lectus, ultrices vel placerat et, finibus ultricies dolor. Integer facilisis fermentum placerat. Nam malesuada fermentum nunc ac consectetur. Donec velit tortor, feugiat in euismod eu, semper blandit lacus. Nunc ultricies lorem sed libero bibendum, id vestibulum massa lacinia. In hac habitasse platea dictumst. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam interdum lacinia metus, nec rutrum diam congue ut. Phasellus accumsan at leo ac eleifend. Phasellus cursus vitae tortor vestibulum faucibus. Pellentesque dictum libero ut tellus tristique condimentum.	\N	t	images/1080_v39ZV53	LIV	50	0	10	f	f
1c575377-74bb-4321-8f37-6d996f4205da	Scène ouverte 2	scene-ouverte-2-240519-1719	2024-05-19 17:19:43.937+04	2023-10-18 17:19:46.406767+04	Viens jouer avec tes potes !	Lorem ipsum dolor sit amet, consectetur adipiscing elit. Donec ipsum lectus, ultrices vel placerat et, finibus ultricies dolor. Integer facilisis fermentum placerat. Nam malesuada fermentum nunc ac consectetur. Donec velit tortor, feugiat in euismod eu, semper blandit lacus. Nunc ultricies lorem sed libero bibendum, id vestibulum massa lacinia. In hac habitasse platea dictumst. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam interdum lacinia metus, nec rutrum diam congue ut. Phasellus accumsan at leo ac eleifend. Phasellus cursus vitae tortor vestibulum faucibus. Pellentesque dictum libero ut tellus tristique condimentum.	\N	t	images/1080_SVDNjws	LIV	50	0	10	f	f
\.


--
-- Data for Name: BaseBillet_event_options_checkbox; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_event_options_checkbox" (id, event_id, optiongenerale_id) FROM stdin;
1	1a8eb214-faab-4cb3-b8a8-ece9b8286fdc	5c5f408b-2856-407f-886b-b44eb00ba66e
2	1a8eb214-faab-4cb3-b8a8-ece9b8286fdc	2a021db2-5711-496d-893f-631281a60e37
3	2ff701f8-ece7-4b30-aa15-b4ec444a6a73	0124dcd2-6518-4a20-a04e-5dde6c37f87d
4	2ff701f8-ece7-4b30-aa15-b4ec444a6a73	c84c923c-b976-44b8-a575-97ed926f9764
5	1c575377-74bb-4321-8f37-6d996f4205da	0124dcd2-6518-4a20-a04e-5dde6c37f87d
6	1c575377-74bb-4321-8f37-6d996f4205da	c84c923c-b976-44b8-a575-97ed926f9764
\.


--
-- Data for Name: BaseBillet_event_options_radio; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_event_options_radio" (id, event_id, optiongenerale_id) FROM stdin;
1	1a8eb214-faab-4cb3-b8a8-ece9b8286fdc	1867cd45-e2e6-4688-b4cb-63c5094e6467
2	1a8eb214-faab-4cb3-b8a8-ece9b8286fdc	041b0346-6e51-4197-b52c-c937cad4505f
3	2ff701f8-ece7-4b30-aa15-b4ec444a6a73	1867cd45-e2e6-4688-b4cb-63c5094e6467
4	2ff701f8-ece7-4b30-aa15-b4ec444a6a73	041b0346-6e51-4197-b52c-c937cad4505f
5	1c575377-74bb-4321-8f37-6d996f4205da	1867cd45-e2e6-4688-b4cb-63c5094e6467
\.


--
-- Data for Name: BaseBillet_event_products; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_event_products" (id, event_id, product_id) FROM stdin;
1	fec06317-878c-4c6d-9f87-52f1f59831c7	d3c695c4-c011-419e-a539-71b900b09851
2	fec06317-878c-4c6d-9f87-52f1f59831c7	967af67f-7185-4434-b55d-c56edc66e8a0
3	fec06317-878c-4c6d-9f87-52f1f59831c7	98379f43-c8e4-4ffb-b9d8-f64ec89fc7a8
4	fec06317-878c-4c6d-9f87-52f1f59831c7	307407d0-91e8-4141-978c-871a1b47605f
5	0f60248a-70b8-4e1d-9d4a-53955b2b3b0c	11020bca-228a-4e47-ac9e-3cee684dcfad
6	0f60248a-70b8-4e1d-9d4a-53955b2b3b0c	98379f43-c8e4-4ffb-b9d8-f64ec89fc7a8
7	0f60248a-70b8-4e1d-9d4a-53955b2b3b0c	307407d0-91e8-4141-978c-871a1b47605f
8	1a8eb214-faab-4cb3-b8a8-ece9b8286fdc	bf47054a-2bc1-4a4a-873f-8379716705df
9	1a8eb214-faab-4cb3-b8a8-ece9b8286fdc	bd6a5d99-402a-4d4c-a83f-b0fe1b165028
10	1a8eb214-faab-4cb3-b8a8-ece9b8286fdc	98379f43-c8e4-4ffb-b9d8-f64ec89fc7a8
11	1a8eb214-faab-4cb3-b8a8-ece9b8286fdc	307407d0-91e8-4141-978c-871a1b47605f
\.


--
-- Data for Name: BaseBillet_event_recurrent; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_event_recurrent" (id, event_id, weekday_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_tag; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_event_tag" (id, event_id, tag_id) FROM stdin;
1	fec06317-878c-4c6d-9f87-52f1f59831c7	df5c3d38-2f1e-40c8-94d9-4bf8d682f1b6
2	0f60248a-70b8-4e1d-9d4a-53955b2b3b0c	9285df87-d299-49be-bba8-b75071dd78a7
3	1a8eb214-faab-4cb3-b8a8-ece9b8286fdc	0e494bdd-ec5f-43ef-b8f9-534502461bab
4	1a8eb214-faab-4cb3-b8a8-ece9b8286fdc	c73ff329-4870-4df1-b3cc-5e594ed8b914
5	1a8eb214-faab-4cb3-b8a8-ece9b8286fdc	4289f89c-34df-4bc1-a00c-deac0eea19c4
6	2ff701f8-ece7-4b30-aa15-b4ec444a6a73	1f0b4275-adcd-4b86-a0cd-0bdf1a414b24
7	1c575377-74bb-4321-8f37-6d996f4205da	34bd78fc-82db-4471-a169-c31ce43995d2
8	1c575377-74bb-4321-8f37-6d996f4205da	4289f89c-34df-4bc1-a00c-deac0eea19c4
\.


--
-- Data for Name: BaseBillet_externalapikey; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_externalapikey" (id, ip, revoquer_apikey, created, name, event, product, artist, place, user_id, reservation, ticket, key_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_lignearticle; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_lignearticle" (uuid, datetime, qty, status, carte_id, paiement_stripe_id, pricesold_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_membership; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_membership" (id, date_added, first_contribution, last_contribution, contribution_value, last_action, first_name, last_name, pseudo, newsletter, postal_code, birth_date, phone, commentaire, user_id, price_id, stripe_id_subscription, last_stripe_invoice, status) FROM stdin;
\.


--
-- Data for Name: BaseBillet_membership_option_generale; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_membership_option_generale" (id, membership_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_optiongenerale; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_optiongenerale" (uuid, name, poids, description) FROM stdin;
18b0a432-03df-4f82-8dc6-044996520627	optionAdhesionRadio1	2	\N
80149104-83e0-411e-8f70-f1c38b97a57a	optionAdhesionRadio2	3	\N
1867cd45-e2e6-4688-b4cb-63c5094e6467	Balcon	4	\N
041b0346-6e51-4197-b52c-c937cad4505f	Fosse	5	\N
0124dcd2-6518-4a20-a04e-5dde6c37f87d	Vegétarien	6	\N
c84c923c-b976-44b8-a575-97ed926f9764	Vegan	7	\N
40b015ec-23e4-48f7-b336-0fe40c5c5f59	Membre actif	8	\N
5c5f408b-2856-407f-886b-b44eb00ba66e	eventOptionCheckbox2	9	\N
2a021db2-5711-496d-893f-631281a60e37	eventOptionCheckbox3	10	\N
266e9c57-a99c-462e-b40d-69a91aaee060	eventOptionRadio1	11	\N
bb6b932c-d828-4b4e-be16-3a495a89662a	eventOptionRadio2	12	\N
d1f6af91-c10e-4913-ae38-f48c138b9280	eventOptionRadio3	13	\N
\.


--
-- Data for Name: BaseBillet_paiement_stripe; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_paiement_stripe" (uuid, detail, datetime, checkout_session_id_stripe, payment_intent_id, metadata_stripe, order_date, last_action, status, traitement_en_cours, source_traitement, source, total, reservation_id, user_id, customer_stripe, invoice_stripe, subscription) FROM stdin;
\.


--
-- Data for Name: BaseBillet_price; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_price" (uuid, name, prix, vat, stock, max_per_user, product_id, adhesion_obligatoire_id, long_description, short_description, subscription_type, recurring_payment) FROM stdin;
8778a6eb-d91e-49ff-a82e-7af372b83f0e	Plein tarif - Maximum 6 personnes	20.00	NA	30	6	11020bca-228a-4e47-ac9e-3cee684dcfad	\N	\N	\N	N	f
646f96ec-abc1-42e5-bd4f-2bf696056dcc	Tarif associatif - Maximum 1 personnes	5.00	NA	10	1	11020bca-228a-4e47-ac9e-3cee684dcfad	df782241-b649-4c7c-9127-60769c7ee646	\N	\N	N	f
c767adbd-6ec1-4fe3-a32a-39631873784c	Tarif unique	12.00	NA	6	1	647f0e6e-c302-440d-9c7c-17ffa2752178	\N	\N	\N	N	f
021797c6-eaa7-4ad1-bd53-d4d6853cf7ae	Tarif associatif	5.00	NA	12	2	d3c695c4-c011-419e-a539-71b900b09851	dd3c8bee-4d23-4709-8b2f-241dbae0c438	\N	\N	N	f
64dbceea-49f1-430b-b064-e9bbce95b64f	Plein tarif	15.00	NA	20	1	d3c695c4-c011-419e-a539-71b900b09851	\N	\N	\N	N	f
9a3dc304-8f16-4d63-bce2-cc246606f37a	Petit prix	3.00	NA	3	6	967af67f-7185-4434-b55d-c56edc66e8a0	\N	\N	\N	N	f
9aa14a06-0648-4742-b51d-70f1914b9cfe	Tarif associatif	5.00	NA	5	1	bf47054a-2bc1-4a4a-873f-8379716705df	dd3c8bee-4d23-4709-8b2f-241dbae0c438	\N	\N	N	f
b21e0842-4fc2-4b3b-9e30-eb727f4101fb	Demi Tarif	5.00	NA	4	10	bf47054a-2bc1-4a4a-873f-8379716705df	\N	\N	\N	N	f
38fe9e82-f3b4-4f51-abee-d83d52f87cb9	Plein Tarif	10.00	NA	100	10	bf47054a-2bc1-4a4a-873f-8379716705df	\N	\N	\N	N	f
7f9f6125-312e-465f-bc8f-4de7730e39a9	Plein Tarif	45.00	NA	100	5	bd6a5d99-402a-4d4c-a83f-b0fe1b165028	\N	\N	\N	N	f
44cf8ba2-be16-496d-993d-5e9dc2441bda	L	25.00	NA	30	10	d3160bae-7cb0-4f0d-bbd0-7ef5d4bb93dd	\N	Un tshirt L !	Taille L	N	f
6ea89fca-941b-46df-8e7f-e8a38a7a55c7	Plein Tarif	20.00	NA	\N	10	dd3c8bee-4d23-4709-8b2f-241dbae0c438	\N	\N	\N	Y	f
fab316a6-f786-4302-ac97-ed0bdf9a78be	Tarif solidaire	10.00	NA	\N	10	dd3c8bee-4d23-4709-8b2f-241dbae0c438	\N	\N	\N	Y	f
9c8d06f6-2a1a-4b2e-9911-e55b32f4fb5f	récurente par mois	2.00	NA	\N	10	dd3c8bee-4d23-4709-8b2f-241dbae0c438	\N	\N	\N	M	t
1116545b-6fe2-4dc1-bf72-472eb66e9d52	Amap A l'année	360.00	NA	\N	10	c229d845-d14d-4cc8-99fc-fcf897cefe2d	\N	\N	Payez pour un an.	Y	f
9931174c-8930-498a-8e50-c3ac82ff060f	Amap par mois	30.00	NA	\N	10	c229d845-d14d-4cc8-99fc-fcf897cefe2d	\N	\N	Payez au mois	M	t
09a48cbf-6943-4604-a86d-02b07c87a6ae	Par mois	16.00	NA	\N	10	df782241-b649-4c7c-9127-60769c7ee646	\N	\N	Payez au mois	M	t
bd9e374d-cdff-41e3-bdd2-9a0e22e2c9e6	Recharge	1.00	NA	10001	1000	98379f43-c8e4-4ffb-b9d8-f64ec89fc7a8	\N	\N	Recharge	N	f
f3142426-e5de-4c22-8077-3a7290eac68d	Coopérative TiBillet	1.00	NA	\N	10	307407d0-91e8-4141-978c-871a1b47605f	\N	\N	\N	N	f
\.


--
-- Data for Name: BaseBillet_pricesold; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_pricesold" (uuid, id_price_stripe, qty_solded, prix, price_id, productsold_id, gift) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_product" (uuid, name, publish, img, categorie_article, long_description, short_description, terms_and_conditions_document, send_to_cashless, poids, archive, legal_link, nominative) FROM stdin;
dd3c8bee-4d23-4709-8b2f-241dbae0c438	Adhésion Associative	t	images/540_VYTXjSv	A	Scannez votre carte et vous verrez l'agenda du lieu et ses besoins en volontariat !	Une adhésion qui sera visible sur une carte de membre rechargeable en monnaie locale.	\N	t	2	f	\N	t
98379f43-c8e4-4ffb-b9d8-f64ec89fc7a8	Recharge cashless	t	images/540_zt0PTVv	S	\N	\N	\N	f	3	f	\N	t
df782241-b649-4c7c-9127-60769c7ee646	Abonnement AMAC	t	images/540_ijEVgpc	A	Soutenez les conditions de la crétion artistique en s'abonnant à l'Amac et bénéficiez de réduction sur tout les évènements.	Association pour le maintient d'une activité culturelle	\N	f	4	f	\N	t
c229d845-d14d-4cc8-99fc-fcf897cefe2d	Abonnement AMAP	t	images/540_FcdKzVB	A	\N	Association pour le maintient d'une activité paysanne	\N	f	5	f	\N	t
d3c695c4-c011-419e-a539-71b900b09851	Reservation non nominative	t	images/540_yVK1O1X	B	\N	\N	\N	f	6	f	\N	f
967af67f-7185-4434-b55d-c56edc66e8a0	Billet non nominatif	t	images/540_n8KyffD	B	\N	\N	\N	f	7	f	\N	f
11020bca-228a-4e47-ac9e-3cee684dcfad	Reserver une table	t	images/540_R86bAeq	B	\N	\N	\N	f	8	f	\N	f
bf47054a-2bc1-4a4a-873f-8379716705df	Billet	t	images/540_nhUEWkO	B	\N	\N	\N	f	9	f	\N	t
bd6a5d99-402a-4d4c-a83f-b0fe1b165028	Pass Weekend	t	images/540_UbGr7gj	B	\N	\N	\N	f	10	f	\N	t
d3160bae-7cb0-4f0d-bbd0-7ef5d4bb93dd	Tshirt	t	images/540_t54zq5a	T	\N	\N	\N	f	11	f	\N	t
647f0e6e-c302-440d-9c7c-17ffa2752178	Repas	f	images/540_nJQEFxD	B	\N	\N	\N	f	12	f	\N	t
307407d0-91e8-4141-978c-871a1b47605f	Don pour la coopérative	t		D	\N	\N	\N	f	13	f	\N	t
\.


--
-- Data for Name: BaseBillet_product_option_generale_checkbox; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_product_option_generale_checkbox" (id, product_id, optiongenerale_id) FROM stdin;
1	dd3c8bee-4d23-4709-8b2f-241dbae0c438	40b015ec-23e4-48f7-b336-0fe40c5c5f59
2	c229d845-d14d-4cc8-99fc-fcf897cefe2d	40b015ec-23e4-48f7-b336-0fe40c5c5f59
\.


--
-- Data for Name: BaseBillet_product_option_generale_radio; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_product_option_generale_radio" (id, product_id, optiongenerale_id) FROM stdin;
1	dd3c8bee-4d23-4709-8b2f-241dbae0c438	d1f6af91-c10e-4913-ae38-f48c138b9280
2	dd3c8bee-4d23-4709-8b2f-241dbae0c438	bb6b932c-d828-4b4e-be16-3a495a89662a
3	dd3c8bee-4d23-4709-8b2f-241dbae0c438	266e9c57-a99c-462e-b40d-69a91aaee060
4	c229d845-d14d-4cc8-99fc-fcf897cefe2d	18b0a432-03df-4f82-8dc6-044996520627
5	c229d845-d14d-4cc8-99fc-fcf897cefe2d	80149104-83e0-411e-8f70-f1c38b97a57a
\.


--
-- Data for Name: BaseBillet_product_tag; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_product_tag" (id, product_id, tag_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_productsold; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_productsold" (uuid, id_product_stripe, event_id, product_id, categorie_article) FROM stdin;
\.


--
-- Data for Name: BaseBillet_reservation; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_reservation" (uuid, datetime, status, to_mail, mail_send, mail_error, event_id, user_commande_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_reservation_options; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_reservation_options" (id, reservation_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_tag; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_tag" (uuid, name, color) FROM stdin;
df5c3d38-2f1e-40c8-94d9-4bf8d682f1b6	test2	#000000
9285df87-d299-49be-bba8-b75071dd78a7	goutu	#000000
0e494bdd-ec5f-43ef-b8f9-534502461bab	cool	#000000
c73ff329-4870-4df1-b3cc-5e594ed8b914	balaise	#000000
4289f89c-34df-4bc1-a00c-deac0eea19c4	original	#000000
1f0b4275-adcd-4b86-a0cd-0bdf1a414b24	test	#000000
34bd78fc-82db-4471-a169-c31ce43995d2	test3	#000000
\.


--
-- Data for Name: BaseBillet_ticket; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_ticket" (uuid, first_name, last_name, status, seat, pricesold_id, reservation_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_webhook; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_webhook" (id, url, event, active, last_response) FROM stdin;
\.


--
-- Data for Name: BaseBillet_weekday; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo."BaseBillet_weekday" (id, day) FROM stdin;
1	0
2	1
3	2
4	3
5	4
6	5
7	6
\.


--
-- Data for Name: django_content_type; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo.django_content_type (id, app_label, model) FROM stdin;
1	Customers	client
2	Customers	domain
3	contenttypes	contenttype
4	auth	permission
5	auth	group
6	AuthBillet	tibilletuser
7	AuthBillet	humanuser
8	AuthBillet	superhumanuser
9	AuthBillet	termuser
10	AuthBillet	terminalpairingtoken
11	QrcodeCashless	detail
12	QrcodeCashless	cartecashless
13	QrcodeCashless	asset
14	QrcodeCashless	wallet
15	QrcodeCashless	syncfederatedlog
16	QrcodeCashless	federatedcashless
17	authtoken	token
18	authtoken	tokenproxy
19	token_blacklist	blacklistedtoken
20	token_blacklist	outstandingtoken
21	sessions	session
22	sites	site
23	admin	logentry
24	MetaBillet	eventdirectory
25	MetaBillet	productdirectory
26	root_billet	rootconfiguration
27	rest_framework_api_key	apikey
28	BaseBillet	event
29	BaseBillet	optiongenerale
30	BaseBillet	price
31	BaseBillet	pricesold
32	BaseBillet	product
33	BaseBillet	reservation
34	BaseBillet	ticket
35	BaseBillet	productsold
36	BaseBillet	paiement_stripe
37	BaseBillet	membership
38	BaseBillet	lignearticle
39	BaseBillet	configuration
40	BaseBillet	artist_on_event
41	BaseBillet	webhook
42	BaseBillet	externalapikey
43	BaseBillet	tag
44	BaseBillet	weekday
\.


--
-- Data for Name: django_migrations; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo.django_migrations (id, app, name, applied) FROM stdin;
1	contenttypes	0001_initial	2023-10-18 17:18:42.260292+04
2	contenttypes	0002_remove_content_type_name	2023-10-18 17:18:42.282397+04
3	auth	0001_initial	2023-10-18 17:18:42.349567+04
4	auth	0002_alter_permission_name_max_length	2023-10-18 17:18:42.354048+04
5	auth	0003_alter_user_email_max_length	2023-10-18 17:18:42.358981+04
6	auth	0004_alter_user_username_opts	2023-10-18 17:18:42.363986+04
7	auth	0005_alter_user_last_login_null	2023-10-18 17:18:42.371055+04
8	auth	0006_require_contenttypes_0002	2023-10-18 17:18:42.37309+04
9	auth	0007_alter_validators_add_error_messages	2023-10-18 17:18:42.38053+04
10	auth	0008_alter_user_username_max_length	2023-10-18 17:18:42.388456+04
11	auth	0009_alter_user_last_name_max_length	2023-10-18 17:18:42.393976+04
12	auth	0010_alter_group_name_max_length	2023-10-18 17:18:42.401869+04
13	auth	0011_update_proxy_permissions	2023-10-18 17:18:42.405065+04
14	auth	0012_alter_user_first_name_max_length	2023-10-18 17:18:42.413696+04
15	Customers	0001_initial	2023-10-18 17:18:42.419877+04
16	AuthBillet	0001_initial	2023-10-18 17:18:42.436047+04
17	AuthBillet	0002_alter_tibilletuser_is_active	2023-10-18 17:18:42.446629+04
18	AuthBillet	0003_tibilletuser_user_parent_pk	2023-10-18 17:18:42.456562+04
19	AuthBillet	0004_terminalpairingtoken	2023-10-18 17:18:42.469528+04
20	AuthBillet	0005_auto_20220422_1601	2023-10-18 17:18:42.509096+04
21	AuthBillet	0006_terminalpairingtoken_used	2023-10-18 17:18:42.521146+04
22	AuthBillet	0007_alter_terminalpairingtoken_datetime	2023-10-18 17:18:42.53265+04
23	AuthBillet	0008_alter_terminalpairingtoken_datetime	2023-10-18 17:18:42.545834+04
24	AuthBillet	0009_alter_tibilletuser_is_active	2023-10-18 17:18:42.559903+04
25	rest_framework_api_key	0001_initial	2023-10-18 17:18:42.583554+04
26	rest_framework_api_key	0002_auto_20190529_2243	2023-10-18 17:18:42.605929+04
27	rest_framework_api_key	0003_auto_20190623_1952	2023-10-18 17:18:42.612726+04
28	rest_framework_api_key	0004_prefix_hashed_key	2023-10-18 17:18:42.649813+04
29	rest_framework_api_key	0005_auto_20220110_1102	2023-10-18 17:18:42.656118+04
30	QrcodeCashless	0001_initial	2023-10-18 17:18:42.682969+04
31	BaseBillet	0001_initial	2023-10-18 17:18:43.451145+04
32	BaseBillet	0002_alter_ticket_seat	2023-10-18 17:18:43.485845+04
33	BaseBillet	0003_alter_reservation_user_commande	2023-10-18 17:18:43.516042+04
34	BaseBillet	0004_auto_20220421_1129	2023-10-18 17:18:43.548248+04
35	BaseBillet	0005_alter_reservation_status	2023-10-18 17:18:43.571044+04
36	BaseBillet	0006_auto_20220428_1533	2023-10-18 17:18:43.593197+04
37	BaseBillet	0007_alter_configuration_img	2023-10-18 17:18:43.605315+04
38	BaseBillet	0008_auto_20220505_1520	2023-10-18 17:18:43.630229+04
39	BaseBillet	0009_configuration_slug	2023-10-18 17:18:43.655741+04
40	BaseBillet	0010_auto_20220531_0920	2023-10-18 17:18:43.722918+04
41	BaseBillet	0011_membership_price	2023-10-18 17:18:43.75418+04
42	BaseBillet	0012_configuration_legal_documents	2023-10-18 17:18:43.76979+04
43	BaseBillet	0013_auto_20220602_1013	2023-10-18 17:18:43.870535+04
44	BaseBillet	0014_product_terms_and_conditions_document	2023-10-18 17:18:43.878547+04
45	BaseBillet	0015_price_subscription_type	2023-10-18 17:18:43.889307+04
46	BaseBillet	0016_alter_membership_unique_together	2023-10-18 17:18:43.97412+04
47	BaseBillet	0017_product_send_to_cashless	2023-10-18 17:18:43.983534+04
48	BaseBillet	0018_auto_20220608_1607	2023-10-18 17:18:44.004252+04
49	BaseBillet	0019_auto_20220624_0726	2023-10-18 17:18:44.036318+04
50	BaseBillet	0020_membership_stripe_id_subscription	2023-10-18 17:18:44.054261+04
51	BaseBillet	0021_paiement_stripe_invoice_stripe	2023-10-18 17:18:44.07397+04
52	BaseBillet	0022_paiement_stripe_subscription	2023-10-18 17:18:44.093721+04
53	BaseBillet	0023_membership_last_stripe_invoice	2023-10-18 17:18:44.110494+04
54	BaseBillet	0024_auto_20220626_1257	2023-10-18 17:18:44.159901+04
55	BaseBillet	0025_auto_20220810_1245	2023-10-18 17:18:44.182477+04
56	BaseBillet	0026_alter_configuration_slug	2023-10-18 17:18:44.199962+04
57	BaseBillet	0027_product_poids	2023-10-18 17:18:44.211121+04
58	BaseBillet	0028_auto_20220826_1559	2023-10-18 17:18:44.385746+04
59	BaseBillet	0029_remove_configuration_activer_billetterie	2023-10-18 17:18:44.470085+04
60	BaseBillet	0030_auto_20220927_1855	2023-10-18 17:18:44.516129+04
61	BaseBillet	0031_apikey	2023-10-18 17:18:44.545423+04
62	BaseBillet	0032_apikey_created	2023-10-18 17:18:44.552708+04
63	BaseBillet	0033_apikey_name	2023-10-18 17:18:44.568828+04
64	BaseBillet	0034_apikey_auth	2023-10-18 17:18:44.575284+04
65	BaseBillet	0035_alter_apikey_auth	2023-10-18 17:18:44.581288+04
66	BaseBillet	0036_remove_apikey_auth	2023-10-18 17:18:44.588343+04
67	BaseBillet	0037_auto_20221017_1320	2023-10-18 17:18:44.602733+04
68	BaseBillet	0038_apikey_product	2023-10-18 17:18:44.608949+04
69	BaseBillet	0039_auto_20221017_1402	2023-10-18 17:18:44.624406+04
70	BaseBillet	0040_apikey_user	2023-10-18 17:18:44.660113+04
71	BaseBillet	0041_auto_20221018_0932	2023-10-18 17:18:44.69495+04
72	BaseBillet	0042_webhook	2023-10-18 17:18:44.70535+04
73	BaseBillet	0043_webhook_active	2023-10-18 17:18:44.713425+04
74	BaseBillet	0044_webhook_last_response	2023-10-18 17:18:44.723493+04
75	BaseBillet	0045_auto_20221021_1031	2023-10-18 17:18:44.749234+04
76	BaseBillet	0046_alter_product_categorie_article	2023-10-18 17:18:44.783394+04
77	BaseBillet	0047_auto_20221121_1256	2023-10-18 17:18:44.806115+04
78	BaseBillet	0048_configuration_stripe_payouts_enabled	2023-10-18 17:18:44.820438+04
79	BaseBillet	0049_rename_apikey_externalapikey	2023-10-18 17:18:44.863341+04
80	BaseBillet	0050_alter_externalapikey_options	2023-10-18 17:18:44.87869+04
81	BaseBillet	0051_auto_20221125_1847	2023-10-18 17:18:44.925639+04
82	BaseBillet	0052_externalapikey_key	2023-10-18 17:18:44.970317+04
83	BaseBillet	0053_alter_externalapikey_options	2023-10-18 17:18:44.995368+04
84	BaseBillet	0054_price_recurring_payment	2023-10-18 17:18:45.009652+04
85	BaseBillet	0055_auto_20221215_1922	2023-10-18 17:18:45.097357+04
86	BaseBillet	0056_pricesold_gift	2023-10-18 17:18:45.115806+04
87	BaseBillet	0057_auto_20230102_1847	2023-10-18 17:18:45.164808+04
88	BaseBillet	0058_alter_paiement_stripe_status	2023-10-18 17:18:45.204796+04
89	BaseBillet	0059_event_cashless	2023-10-18 17:18:45.291069+04
90	BaseBillet	0060_event_minimum_cashless_required	2023-10-18 17:18:45.304131+04
91	BaseBillet	0061_configuration_federated_cashless	2023-10-18 17:18:45.315699+04
92	BaseBillet	0062_remove_configuration_mollie_api_key	2023-10-18 17:18:45.329278+04
93	BaseBillet	0063_auto_20230427_1105	2023-10-18 17:18:46.144094+04
94	BaseBillet	0064_auto_20230427_1146	2023-10-18 17:18:46.217967+04
95	BaseBillet	0065_auto_20230427_1248	2023-10-18 17:18:46.323172+04
96	BaseBillet	0066_optiongenerale_description	2023-10-18 17:18:46.337628+04
97	BaseBillet	0067_auto_20230427_1410	2023-10-18 17:18:46.445966+04
98	BaseBillet	0068_auto_20230427_1826	2023-10-18 17:18:46.487634+04
99	BaseBillet	0069_alter_optiongenerale_options	2023-10-18 17:18:46.503736+04
100	BaseBillet	0070_alter_configuration_short_description	2023-10-18 17:18:46.597323+04
101	BaseBillet	0071_event_tag	2023-10-18 17:18:46.649705+04
102	BaseBillet	0072_auto_20230522_1614	2023-10-18 17:18:46.700647+04
103	BaseBillet	0073_auto_20230523_1411	2023-10-18 17:18:46.72694+04
104	BaseBillet	0074_auto_20230523_1548	2023-10-18 17:18:46.90883+04
105	BaseBillet	0075_auto_20230524_1706	2023-10-18 17:18:46.968506+04
106	BaseBillet	0076_auto_20230525_1315	2023-10-18 17:18:46.99573+04
107	BaseBillet	0077_auto_20230525_1409	2023-10-18 17:18:47.105509+04
108	BaseBillet	0078_auto_20230602_1441	2023-10-18 17:18:47.14065+04
109	BaseBillet	0079_auto_20230822_0932	2023-10-18 17:18:47.190561+04
110	BaseBillet	0080_productsold_categorie_article	2023-10-18 17:18:47.209148+04
111	BaseBillet	0081_auto_20230822_1459	2023-10-18 17:18:47.241415+04
112	BaseBillet	0082_auto_20230906_1231	2023-10-18 17:18:47.312143+04
113	BaseBillet	0083_auto_20230906_1237	2023-10-18 17:18:47.359951+04
114	BaseBillet	0084_auto_20230906_1243	2023-10-18 17:18:47.407739+04
115	BaseBillet	0085_auto_20230908_1409	2023-10-18 17:18:47.49592+04
116	BaseBillet	0086_auto_20230908_1410	2023-10-18 17:18:47.547815+04
117	Customers	0002_alter_client_categorie	2023-10-18 17:18:47.647408+04
118	MetaBillet	0001_initial	2023-10-18 17:18:47.651284+04
119	MetaBillet	0002_auto_20220519_0904	2023-10-18 17:18:47.682064+04
120	MetaBillet	0003_productdirectory	2023-10-18 17:18:47.717112+04
121	QrcodeCashless	0002_alter_detail_img	2023-10-18 17:18:47.729693+04
122	QrcodeCashless	0003_auto_20221101_1820	2023-10-18 17:18:47.842848+04
123	QrcodeCashless	0004_detail_uuid	2023-10-18 17:18:47.853823+04
124	QrcodeCashless	0005_auto_20230103_1240	2023-10-18 17:18:47.921228+04
125	QrcodeCashless	0006_alter_wallet_unique_together	2023-10-18 17:18:47.941172+04
126	QrcodeCashless	0007_alter_wallet_unique_together	2023-10-18 17:18:47.961467+04
127	QrcodeCashless	0008_alter_cartecashless_uuid	2023-10-18 17:18:47.979061+04
128	QrcodeCashless	0009_federatedcashless_syncfederatedlog	2023-10-18 17:18:48.108197+04
129	QrcodeCashless	0010_auto_20230111_0701	2023-10-18 17:18:48.157053+04
130	QrcodeCashless	0011_auto_20230125_1445	2023-10-18 17:18:48.187842+04
131	QrcodeCashless	0012_syncfederatedlog_categorie	2023-10-18 17:18:48.207509+04
132	QrcodeCashless	0013_auto_20230125_1802	2023-10-18 17:18:48.279894+04
133	QrcodeCashless	0014_asset_categorie	2023-10-18 17:18:48.297115+04
134	QrcodeCashless	0015_alter_asset_unique_together	2023-10-18 17:18:48.30911+04
135	QrcodeCashless	0016_detail_slug	2023-10-18 17:18:48.326824+04
136	admin	0001_initial	2023-10-18 17:18:48.369545+04
137	admin	0002_logentry_remove_auto_add	2023-10-18 17:18:48.386929+04
138	admin	0003_logentry_add_action_flag_choices	2023-10-18 17:18:48.403215+04
139	authtoken	0001_initial	2023-10-18 17:18:48.441998+04
140	authtoken	0002_auto_20160226_1747	2023-10-18 17:18:48.526448+04
141	authtoken	0003_tokenproxy	2023-10-18 17:18:48.530323+04
142	root_billet	0001_initial	2023-10-18 17:18:48.533594+04
143	sessions	0001_initial	2023-10-18 17:18:48.53872+04
144	sites	0001_initial	2023-10-18 17:18:48.544077+04
145	sites	0002_alter_domain_unique	2023-10-18 17:18:48.552729+04
146	token_blacklist	0001_initial	2023-10-18 17:18:48.703922+04
147	token_blacklist	0002_outstandingtoken_jti_hex	2023-10-18 17:18:48.723272+04
148	token_blacklist	0003_auto_20171017_2007	2023-10-18 17:18:48.728549+04
149	token_blacklist	0004_auto_20171017_2013	2023-10-18 17:18:48.757001+04
150	token_blacklist	0005_remove_outstandingtoken_jti	2023-10-18 17:18:48.780898+04
151	token_blacklist	0006_auto_20171017_2113	2023-10-18 17:18:48.802092+04
152	token_blacklist	0007_auto_20171017_2214	2023-10-18 17:18:48.860646+04
153	token_blacklist	0008_migrate_to_bigautofield	2023-10-18 17:18:48.904507+04
154	token_blacklist	0010_fix_migrate_to_bigautofield	2023-10-18 17:18:48.951302+04
155	token_blacklist	0011_linearizes_history	2023-10-18 17:18:48.954038+04
156	token_blacklist	0012_alter_outstandingtoken_user	2023-10-18 17:18:48.991405+04
\.


--
-- Data for Name: rest_framework_api_key_apikey; Type: TABLE DATA; Schema: demo; Owner: ticket_postgres_user
--

COPY demo.rest_framework_api_key_apikey (id, created, name, revoked, expiry_date, hashed_key, prefix) FROM stdin;
\.


--
-- Data for Name: BaseBillet_artist_on_event; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_artist_on_event" (id, datetime, artist_id, event_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_configuration; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_configuration" (id, organisation, short_description, long_description, adress, postal_code, city, phone, email, site_web, twitter, facebook, instagram, map_img, carte_restaurant, img, fuseau_horaire, logo, stripe_api_key, stripe_test_api_key, stripe_mode_test, jauge_max, server_cashless, key_cashless, template_billetterie, template_meta, activate_mailjet, email_confirm_template, slug, legal_documents, stripe_connect_account, stripe_connect_account_test, stripe_payouts_enabled, federated_cashless, ghost_key, ghost_last_log, ghost_url, key_fedow, server_fedow) FROM stdin;
1		\N	\N	\N	\N	\N			\N	\N	\N	\N				Indian/Reunion		\N	\N	t	50	\N	\N	arnaud_mvc	html5up-masseively	f	3898061		\N	\N	\N	f	f	\N	\N	\N	\N	\N
\.


--
-- Data for Name: BaseBillet_configuration_option_generale_checkbox; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_configuration_option_generale_checkbox" (id, configuration_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_configuration_option_generale_radio; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_configuration_option_generale_radio" (id, configuration_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_event" (uuid, name, slug, datetime, created, short_description, long_description, url_external, published, img, categorie, jauge_max, minimum_cashless_required, max_per_user, is_external, booking) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_options_checkbox; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_event_options_checkbox" (id, event_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_options_radio; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_event_options_radio" (id, event_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_products; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_event_products" (id, event_id, product_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_recurrent; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_event_recurrent" (id, event_id, weekday_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_tag; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_event_tag" (id, event_id, tag_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_externalapikey; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_externalapikey" (id, ip, revoquer_apikey, created, name, event, product, artist, place, user_id, reservation, ticket, key_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_lignearticle; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_lignearticle" (uuid, datetime, qty, status, carte_id, paiement_stripe_id, pricesold_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_membership; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_membership" (id, date_added, first_contribution, last_contribution, contribution_value, last_action, first_name, last_name, pseudo, newsletter, postal_code, birth_date, phone, commentaire, user_id, price_id, stripe_id_subscription, last_stripe_invoice, status) FROM stdin;
\.


--
-- Data for Name: BaseBillet_membership_option_generale; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_membership_option_generale" (id, membership_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_optiongenerale; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_optiongenerale" (uuid, name, poids, description) FROM stdin;
\.


--
-- Data for Name: BaseBillet_paiement_stripe; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_paiement_stripe" (uuid, detail, datetime, checkout_session_id_stripe, payment_intent_id, metadata_stripe, order_date, last_action, status, traitement_en_cours, source_traitement, source, total, reservation_id, user_id, customer_stripe, invoice_stripe, subscription) FROM stdin;
\.


--
-- Data for Name: BaseBillet_price; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_price" (uuid, name, prix, vat, stock, max_per_user, product_id, adhesion_obligatoire_id, long_description, short_description, subscription_type, recurring_payment) FROM stdin;
\.


--
-- Data for Name: BaseBillet_pricesold; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_pricesold" (uuid, id_price_stripe, qty_solded, prix, price_id, productsold_id, gift) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_product" (uuid, name, publish, img, categorie_article, long_description, short_description, terms_and_conditions_document, send_to_cashless, poids, archive, legal_link, nominative) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product_option_generale_checkbox; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_product_option_generale_checkbox" (id, product_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product_option_generale_radio; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_product_option_generale_radio" (id, product_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product_tag; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_product_tag" (id, product_id, tag_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_productsold; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_productsold" (uuid, id_product_stripe, event_id, product_id, categorie_article) FROM stdin;
\.


--
-- Data for Name: BaseBillet_reservation; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_reservation" (uuid, datetime, status, to_mail, mail_send, mail_error, event_id, user_commande_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_reservation_options; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_reservation_options" (id, reservation_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_tag; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_tag" (uuid, name, color) FROM stdin;
\.


--
-- Data for Name: BaseBillet_ticket; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_ticket" (uuid, first_name, last_name, status, seat, pricesold_id, reservation_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_webhook; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_webhook" (id, url, event, active, last_response) FROM stdin;
\.


--
-- Data for Name: BaseBillet_weekday; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta."BaseBillet_weekday" (id, day) FROM stdin;
1	0
2	1
3	2
4	3
5	4
6	5
7	6
\.


--
-- Data for Name: django_content_type; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta.django_content_type (id, app_label, model) FROM stdin;
1	Customers	client
2	Customers	domain
3	contenttypes	contenttype
4	auth	permission
5	auth	group
6	AuthBillet	tibilletuser
7	AuthBillet	humanuser
8	AuthBillet	superhumanuser
9	AuthBillet	termuser
10	AuthBillet	terminalpairingtoken
11	QrcodeCashless	detail
12	QrcodeCashless	cartecashless
13	QrcodeCashless	asset
14	QrcodeCashless	wallet
15	QrcodeCashless	syncfederatedlog
16	QrcodeCashless	federatedcashless
17	authtoken	token
18	authtoken	tokenproxy
19	token_blacklist	blacklistedtoken
20	token_blacklist	outstandingtoken
21	sessions	session
22	sites	site
23	admin	logentry
24	MetaBillet	eventdirectory
25	MetaBillet	productdirectory
26	root_billet	rootconfiguration
27	rest_framework_api_key	apikey
28	BaseBillet	event
29	BaseBillet	optiongenerale
30	BaseBillet	price
31	BaseBillet	pricesold
32	BaseBillet	product
33	BaseBillet	reservation
34	BaseBillet	ticket
35	BaseBillet	productsold
36	BaseBillet	paiement_stripe
37	BaseBillet	membership
38	BaseBillet	lignearticle
39	BaseBillet	configuration
40	BaseBillet	artist_on_event
41	BaseBillet	webhook
42	BaseBillet	externalapikey
43	BaseBillet	tag
44	BaseBillet	weekday
\.


--
-- Data for Name: django_migrations; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta.django_migrations (id, app, name, applied) FROM stdin;
1	contenttypes	0001_initial	2023-10-18 17:18:19.863829+04
2	contenttypes	0002_remove_content_type_name	2023-10-18 17:18:19.872158+04
3	auth	0001_initial	2023-10-18 17:18:19.887081+04
4	auth	0002_alter_permission_name_max_length	2023-10-18 17:18:19.895121+04
5	auth	0003_alter_user_email_max_length	2023-10-18 17:18:19.904836+04
6	auth	0004_alter_user_username_opts	2023-10-18 17:18:19.913464+04
7	auth	0005_alter_user_last_login_null	2023-10-18 17:18:19.92288+04
8	auth	0006_require_contenttypes_0002	2023-10-18 17:18:19.925397+04
9	auth	0007_alter_validators_add_error_messages	2023-10-18 17:18:19.93525+04
10	auth	0008_alter_user_username_max_length	2023-10-18 17:18:19.94186+04
11	auth	0009_alter_user_last_name_max_length	2023-10-18 17:18:19.949498+04
12	auth	0010_alter_group_name_max_length	2023-10-18 17:18:19.955726+04
13	auth	0011_update_proxy_permissions	2023-10-18 17:18:19.959244+04
14	auth	0012_alter_user_first_name_max_length	2023-10-18 17:18:19.968308+04
15	Customers	0001_initial	2023-10-18 17:18:19.977392+04
16	AuthBillet	0001_initial	2023-10-18 17:18:19.990498+04
17	AuthBillet	0002_alter_tibilletuser_is_active	2023-10-18 17:18:20.006893+04
18	AuthBillet	0003_tibilletuser_user_parent_pk	2023-10-18 17:18:20.018675+04
19	AuthBillet	0004_terminalpairingtoken	2023-10-18 17:18:20.030922+04
20	AuthBillet	0005_auto_20220422_1601	2023-10-18 17:18:20.072699+04
21	AuthBillet	0006_terminalpairingtoken_used	2023-10-18 17:18:20.085028+04
22	AuthBillet	0007_alter_terminalpairingtoken_datetime	2023-10-18 17:18:20.097038+04
23	AuthBillet	0008_alter_terminalpairingtoken_datetime	2023-10-18 17:18:20.107217+04
24	AuthBillet	0009_alter_tibilletuser_is_active	2023-10-18 17:18:20.120998+04
25	rest_framework_api_key	0001_initial	2023-10-18 17:18:20.154624+04
26	rest_framework_api_key	0002_auto_20190529_2243	2023-10-18 17:18:20.164709+04
27	rest_framework_api_key	0003_auto_20190623_1952	2023-10-18 17:18:20.171999+04
28	rest_framework_api_key	0004_prefix_hashed_key	2023-10-18 17:18:20.222162+04
29	rest_framework_api_key	0005_auto_20220110_1102	2023-10-18 17:18:20.233961+04
30	QrcodeCashless	0001_initial	2023-10-18 17:18:20.270041+04
31	BaseBillet	0001_initial	2023-10-18 17:18:21.316798+04
32	BaseBillet	0002_alter_ticket_seat	2023-10-18 17:18:21.342556+04
33	BaseBillet	0003_alter_reservation_user_commande	2023-10-18 17:18:21.387584+04
34	BaseBillet	0004_auto_20220421_1129	2023-10-18 17:18:21.444471+04
35	BaseBillet	0005_alter_reservation_status	2023-10-18 17:18:21.477069+04
36	BaseBillet	0006_auto_20220428_1533	2023-10-18 17:18:21.504233+04
37	BaseBillet	0007_alter_configuration_img	2023-10-18 17:18:21.524093+04
38	BaseBillet	0008_auto_20220505_1520	2023-10-18 17:18:21.563431+04
39	BaseBillet	0009_configuration_slug	2023-10-18 17:18:21.584921+04
40	BaseBillet	0010_auto_20220531_0920	2023-10-18 17:18:21.667253+04
41	BaseBillet	0011_membership_price	2023-10-18 17:18:21.704728+04
42	BaseBillet	0012_configuration_legal_documents	2023-10-18 17:18:21.724458+04
43	BaseBillet	0013_auto_20220602_1013	2023-10-18 17:18:21.915069+04
44	BaseBillet	0014_product_terms_and_conditions_document	2023-10-18 17:18:21.928333+04
45	BaseBillet	0015_price_subscription_type	2023-10-18 17:18:21.943595+04
46	BaseBillet	0016_alter_membership_unique_together	2023-10-18 17:18:21.970413+04
47	BaseBillet	0017_product_send_to_cashless	2023-10-18 17:18:21.984986+04
48	BaseBillet	0018_auto_20220608_1607	2023-10-18 17:18:22.017803+04
49	BaseBillet	0019_auto_20220624_0726	2023-10-18 17:18:22.057013+04
50	BaseBillet	0020_membership_stripe_id_subscription	2023-10-18 17:18:22.07931+04
51	BaseBillet	0021_paiement_stripe_invoice_stripe	2023-10-18 17:18:22.107212+04
52	BaseBillet	0022_paiement_stripe_subscription	2023-10-18 17:18:22.137085+04
53	BaseBillet	0023_membership_last_stripe_invoice	2023-10-18 17:18:22.160548+04
54	BaseBillet	0024_auto_20220626_1257	2023-10-18 17:18:22.221425+04
55	BaseBillet	0025_auto_20220810_1245	2023-10-18 17:18:22.25561+04
56	BaseBillet	0026_alter_configuration_slug	2023-10-18 17:18:22.274472+04
57	BaseBillet	0027_product_poids	2023-10-18 17:18:22.286773+04
58	BaseBillet	0028_auto_20220826_1559	2023-10-18 17:18:22.56503+04
59	BaseBillet	0029_remove_configuration_activer_billetterie	2023-10-18 17:18:22.576823+04
60	BaseBillet	0030_auto_20220927_1855	2023-10-18 17:18:22.631065+04
61	BaseBillet	0031_apikey	2023-10-18 17:18:22.656301+04
62	BaseBillet	0032_apikey_created	2023-10-18 17:18:22.666224+04
63	BaseBillet	0033_apikey_name	2023-10-18 17:18:22.685711+04
64	BaseBillet	0034_apikey_auth	2023-10-18 17:18:22.693455+04
65	BaseBillet	0035_alter_apikey_auth	2023-10-18 17:18:22.7024+04
66	BaseBillet	0036_remove_apikey_auth	2023-10-18 17:18:22.708182+04
67	BaseBillet	0037_auto_20221017_1320	2023-10-18 17:18:22.723837+04
68	BaseBillet	0038_apikey_product	2023-10-18 17:18:22.740312+04
69	BaseBillet	0039_auto_20221017_1402	2023-10-18 17:18:22.769208+04
70	BaseBillet	0040_apikey_user	2023-10-18 17:18:22.812042+04
71	BaseBillet	0041_auto_20221018_0932	2023-10-18 17:18:22.848105+04
72	BaseBillet	0042_webhook	2023-10-18 17:18:22.858198+04
73	BaseBillet	0043_webhook_active	2023-10-18 17:18:22.864849+04
74	BaseBillet	0044_webhook_last_response	2023-10-18 17:18:22.874165+04
75	BaseBillet	0045_auto_20221021_1031	2023-10-18 17:18:22.900622+04
76	BaseBillet	0046_alter_product_categorie_article	2023-10-18 17:18:22.935283+04
77	BaseBillet	0047_auto_20221121_1256	2023-10-18 17:18:22.963228+04
78	BaseBillet	0048_configuration_stripe_payouts_enabled	2023-10-18 17:18:22.982715+04
79	BaseBillet	0049_rename_apikey_externalapikey	2023-10-18 17:18:23.032425+04
80	BaseBillet	0050_alter_externalapikey_options	2023-10-18 17:18:23.055927+04
81	BaseBillet	0051_auto_20221125_1847	2023-10-18 17:18:23.107407+04
82	BaseBillet	0052_externalapikey_key	2023-10-18 17:18:23.155886+04
83	BaseBillet	0053_alter_externalapikey_options	2023-10-18 17:18:23.180513+04
84	BaseBillet	0054_price_recurring_payment	2023-10-18 17:18:23.195384+04
85	BaseBillet	0055_auto_20221215_1922	2023-10-18 17:18:23.324162+04
86	BaseBillet	0056_pricesold_gift	2023-10-18 17:18:23.385323+04
87	BaseBillet	0057_auto_20230102_1847	2023-10-18 17:18:23.488872+04
88	BaseBillet	0058_alter_paiement_stripe_status	2023-10-18 17:18:23.602686+04
89	BaseBillet	0059_event_cashless	2023-10-18 17:18:23.619761+04
90	BaseBillet	0060_event_minimum_cashless_required	2023-10-18 17:18:23.64111+04
91	BaseBillet	0061_configuration_federated_cashless	2023-10-18 17:18:23.658081+04
92	BaseBillet	0062_remove_configuration_mollie_api_key	2023-10-18 17:18:23.672834+04
93	BaseBillet	0063_auto_20230427_1105	2023-10-18 17:18:23.85483+04
94	BaseBillet	0064_auto_20230427_1146	2023-10-18 17:18:23.911652+04
95	BaseBillet	0065_auto_20230427_1248	2023-10-18 17:18:24.026706+04
96	BaseBillet	0066_optiongenerale_description	2023-10-18 17:18:24.047927+04
97	BaseBillet	0067_auto_20230427_1410	2023-10-18 17:18:24.17148+04
98	BaseBillet	0068_auto_20230427_1826	2023-10-18 17:18:24.223709+04
99	BaseBillet	0069_alter_optiongenerale_options	2023-10-18 17:18:24.342396+04
100	BaseBillet	0070_alter_configuration_short_description	2023-10-18 17:18:24.363188+04
101	BaseBillet	0071_event_tag	2023-10-18 17:18:24.421359+04
102	BaseBillet	0072_auto_20230522_1614	2023-10-18 17:18:24.471641+04
103	BaseBillet	0073_auto_20230523_1411	2023-10-18 17:18:24.506474+04
104	BaseBillet	0074_auto_20230523_1548	2023-10-18 17:18:24.695674+04
105	BaseBillet	0075_auto_20230524_1706	2023-10-18 17:18:24.772778+04
106	BaseBillet	0076_auto_20230525_1315	2023-10-18 17:18:24.805381+04
107	BaseBillet	0077_auto_20230525_1409	2023-10-18 17:18:24.930759+04
108	BaseBillet	0078_auto_20230602_1441	2023-10-18 17:18:24.977821+04
109	BaseBillet	0079_auto_20230822_0932	2023-10-18 17:18:25.060403+04
110	BaseBillet	0080_productsold_categorie_article	2023-10-18 17:18:25.07653+04
111	BaseBillet	0081_auto_20230822_1459	2023-10-18 17:18:25.110639+04
112	BaseBillet	0082_auto_20230906_1231	2023-10-18 17:18:25.185643+04
113	BaseBillet	0083_auto_20230906_1237	2023-10-18 17:18:25.229297+04
114	BaseBillet	0084_auto_20230906_1243	2023-10-18 17:18:25.279049+04
115	BaseBillet	0085_auto_20230908_1409	2023-10-18 17:18:25.385442+04
116	BaseBillet	0086_auto_20230908_1410	2023-10-18 17:18:25.522381+04
117	Customers	0002_alter_client_categorie	2023-10-18 17:18:25.551868+04
118	MetaBillet	0001_initial	2023-10-18 17:18:25.559137+04
119	MetaBillet	0002_auto_20220519_0904	2023-10-18 17:18:25.599913+04
120	MetaBillet	0003_productdirectory	2023-10-18 17:18:25.63785+04
121	QrcodeCashless	0002_alter_detail_img	2023-10-18 17:18:25.658867+04
122	QrcodeCashless	0003_auto_20221101_1820	2023-10-18 17:18:25.798678+04
123	QrcodeCashless	0004_detail_uuid	2023-10-18 17:18:25.81149+04
124	QrcodeCashless	0005_auto_20230103_1240	2023-10-18 17:18:25.885369+04
125	QrcodeCashless	0006_alter_wallet_unique_together	2023-10-18 17:18:25.904092+04
126	QrcodeCashless	0007_alter_wallet_unique_together	2023-10-18 17:18:25.929458+04
127	QrcodeCashless	0008_alter_cartecashless_uuid	2023-10-18 17:18:25.95717+04
128	QrcodeCashless	0009_federatedcashless_syncfederatedlog	2023-10-18 17:18:26.112348+04
129	QrcodeCashless	0010_auto_20230111_0701	2023-10-18 17:18:26.156155+04
130	QrcodeCashless	0011_auto_20230125_1445	2023-10-18 17:18:26.196068+04
131	QrcodeCashless	0012_syncfederatedlog_categorie	2023-10-18 17:18:26.213796+04
132	QrcodeCashless	0013_auto_20230125_1802	2023-10-18 17:18:26.2862+04
133	QrcodeCashless	0014_asset_categorie	2023-10-18 17:18:26.302706+04
134	QrcodeCashless	0015_alter_asset_unique_together	2023-10-18 17:18:26.314592+04
135	QrcodeCashless	0016_detail_slug	2023-10-18 17:18:26.33289+04
136	admin	0001_initial	2023-10-18 17:18:26.376177+04
137	admin	0002_logentry_remove_auto_add	2023-10-18 17:18:26.394132+04
138	admin	0003_logentry_add_action_flag_choices	2023-10-18 17:18:26.414169+04
139	authtoken	0001_initial	2023-10-18 17:18:26.463438+04
140	authtoken	0002_auto_20160226_1747	2023-10-18 17:18:26.564933+04
141	authtoken	0003_tokenproxy	2023-10-18 17:18:26.570712+04
142	root_billet	0001_initial	2023-10-18 17:18:26.576445+04
143	sessions	0001_initial	2023-10-18 17:18:26.583899+04
144	sites	0001_initial	2023-10-18 17:18:26.589243+04
145	sites	0002_alter_domain_unique	2023-10-18 17:18:26.685301+04
146	token_blacklist	0001_initial	2023-10-18 17:18:26.789343+04
147	token_blacklist	0002_outstandingtoken_jti_hex	2023-10-18 17:18:26.813019+04
148	token_blacklist	0003_auto_20171017_2007	2023-10-18 17:18:26.816489+04
149	token_blacklist	0004_auto_20171017_2013	2023-10-18 17:18:26.845277+04
150	token_blacklist	0005_remove_outstandingtoken_jti	2023-10-18 17:18:26.874638+04
151	token_blacklist	0006_auto_20171017_2113	2023-10-18 17:18:26.902208+04
152	token_blacklist	0007_auto_20171017_2214	2023-10-18 17:18:26.975543+04
153	token_blacklist	0008_migrate_to_bigautofield	2023-10-18 17:18:27.030187+04
154	token_blacklist	0010_fix_migrate_to_bigautofield	2023-10-18 17:18:27.090751+04
155	token_blacklist	0011_linearizes_history	2023-10-18 17:18:27.093028+04
156	token_blacklist	0012_alter_outstandingtoken_user	2023-10-18 17:18:27.138203+04
\.


--
-- Data for Name: rest_framework_api_key_apikey; Type: TABLE DATA; Schema: meta; Owner: ticket_postgres_user
--

COPY meta.rest_framework_api_key_apikey (id, created, name, revoked, expiry_date, hashed_key, prefix) FROM stdin;
\.


--
-- Data for Name: AuthBillet_terminalpairingtoken; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."AuthBillet_terminalpairingtoken" (id, datetime, token, user_id, used) FROM stdin;
\.


--
-- Data for Name: AuthBillet_tibilletuser; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."AuthBillet_tibilletuser" (password, last_login, is_superuser, is_staff, is_active, date_joined, id, email, email_error, username, first_name, last_name, phone, last_see, accept_newsletter, postal_code, birth_date, can_create_tenant, espece, offre, client_source_id, user_parent_pk, local_ip_sended, mac_adress_sended, terminal_uuid) FROM stdin;
pbkdf2_sha256$260000$c6mfOKu26b8HKKF73YRUGD$GoQZoRhoOIF/XOls1EkCm1Bp6UM6ABp3qFpVMNNy3MA=	\N	t	t	t	2023-10-18 17:18:30.10974+04	c3521968-16b8-4c42-a7fc-4385e40f9ecd	root@root.root	f	root@root.root	\N	\N	\N	2023-10-18 17:19:22.399133+04	t	\N	\N	f	HU	PU	bd928f6c-94bb-4ab5-b281-cb6a260c2ea5	\N	\N	\N	\N
\.


--
-- Data for Name: AuthBillet_tibilletuser_client_achat; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."AuthBillet_tibilletuser_client_achat" (id, tibilletuser_id, client_id) FROM stdin;
\.


--
-- Data for Name: AuthBillet_tibilletuser_client_admin; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."AuthBillet_tibilletuser_client_admin" (id, tibilletuser_id, client_id) FROM stdin;
1	c3521968-16b8-4c42-a7fc-4385e40f9ecd	a62d5533-b717-4b33-8e0c-b01cd490f621
2	c3521968-16b8-4c42-a7fc-4385e40f9ecd	1203624e-4826-4a0e-813f-a8a590769b8d
3	c3521968-16b8-4c42-a7fc-4385e40f9ecd	9cfbb542-ccd0-4b41-bb46-8c627a0a7fb9
4	c3521968-16b8-4c42-a7fc-4385e40f9ecd	64d8bfb6-8acb-4ab9-a46d-d2cb7fb6745f
\.


--
-- Data for Name: AuthBillet_tibilletuser_groups; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."AuthBillet_tibilletuser_groups" (id, tibilletuser_id, group_id) FROM stdin;
1	c3521968-16b8-4c42-a7fc-4385e40f9ecd	1
\.


--
-- Data for Name: AuthBillet_tibilletuser_user_permissions; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."AuthBillet_tibilletuser_user_permissions" (id, tibilletuser_id, permission_id) FROM stdin;
\.


--
-- Data for Name: Customers_client; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."Customers_client" (schema_name, uuid, name, paid_until, on_trial, created_on, categorie) FROM stdin;
public	bd928f6c-94bb-4ab5-b281-cb6a260c2ea5	TiBillet Coop.	2023-10-18	f	2023-10-18	R
meta	36f1d3b6-1ba1-4eff-87af-d1e082b6452a	agenda	2023-10-18	f	2023-10-18	M
demo	a62d5533-b717-4b33-8e0c-b01cd490f621	Demo	2023-10-18	t	2023-10-18	S
billetistan	1203624e-4826-4a0e-813f-a8a590769b8d	Billetistan	2023-10-18	t	2023-10-18	S
ziskakan	9cfbb542-ccd0-4b41-bb46-8c627a0a7fb9	Ziskakan	2023-10-18	t	2023-10-18	A
balaphonik-sound-system	64d8bfb6-8acb-4ab9-a46d-d2cb7fb6745f	Balaphonik Sound System	2023-10-18	t	2023-10-18	A
\.


--
-- Data for Name: Customers_domain; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."Customers_domain" (id, domain, is_primary, tenant_id) FROM stdin;
1	filaos.re	f	bd928f6c-94bb-4ab5-b281-cb6a260c2ea5
2	www.filaos.re	t	bd928f6c-94bb-4ab5-b281-cb6a260c2ea5
3	m.filaos.re	f	36f1d3b6-1ba1-4eff-87af-d1e082b6452a
4	agenda.filaos.re	t	36f1d3b6-1ba1-4eff-87af-d1e082b6452a
5	demo.filaos.re	t	a62d5533-b717-4b33-8e0c-b01cd490f621
6	billetistan.filaos.re	t	1203624e-4826-4a0e-813f-a8a590769b8d
7	ziskakan.filaos.re	t	9cfbb542-ccd0-4b41-bb46-8c627a0a7fb9
8	balaphonik-sound-system.filaos.re	t	64d8bfb6-8acb-4ab9-a46d-d2cb7fb6745f
\.


--
-- Data for Name: MetaBillet_eventdirectory; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."MetaBillet_eventdirectory" (id, datetime, event_uuid, artist_id, place_id) FROM stdin;
1	2024-07-20 17:19:39.023+04	fec06317-878c-4c6d-9f87-52f1f59831c7	9cfbb542-ccd0-4b41-bb46-8c627a0a7fb9	a62d5533-b717-4b33-8e0c-b01cd490f621
2	2023-12-27 17:19:41.205+04	1a8eb214-faab-4cb3-b8a8-ece9b8286fdc	64d8bfb6-8acb-4ab9-a46d-d2cb7fb6745f	a62d5533-b717-4b33-8e0c-b01cd490f621
\.


--
-- Data for Name: MetaBillet_productdirectory; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."MetaBillet_productdirectory" (id, product_sold_stripe_id, place_id) FROM stdin;
\.


--
-- Data for Name: QrcodeCashless_asset; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."QrcodeCashless_asset" (id, name, is_federated, origin_id, categorie) FROM stdin;
\.


--
-- Data for Name: QrcodeCashless_cartecashless; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."QrcodeCashless_cartecashless" (id, tag_id, uuid, number, detail_id, user_id) FROM stdin;
1	EE144CE8	76dc433c-00ac-479c-93c4-b7a0710246af	76DC433C	1	\N
2	93BD3684	87683c94-1187-49ae-a64d-54174f6eb76d	87683C94	1	\N
3	41726643	c2b2400c-1f7e-4305-b75e-8c1db3f8d113	C2B2400C	1	\N
4	11372ACA	7c9b0d8a-6c37-433b-a091-2c6017b085f0	7C9B0D8A	1	\N
5	4D64463B	8ee38b17-fc02-4c8d-84cb-59eaaa059ee0	A9253967	1	\N
6	CC3EB41E	f75234fc-0c86-40cf-ae00-604cd3719403	F75234FC	1	\N
7	91168FE9	b2eba074-f070-4fe3-9150-deda224b708d	B2EBA074	1	\N
8	A14F75E9	5ddb4c9f-5f9e-4fa1-aacb-60316f2a3aea	5DDB4C9F	1	\N
9	A14DD6CA	189ce45e-d606-4e5a-bfbe-5ed5ec5e4995	189CE45E	1	\N
10	01F097CA	d6cad253-b6cf-4d8f-9238-0927de8a4ce9	D6CAD253	1	\N
11	4172AACA	eced8aef-3e1f-4614-be11-b756768c9bad	ECED8AEF	1	\N
12	F18923CB	7dc2fee6-a312-4ff3-849c-b26da9302174	7DC2FEE6	1	\N
\.


--
-- Data for Name: QrcodeCashless_detail; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."QrcodeCashless_detail" (id, img, img_url, base_url, generation, origine_id, uuid, slug) FROM stdin;
1		\N	https://demo.tibillet.localhost/qr/	1	a62d5533-b717-4b33-8e0c-b01cd490f621	0479041f-fcd4-4aad-b5a7-00466556d639	demo-1
\.


--
-- Data for Name: QrcodeCashless_federatedcashless; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."QrcodeCashless_federatedcashless" (id, server_cashless, key_cashless, asset_id, client_id) FROM stdin;
\.


--
-- Data for Name: QrcodeCashless_syncfederatedlog; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."QrcodeCashless_syncfederatedlog" (id, uuid, date, etat_client_sync, card_id, client_source_id, new_qty, old_qty, categorie, wallet_id) FROM stdin;
\.


--
-- Data for Name: QrcodeCashless_wallet; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public."QrcodeCashless_wallet" (id, qty, last_date_used, sync, asset_id, user_id, card_id) FROM stdin;
\.


--
-- Data for Name: auth_group; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public.auth_group (id, name) FROM stdin;
1	staff
\.


--
-- Data for Name: auth_group_permissions; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public.auth_group_permissions (id, group_id, permission_id) FROM stdin;
1	1	298
2	1	300
3	1	293
4	1	294
5	1	295
6	1	296
7	1	301
8	1	302
9	1	303
10	1	304
11	1	305
12	1	306
13	1	307
14	1	308
15	1	309
16	1	310
17	1	311
18	1	312
19	1	336
20	1	325
21	1	326
22	1	327
23	1	328
24	1	329
25	1	330
26	1	331
27	1	332
28	1	341
29	1	342
30	1	343
31	1	344
32	1	281
33	1	282
34	1	283
35	1	284
36	1	345
37	1	346
38	1	347
39	1	348
40	1	349
41	1	350
42	1	351
43	1	352
\.


--
-- Data for Name: auth_permission; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public.auth_permission (id, name, content_type_id, codename) FROM stdin;
177	Can add client	1	add_client
178	Can change client	1	change_client
179	Can delete client	1	delete_client
180	Can view client	1	view_client
181	Can add domain	2	add_domain
182	Can change domain	2	change_domain
183	Can delete domain	2	delete_domain
184	Can view domain	2	view_domain
185	Can add content type	3	add_contenttype
186	Can change content type	3	change_contenttype
187	Can delete content type	3	delete_contenttype
188	Can view content type	3	view_contenttype
189	Can add permission	4	add_permission
190	Can change permission	4	change_permission
191	Can delete permission	4	delete_permission
192	Can view permission	4	view_permission
193	Can add group	5	add_group
194	Can change group	5	change_group
195	Can delete group	5	delete_group
196	Can view group	5	view_group
197	Can add user	6	add_tibilletuser
198	Can change user	6	change_tibilletuser
199	Can delete user	6	delete_tibilletuser
200	Can view user	6	view_tibilletuser
201	Can add Terminal	9	add_termuser
202	Can change Terminal	9	change_termuser
203	Can delete Terminal	9	delete_termuser
204	Can view Terminal	9	view_termuser
205	Can add Utilisateur	7	add_humanuser
206	Can change Utilisateur	7	change_humanuser
207	Can delete Utilisateur	7	delete_humanuser
208	Can view Utilisateur	7	view_humanuser
209	Can add Administrateur	8	add_superhumanuser
210	Can change Administrateur	8	change_superhumanuser
211	Can delete Administrateur	8	delete_superhumanuser
212	Can view Administrateur	8	view_superhumanuser
213	Can add terminal pairing token	10	add_terminalpairingtoken
214	Can change terminal pairing token	10	change_terminalpairingtoken
215	Can delete terminal pairing token	10	delete_terminalpairingtoken
216	Can view terminal pairing token	10	view_terminalpairingtoken
217	Can add detail	11	add_detail
218	Can change detail	11	change_detail
219	Can delete detail	11	delete_detail
220	Can view detail	11	view_detail
221	Can add asset	13	add_asset
222	Can change asset	13	change_asset
223	Can delete asset	13	delete_asset
224	Can view asset	13	view_asset
225	Can add carte cashless	12	add_cartecashless
226	Can change carte cashless	12	change_cartecashless
227	Can delete carte cashless	12	delete_cartecashless
228	Can view carte cashless	12	view_cartecashless
229	Can add wallet	14	add_wallet
230	Can change wallet	14	change_wallet
231	Can delete wallet	14	delete_wallet
232	Can view wallet	14	view_wallet
233	Can add federated cashless	16	add_federatedcashless
234	Can change federated cashless	16	change_federatedcashless
235	Can delete federated cashless	16	delete_federatedcashless
236	Can view federated cashless	16	view_federatedcashless
237	Can add sync federated log	15	add_syncfederatedlog
238	Can change sync federated log	15	change_syncfederatedlog
239	Can delete sync federated log	15	delete_syncfederatedlog
240	Can view sync federated log	15	view_syncfederatedlog
241	Can add Token	17	add_token
242	Can change Token	17	change_token
243	Can delete Token	17	delete_token
244	Can view Token	17	view_token
245	Can add token	18	add_tokenproxy
246	Can change token	18	change_tokenproxy
247	Can delete token	18	delete_tokenproxy
248	Can view token	18	view_tokenproxy
249	Can add outstanding token	20	add_outstandingtoken
250	Can change outstanding token	20	change_outstandingtoken
251	Can delete outstanding token	20	delete_outstandingtoken
252	Can view outstanding token	20	view_outstandingtoken
253	Can add blacklisted token	19	add_blacklistedtoken
254	Can change blacklisted token	19	change_blacklistedtoken
255	Can delete blacklisted token	19	delete_blacklistedtoken
256	Can view blacklisted token	19	view_blacklistedtoken
257	Can add session	21	add_session
258	Can change session	21	change_session
259	Can delete session	21	delete_session
260	Can view session	21	view_session
261	Can add site	22	add_site
262	Can change site	22	change_site
263	Can delete site	22	delete_site
264	Can view site	22	view_site
265	Can add log entry	23	add_logentry
266	Can change log entry	23	change_logentry
267	Can delete log entry	23	delete_logentry
268	Can view log entry	23	view_logentry
269	Can add event directory	24	add_eventdirectory
270	Can change event directory	24	change_eventdirectory
271	Can delete event directory	24	delete_eventdirectory
272	Can view event directory	24	view_eventdirectory
273	Can add product directory	25	add_productdirectory
274	Can change product directory	25	change_productdirectory
275	Can delete product directory	25	delete_productdirectory
276	Can view product directory	25	view_productdirectory
277	Can add root configuration	26	add_rootconfiguration
278	Can change root configuration	26	change_rootconfiguration
279	Can delete root configuration	26	delete_rootconfiguration
280	Can view root configuration	26	view_rootconfiguration
281	Can add API key	27	add_apikey
282	Can change API key	27	change_apikey
283	Can delete API key	27	delete_apikey
284	Can view API key	27	view_apikey
285	Can add weekday	44	add_weekday
286	Can change weekday	44	change_weekday
287	Can delete weekday	44	delete_weekday
288	Can view weekday	44	view_weekday
289	Can add Tag	43	add_tag
290	Can change Tag	43	change_tag
291	Can delete Tag	43	delete_tag
292	Can view Tag	43	view_tag
293	Can add Option	29	add_optiongenerale
294	Can change Option	29	change_optiongenerale
295	Can delete Option	29	delete_optiongenerale
296	Can view Option	29	view_optiongenerale
297	Can add Paramètres	39	add_configuration
298	Can change Paramètres	39	change_configuration
299	Can delete Paramètres	39	delete_configuration
300	Can view Paramètres	39	view_configuration
301	Can add Produit	32	add_product
302	Can change Produit	32	change_product
303	Can delete Produit	32	delete_product
304	Can view Produit	32	view_product
305	Can add Tarif	30	add_price
306	Can change Tarif	30	change_price
307	Can delete Tarif	30	delete_price
308	Can view Tarif	30	view_price
309	Can add Evenement	28	add_event
310	Can change Evenement	28	change_event
311	Can delete Evenement	28	delete_event
312	Can view Evenement	28	view_event
313	Can add artist_on_event	40	add_artist_on_event
314	Can change artist_on_event	40	change_artist_on_event
315	Can delete artist_on_event	40	delete_artist_on_event
316	Can view artist_on_event	40	view_artist_on_event
317	Can add product sold	35	add_productsold
318	Can change product sold	35	change_productsold
319	Can delete product sold	35	delete_productsold
320	Can view product sold	35	view_productsold
321	Can add price sold	31	add_pricesold
322	Can change price sold	31	change_pricesold
323	Can delete price sold	31	delete_pricesold
324	Can view price sold	31	view_pricesold
325	Can add reservation	33	add_reservation
326	Can change reservation	33	change_reservation
327	Can delete reservation	33	delete_reservation
328	Can view reservation	33	view_reservation
329	Can add Réservation	34	add_ticket
330	Can change Réservation	34	change_ticket
331	Can delete Réservation	34	delete_ticket
332	Can view Réservation	34	view_ticket
333	Can add Paiement Stripe	36	add_paiement_stripe
334	Can change Paiement Stripe	36	change_paiement_stripe
335	Can delete Paiement Stripe	36	delete_paiement_stripe
336	Can view Paiement Stripe	36	view_paiement_stripe
337	Can add ligne article	38	add_lignearticle
338	Can change ligne article	38	change_lignearticle
339	Can delete ligne article	38	delete_lignearticle
340	Can view ligne article	38	view_lignearticle
341	Can add Adhésion	37	add_membership
342	Can change Adhésion	37	change_membership
343	Can delete Adhésion	37	delete_membership
344	Can view Adhésion	37	view_membership
345	Can add Api key	42	add_externalapikey
346	Can change Api key	42	change_externalapikey
347	Can delete Api key	42	delete_externalapikey
348	Can view Api key	42	view_externalapikey
349	Can add webhook	41	add_webhook
350	Can change webhook	41	change_webhook
351	Can delete webhook	41	delete_webhook
352	Can view webhook	41	view_webhook
\.


--
-- Data for Name: authtoken_token; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public.authtoken_token (key, created, user_id) FROM stdin;
\.


--
-- Data for Name: django_admin_log; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public.django_admin_log (id, action_time, object_id, object_repr, action_flag, change_message, content_type_id, user_id) FROM stdin;
\.


--
-- Data for Name: django_content_type; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public.django_content_type (id, app_label, model) FROM stdin;
1	Customers	client
2	Customers	domain
3	contenttypes	contenttype
4	auth	permission
5	auth	group
6	AuthBillet	tibilletuser
7	AuthBillet	humanuser
8	AuthBillet	superhumanuser
9	AuthBillet	termuser
10	AuthBillet	terminalpairingtoken
11	QrcodeCashless	detail
12	QrcodeCashless	cartecashless
13	QrcodeCashless	asset
14	QrcodeCashless	wallet
15	QrcodeCashless	syncfederatedlog
16	QrcodeCashless	federatedcashless
17	authtoken	token
18	authtoken	tokenproxy
19	token_blacklist	blacklistedtoken
20	token_blacklist	outstandingtoken
21	sessions	session
22	sites	site
23	admin	logentry
24	MetaBillet	eventdirectory
25	MetaBillet	productdirectory
26	root_billet	rootconfiguration
27	rest_framework_api_key	apikey
28	BaseBillet	event
29	BaseBillet	optiongenerale
30	BaseBillet	price
31	BaseBillet	pricesold
32	BaseBillet	product
33	BaseBillet	reservation
34	BaseBillet	ticket
35	BaseBillet	productsold
36	BaseBillet	paiement_stripe
37	BaseBillet	membership
38	BaseBillet	lignearticle
39	BaseBillet	configuration
40	BaseBillet	artist_on_event
41	BaseBillet	webhook
42	BaseBillet	externalapikey
43	BaseBillet	tag
44	BaseBillet	weekday
\.


--
-- Data for Name: django_migrations; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public.django_migrations (id, app, name, applied) FROM stdin;
1	contenttypes	0001_initial	2023-10-18 17:18:08.893114+04
2	contenttypes	0002_remove_content_type_name	2023-10-18 17:18:08.903448+04
3	auth	0001_initial	2023-10-18 17:18:09.004368+04
4	auth	0002_alter_permission_name_max_length	2023-10-18 17:18:09.012481+04
5	auth	0003_alter_user_email_max_length	2023-10-18 17:18:09.023058+04
6	auth	0004_alter_user_username_opts	2023-10-18 17:18:09.032323+04
7	auth	0005_alter_user_last_login_null	2023-10-18 17:18:09.03993+04
8	auth	0006_require_contenttypes_0002	2023-10-18 17:18:09.043939+04
9	auth	0007_alter_validators_add_error_messages	2023-10-18 17:18:09.051619+04
10	auth	0008_alter_user_username_max_length	2023-10-18 17:18:09.064763+04
11	auth	0009_alter_user_last_name_max_length	2023-10-18 17:18:09.07499+04
12	auth	0010_alter_group_name_max_length	2023-10-18 17:18:09.084674+04
13	auth	0011_update_proxy_permissions	2023-10-18 17:18:09.095166+04
14	auth	0012_alter_user_first_name_max_length	2023-10-18 17:18:09.103187+04
15	Customers	0001_initial	2023-10-18 17:18:09.339644+04
16	AuthBillet	0001_initial	2023-10-18 17:18:09.551958+04
17	AuthBillet	0002_alter_tibilletuser_is_active	2023-10-18 17:18:09.586529+04
18	AuthBillet	0003_tibilletuser_user_parent_pk	2023-10-18 17:18:09.625695+04
19	AuthBillet	0004_terminalpairingtoken	2023-10-18 17:18:09.673888+04
20	AuthBillet	0005_auto_20220422_1601	2023-10-18 17:18:09.744145+04
21	AuthBillet	0006_terminalpairingtoken_used	2023-10-18 17:18:09.761074+04
22	AuthBillet	0007_alter_terminalpairingtoken_datetime	2023-10-18 17:18:09.794415+04
23	AuthBillet	0008_alter_terminalpairingtoken_datetime	2023-10-18 17:18:09.808336+04
24	AuthBillet	0009_alter_tibilletuser_is_active	2023-10-18 17:18:09.823645+04
25	rest_framework_api_key	0001_initial	2023-10-18 17:18:09.831236+04
26	rest_framework_api_key	0002_auto_20190529_2243	2023-10-18 17:18:09.847642+04
27	rest_framework_api_key	0003_auto_20190623_1952	2023-10-18 17:18:09.855386+04
28	rest_framework_api_key	0004_prefix_hashed_key	2023-10-18 17:18:09.870074+04
29	rest_framework_api_key	0005_auto_20220110_1102	2023-10-18 17:18:09.879595+04
30	QrcodeCashless	0001_initial	2023-10-18 17:18:10.019497+04
31	BaseBillet	0001_initial	2023-10-18 17:18:10.325426+04
32	BaseBillet	0002_alter_ticket_seat	2023-10-18 17:18:10.344709+04
33	BaseBillet	0003_alter_reservation_user_commande	2023-10-18 17:18:10.379981+04
34	BaseBillet	0004_auto_20220421_1129	2023-10-18 17:18:10.418605+04
35	BaseBillet	0005_alter_reservation_status	2023-10-18 17:18:10.442593+04
36	BaseBillet	0006_auto_20220428_1533	2023-10-18 17:18:10.476217+04
37	BaseBillet	0007_alter_configuration_img	2023-10-18 17:18:10.492052+04
38	BaseBillet	0008_auto_20220505_1520	2023-10-18 17:18:10.520217+04
39	BaseBillet	0009_configuration_slug	2023-10-18 17:18:10.536858+04
40	BaseBillet	0010_auto_20220531_0920	2023-10-18 17:18:10.59372+04
41	BaseBillet	0011_membership_price	2023-10-18 17:18:10.627467+04
42	BaseBillet	0012_configuration_legal_documents	2023-10-18 17:18:10.642238+04
43	BaseBillet	0013_auto_20220602_1013	2023-10-18 17:18:10.747313+04
44	BaseBillet	0014_product_terms_and_conditions_document	2023-10-18 17:18:10.757202+04
45	BaseBillet	0015_price_subscription_type	2023-10-18 17:18:10.773427+04
46	BaseBillet	0016_alter_membership_unique_together	2023-10-18 17:18:10.874979+04
47	BaseBillet	0017_product_send_to_cashless	2023-10-18 17:18:10.899234+04
48	BaseBillet	0018_auto_20220608_1607	2023-10-18 17:18:10.935413+04
49	BaseBillet	0019_auto_20220624_0726	2023-10-18 17:18:10.972659+04
50	BaseBillet	0020_membership_stripe_id_subscription	2023-10-18 17:18:10.997551+04
51	BaseBillet	0021_paiement_stripe_invoice_stripe	2023-10-18 17:18:11.028627+04
52	BaseBillet	0022_paiement_stripe_subscription	2023-10-18 17:18:11.059274+04
53	BaseBillet	0023_membership_last_stripe_invoice	2023-10-18 17:18:11.094387+04
54	BaseBillet	0024_auto_20220626_1257	2023-10-18 17:18:11.157391+04
55	BaseBillet	0025_auto_20220810_1245	2023-10-18 17:18:11.19495+04
56	BaseBillet	0026_alter_configuration_slug	2023-10-18 17:18:11.213297+04
57	BaseBillet	0027_product_poids	2023-10-18 17:18:11.229338+04
58	BaseBillet	0028_auto_20220826_1559	2023-10-18 17:18:11.445824+04
59	BaseBillet	0029_remove_configuration_activer_billetterie	2023-10-18 17:18:11.461+04
60	BaseBillet	0030_auto_20220927_1855	2023-10-18 17:18:11.591613+04
61	BaseBillet	0031_apikey	2023-10-18 17:18:11.599535+04
62	BaseBillet	0032_apikey_created	2023-10-18 17:18:11.607688+04
63	BaseBillet	0033_apikey_name	2023-10-18 17:18:11.616487+04
64	BaseBillet	0034_apikey_auth	2023-10-18 17:18:11.626753+04
65	BaseBillet	0035_alter_apikey_auth	2023-10-18 17:18:11.63581+04
66	BaseBillet	0036_remove_apikey_auth	2023-10-18 17:18:11.643672+04
67	BaseBillet	0037_auto_20221017_1320	2023-10-18 17:18:11.657409+04
68	BaseBillet	0038_apikey_product	2023-10-18 17:18:11.669658+04
69	BaseBillet	0039_auto_20221017_1402	2023-10-18 17:18:11.688712+04
70	BaseBillet	0040_apikey_user	2023-10-18 17:18:11.733431+04
71	BaseBillet	0041_auto_20221018_0932	2023-10-18 17:18:11.786389+04
72	BaseBillet	0042_webhook	2023-10-18 17:18:11.795276+04
73	BaseBillet	0043_webhook_active	2023-10-18 17:18:11.803903+04
74	BaseBillet	0044_webhook_last_response	2023-10-18 17:18:11.810143+04
75	BaseBillet	0045_auto_20221021_1031	2023-10-18 17:18:11.840602+04
76	BaseBillet	0046_alter_product_categorie_article	2023-10-18 17:18:11.885807+04
77	BaseBillet	0047_auto_20221121_1256	2023-10-18 17:18:11.912485+04
78	BaseBillet	0048_configuration_stripe_payouts_enabled	2023-10-18 17:18:11.933811+04
79	BaseBillet	0049_rename_apikey_externalapikey	2023-10-18 17:18:11.964715+04
80	BaseBillet	0050_alter_externalapikey_options	2023-10-18 17:18:11.989625+04
81	BaseBillet	0051_auto_20221125_1847	2023-10-18 17:18:12.055556+04
82	BaseBillet	0052_externalapikey_key	2023-10-18 17:18:12.101675+04
83	BaseBillet	0053_alter_externalapikey_options	2023-10-18 17:18:12.128521+04
84	BaseBillet	0054_price_recurring_payment	2023-10-18 17:18:12.143996+04
85	BaseBillet	0055_auto_20221215_1922	2023-10-18 17:18:12.196295+04
86	BaseBillet	0056_pricesold_gift	2023-10-18 17:18:12.218408+04
87	BaseBillet	0057_auto_20230102_1847	2023-10-18 17:18:12.275011+04
88	BaseBillet	0058_alter_paiement_stripe_status	2023-10-18 17:18:12.297022+04
89	BaseBillet	0059_event_cashless	2023-10-18 17:18:12.322535+04
90	BaseBillet	0060_event_minimum_cashless_required	2023-10-18 17:18:12.34953+04
91	BaseBillet	0061_configuration_federated_cashless	2023-10-18 17:18:12.36481+04
92	BaseBillet	0062_remove_configuration_mollie_api_key	2023-10-18 17:18:12.480843+04
93	BaseBillet	0063_auto_20230427_1105	2023-10-18 17:18:12.584374+04
94	BaseBillet	0064_auto_20230427_1146	2023-10-18 17:18:12.660448+04
95	BaseBillet	0065_auto_20230427_1248	2023-10-18 17:18:12.741723+04
96	BaseBillet	0066_optiongenerale_description	2023-10-18 17:18:12.773236+04
97	BaseBillet	0067_auto_20230427_1410	2023-10-18 17:18:12.885184+04
98	BaseBillet	0068_auto_20230427_1826	2023-10-18 17:18:12.948696+04
99	BaseBillet	0069_alter_optiongenerale_options	2023-10-18 17:18:12.970598+04
100	BaseBillet	0070_alter_configuration_short_description	2023-10-18 17:18:13.003475+04
101	BaseBillet	0071_event_tag	2023-10-18 17:18:13.051397+04
102	BaseBillet	0072_auto_20230522_1614	2023-10-18 17:18:13.199992+04
103	BaseBillet	0073_auto_20230523_1411	2023-10-18 17:18:13.240255+04
104	BaseBillet	0074_auto_20230523_1548	2023-10-18 17:18:13.447545+04
105	BaseBillet	0075_auto_20230524_1706	2023-10-18 17:18:13.527066+04
106	BaseBillet	0076_auto_20230525_1315	2023-10-18 17:18:13.565225+04
107	BaseBillet	0077_auto_20230525_1409	2023-10-18 17:18:13.609819+04
108	BaseBillet	0078_auto_20230602_1441	2023-10-18 17:18:13.733972+04
109	BaseBillet	0079_auto_20230822_0932	2023-10-18 17:18:13.785158+04
110	BaseBillet	0080_productsold_categorie_article	2023-10-18 17:18:13.813485+04
111	BaseBillet	0081_auto_20230822_1459	2023-10-18 17:18:13.856208+04
112	BaseBillet	0082_auto_20230906_1231	2023-10-18 17:18:13.932585+04
113	BaseBillet	0083_auto_20230906_1237	2023-10-18 17:18:13.980363+04
114	BaseBillet	0084_auto_20230906_1243	2023-10-18 17:18:14.037343+04
115	BaseBillet	0085_auto_20230908_1409	2023-10-18 17:18:14.095459+04
116	BaseBillet	0086_auto_20230908_1410	2023-10-18 17:18:14.100931+04
117	Customers	0002_alter_client_categorie	2023-10-18 17:18:14.14078+04
118	MetaBillet	0001_initial	2023-10-18 17:18:14.154839+04
119	MetaBillet	0002_auto_20220519_0904	2023-10-18 17:18:14.230137+04
120	MetaBillet	0003_productdirectory	2023-10-18 17:18:14.390323+04
121	QrcodeCashless	0002_alter_detail_img	2023-10-18 17:18:14.408138+04
122	QrcodeCashless	0003_auto_20221101_1820	2023-10-18 17:18:14.625321+04
123	QrcodeCashless	0004_detail_uuid	2023-10-18 17:18:14.641413+04
124	QrcodeCashless	0005_auto_20230103_1240	2023-10-18 17:18:14.734049+04
125	QrcodeCashless	0006_alter_wallet_unique_together	2023-10-18 17:18:14.767102+04
126	QrcodeCashless	0007_alter_wallet_unique_together	2023-10-18 17:18:14.803744+04
127	QrcodeCashless	0008_alter_cartecashless_uuid	2023-10-18 17:18:14.828275+04
128	QrcodeCashless	0009_federatedcashless_syncfederatedlog	2023-10-18 17:18:14.95444+04
129	QrcodeCashless	0010_auto_20230111_0701	2023-10-18 17:18:15.014523+04
130	QrcodeCashless	0011_auto_20230125_1445	2023-10-18 17:18:15.160297+04
131	QrcodeCashless	0012_syncfederatedlog_categorie	2023-10-18 17:18:15.185943+04
132	QrcodeCashless	0013_auto_20230125_1802	2023-10-18 17:18:15.277766+04
133	QrcodeCashless	0014_asset_categorie	2023-10-18 17:18:15.301146+04
134	QrcodeCashless	0015_alter_asset_unique_together	2023-10-18 17:18:15.329115+04
135	QrcodeCashless	0016_detail_slug	2023-10-18 17:18:15.366137+04
136	admin	0001_initial	2023-10-18 17:18:15.448155+04
137	admin	0002_logentry_remove_auto_add	2023-10-18 17:18:15.469304+04
138	admin	0003_logentry_add_action_flag_choices	2023-10-18 17:18:15.494942+04
139	authtoken	0001_initial	2023-10-18 17:18:15.568537+04
140	authtoken	0002_auto_20160226_1747	2023-10-18 17:18:15.659553+04
141	authtoken	0003_tokenproxy	2023-10-18 17:18:15.666896+04
142	root_billet	0001_initial	2023-10-18 17:18:15.677889+04
143	sessions	0001_initial	2023-10-18 17:18:15.705964+04
144	sites	0001_initial	2023-10-18 17:18:15.719182+04
145	sites	0002_alter_domain_unique	2023-10-18 17:18:15.740358+04
146	token_blacklist	0001_initial	2023-10-18 17:18:15.857294+04
147	token_blacklist	0002_outstandingtoken_jti_hex	2023-10-18 17:18:15.964593+04
148	token_blacklist	0003_auto_20171017_2007	2023-10-18 17:18:16.013201+04
149	token_blacklist	0004_auto_20171017_2013	2023-10-18 17:18:16.055303+04
150	token_blacklist	0005_remove_outstandingtoken_jti	2023-10-18 17:18:16.077548+04
151	token_blacklist	0006_auto_20171017_2113	2023-10-18 17:18:16.104431+04
152	token_blacklist	0007_auto_20171017_2214	2023-10-18 17:18:16.247701+04
153	token_blacklist	0008_migrate_to_bigautofield	2023-10-18 17:18:16.377056+04
154	token_blacklist	0010_fix_migrate_to_bigautofield	2023-10-18 17:18:16.435696+04
155	token_blacklist	0011_linearizes_history	2023-10-18 17:18:16.439865+04
156	token_blacklist	0012_alter_outstandingtoken_user	2023-10-18 17:18:16.488649+04
\.


--
-- Data for Name: django_session; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public.django_session (session_key, session_data, expire_date) FROM stdin;
\.


--
-- Data for Name: django_site; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public.django_site (id, domain, name) FROM stdin;
1	example.com	example.com
\.


--
-- Data for Name: root_billet_rootconfiguration; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public.root_billet_rootconfiguration (id, fuseau_horaire, stripe_api_key, stripe_test_api_key, stripe_mode_test) FROM stdin;
1	Indian/Reunion		sk_test_51L8IaaE69ziSlaLWnzb5Y2dfO969Ewvup76BlCXIrHVPFpIafRpcvCDa6P7FIkPWhQS03VzmMrWi0zqHf057QcDa00C9jmoUPJ	t
\.


--
-- Data for Name: token_blacklist_blacklistedtoken; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public.token_blacklist_blacklistedtoken (id, blacklisted_at, token_id) FROM stdin;
\.


--
-- Data for Name: token_blacklist_outstandingtoken; Type: TABLE DATA; Schema: public; Owner: ticket_postgres_user
--

COPY public.token_blacklist_outstandingtoken (id, token, created_at, expires_at, user_id, jti) FROM stdin;
1	eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTcwMDIyNzExNiwiaWF0IjoxNjk3NjM1MTE2LCJqdGkiOiIyOGUxNGNhMTg1MDU0MDhlYWFmZGQ0YzIyYzA4OGZkMSIsInVzZXJfaWQiOiJjMzUyMTk2OC0xNmI4LTRjNDItYTdmYy00Mzg1ZTQwZjllY2QifQ.k5IukatUkNqQ3jwzs3UfHiX3Dedl_DD_KbvN87p4DLA	2023-10-18 17:18:36.36153+04	2023-11-17 17:18:36+04	c3521968-16b8-4c42-a7fc-4385e40f9ecd	28e14ca18505408eaafdd4c22c088fd1
\.


--
-- Data for Name: BaseBillet_artist_on_event; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_artist_on_event" (id, datetime, artist_id, event_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_configuration; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_configuration" (id, organisation, short_description, long_description, adress, postal_code, city, phone, email, site_web, twitter, facebook, instagram, map_img, carte_restaurant, img, fuseau_horaire, logo, stripe_api_key, stripe_test_api_key, stripe_mode_test, jauge_max, server_cashless, key_cashless, template_billetterie, template_meta, activate_mailjet, email_confirm_template, slug, legal_documents, stripe_connect_account, stripe_connect_account_test, stripe_payouts_enabled, federated_cashless, ghost_key, ghost_last_log, ghost_url, key_fedow, server_fedow) FROM stdin;
1	Ziskakan	40 ans de Maloya Rock !	Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.	\N	\N	\N		root@root.root	\N	\N	\N	\N			images/1080_3gJsPNG	Indian/Reunion	images/540_B5fytYV	\N	\N	t	50	\N	\N	arnaud_mvc	html5up-masseively	f	3898061	ziskakan	\N	acct_1M7YYOE0J1b3jXbW	\N	f	f	\N	\N	\N	\N	\N
\.


--
-- Data for Name: BaseBillet_configuration_option_generale_checkbox; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_configuration_option_generale_checkbox" (id, configuration_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_configuration_option_generale_radio; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_configuration_option_generale_radio" (id, configuration_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_event" (uuid, name, slug, datetime, created, short_description, long_description, url_external, published, img, categorie, jauge_max, minimum_cashless_required, max_per_user, is_external, booking) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_options_checkbox; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_event_options_checkbox" (id, event_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_options_radio; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_event_options_radio" (id, event_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_products; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_event_products" (id, event_id, product_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_recurrent; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_event_recurrent" (id, event_id, weekday_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_event_tag; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_event_tag" (id, event_id, tag_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_externalapikey; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_externalapikey" (id, ip, revoquer_apikey, created, name, event, product, artist, place, user_id, reservation, ticket, key_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_lignearticle; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_lignearticle" (uuid, datetime, qty, status, carte_id, paiement_stripe_id, pricesold_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_membership; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_membership" (id, date_added, first_contribution, last_contribution, contribution_value, last_action, first_name, last_name, pseudo, newsletter, postal_code, birth_date, phone, commentaire, user_id, price_id, stripe_id_subscription, last_stripe_invoice, status) FROM stdin;
\.


--
-- Data for Name: BaseBillet_membership_option_generale; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_membership_option_generale" (id, membership_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_optiongenerale; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_optiongenerale" (uuid, name, poids, description) FROM stdin;
\.


--
-- Data for Name: BaseBillet_paiement_stripe; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_paiement_stripe" (uuid, detail, datetime, checkout_session_id_stripe, payment_intent_id, metadata_stripe, order_date, last_action, status, traitement_en_cours, source_traitement, source, total, reservation_id, user_id, customer_stripe, invoice_stripe, subscription) FROM stdin;
\.


--
-- Data for Name: BaseBillet_price; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_price" (uuid, name, prix, vat, stock, max_per_user, product_id, adhesion_obligatoire_id, long_description, short_description, subscription_type, recurring_payment) FROM stdin;
\.


--
-- Data for Name: BaseBillet_pricesold; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_pricesold" (uuid, id_price_stripe, qty_solded, prix, price_id, productsold_id, gift) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_product" (uuid, name, publish, img, categorie_article, long_description, short_description, terms_and_conditions_document, send_to_cashless, poids, archive, legal_link, nominative) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product_option_generale_checkbox; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_product_option_generale_checkbox" (id, product_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product_option_generale_radio; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_product_option_generale_radio" (id, product_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_product_tag; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_product_tag" (id, product_id, tag_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_productsold; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_productsold" (uuid, id_product_stripe, event_id, product_id, categorie_article) FROM stdin;
\.


--
-- Data for Name: BaseBillet_reservation; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_reservation" (uuid, datetime, status, to_mail, mail_send, mail_error, event_id, user_commande_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_reservation_options; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_reservation_options" (id, reservation_id, optiongenerale_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_tag; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_tag" (uuid, name, color) FROM stdin;
\.


--
-- Data for Name: BaseBillet_ticket; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_ticket" (uuid, first_name, last_name, status, seat, pricesold_id, reservation_id) FROM stdin;
\.


--
-- Data for Name: BaseBillet_webhook; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_webhook" (id, url, event, active, last_response) FROM stdin;
\.


--
-- Data for Name: BaseBillet_weekday; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan."BaseBillet_weekday" (id, day) FROM stdin;
1	0
2	1
3	2
4	3
5	4
6	5
7	6
\.


--
-- Data for Name: django_content_type; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan.django_content_type (id, app_label, model) FROM stdin;
1	Customers	client
2	Customers	domain
3	contenttypes	contenttype
4	auth	permission
5	auth	group
6	AuthBillet	tibilletuser
7	AuthBillet	humanuser
8	AuthBillet	superhumanuser
9	AuthBillet	termuser
10	AuthBillet	terminalpairingtoken
11	QrcodeCashless	detail
12	QrcodeCashless	cartecashless
13	QrcodeCashless	asset
14	QrcodeCashless	wallet
15	QrcodeCashless	syncfederatedlog
16	QrcodeCashless	federatedcashless
17	authtoken	token
18	authtoken	tokenproxy
19	token_blacklist	blacklistedtoken
20	token_blacklist	outstandingtoken
21	sessions	session
22	sites	site
23	admin	logentry
24	MetaBillet	eventdirectory
25	MetaBillet	productdirectory
26	root_billet	rootconfiguration
27	rest_framework_api_key	apikey
28	BaseBillet	event
29	BaseBillet	optiongenerale
30	BaseBillet	price
31	BaseBillet	pricesold
32	BaseBillet	product
33	BaseBillet	reservation
34	BaseBillet	ticket
35	BaseBillet	productsold
36	BaseBillet	paiement_stripe
37	BaseBillet	membership
38	BaseBillet	lignearticle
39	BaseBillet	configuration
40	BaseBillet	artist_on_event
41	BaseBillet	webhook
42	BaseBillet	externalapikey
43	BaseBillet	tag
44	BaseBillet	weekday
\.


--
-- Data for Name: django_migrations; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan.django_migrations (id, app, name, applied) FROM stdin;
1	contenttypes	0001_initial	2023-10-18 17:19:04.590249+04
2	contenttypes	0002_remove_content_type_name	2023-10-18 17:19:04.604082+04
3	auth	0001_initial	2023-10-18 17:19:04.617184+04
4	auth	0002_alter_permission_name_max_length	2023-10-18 17:19:04.625072+04
5	auth	0003_alter_user_email_max_length	2023-10-18 17:19:04.632577+04
6	auth	0004_alter_user_username_opts	2023-10-18 17:19:04.642084+04
7	auth	0005_alter_user_last_login_null	2023-10-18 17:19:04.648618+04
8	auth	0006_require_contenttypes_0002	2023-10-18 17:19:04.651998+04
9	auth	0007_alter_validators_add_error_messages	2023-10-18 17:19:04.659915+04
10	auth	0008_alter_user_username_max_length	2023-10-18 17:19:04.667366+04
11	auth	0009_alter_user_last_name_max_length	2023-10-18 17:19:04.673373+04
12	auth	0010_alter_group_name_max_length	2023-10-18 17:19:04.6783+04
13	auth	0011_update_proxy_permissions	2023-10-18 17:19:04.681658+04
14	auth	0012_alter_user_first_name_max_length	2023-10-18 17:19:04.689989+04
15	Customers	0001_initial	2023-10-18 17:19:04.699588+04
16	AuthBillet	0001_initial	2023-10-18 17:19:04.713052+04
17	AuthBillet	0002_alter_tibilletuser_is_active	2023-10-18 17:19:04.830035+04
18	AuthBillet	0003_tibilletuser_user_parent_pk	2023-10-18 17:19:04.840665+04
19	AuthBillet	0004_terminalpairingtoken	2023-10-18 17:19:04.851405+04
20	AuthBillet	0005_auto_20220422_1601	2023-10-18 17:19:04.887914+04
21	AuthBillet	0006_terminalpairingtoken_used	2023-10-18 17:19:04.897092+04
22	AuthBillet	0007_alter_terminalpairingtoken_datetime	2023-10-18 17:19:04.907886+04
23	AuthBillet	0008_alter_terminalpairingtoken_datetime	2023-10-18 17:19:04.919445+04
24	AuthBillet	0009_alter_tibilletuser_is_active	2023-10-18 17:19:04.930611+04
25	rest_framework_api_key	0001_initial	2023-10-18 17:19:04.964225+04
26	rest_framework_api_key	0002_auto_20190529_2243	2023-10-18 17:19:04.987333+04
27	rest_framework_api_key	0003_auto_20190623_1952	2023-10-18 17:19:05.001685+04
28	rest_framework_api_key	0004_prefix_hashed_key	2023-10-18 17:19:05.056702+04
29	rest_framework_api_key	0005_auto_20220110_1102	2023-10-18 17:19:05.06323+04
30	QrcodeCashless	0001_initial	2023-10-18 17:19:05.083621+04
31	BaseBillet	0001_initial	2023-10-18 17:19:05.930368+04
32	BaseBillet	0002_alter_ticket_seat	2023-10-18 17:19:05.9814+04
33	BaseBillet	0003_alter_reservation_user_commande	2023-10-18 17:19:06.07256+04
34	BaseBillet	0004_auto_20220421_1129	2023-10-18 17:19:06.105408+04
35	BaseBillet	0005_alter_reservation_status	2023-10-18 17:19:06.127734+04
36	BaseBillet	0006_auto_20220428_1533	2023-10-18 17:19:06.15738+04
37	BaseBillet	0007_alter_configuration_img	2023-10-18 17:19:06.172205+04
38	BaseBillet	0008_auto_20220505_1520	2023-10-18 17:19:06.195075+04
39	BaseBillet	0009_configuration_slug	2023-10-18 17:19:06.225536+04
40	BaseBillet	0010_auto_20220531_0920	2023-10-18 17:19:06.287176+04
41	BaseBillet	0011_membership_price	2023-10-18 17:19:06.317572+04
42	BaseBillet	0012_configuration_legal_documents	2023-10-18 17:19:06.330107+04
43	BaseBillet	0013_auto_20220602_1013	2023-10-18 17:19:06.433639+04
44	BaseBillet	0014_product_terms_and_conditions_document	2023-10-18 17:19:06.444237+04
45	BaseBillet	0015_price_subscription_type	2023-10-18 17:19:06.45714+04
46	BaseBillet	0016_alter_membership_unique_together	2023-10-18 17:19:06.47994+04
47	BaseBillet	0017_product_send_to_cashless	2023-10-18 17:19:06.491989+04
48	BaseBillet	0018_auto_20220608_1607	2023-10-18 17:19:06.519442+04
49	BaseBillet	0019_auto_20220624_0726	2023-10-18 17:19:06.552686+04
50	BaseBillet	0020_membership_stripe_id_subscription	2023-10-18 17:19:06.570738+04
51	BaseBillet	0021_paiement_stripe_invoice_stripe	2023-10-18 17:19:06.598486+04
52	BaseBillet	0022_paiement_stripe_subscription	2023-10-18 17:19:06.691835+04
53	BaseBillet	0023_membership_last_stripe_invoice	2023-10-18 17:19:06.706558+04
54	BaseBillet	0024_auto_20220626_1257	2023-10-18 17:19:06.760597+04
55	BaseBillet	0025_auto_20220810_1245	2023-10-18 17:19:06.787836+04
56	BaseBillet	0026_alter_configuration_slug	2023-10-18 17:19:06.800156+04
57	BaseBillet	0027_product_poids	2023-10-18 17:19:06.812047+04
58	BaseBillet	0028_auto_20220826_1559	2023-10-18 17:19:06.984467+04
59	BaseBillet	0029_remove_configuration_activer_billetterie	2023-10-18 17:19:06.997897+04
60	BaseBillet	0030_auto_20220927_1855	2023-10-18 17:19:07.039934+04
61	BaseBillet	0031_apikey	2023-10-18 17:19:07.069628+04
62	BaseBillet	0032_apikey_created	2023-10-18 17:19:07.076041+04
63	BaseBillet	0033_apikey_name	2023-10-18 17:19:07.094446+04
64	BaseBillet	0034_apikey_auth	2023-10-18 17:19:07.103078+04
65	BaseBillet	0035_alter_apikey_auth	2023-10-18 17:19:07.110505+04
66	BaseBillet	0036_remove_apikey_auth	2023-10-18 17:19:07.1175+04
67	BaseBillet	0037_auto_20221017_1320	2023-10-18 17:19:07.129568+04
68	BaseBillet	0038_apikey_product	2023-10-18 17:19:07.136819+04
69	BaseBillet	0039_auto_20221017_1402	2023-10-18 17:19:07.153676+04
70	BaseBillet	0040_apikey_user	2023-10-18 17:19:07.193486+04
71	BaseBillet	0041_auto_20221018_0932	2023-10-18 17:19:07.302681+04
72	BaseBillet	0042_webhook	2023-10-18 17:19:07.313968+04
73	BaseBillet	0043_webhook_active	2023-10-18 17:19:07.319272+04
74	BaseBillet	0044_webhook_last_response	2023-10-18 17:19:07.333597+04
75	BaseBillet	0045_auto_20221021_1031	2023-10-18 17:19:07.377851+04
76	BaseBillet	0046_alter_product_categorie_article	2023-10-18 17:19:07.408508+04
77	BaseBillet	0047_auto_20221121_1256	2023-10-18 17:19:07.434273+04
78	BaseBillet	0048_configuration_stripe_payouts_enabled	2023-10-18 17:19:07.44817+04
79	BaseBillet	0049_rename_apikey_externalapikey	2023-10-18 17:19:07.49269+04
80	BaseBillet	0050_alter_externalapikey_options	2023-10-18 17:19:07.506481+04
81	BaseBillet	0051_auto_20221125_1847	2023-10-18 17:19:07.552514+04
82	BaseBillet	0052_externalapikey_key	2023-10-18 17:19:07.591073+04
83	BaseBillet	0053_alter_externalapikey_options	2023-10-18 17:19:07.606622+04
84	BaseBillet	0054_price_recurring_payment	2023-10-18 17:19:07.621815+04
85	BaseBillet	0055_auto_20221215_1922	2023-10-18 17:19:07.685467+04
86	BaseBillet	0056_pricesold_gift	2023-10-18 17:19:07.699183+04
87	BaseBillet	0057_auto_20230102_1847	2023-10-18 17:19:07.754945+04
88	BaseBillet	0058_alter_paiement_stripe_status	2023-10-18 17:19:07.775788+04
89	BaseBillet	0059_event_cashless	2023-10-18 17:19:07.795324+04
90	BaseBillet	0060_event_minimum_cashless_required	2023-10-18 17:19:07.813684+04
91	BaseBillet	0061_configuration_federated_cashless	2023-10-18 17:19:07.829743+04
92	BaseBillet	0062_remove_configuration_mollie_api_key	2023-10-18 17:19:07.84446+04
93	BaseBillet	0063_auto_20230427_1105	2023-10-18 17:19:08.170432+04
94	BaseBillet	0064_auto_20230427_1146	2023-10-18 17:19:08.248954+04
95	BaseBillet	0065_auto_20230427_1248	2023-10-18 17:19:08.369566+04
96	BaseBillet	0066_optiongenerale_description	2023-10-18 17:19:08.419766+04
97	BaseBillet	0067_auto_20230427_1410	2023-10-18 17:19:08.543312+04
98	BaseBillet	0068_auto_20230427_1826	2023-10-18 17:19:08.619851+04
99	BaseBillet	0069_alter_optiongenerale_options	2023-10-18 17:19:08.63449+04
100	BaseBillet	0070_alter_configuration_short_description	2023-10-18 17:19:08.653535+04
101	BaseBillet	0071_event_tag	2023-10-18 17:19:08.712208+04
102	BaseBillet	0072_auto_20230522_1614	2023-10-18 17:19:08.770814+04
103	BaseBillet	0073_auto_20230523_1411	2023-10-18 17:19:08.795013+04
104	BaseBillet	0074_auto_20230523_1548	2023-10-18 17:19:09.049031+04
105	BaseBillet	0075_auto_20230524_1706	2023-10-18 17:19:09.108564+04
106	BaseBillet	0076_auto_20230525_1315	2023-10-18 17:19:09.132532+04
107	BaseBillet	0077_auto_20230525_1409	2023-10-18 17:19:09.17326+04
108	BaseBillet	0078_auto_20230602_1441	2023-10-18 17:19:09.210003+04
109	BaseBillet	0079_auto_20230822_0932	2023-10-18 17:19:09.266318+04
110	BaseBillet	0080_productsold_categorie_article	2023-10-18 17:19:09.363265+04
111	BaseBillet	0081_auto_20230822_1459	2023-10-18 17:19:09.394606+04
112	BaseBillet	0082_auto_20230906_1231	2023-10-18 17:19:09.471923+04
113	BaseBillet	0083_auto_20230906_1237	2023-10-18 17:19:09.523586+04
114	BaseBillet	0084_auto_20230906_1243	2023-10-18 17:19:09.575159+04
115	BaseBillet	0085_auto_20230908_1409	2023-10-18 17:19:09.66001+04
116	BaseBillet	0086_auto_20230908_1410	2023-10-18 17:19:09.692974+04
117	Customers	0002_alter_client_categorie	2023-10-18 17:19:09.727681+04
118	MetaBillet	0001_initial	2023-10-18 17:19:09.732289+04
119	MetaBillet	0002_auto_20220519_0904	2023-10-18 17:19:09.769677+04
120	MetaBillet	0003_productdirectory	2023-10-18 17:19:09.805746+04
121	QrcodeCashless	0002_alter_detail_img	2023-10-18 17:19:09.819336+04
122	QrcodeCashless	0003_auto_20221101_1820	2023-10-18 17:19:10.030858+04
123	QrcodeCashless	0004_detail_uuid	2023-10-18 17:19:10.045123+04
124	QrcodeCashless	0005_auto_20230103_1240	2023-10-18 17:19:10.110806+04
125	QrcodeCashless	0006_alter_wallet_unique_together	2023-10-18 17:19:10.128257+04
126	QrcodeCashless	0007_alter_wallet_unique_together	2023-10-18 17:19:10.147902+04
127	QrcodeCashless	0008_alter_cartecashless_uuid	2023-10-18 17:19:10.17156+04
128	QrcodeCashless	0009_federatedcashless_syncfederatedlog	2023-10-18 17:19:10.245367+04
129	QrcodeCashless	0010_auto_20230111_0701	2023-10-18 17:19:10.288675+04
130	QrcodeCashless	0011_auto_20230125_1445	2023-10-18 17:19:10.320004+04
131	QrcodeCashless	0012_syncfederatedlog_categorie	2023-10-18 17:19:10.345879+04
132	QrcodeCashless	0013_auto_20230125_1802	2023-10-18 17:19:10.499483+04
133	QrcodeCashless	0014_asset_categorie	2023-10-18 17:19:10.511332+04
134	QrcodeCashless	0015_alter_asset_unique_together	2023-10-18 17:19:10.524307+04
135	QrcodeCashless	0016_detail_slug	2023-10-18 17:19:10.537696+04
136	admin	0001_initial	2023-10-18 17:19:10.575908+04
137	admin	0002_logentry_remove_auto_add	2023-10-18 17:19:10.594961+04
138	admin	0003_logentry_add_action_flag_choices	2023-10-18 17:19:10.618438+04
139	authtoken	0001_initial	2023-10-18 17:19:10.656148+04
140	authtoken	0002_auto_20160226_1747	2023-10-18 17:19:10.739144+04
141	authtoken	0003_tokenproxy	2023-10-18 17:19:10.744935+04
142	root_billet	0001_initial	2023-10-18 17:19:10.750931+04
143	sessions	0001_initial	2023-10-18 17:19:10.75757+04
144	sites	0001_initial	2023-10-18 17:19:10.764657+04
145	sites	0002_alter_domain_unique	2023-10-18 17:19:10.771986+04
146	token_blacklist	0001_initial	2023-10-18 17:19:10.847547+04
147	token_blacklist	0002_outstandingtoken_jti_hex	2023-10-18 17:19:10.868409+04
148	token_blacklist	0003_auto_20171017_2007	2023-10-18 17:19:10.872611+04
149	token_blacklist	0004_auto_20171017_2013	2023-10-18 17:19:10.893312+04
150	token_blacklist	0005_remove_outstandingtoken_jti	2023-10-18 17:19:10.99284+04
151	token_blacklist	0006_auto_20171017_2113	2023-10-18 17:19:11.010471+04
152	token_blacklist	0007_auto_20171017_2214	2023-10-18 17:19:11.067697+04
153	token_blacklist	0008_migrate_to_bigautofield	2023-10-18 17:19:11.111546+04
154	token_blacklist	0010_fix_migrate_to_bigautofield	2023-10-18 17:19:11.160042+04
155	token_blacklist	0011_linearizes_history	2023-10-18 17:19:11.163248+04
156	token_blacklist	0012_alter_outstandingtoken_user	2023-10-18 17:19:11.203183+04
\.


--
-- Data for Name: rest_framework_api_key_apikey; Type: TABLE DATA; Schema: ziskakan; Owner: ticket_postgres_user
--

COPY ziskakan.rest_framework_api_key_apikey (id, created, name, revoked, expiry_date, hashed_key, prefix) FROM stdin;
\.


--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_apikey_id_seq"', 1, false);


--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_artist_on_event_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_configuration_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio_id_seq"', 1, false);


--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_event_options_checkbox_id_seq"', 1, false);


--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_event_options_radio_id_seq"', 1, false);


--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_event_products_id_seq"', 1, false);


--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_event_recurrent_id_seq"', 1, false);


--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_event_tag_id_seq"', 1, false);


--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_membership_id_seq"', 1, false);


--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_membership_option_generale_id_seq"', 1, false);


--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox_id_seq"', 1, false);


--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_product_option_generale_radio_id_seq"', 1, false);


--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_product_tag_id_seq"', 1, false);


--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_reservation_options_id_seq"', 1, false);


--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_webhook_id_seq"', 1, false);


--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system"."BaseBillet_weekday_id_seq"', 7, true);


--
-- Name: django_content_type_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system".django_content_type_id_seq', 44, true);


--
-- Name: django_migrations_id_seq; Type: SEQUENCE SET; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('"balaphonik-sound-system".django_migrations_id_seq', 156, true);


--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_apikey_id_seq"', 1, false);


--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_artist_on_event_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_configuration_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_configuration_option_generale_checkbox_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_configuration_option_generale_radio_id_seq"', 1, false);


--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_event_options_checkbox_id_seq"', 1, false);


--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_event_options_radio_id_seq"', 1, false);


--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_event_products_id_seq"', 1, false);


--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_event_recurrent_id_seq"', 1, false);


--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_event_tag_id_seq"', 1, false);


--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_membership_id_seq"', 1, false);


--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_membership_option_generale_id_seq"', 1, false);


--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_product_option_generale_checkbox_id_seq"', 1, false);


--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_product_option_generale_radio_id_seq"', 1, false);


--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_product_tag_id_seq"', 1, false);


--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_reservation_options_id_seq"', 1, false);


--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_webhook_id_seq"', 1, false);


--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan."BaseBillet_weekday_id_seq"', 7, true);


--
-- Name: django_content_type_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan.django_content_type_id_seq', 44, true);


--
-- Name: django_migrations_id_seq; Type: SEQUENCE SET; Schema: billetistan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('billetistan.django_migrations_id_seq', 156, true);


--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_apikey_id_seq"', 1, false);


--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_artist_on_event_id_seq"', 2, true);


--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_configuration_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_configuration_option_generale_checkbox_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_configuration_option_generale_radio_id_seq"', 1, false);


--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_event_options_checkbox_id_seq"', 6, true);


--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_event_options_radio_id_seq"', 5, true);


--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_event_products_id_seq"', 14, true);


--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_event_recurrent_id_seq"', 1, false);


--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_event_tag_id_seq"', 8, true);


--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_membership_id_seq"', 1, false);


--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_membership_option_generale_id_seq"', 1, false);


--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_product_option_generale_checkbox_id_seq"', 2, true);


--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_product_option_generale_radio_id_seq"', 5, true);


--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_product_tag_id_seq"', 1, false);


--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_reservation_options_id_seq"', 1, false);


--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_webhook_id_seq"', 1, false);


--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo."BaseBillet_weekday_id_seq"', 7, true);


--
-- Name: django_content_type_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo.django_content_type_id_seq', 44, true);


--
-- Name: django_migrations_id_seq; Type: SEQUENCE SET; Schema: demo; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('demo.django_migrations_id_seq', 156, true);


--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_apikey_id_seq"', 1, false);


--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_artist_on_event_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_configuration_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_configuration_option_generale_checkbox_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_configuration_option_generale_radio_id_seq"', 1, false);


--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_event_options_checkbox_id_seq"', 1, false);


--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_event_options_radio_id_seq"', 1, false);


--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_event_products_id_seq"', 1, false);


--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_event_recurrent_id_seq"', 1, false);


--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_event_tag_id_seq"', 1, false);


--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_membership_id_seq"', 1, false);


--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_membership_option_generale_id_seq"', 1, false);


--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_product_option_generale_checkbox_id_seq"', 1, false);


--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_product_option_generale_radio_id_seq"', 1, false);


--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_product_tag_id_seq"', 1, false);


--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_reservation_options_id_seq"', 1, false);


--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_webhook_id_seq"', 1, false);


--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta."BaseBillet_weekday_id_seq"', 7, true);


--
-- Name: django_content_type_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta.django_content_type_id_seq', 44, true);


--
-- Name: django_migrations_id_seq; Type: SEQUENCE SET; Schema: meta; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('meta.django_migrations_id_seq', 156, true);


--
-- Name: AuthBillet_terminalpairingtoken_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public."AuthBillet_terminalpairingtoken_id_seq"', 1, false);


--
-- Name: AuthBillet_tibilletuser_client_achat_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public."AuthBillet_tibilletuser_client_achat_id_seq"', 1, false);


--
-- Name: AuthBillet_tibilletuser_client_admin_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public."AuthBillet_tibilletuser_client_admin_id_seq"', 4, true);


--
-- Name: AuthBillet_tibilletuser_groups_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public."AuthBillet_tibilletuser_groups_id_seq"', 4, true);


--
-- Name: AuthBillet_tibilletuser_user_permissions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public."AuthBillet_tibilletuser_user_permissions_id_seq"', 1, false);


--
-- Name: Customers_domain_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public."Customers_domain_id_seq"', 8, true);


--
-- Name: MetaBillet_eventdirectory_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public."MetaBillet_eventdirectory_id_seq"', 2, true);


--
-- Name: MetaBillet_productdirectory_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public."MetaBillet_productdirectory_id_seq"', 1, false);


--
-- Name: QrcodeCashless_cartecashless_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public."QrcodeCashless_cartecashless_id_seq"', 12, true);


--
-- Name: QrcodeCashless_detail_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public."QrcodeCashless_detail_id_seq"', 1, true);


--
-- Name: QrcodeCashless_syncfederatedlog_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public."QrcodeCashless_syncfederatedlog_id_seq"', 1, false);


--
-- Name: auth_group_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public.auth_group_id_seq', 1, true);


--
-- Name: auth_group_permissions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public.auth_group_permissions_id_seq', 43, true);


--
-- Name: auth_permission_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public.auth_permission_id_seq', 352, true);


--
-- Name: django_admin_log_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public.django_admin_log_id_seq', 1, false);


--
-- Name: django_content_type_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public.django_content_type_id_seq', 44, true);


--
-- Name: django_migrations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public.django_migrations_id_seq', 156, true);


--
-- Name: django_site_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public.django_site_id_seq', 1, true);


--
-- Name: root_billet_rootconfiguration_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public.root_billet_rootconfiguration_id_seq', 1, false);


--
-- Name: token_blacklist_blacklistedtoken_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public.token_blacklist_blacklistedtoken_id_seq', 1, false);


--
-- Name: token_blacklist_outstandingtoken_id_seq; Type: SEQUENCE SET; Schema: public; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('public.token_blacklist_outstandingtoken_id_seq', 1, true);


--
-- Name: BaseBillet_apikey_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_apikey_id_seq"', 1, false);


--
-- Name: BaseBillet_artist_on_event_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_artist_on_event_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_configuration_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_option_generale_checkbox_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_configuration_option_generale_checkbox_id_seq"', 1, false);


--
-- Name: BaseBillet_configuration_option_generale_radio_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_configuration_option_generale_radio_id_seq"', 1, false);


--
-- Name: BaseBillet_event_options_checkbox_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_event_options_checkbox_id_seq"', 1, false);


--
-- Name: BaseBillet_event_options_radio_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_event_options_radio_id_seq"', 1, false);


--
-- Name: BaseBillet_event_products_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_event_products_id_seq"', 1, false);


--
-- Name: BaseBillet_event_recurrent_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_event_recurrent_id_seq"', 1, false);


--
-- Name: BaseBillet_event_tag_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_event_tag_id_seq"', 1, false);


--
-- Name: BaseBillet_membership_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_membership_id_seq"', 1, false);


--
-- Name: BaseBillet_membership_option_generale_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_membership_option_generale_id_seq"', 1, false);


--
-- Name: BaseBillet_product_option_generale_checkbox_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_product_option_generale_checkbox_id_seq"', 1, false);


--
-- Name: BaseBillet_product_option_generale_radio_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_product_option_generale_radio_id_seq"', 1, false);


--
-- Name: BaseBillet_product_tag_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_product_tag_id_seq"', 1, false);


--
-- Name: BaseBillet_reservation_options_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_reservation_options_id_seq"', 1, false);


--
-- Name: BaseBillet_webhook_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_webhook_id_seq"', 1, false);


--
-- Name: BaseBillet_weekday_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan."BaseBillet_weekday_id_seq"', 7, true);


--
-- Name: django_content_type_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan.django_content_type_id_seq', 44, true);


--
-- Name: django_migrations_id_seq; Type: SEQUENCE SET; Schema: ziskakan; Owner: ticket_postgres_user
--

SELECT pg_catalog.setval('ziskakan.django_migrations_id_seq', 156, true);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_name_key; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_name_key" UNIQUE (name);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_user_id_key; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_user_id_key" UNIQUE (user_id);


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_event_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_event_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configuration_configuration_id_optiong_5a48033a_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configuration_configuration_id_optiong_5a48033a_uniq" UNIQUE (configuration_id, optiongenerale_id);


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configuration_configuration_id_optiong_83744681_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configuration_configuration_id_optiong_83744681_uniq" UNIQUE (configuration_id, optiongenerale_id);


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configuration_option_generale_checkbox_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configuration_option_generale_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configuration_option_generale_radio_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configuration_option_generale_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration BaseBillet_configuration_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_configuration"
    ADD CONSTRAINT "BaseBillet_configuration_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_name_datetime_0e242bcf_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_name_datetime_0e242bcf_uniq" UNIQUE (name, datetime);


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_options_checkbox_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_options_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_options_event_id_optiongenerale__b37606e9_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_options_event_id_optiongenerale__b37606e9_uniq" UNIQUE (event_id, optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_options_event_id_optiongenerale__f1ff3e5e_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_options_event_id_optiongenerale__f1ff3e5e_uniq" UNIQUE (event_id, optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_options_radio_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_options_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_event_products BaseBillet_event_products_event_id_product_id_0292c8a3_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_products_event_id_product_id_0292c8a3_uniq" UNIQUE (event_id, product_id);


--
-- Name: BaseBillet_event_products BaseBillet_event_products_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_products_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_recurrent_event_id_weekday_id_0f8358b4_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_recurrent_event_id_weekday_id_0f8358b4_uniq" UNIQUE (event_id, weekday_id);


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_recurrent_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_recurrent_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_slug_key; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_slug_key" UNIQUE (slug);


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_event_id_tag_id_6f9dba44_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_event_id_tag_id_6f9dba44_uniq" UNIQUE (event_id, tag_id);


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_externalapikey BaseBillet_externalapikey_key_id_key; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_externalapikey_key_id_key" UNIQUE (key_id);


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearticle_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearticle_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membership_op_membership_id_optiongene_32d9eed9_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membership_op_membership_id_optiongene_32d9eed9_uniq" UNIQUE (membership_id, optiongenerale_id);


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membership_option_generale_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membership_option_generale_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_membership BaseBillet_membership_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membership_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_membership BaseBillet_membership_user_id_price_id_22c167ba_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membership_user_id_price_id_22c167ba_uniq" UNIQUE (user_id, price_id);


--
-- Name: BaseBillet_optiongenerale BaseBillet_optiongenerale_name_key; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_optiongenerale"
    ADD CONSTRAINT "BaseBillet_optiongenerale_name_key" UNIQUE (name);


--
-- Name: BaseBillet_optiongenerale BaseBillet_optiongenerale_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_optiongenerale"
    ADD CONSTRAINT "BaseBillet_optiongenerale_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement_stripe_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement_stripe_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_price BaseBillet_price_name_product_id_cf5fcf03_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_name_product_id_cf5fcf03_uniq" UNIQUE (name, product_id);


--
-- Name: BaseBillet_price BaseBillet_price_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_product BaseBillet_product_categorie_article_name_fa9da1c7_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product"
    ADD CONSTRAINT "BaseBillet_product_categorie_article_name_fa9da1c7_uniq" UNIQUE (categorie_article, name);


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_optio_product_id_optiongeneral_09a1ea40_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_optio_product_id_optiongeneral_09a1ea40_uniq" UNIQUE (product_id, optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_optio_product_id_optiongeneral_bdb7af0e_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_optio_product_id_optiongeneral_bdb7af0e_uniq" UNIQUE (product_id, optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_option_generale_checkbox_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_option_generale_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_option_generale_radio_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_option_generale_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product BaseBillet_product_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product"
    ADD CONSTRAINT "BaseBillet_product_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_product_id_tag_id_d023f294_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_product_id_tag_id_d023f294_uniq" UNIQUE (product_id, tag_id);


--
-- Name: BaseBillet_productsold BaseBillet_productsold_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productsold_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_reservation_options BaseBillet_reservation_o_reservation_id_optiongen_bd545d00_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservation_o_reservation_id_optiongen_bd545d00_uniq" UNIQUE (reservation_id, optiongenerale_id);


--
-- Name: BaseBillet_reservation_options BaseBillet_reservation_options_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservation_options_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_reservation BaseBillet_reservation_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservation_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_tag BaseBillet_tag_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_tag"
    ADD CONSTRAINT "BaseBillet_tag_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_ticket BaseBillet_ticket_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_webhook BaseBillet_webhook_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_webhook"
    ADD CONSTRAINT "BaseBillet_webhook_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_weekday BaseBillet_weekday_day_key; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_weekday"
    ADD CONSTRAINT "BaseBillet_weekday_day_key" UNIQUE (day);


--
-- Name: BaseBillet_weekday BaseBillet_weekday_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_weekday"
    ADD CONSTRAINT "BaseBillet_weekday_pkey" PRIMARY KEY (id);


--
-- Name: django_content_type django_content_type_app_label_model_76bd3d3b_uniq; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system".django_content_type
    ADD CONSTRAINT django_content_type_app_label_model_76bd3d3b_uniq UNIQUE (app_label, model);


--
-- Name: django_content_type django_content_type_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system".django_content_type
    ADD CONSTRAINT django_content_type_pkey PRIMARY KEY (id);


--
-- Name: django_migrations django_migrations_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system".django_migrations
    ADD CONSTRAINT django_migrations_pkey PRIMARY KEY (id);


--
-- Name: rest_framework_api_key_apikey rest_framework_api_key_apikey_pkey; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system".rest_framework_api_key_apikey
    ADD CONSTRAINT rest_framework_api_key_apikey_pkey PRIMARY KEY (id);


--
-- Name: rest_framework_api_key_apikey rest_framework_api_key_apikey_prefix_key; Type: CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system".rest_framework_api_key_apikey
    ADD CONSTRAINT rest_framework_api_key_apikey_prefix_key UNIQUE (prefix);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_name_key; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_name_key" UNIQUE (name);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_user_id_key; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_user_id_key" UNIQUE (user_id);


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_event_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_event_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configuration_configuration_id_optiong_5a48033a_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configuration_configuration_id_optiong_5a48033a_uniq" UNIQUE (configuration_id, optiongenerale_id);


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configuration_configuration_id_optiong_83744681_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configuration_configuration_id_optiong_83744681_uniq" UNIQUE (configuration_id, optiongenerale_id);


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configuration_option_generale_checkbox_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configuration_option_generale_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configuration_option_generale_radio_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configuration_option_generale_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration BaseBillet_configuration_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_configuration"
    ADD CONSTRAINT "BaseBillet_configuration_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_name_datetime_0e242bcf_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_name_datetime_0e242bcf_uniq" UNIQUE (name, datetime);


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_options_checkbox_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_options_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_options_event_id_optiongenerale__b37606e9_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_options_event_id_optiongenerale__b37606e9_uniq" UNIQUE (event_id, optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_options_event_id_optiongenerale__f1ff3e5e_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_options_event_id_optiongenerale__f1ff3e5e_uniq" UNIQUE (event_id, optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_options_radio_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_options_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_event_products BaseBillet_event_products_event_id_product_id_0292c8a3_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_products_event_id_product_id_0292c8a3_uniq" UNIQUE (event_id, product_id);


--
-- Name: BaseBillet_event_products BaseBillet_event_products_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_products_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_recurrent_event_id_weekday_id_0f8358b4_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_recurrent_event_id_weekday_id_0f8358b4_uniq" UNIQUE (event_id, weekday_id);


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_recurrent_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_recurrent_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_slug_key; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_slug_key" UNIQUE (slug);


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_event_id_tag_id_6f9dba44_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_event_id_tag_id_6f9dba44_uniq" UNIQUE (event_id, tag_id);


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_externalapikey BaseBillet_externalapikey_key_id_key; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_externalapikey_key_id_key" UNIQUE (key_id);


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearticle_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearticle_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membership_op_membership_id_optiongene_32d9eed9_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membership_op_membership_id_optiongene_32d9eed9_uniq" UNIQUE (membership_id, optiongenerale_id);


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membership_option_generale_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membership_option_generale_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_membership BaseBillet_membership_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membership_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_membership BaseBillet_membership_user_id_price_id_22c167ba_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membership_user_id_price_id_22c167ba_uniq" UNIQUE (user_id, price_id);


--
-- Name: BaseBillet_optiongenerale BaseBillet_optiongenerale_name_key; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_optiongenerale"
    ADD CONSTRAINT "BaseBillet_optiongenerale_name_key" UNIQUE (name);


--
-- Name: BaseBillet_optiongenerale BaseBillet_optiongenerale_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_optiongenerale"
    ADD CONSTRAINT "BaseBillet_optiongenerale_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement_stripe_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement_stripe_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_price BaseBillet_price_name_product_id_cf5fcf03_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_name_product_id_cf5fcf03_uniq" UNIQUE (name, product_id);


--
-- Name: BaseBillet_price BaseBillet_price_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_product BaseBillet_product_categorie_article_name_fa9da1c7_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product"
    ADD CONSTRAINT "BaseBillet_product_categorie_article_name_fa9da1c7_uniq" UNIQUE (categorie_article, name);


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_optio_product_id_optiongeneral_09a1ea40_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_optio_product_id_optiongeneral_09a1ea40_uniq" UNIQUE (product_id, optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_optio_product_id_optiongeneral_bdb7af0e_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_optio_product_id_optiongeneral_bdb7af0e_uniq" UNIQUE (product_id, optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_option_generale_checkbox_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_option_generale_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_option_generale_radio_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_option_generale_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product BaseBillet_product_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product"
    ADD CONSTRAINT "BaseBillet_product_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_product_id_tag_id_d023f294_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_product_id_tag_id_d023f294_uniq" UNIQUE (product_id, tag_id);


--
-- Name: BaseBillet_productsold BaseBillet_productsold_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productsold_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_reservation_options BaseBillet_reservation_o_reservation_id_optiongen_bd545d00_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservation_o_reservation_id_optiongen_bd545d00_uniq" UNIQUE (reservation_id, optiongenerale_id);


--
-- Name: BaseBillet_reservation_options BaseBillet_reservation_options_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservation_options_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_reservation BaseBillet_reservation_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservation_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_tag BaseBillet_tag_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_tag"
    ADD CONSTRAINT "BaseBillet_tag_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_ticket BaseBillet_ticket_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_webhook BaseBillet_webhook_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_webhook"
    ADD CONSTRAINT "BaseBillet_webhook_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_weekday BaseBillet_weekday_day_key; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_weekday"
    ADD CONSTRAINT "BaseBillet_weekday_day_key" UNIQUE (day);


--
-- Name: BaseBillet_weekday BaseBillet_weekday_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_weekday"
    ADD CONSTRAINT "BaseBillet_weekday_pkey" PRIMARY KEY (id);


--
-- Name: django_content_type django_content_type_app_label_model_76bd3d3b_uniq; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan.django_content_type
    ADD CONSTRAINT django_content_type_app_label_model_76bd3d3b_uniq UNIQUE (app_label, model);


--
-- Name: django_content_type django_content_type_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan.django_content_type
    ADD CONSTRAINT django_content_type_pkey PRIMARY KEY (id);


--
-- Name: django_migrations django_migrations_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan.django_migrations
    ADD CONSTRAINT django_migrations_pkey PRIMARY KEY (id);


--
-- Name: rest_framework_api_key_apikey rest_framework_api_key_apikey_pkey; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan.rest_framework_api_key_apikey
    ADD CONSTRAINT rest_framework_api_key_apikey_pkey PRIMARY KEY (id);


--
-- Name: rest_framework_api_key_apikey rest_framework_api_key_apikey_prefix_key; Type: CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan.rest_framework_api_key_apikey
    ADD CONSTRAINT rest_framework_api_key_apikey_prefix_key UNIQUE (prefix);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_name_key; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_name_key" UNIQUE (name);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_user_id_key; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_user_id_key" UNIQUE (user_id);


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_event_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_event_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configuration_configuration_id_optiong_5a48033a_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configuration_configuration_id_optiong_5a48033a_uniq" UNIQUE (configuration_id, optiongenerale_id);


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configuration_configuration_id_optiong_83744681_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configuration_configuration_id_optiong_83744681_uniq" UNIQUE (configuration_id, optiongenerale_id);


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configuration_option_generale_checkbox_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configuration_option_generale_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configuration_option_generale_radio_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configuration_option_generale_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration BaseBillet_configuration_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_configuration"
    ADD CONSTRAINT "BaseBillet_configuration_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_name_datetime_0e242bcf_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_name_datetime_0e242bcf_uniq" UNIQUE (name, datetime);


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_options_checkbox_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_options_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_options_event_id_optiongenerale__b37606e9_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_options_event_id_optiongenerale__b37606e9_uniq" UNIQUE (event_id, optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_options_event_id_optiongenerale__f1ff3e5e_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_options_event_id_optiongenerale__f1ff3e5e_uniq" UNIQUE (event_id, optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_options_radio_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_options_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_event_products BaseBillet_event_products_event_id_product_id_0292c8a3_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_products_event_id_product_id_0292c8a3_uniq" UNIQUE (event_id, product_id);


--
-- Name: BaseBillet_event_products BaseBillet_event_products_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_products_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_recurrent_event_id_weekday_id_0f8358b4_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_recurrent_event_id_weekday_id_0f8358b4_uniq" UNIQUE (event_id, weekday_id);


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_recurrent_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_recurrent_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_slug_key; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_slug_key" UNIQUE (slug);


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_event_id_tag_id_6f9dba44_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_event_id_tag_id_6f9dba44_uniq" UNIQUE (event_id, tag_id);


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_externalapikey BaseBillet_externalapikey_key_id_key; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_externalapikey_key_id_key" UNIQUE (key_id);


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearticle_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearticle_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membership_op_membership_id_optiongene_32d9eed9_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membership_op_membership_id_optiongene_32d9eed9_uniq" UNIQUE (membership_id, optiongenerale_id);


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membership_option_generale_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membership_option_generale_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_membership BaseBillet_membership_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membership_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_membership BaseBillet_membership_user_id_price_id_22c167ba_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membership_user_id_price_id_22c167ba_uniq" UNIQUE (user_id, price_id);


--
-- Name: BaseBillet_optiongenerale BaseBillet_optiongenerale_name_key; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_optiongenerale"
    ADD CONSTRAINT "BaseBillet_optiongenerale_name_key" UNIQUE (name);


--
-- Name: BaseBillet_optiongenerale BaseBillet_optiongenerale_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_optiongenerale"
    ADD CONSTRAINT "BaseBillet_optiongenerale_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement_stripe_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement_stripe_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_price BaseBillet_price_name_product_id_cf5fcf03_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_name_product_id_cf5fcf03_uniq" UNIQUE (name, product_id);


--
-- Name: BaseBillet_price BaseBillet_price_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_product BaseBillet_product_categorie_article_name_fa9da1c7_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product"
    ADD CONSTRAINT "BaseBillet_product_categorie_article_name_fa9da1c7_uniq" UNIQUE (categorie_article, name);


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_optio_product_id_optiongeneral_09a1ea40_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_optio_product_id_optiongeneral_09a1ea40_uniq" UNIQUE (product_id, optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_optio_product_id_optiongeneral_bdb7af0e_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_optio_product_id_optiongeneral_bdb7af0e_uniq" UNIQUE (product_id, optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_option_generale_checkbox_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_option_generale_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_option_generale_radio_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_option_generale_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product BaseBillet_product_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product"
    ADD CONSTRAINT "BaseBillet_product_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_product_id_tag_id_d023f294_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_product_id_tag_id_d023f294_uniq" UNIQUE (product_id, tag_id);


--
-- Name: BaseBillet_productsold BaseBillet_productsold_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productsold_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_reservation_options BaseBillet_reservation_o_reservation_id_optiongen_bd545d00_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservation_o_reservation_id_optiongen_bd545d00_uniq" UNIQUE (reservation_id, optiongenerale_id);


--
-- Name: BaseBillet_reservation_options BaseBillet_reservation_options_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservation_options_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_reservation BaseBillet_reservation_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservation_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_tag BaseBillet_tag_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_tag"
    ADD CONSTRAINT "BaseBillet_tag_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_ticket BaseBillet_ticket_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_webhook BaseBillet_webhook_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_webhook"
    ADD CONSTRAINT "BaseBillet_webhook_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_weekday BaseBillet_weekday_day_key; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_weekday"
    ADD CONSTRAINT "BaseBillet_weekday_day_key" UNIQUE (day);


--
-- Name: BaseBillet_weekday BaseBillet_weekday_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_weekday"
    ADD CONSTRAINT "BaseBillet_weekday_pkey" PRIMARY KEY (id);


--
-- Name: django_content_type django_content_type_app_label_model_76bd3d3b_uniq; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo.django_content_type
    ADD CONSTRAINT django_content_type_app_label_model_76bd3d3b_uniq UNIQUE (app_label, model);


--
-- Name: django_content_type django_content_type_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo.django_content_type
    ADD CONSTRAINT django_content_type_pkey PRIMARY KEY (id);


--
-- Name: django_migrations django_migrations_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo.django_migrations
    ADD CONSTRAINT django_migrations_pkey PRIMARY KEY (id);


--
-- Name: rest_framework_api_key_apikey rest_framework_api_key_apikey_pkey; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo.rest_framework_api_key_apikey
    ADD CONSTRAINT rest_framework_api_key_apikey_pkey PRIMARY KEY (id);


--
-- Name: rest_framework_api_key_apikey rest_framework_api_key_apikey_prefix_key; Type: CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo.rest_framework_api_key_apikey
    ADD CONSTRAINT rest_framework_api_key_apikey_prefix_key UNIQUE (prefix);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_name_key; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_name_key" UNIQUE (name);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_user_id_key; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_user_id_key" UNIQUE (user_id);


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_event_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_event_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configuration_configuration_id_optiong_5a48033a_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configuration_configuration_id_optiong_5a48033a_uniq" UNIQUE (configuration_id, optiongenerale_id);


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configuration_configuration_id_optiong_83744681_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configuration_configuration_id_optiong_83744681_uniq" UNIQUE (configuration_id, optiongenerale_id);


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configuration_option_generale_checkbox_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configuration_option_generale_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configuration_option_generale_radio_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configuration_option_generale_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration BaseBillet_configuration_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_configuration"
    ADD CONSTRAINT "BaseBillet_configuration_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_name_datetime_0e242bcf_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_name_datetime_0e242bcf_uniq" UNIQUE (name, datetime);


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_options_checkbox_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_options_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_options_event_id_optiongenerale__b37606e9_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_options_event_id_optiongenerale__b37606e9_uniq" UNIQUE (event_id, optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_options_event_id_optiongenerale__f1ff3e5e_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_options_event_id_optiongenerale__f1ff3e5e_uniq" UNIQUE (event_id, optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_options_radio_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_options_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_event_products BaseBillet_event_products_event_id_product_id_0292c8a3_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_products_event_id_product_id_0292c8a3_uniq" UNIQUE (event_id, product_id);


--
-- Name: BaseBillet_event_products BaseBillet_event_products_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_products_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_recurrent_event_id_weekday_id_0f8358b4_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_recurrent_event_id_weekday_id_0f8358b4_uniq" UNIQUE (event_id, weekday_id);


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_recurrent_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_recurrent_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_slug_key; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_slug_key" UNIQUE (slug);


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_event_id_tag_id_6f9dba44_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_event_id_tag_id_6f9dba44_uniq" UNIQUE (event_id, tag_id);


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_externalapikey BaseBillet_externalapikey_key_id_key; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_externalapikey_key_id_key" UNIQUE (key_id);


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearticle_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearticle_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membership_op_membership_id_optiongene_32d9eed9_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membership_op_membership_id_optiongene_32d9eed9_uniq" UNIQUE (membership_id, optiongenerale_id);


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membership_option_generale_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membership_option_generale_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_membership BaseBillet_membership_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membership_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_membership BaseBillet_membership_user_id_price_id_22c167ba_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membership_user_id_price_id_22c167ba_uniq" UNIQUE (user_id, price_id);


--
-- Name: BaseBillet_optiongenerale BaseBillet_optiongenerale_name_key; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_optiongenerale"
    ADD CONSTRAINT "BaseBillet_optiongenerale_name_key" UNIQUE (name);


--
-- Name: BaseBillet_optiongenerale BaseBillet_optiongenerale_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_optiongenerale"
    ADD CONSTRAINT "BaseBillet_optiongenerale_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement_stripe_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement_stripe_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_price BaseBillet_price_name_product_id_cf5fcf03_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_name_product_id_cf5fcf03_uniq" UNIQUE (name, product_id);


--
-- Name: BaseBillet_price BaseBillet_price_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_product BaseBillet_product_categorie_article_name_fa9da1c7_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product"
    ADD CONSTRAINT "BaseBillet_product_categorie_article_name_fa9da1c7_uniq" UNIQUE (categorie_article, name);


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_optio_product_id_optiongeneral_09a1ea40_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_optio_product_id_optiongeneral_09a1ea40_uniq" UNIQUE (product_id, optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_optio_product_id_optiongeneral_bdb7af0e_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_optio_product_id_optiongeneral_bdb7af0e_uniq" UNIQUE (product_id, optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_option_generale_checkbox_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_option_generale_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_option_generale_radio_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_option_generale_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product BaseBillet_product_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product"
    ADD CONSTRAINT "BaseBillet_product_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_product_id_tag_id_d023f294_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_product_id_tag_id_d023f294_uniq" UNIQUE (product_id, tag_id);


--
-- Name: BaseBillet_productsold BaseBillet_productsold_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productsold_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_reservation_options BaseBillet_reservation_o_reservation_id_optiongen_bd545d00_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservation_o_reservation_id_optiongen_bd545d00_uniq" UNIQUE (reservation_id, optiongenerale_id);


--
-- Name: BaseBillet_reservation_options BaseBillet_reservation_options_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservation_options_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_reservation BaseBillet_reservation_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservation_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_tag BaseBillet_tag_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_tag"
    ADD CONSTRAINT "BaseBillet_tag_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_ticket BaseBillet_ticket_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_webhook BaseBillet_webhook_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_webhook"
    ADD CONSTRAINT "BaseBillet_webhook_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_weekday BaseBillet_weekday_day_key; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_weekday"
    ADD CONSTRAINT "BaseBillet_weekday_day_key" UNIQUE (day);


--
-- Name: BaseBillet_weekday BaseBillet_weekday_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_weekday"
    ADD CONSTRAINT "BaseBillet_weekday_pkey" PRIMARY KEY (id);


--
-- Name: django_content_type django_content_type_app_label_model_76bd3d3b_uniq; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta.django_content_type
    ADD CONSTRAINT django_content_type_app_label_model_76bd3d3b_uniq UNIQUE (app_label, model);


--
-- Name: django_content_type django_content_type_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta.django_content_type
    ADD CONSTRAINT django_content_type_pkey PRIMARY KEY (id);


--
-- Name: django_migrations django_migrations_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta.django_migrations
    ADD CONSTRAINT django_migrations_pkey PRIMARY KEY (id);


--
-- Name: rest_framework_api_key_apikey rest_framework_api_key_apikey_pkey; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta.rest_framework_api_key_apikey
    ADD CONSTRAINT rest_framework_api_key_apikey_pkey PRIMARY KEY (id);


--
-- Name: rest_framework_api_key_apikey rest_framework_api_key_apikey_prefix_key; Type: CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta.rest_framework_api_key_apikey
    ADD CONSTRAINT rest_framework_api_key_apikey_prefix_key UNIQUE (prefix);


--
-- Name: AuthBillet_terminalpairingtoken AuthBillet_terminalpairingtoken_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_terminalpairingtoken"
    ADD CONSTRAINT "AuthBillet_terminalpairingtoken_pkey" PRIMARY KEY (id);


--
-- Name: AuthBillet_tibilletuser_client_admin AuthBillet_tibilletuser__tibilletuser_id_client_i_50f0a528_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_client_admin"
    ADD CONSTRAINT "AuthBillet_tibilletuser__tibilletuser_id_client_i_50f0a528_uniq" UNIQUE (tibilletuser_id, client_id);


--
-- Name: AuthBillet_tibilletuser_client_achat AuthBillet_tibilletuser__tibilletuser_id_client_i_a771d6b7_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_client_achat"
    ADD CONSTRAINT "AuthBillet_tibilletuser__tibilletuser_id_client_i_a771d6b7_uniq" UNIQUE (tibilletuser_id, client_id);


--
-- Name: AuthBillet_tibilletuser_groups AuthBillet_tibilletuser__tibilletuser_id_group_id_69ddfff3_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_groups"
    ADD CONSTRAINT "AuthBillet_tibilletuser__tibilletuser_id_group_id_69ddfff3_uniq" UNIQUE (tibilletuser_id, group_id);


--
-- Name: AuthBillet_tibilletuser_user_permissions AuthBillet_tibilletuser__tibilletuser_id_permissi_f1e9832d_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_user_permissions"
    ADD CONSTRAINT "AuthBillet_tibilletuser__tibilletuser_id_permissi_f1e9832d_uniq" UNIQUE (tibilletuser_id, permission_id);


--
-- Name: AuthBillet_tibilletuser_client_achat AuthBillet_tibilletuser_client_achat_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_client_achat"
    ADD CONSTRAINT "AuthBillet_tibilletuser_client_achat_pkey" PRIMARY KEY (id);


--
-- Name: AuthBillet_tibilletuser_client_admin AuthBillet_tibilletuser_client_admin_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_client_admin"
    ADD CONSTRAINT "AuthBillet_tibilletuser_client_admin_pkey" PRIMARY KEY (id);


--
-- Name: AuthBillet_tibilletuser AuthBillet_tibilletuser_email_key; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser"
    ADD CONSTRAINT "AuthBillet_tibilletuser_email_key" UNIQUE (email);


--
-- Name: AuthBillet_tibilletuser_groups AuthBillet_tibilletuser_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_groups"
    ADD CONSTRAINT "AuthBillet_tibilletuser_groups_pkey" PRIMARY KEY (id);


--
-- Name: AuthBillet_tibilletuser AuthBillet_tibilletuser_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser"
    ADD CONSTRAINT "AuthBillet_tibilletuser_pkey" PRIMARY KEY (id);


--
-- Name: AuthBillet_tibilletuser_user_permissions AuthBillet_tibilletuser_user_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_user_permissions"
    ADD CONSTRAINT "AuthBillet_tibilletuser_user_permissions_pkey" PRIMARY KEY (id);


--
-- Name: AuthBillet_tibilletuser AuthBillet_tibilletuser_username_key; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser"
    ADD CONSTRAINT "AuthBillet_tibilletuser_username_key" UNIQUE (username);


--
-- Name: Customers_client Customers_client_name_key; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."Customers_client"
    ADD CONSTRAINT "Customers_client_name_key" UNIQUE (name);


--
-- Name: Customers_client Customers_client_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."Customers_client"
    ADD CONSTRAINT "Customers_client_pkey" PRIMARY KEY (uuid);


--
-- Name: Customers_client Customers_client_schema_name_key; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."Customers_client"
    ADD CONSTRAINT "Customers_client_schema_name_key" UNIQUE (schema_name);


--
-- Name: Customers_domain Customers_domain_domain_key; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."Customers_domain"
    ADD CONSTRAINT "Customers_domain_domain_key" UNIQUE (domain);


--
-- Name: Customers_domain Customers_domain_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."Customers_domain"
    ADD CONSTRAINT "Customers_domain_pkey" PRIMARY KEY (id);


--
-- Name: MetaBillet_eventdirectory MetaBillet_eventdirectory_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."MetaBillet_eventdirectory"
    ADD CONSTRAINT "MetaBillet_eventdirectory_pkey" PRIMARY KEY (id);


--
-- Name: MetaBillet_productdirectory MetaBillet_productdirectory_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."MetaBillet_productdirectory"
    ADD CONSTRAINT "MetaBillet_productdirectory_pkey" PRIMARY KEY (id);


--
-- Name: QrcodeCashless_asset QrcodeCashless_asset_origin_id_categorie_4b1d80bf_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_asset"
    ADD CONSTRAINT "QrcodeCashless_asset_origin_id_categorie_4b1d80bf_uniq" UNIQUE (origin_id, categorie);


--
-- Name: QrcodeCashless_asset QrcodeCashless_asset_origin_id_name_e06d6423_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_asset"
    ADD CONSTRAINT "QrcodeCashless_asset_origin_id_name_e06d6423_uniq" UNIQUE (origin_id, name);


--
-- Name: QrcodeCashless_asset QrcodeCashless_asset_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_asset"
    ADD CONSTRAINT "QrcodeCashless_asset_pkey" PRIMARY KEY (id);


--
-- Name: QrcodeCashless_cartecashless QrcodeCashless_cartecashless_number_key; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_cartecashless"
    ADD CONSTRAINT "QrcodeCashless_cartecashless_number_key" UNIQUE (number);


--
-- Name: QrcodeCashless_cartecashless QrcodeCashless_cartecashless_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_cartecashless"
    ADD CONSTRAINT "QrcodeCashless_cartecashless_pkey" PRIMARY KEY (id);


--
-- Name: QrcodeCashless_cartecashless QrcodeCashless_cartecashless_tag_id_key; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_cartecashless"
    ADD CONSTRAINT "QrcodeCashless_cartecashless_tag_id_key" UNIQUE (tag_id);


--
-- Name: QrcodeCashless_cartecashless QrcodeCashless_cartecashless_uuid_5026f310_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_cartecashless"
    ADD CONSTRAINT "QrcodeCashless_cartecashless_uuid_5026f310_uniq" UNIQUE (uuid);


--
-- Name: QrcodeCashless_detail QrcodeCashless_detail_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_detail"
    ADD CONSTRAINT "QrcodeCashless_detail_pkey" PRIMARY KEY (id);


--
-- Name: QrcodeCashless_detail QrcodeCashless_detail_slug_key; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_detail"
    ADD CONSTRAINT "QrcodeCashless_detail_slug_key" UNIQUE (slug);


--
-- Name: QrcodeCashless_federatedcashless QrcodeCashless_federated_client_id_asset_id_d53dd66c_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_federatedcashless"
    ADD CONSTRAINT "QrcodeCashless_federated_client_id_asset_id_d53dd66c_uniq" UNIQUE (client_id, asset_id);


--
-- Name: QrcodeCashless_federatedcashless QrcodeCashless_federatedcashless_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_federatedcashless"
    ADD CONSTRAINT "QrcodeCashless_federatedcashless_pkey" PRIMARY KEY (id);


--
-- Name: QrcodeCashless_syncfederatedlog QrcodeCashless_syncfederatedlog_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_syncfederatedlog"
    ADD CONSTRAINT "QrcodeCashless_syncfederatedlog_pkey" PRIMARY KEY (id);


--
-- Name: QrcodeCashless_wallet QrcodeCashless_wallet_asset_id_user_id_c2d15d6c_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_wallet"
    ADD CONSTRAINT "QrcodeCashless_wallet_asset_id_user_id_c2d15d6c_uniq" UNIQUE (asset_id, user_id);


--
-- Name: QrcodeCashless_wallet QrcodeCashless_wallet_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_wallet"
    ADD CONSTRAINT "QrcodeCashless_wallet_pkey" PRIMARY KEY (id);


--
-- Name: auth_group auth_group_name_key; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.auth_group
    ADD CONSTRAINT auth_group_name_key UNIQUE (name);


--
-- Name: auth_group_permissions auth_group_permissions_group_id_permission_id_0cd325b0_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissions_group_id_permission_id_0cd325b0_uniq UNIQUE (group_id, permission_id);


--
-- Name: auth_group_permissions auth_group_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissions_pkey PRIMARY KEY (id);


--
-- Name: auth_group auth_group_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.auth_group
    ADD CONSTRAINT auth_group_pkey PRIMARY KEY (id);


--
-- Name: auth_permission auth_permission_content_type_id_codename_01ab375a_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.auth_permission
    ADD CONSTRAINT auth_permission_content_type_id_codename_01ab375a_uniq UNIQUE (content_type_id, codename);


--
-- Name: auth_permission auth_permission_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.auth_permission
    ADD CONSTRAINT auth_permission_pkey PRIMARY KEY (id);


--
-- Name: authtoken_token authtoken_token_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.authtoken_token
    ADD CONSTRAINT authtoken_token_pkey PRIMARY KEY (key);


--
-- Name: authtoken_token authtoken_token_user_id_key; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.authtoken_token
    ADD CONSTRAINT authtoken_token_user_id_key UNIQUE (user_id);


--
-- Name: django_admin_log django_admin_log_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.django_admin_log
    ADD CONSTRAINT django_admin_log_pkey PRIMARY KEY (id);


--
-- Name: django_content_type django_content_type_app_label_model_76bd3d3b_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.django_content_type
    ADD CONSTRAINT django_content_type_app_label_model_76bd3d3b_uniq UNIQUE (app_label, model);


--
-- Name: django_content_type django_content_type_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.django_content_type
    ADD CONSTRAINT django_content_type_pkey PRIMARY KEY (id);


--
-- Name: django_migrations django_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.django_migrations
    ADD CONSTRAINT django_migrations_pkey PRIMARY KEY (id);


--
-- Name: django_session django_session_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.django_session
    ADD CONSTRAINT django_session_pkey PRIMARY KEY (session_key);


--
-- Name: django_site django_site_domain_a2e37b91_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.django_site
    ADD CONSTRAINT django_site_domain_a2e37b91_uniq UNIQUE (domain);


--
-- Name: django_site django_site_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.django_site
    ADD CONSTRAINT django_site_pkey PRIMARY KEY (id);


--
-- Name: root_billet_rootconfiguration root_billet_rootconfiguration_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.root_billet_rootconfiguration
    ADD CONSTRAINT root_billet_rootconfiguration_pkey PRIMARY KEY (id);


--
-- Name: token_blacklist_blacklistedtoken token_blacklist_blacklistedtoken_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.token_blacklist_blacklistedtoken
    ADD CONSTRAINT token_blacklist_blacklistedtoken_pkey PRIMARY KEY (id);


--
-- Name: token_blacklist_blacklistedtoken token_blacklist_blacklistedtoken_token_id_key; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.token_blacklist_blacklistedtoken
    ADD CONSTRAINT token_blacklist_blacklistedtoken_token_id_key UNIQUE (token_id);


--
-- Name: token_blacklist_outstandingtoken token_blacklist_outstandingtoken_jti_hex_d9bdf6f7_uniq; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.token_blacklist_outstandingtoken
    ADD CONSTRAINT token_blacklist_outstandingtoken_jti_hex_d9bdf6f7_uniq UNIQUE (jti);


--
-- Name: token_blacklist_outstandingtoken token_blacklist_outstandingtoken_pkey; Type: CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.token_blacklist_outstandingtoken
    ADD CONSTRAINT token_blacklist_outstandingtoken_pkey PRIMARY KEY (id);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_name_key; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_name_key" UNIQUE (name);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_user_id_key; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_user_id_key" UNIQUE (user_id);


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_event_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_event_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configuration_configuration_id_optiong_5a48033a_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configuration_configuration_id_optiong_5a48033a_uniq" UNIQUE (configuration_id, optiongenerale_id);


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configuration_configuration_id_optiong_83744681_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configuration_configuration_id_optiong_83744681_uniq" UNIQUE (configuration_id, optiongenerale_id);


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configuration_option_generale_checkbox_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configuration_option_generale_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configuration_option_generale_radio_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configuration_option_generale_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_configuration BaseBillet_configuration_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_configuration"
    ADD CONSTRAINT "BaseBillet_configuration_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_name_datetime_0e242bcf_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_name_datetime_0e242bcf_uniq" UNIQUE (name, datetime);


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_options_checkbox_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_options_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_options_event_id_optiongenerale__b37606e9_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_options_event_id_optiongenerale__b37606e9_uniq" UNIQUE (event_id, optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_options_event_id_optiongenerale__f1ff3e5e_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_options_event_id_optiongenerale__f1ff3e5e_uniq" UNIQUE (event_id, optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_options_radio_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_options_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_event_products BaseBillet_event_products_event_id_product_id_0292c8a3_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_products_event_id_product_id_0292c8a3_uniq" UNIQUE (event_id, product_id);


--
-- Name: BaseBillet_event_products BaseBillet_event_products_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_products_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_recurrent_event_id_weekday_id_0f8358b4_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_recurrent_event_id_weekday_id_0f8358b4_uniq" UNIQUE (event_id, weekday_id);


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_recurrent_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_recurrent_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_event BaseBillet_event_slug_key; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event"
    ADD CONSTRAINT "BaseBillet_event_slug_key" UNIQUE (slug);


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_event_id_tag_id_6f9dba44_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_event_id_tag_id_6f9dba44_uniq" UNIQUE (event_id, tag_id);


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_externalapikey BaseBillet_externalapikey_key_id_key; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_externalapikey_key_id_key" UNIQUE (key_id);


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearticle_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearticle_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membership_op_membership_id_optiongene_32d9eed9_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membership_op_membership_id_optiongene_32d9eed9_uniq" UNIQUE (membership_id, optiongenerale_id);


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membership_option_generale_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membership_option_generale_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_membership BaseBillet_membership_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membership_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_membership BaseBillet_membership_user_id_price_id_22c167ba_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membership_user_id_price_id_22c167ba_uniq" UNIQUE (user_id, price_id);


--
-- Name: BaseBillet_optiongenerale BaseBillet_optiongenerale_name_key; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_optiongenerale"
    ADD CONSTRAINT "BaseBillet_optiongenerale_name_key" UNIQUE (name);


--
-- Name: BaseBillet_optiongenerale BaseBillet_optiongenerale_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_optiongenerale"
    ADD CONSTRAINT "BaseBillet_optiongenerale_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement_stripe_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement_stripe_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_price BaseBillet_price_name_product_id_cf5fcf03_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_name_product_id_cf5fcf03_uniq" UNIQUE (name, product_id);


--
-- Name: BaseBillet_price BaseBillet_price_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_product BaseBillet_product_categorie_article_name_fa9da1c7_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product"
    ADD CONSTRAINT "BaseBillet_product_categorie_article_name_fa9da1c7_uniq" UNIQUE (categorie_article, name);


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_optio_product_id_optiongeneral_09a1ea40_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_optio_product_id_optiongeneral_09a1ea40_uniq" UNIQUE (product_id, optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_optio_product_id_optiongeneral_bdb7af0e_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_optio_product_id_optiongeneral_bdb7af0e_uniq" UNIQUE (product_id, optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_option_generale_checkbox_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_option_generale_checkbox_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_option_generale_radio_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_option_generale_radio_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product BaseBillet_product_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product"
    ADD CONSTRAINT "BaseBillet_product_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_product_id_tag_id_d023f294_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_product_id_tag_id_d023f294_uniq" UNIQUE (product_id, tag_id);


--
-- Name: BaseBillet_productsold BaseBillet_productsold_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productsold_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_reservation_options BaseBillet_reservation_o_reservation_id_optiongen_bd545d00_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservation_o_reservation_id_optiongen_bd545d00_uniq" UNIQUE (reservation_id, optiongenerale_id);


--
-- Name: BaseBillet_reservation_options BaseBillet_reservation_options_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservation_options_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_reservation BaseBillet_reservation_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservation_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_tag BaseBillet_tag_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_tag"
    ADD CONSTRAINT "BaseBillet_tag_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_ticket BaseBillet_ticket_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_pkey" PRIMARY KEY (uuid);


--
-- Name: BaseBillet_webhook BaseBillet_webhook_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_webhook"
    ADD CONSTRAINT "BaseBillet_webhook_pkey" PRIMARY KEY (id);


--
-- Name: BaseBillet_weekday BaseBillet_weekday_day_key; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_weekday"
    ADD CONSTRAINT "BaseBillet_weekday_day_key" UNIQUE (day);


--
-- Name: BaseBillet_weekday BaseBillet_weekday_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_weekday"
    ADD CONSTRAINT "BaseBillet_weekday_pkey" PRIMARY KEY (id);


--
-- Name: django_content_type django_content_type_app_label_model_76bd3d3b_uniq; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan.django_content_type
    ADD CONSTRAINT django_content_type_app_label_model_76bd3d3b_uniq UNIQUE (app_label, model);


--
-- Name: django_content_type django_content_type_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan.django_content_type
    ADD CONSTRAINT django_content_type_pkey PRIMARY KEY (id);


--
-- Name: django_migrations django_migrations_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan.django_migrations
    ADD CONSTRAINT django_migrations_pkey PRIMARY KEY (id);


--
-- Name: rest_framework_api_key_apikey rest_framework_api_key_apikey_pkey; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan.rest_framework_api_key_apikey
    ADD CONSTRAINT rest_framework_api_key_apikey_pkey PRIMARY KEY (id);


--
-- Name: rest_framework_api_key_apikey rest_framework_api_key_apikey_prefix_key; Type: CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan.rest_framework_api_key_apikey
    ADD CONSTRAINT rest_framework_api_key_apikey_prefix_key UNIQUE (prefix);


--
-- Name: BaseBillet_apikey_name_77c0c277_like; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_apikey_name_77c0c277_like" ON "balaphonik-sound-system"."BaseBillet_externalapikey" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_artist_on_event_artist_id_fd91cee9; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_artist_on_event_artist_id_fd91cee9" ON "balaphonik-sound-system"."BaseBillet_artist_on_event" USING btree (artist_id);


--
-- Name: BaseBillet_artist_on_event_event_id_29dd03f1; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_artist_on_event_event_id_29dd03f1" ON "balaphonik-sound-system"."BaseBillet_artist_on_event" USING btree (event_id);


--
-- Name: BaseBillet_configuration_o_configuration_id_2e19f154; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_configuration_id_2e19f154" ON "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio" USING btree (configuration_id);


--
-- Name: BaseBillet_configuration_o_configuration_id_bbe225a5; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_configuration_id_bbe225a5" ON "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox" USING btree (configuration_id);


--
-- Name: BaseBillet_configuration_o_optiongenerale_id_7e69c71b; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_optiongenerale_id_7e69c71b" ON "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_configuration_o_optiongenerale_id_83c65e17; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_optiongenerale_id_83c65e17" ON "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_configuration_organisation_8d66658d; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_organisation_8d66658d" ON "balaphonik-sound-system"."BaseBillet_configuration" USING btree (organisation);


--
-- Name: BaseBillet_configuration_organisation_8d66658d_like; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_organisation_8d66658d_like" ON "balaphonik-sound-system"."BaseBillet_configuration" USING btree (organisation varchar_pattern_ops);


--
-- Name: BaseBillet_configuration_slug_7b38f49e; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_slug_7b38f49e" ON "balaphonik-sound-system"."BaseBillet_configuration" USING btree (slug);


--
-- Name: BaseBillet_configuration_slug_7b38f49e_like; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_slug_7b38f49e_like" ON "balaphonik-sound-system"."BaseBillet_configuration" USING btree (slug varchar_pattern_ops);


--
-- Name: BaseBillet_event_options_checkbox_event_id_6389bff4; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_checkbox_event_id_6389bff4" ON "balaphonik-sound-system"."BaseBillet_event_options_checkbox" USING btree (event_id);


--
-- Name: BaseBillet_event_options_checkbox_optiongenerale_id_b5d7c04b; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_checkbox_optiongenerale_id_b5d7c04b" ON "balaphonik-sound-system"."BaseBillet_event_options_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio_event_id_172366cc; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_radio_event_id_172366cc" ON "balaphonik-sound-system"."BaseBillet_event_options_radio" USING btree (event_id);


--
-- Name: BaseBillet_event_options_radio_optiongenerale_id_0dd0f546; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_radio_optiongenerale_id_0dd0f546" ON "balaphonik-sound-system"."BaseBillet_event_options_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_event_products_event_id_e8b98de0; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_products_event_id_e8b98de0" ON "balaphonik-sound-system"."BaseBillet_event_products" USING btree (event_id);


--
-- Name: BaseBillet_event_products_product_id_cdec0e20; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_products_product_id_cdec0e20" ON "balaphonik-sound-system"."BaseBillet_event_products" USING btree (product_id);


--
-- Name: BaseBillet_event_recurrent_event_id_0656b7d1; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_recurrent_event_id_0656b7d1" ON "balaphonik-sound-system"."BaseBillet_event_recurrent" USING btree (event_id);


--
-- Name: BaseBillet_event_recurrent_weekday_id_130a2743; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_recurrent_weekday_id_130a2743" ON "balaphonik-sound-system"."BaseBillet_event_recurrent" USING btree (weekday_id);


--
-- Name: BaseBillet_event_slug_5bdd3465_like; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_slug_5bdd3465_like" ON "balaphonik-sound-system"."BaseBillet_event" USING btree (slug varchar_pattern_ops);


--
-- Name: BaseBillet_event_tag_event_id_70d3f9f4; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_tag_event_id_70d3f9f4" ON "balaphonik-sound-system"."BaseBillet_event_tag" USING btree (event_id);


--
-- Name: BaseBillet_event_tag_tag_id_42dafd42; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_tag_tag_id_42dafd42" ON "balaphonik-sound-system"."BaseBillet_event_tag" USING btree (tag_id);


--
-- Name: BaseBillet_externalapikey_key_id_f5eff8fe_like; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_externalapikey_key_id_f5eff8fe_like" ON "balaphonik-sound-system"."BaseBillet_externalapikey" USING btree (key_id varchar_pattern_ops);


--
-- Name: BaseBillet_lignearticle_carte_id_8ab02e3c; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_carte_id_8ab02e3c" ON "balaphonik-sound-system"."BaseBillet_lignearticle" USING btree (carte_id);


--
-- Name: BaseBillet_lignearticle_paiement_stripe_id_82b4a0d3; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_paiement_stripe_id_82b4a0d3" ON "balaphonik-sound-system"."BaseBillet_lignearticle" USING btree (paiement_stripe_id);


--
-- Name: BaseBillet_lignearticle_pricesold_id_fc351d3d; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_pricesold_id_fc351d3d" ON "balaphonik-sound-system"."BaseBillet_lignearticle" USING btree (pricesold_id);


--
-- Name: BaseBillet_membership_first_name_80925438; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_first_name_80925438" ON "balaphonik-sound-system"."BaseBillet_membership" USING btree (first_name);


--
-- Name: BaseBillet_membership_first_name_80925438_like; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_first_name_80925438_like" ON "balaphonik-sound-system"."BaseBillet_membership" USING btree (first_name varchar_pattern_ops);


--
-- Name: BaseBillet_membership_opti_optiongenerale_id_87513e51; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_opti_optiongenerale_id_87513e51" ON "balaphonik-sound-system"."BaseBillet_membership_option_generale" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_membership_option_generale_membership_id_d255b3ce; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_option_generale_membership_id_d255b3ce" ON "balaphonik-sound-system"."BaseBillet_membership_option_generale" USING btree (membership_id);


--
-- Name: BaseBillet_membership_price_id_a4571820; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_price_id_a4571820" ON "balaphonik-sound-system"."BaseBillet_membership" USING btree (price_id);


--
-- Name: BaseBillet_membership_user_id_2b02a750; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_user_id_2b02a750" ON "balaphonik-sound-system"."BaseBillet_membership" USING btree (user_id);


--
-- Name: BaseBillet_optiongenerale_name_d6fb0195_like; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_optiongenerale_name_d6fb0195_like" ON "balaphonik-sound-system"."BaseBillet_optiongenerale" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_paiement_stripe_reservation_id_9643913c; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_paiement_stripe_reservation_id_9643913c" ON "balaphonik-sound-system"."BaseBillet_paiement_stripe" USING btree (reservation_id);


--
-- Name: BaseBillet_paiement_stripe_user_id_03041fc6; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_paiement_stripe_user_id_03041fc6" ON "balaphonik-sound-system"."BaseBillet_paiement_stripe" USING btree (user_id);


--
-- Name: BaseBillet_price_adhesion_obligatoire_id_043901b7; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_price_adhesion_obligatoire_id_043901b7" ON "balaphonik-sound-system"."BaseBillet_price" USING btree (adhesion_obligatoire_id);


--
-- Name: BaseBillet_price_product_id_a7d53d46; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_price_product_id_a7d53d46" ON "balaphonik-sound-system"."BaseBillet_price" USING btree (product_id);


--
-- Name: BaseBillet_pricesold_price_id_017f6621; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_pricesold_price_id_017f6621" ON "balaphonik-sound-system"."BaseBillet_pricesold" USING btree (price_id);


--
-- Name: BaseBillet_pricesold_productsold_id_d61e1c5f; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_pricesold_productsold_id_d61e1c5f" ON "balaphonik-sound-system"."BaseBillet_pricesold" USING btree (productsold_id);


--
-- Name: BaseBillet_product_option__optiongenerale_id_7714e607; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option__optiongenerale_id_7714e607" ON "balaphonik-sound-system"."BaseBillet_product_option_generale_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_product_option__optiongenerale_id_ded928b6; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option__optiongenerale_id_ded928b6" ON "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_checkbox_product_id_84a7c765; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option_generale_checkbox_product_id_84a7c765" ON "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox" USING btree (product_id);


--
-- Name: BaseBillet_product_option_generale_radio_product_id_50c10a7b; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option_generale_radio_product_id_50c10a7b" ON "balaphonik-sound-system"."BaseBillet_product_option_generale_radio" USING btree (product_id);


--
-- Name: BaseBillet_product_tag_product_id_00f8ae38; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_tag_product_id_00f8ae38" ON "balaphonik-sound-system"."BaseBillet_product_tag" USING btree (product_id);


--
-- Name: BaseBillet_product_tag_tag_id_68675245; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_tag_tag_id_68675245" ON "balaphonik-sound-system"."BaseBillet_product_tag" USING btree (tag_id);


--
-- Name: BaseBillet_productsold_event_id_c817df43; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_productsold_event_id_c817df43" ON "balaphonik-sound-system"."BaseBillet_productsold" USING btree (event_id);


--
-- Name: BaseBillet_productsold_product_id_afb2fb6e; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_productsold_product_id_afb2fb6e" ON "balaphonik-sound-system"."BaseBillet_productsold" USING btree (product_id);


--
-- Name: BaseBillet_reservation_event_id_7404fad0; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_event_id_7404fad0" ON "balaphonik-sound-system"."BaseBillet_reservation" USING btree (event_id);


--
-- Name: BaseBillet_reservation_options_optiongenerale_id_bc5048ee; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_options_optiongenerale_id_bc5048ee" ON "balaphonik-sound-system"."BaseBillet_reservation_options" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_reservation_options_reservation_id_bf305174; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_options_reservation_id_bf305174" ON "balaphonik-sound-system"."BaseBillet_reservation_options" USING btree (reservation_id);


--
-- Name: BaseBillet_reservation_user_commande_id_2a3fe1fd; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_user_commande_id_2a3fe1fd" ON "balaphonik-sound-system"."BaseBillet_reservation" USING btree (user_commande_id);


--
-- Name: BaseBillet_tag_name_faabf7e0; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_tag_name_faabf7e0" ON "balaphonik-sound-system"."BaseBillet_tag" USING btree (name);


--
-- Name: BaseBillet_tag_name_faabf7e0_like; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_tag_name_faabf7e0_like" ON "balaphonik-sound-system"."BaseBillet_tag" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_ticket_pricesold_id_1984d9e4; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_ticket_pricesold_id_1984d9e4" ON "balaphonik-sound-system"."BaseBillet_ticket" USING btree (pricesold_id);


--
-- Name: BaseBillet_ticket_reservation_id_226cfb21; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_ticket_reservation_id_226cfb21" ON "balaphonik-sound-system"."BaseBillet_ticket" USING btree (reservation_id);


--
-- Name: rest_framework_api_key_apikey_created_c61872d9; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_created_c61872d9 ON "balaphonik-sound-system".rest_framework_api_key_apikey USING btree (created);


--
-- Name: rest_framework_api_key_apikey_id_6e07e68e_like; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_id_6e07e68e_like ON "balaphonik-sound-system".rest_framework_api_key_apikey USING btree (id varchar_pattern_ops);


--
-- Name: rest_framework_api_key_apikey_prefix_4e0db5f8_like; Type: INDEX; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_prefix_4e0db5f8_like ON "balaphonik-sound-system".rest_framework_api_key_apikey USING btree (prefix varchar_pattern_ops);


--
-- Name: BaseBillet_apikey_name_77c0c277_like; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_apikey_name_77c0c277_like" ON billetistan."BaseBillet_externalapikey" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_artist_on_event_artist_id_fd91cee9; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_artist_on_event_artist_id_fd91cee9" ON billetistan."BaseBillet_artist_on_event" USING btree (artist_id);


--
-- Name: BaseBillet_artist_on_event_event_id_29dd03f1; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_artist_on_event_event_id_29dd03f1" ON billetistan."BaseBillet_artist_on_event" USING btree (event_id);


--
-- Name: BaseBillet_configuration_o_configuration_id_2e19f154; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_configuration_id_2e19f154" ON billetistan."BaseBillet_configuration_option_generale_radio" USING btree (configuration_id);


--
-- Name: BaseBillet_configuration_o_configuration_id_bbe225a5; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_configuration_id_bbe225a5" ON billetistan."BaseBillet_configuration_option_generale_checkbox" USING btree (configuration_id);


--
-- Name: BaseBillet_configuration_o_optiongenerale_id_7e69c71b; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_optiongenerale_id_7e69c71b" ON billetistan."BaseBillet_configuration_option_generale_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_configuration_o_optiongenerale_id_83c65e17; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_optiongenerale_id_83c65e17" ON billetistan."BaseBillet_configuration_option_generale_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_configuration_organisation_8d66658d; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_organisation_8d66658d" ON billetistan."BaseBillet_configuration" USING btree (organisation);


--
-- Name: BaseBillet_configuration_organisation_8d66658d_like; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_organisation_8d66658d_like" ON billetistan."BaseBillet_configuration" USING btree (organisation varchar_pattern_ops);


--
-- Name: BaseBillet_configuration_slug_7b38f49e; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_slug_7b38f49e" ON billetistan."BaseBillet_configuration" USING btree (slug);


--
-- Name: BaseBillet_configuration_slug_7b38f49e_like; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_slug_7b38f49e_like" ON billetistan."BaseBillet_configuration" USING btree (slug varchar_pattern_ops);


--
-- Name: BaseBillet_event_options_checkbox_event_id_6389bff4; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_checkbox_event_id_6389bff4" ON billetistan."BaseBillet_event_options_checkbox" USING btree (event_id);


--
-- Name: BaseBillet_event_options_checkbox_optiongenerale_id_b5d7c04b; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_checkbox_optiongenerale_id_b5d7c04b" ON billetistan."BaseBillet_event_options_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio_event_id_172366cc; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_radio_event_id_172366cc" ON billetistan."BaseBillet_event_options_radio" USING btree (event_id);


--
-- Name: BaseBillet_event_options_radio_optiongenerale_id_0dd0f546; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_radio_optiongenerale_id_0dd0f546" ON billetistan."BaseBillet_event_options_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_event_products_event_id_e8b98de0; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_products_event_id_e8b98de0" ON billetistan."BaseBillet_event_products" USING btree (event_id);


--
-- Name: BaseBillet_event_products_product_id_cdec0e20; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_products_product_id_cdec0e20" ON billetistan."BaseBillet_event_products" USING btree (product_id);


--
-- Name: BaseBillet_event_recurrent_event_id_0656b7d1; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_recurrent_event_id_0656b7d1" ON billetistan."BaseBillet_event_recurrent" USING btree (event_id);


--
-- Name: BaseBillet_event_recurrent_weekday_id_130a2743; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_recurrent_weekday_id_130a2743" ON billetistan."BaseBillet_event_recurrent" USING btree (weekday_id);


--
-- Name: BaseBillet_event_slug_5bdd3465_like; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_slug_5bdd3465_like" ON billetistan."BaseBillet_event" USING btree (slug varchar_pattern_ops);


--
-- Name: BaseBillet_event_tag_event_id_70d3f9f4; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_tag_event_id_70d3f9f4" ON billetistan."BaseBillet_event_tag" USING btree (event_id);


--
-- Name: BaseBillet_event_tag_tag_id_42dafd42; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_tag_tag_id_42dafd42" ON billetistan."BaseBillet_event_tag" USING btree (tag_id);


--
-- Name: BaseBillet_externalapikey_key_id_f5eff8fe_like; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_externalapikey_key_id_f5eff8fe_like" ON billetistan."BaseBillet_externalapikey" USING btree (key_id varchar_pattern_ops);


--
-- Name: BaseBillet_lignearticle_carte_id_8ab02e3c; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_carte_id_8ab02e3c" ON billetistan."BaseBillet_lignearticle" USING btree (carte_id);


--
-- Name: BaseBillet_lignearticle_paiement_stripe_id_82b4a0d3; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_paiement_stripe_id_82b4a0d3" ON billetistan."BaseBillet_lignearticle" USING btree (paiement_stripe_id);


--
-- Name: BaseBillet_lignearticle_pricesold_id_fc351d3d; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_pricesold_id_fc351d3d" ON billetistan."BaseBillet_lignearticle" USING btree (pricesold_id);


--
-- Name: BaseBillet_membership_first_name_80925438; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_first_name_80925438" ON billetistan."BaseBillet_membership" USING btree (first_name);


--
-- Name: BaseBillet_membership_first_name_80925438_like; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_first_name_80925438_like" ON billetistan."BaseBillet_membership" USING btree (first_name varchar_pattern_ops);


--
-- Name: BaseBillet_membership_opti_optiongenerale_id_87513e51; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_opti_optiongenerale_id_87513e51" ON billetistan."BaseBillet_membership_option_generale" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_membership_option_generale_membership_id_d255b3ce; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_option_generale_membership_id_d255b3ce" ON billetistan."BaseBillet_membership_option_generale" USING btree (membership_id);


--
-- Name: BaseBillet_membership_price_id_a4571820; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_price_id_a4571820" ON billetistan."BaseBillet_membership" USING btree (price_id);


--
-- Name: BaseBillet_membership_user_id_2b02a750; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_user_id_2b02a750" ON billetistan."BaseBillet_membership" USING btree (user_id);


--
-- Name: BaseBillet_optiongenerale_name_d6fb0195_like; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_optiongenerale_name_d6fb0195_like" ON billetistan."BaseBillet_optiongenerale" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_paiement_stripe_reservation_id_9643913c; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_paiement_stripe_reservation_id_9643913c" ON billetistan."BaseBillet_paiement_stripe" USING btree (reservation_id);


--
-- Name: BaseBillet_paiement_stripe_user_id_03041fc6; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_paiement_stripe_user_id_03041fc6" ON billetistan."BaseBillet_paiement_stripe" USING btree (user_id);


--
-- Name: BaseBillet_price_adhesion_obligatoire_id_043901b7; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_price_adhesion_obligatoire_id_043901b7" ON billetistan."BaseBillet_price" USING btree (adhesion_obligatoire_id);


--
-- Name: BaseBillet_price_product_id_a7d53d46; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_price_product_id_a7d53d46" ON billetistan."BaseBillet_price" USING btree (product_id);


--
-- Name: BaseBillet_pricesold_price_id_017f6621; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_pricesold_price_id_017f6621" ON billetistan."BaseBillet_pricesold" USING btree (price_id);


--
-- Name: BaseBillet_pricesold_productsold_id_d61e1c5f; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_pricesold_productsold_id_d61e1c5f" ON billetistan."BaseBillet_pricesold" USING btree (productsold_id);


--
-- Name: BaseBillet_product_option__optiongenerale_id_7714e607; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option__optiongenerale_id_7714e607" ON billetistan."BaseBillet_product_option_generale_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_product_option__optiongenerale_id_ded928b6; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option__optiongenerale_id_ded928b6" ON billetistan."BaseBillet_product_option_generale_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_checkbox_product_id_84a7c765; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option_generale_checkbox_product_id_84a7c765" ON billetistan."BaseBillet_product_option_generale_checkbox" USING btree (product_id);


--
-- Name: BaseBillet_product_option_generale_radio_product_id_50c10a7b; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option_generale_radio_product_id_50c10a7b" ON billetistan."BaseBillet_product_option_generale_radio" USING btree (product_id);


--
-- Name: BaseBillet_product_tag_product_id_00f8ae38; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_tag_product_id_00f8ae38" ON billetistan."BaseBillet_product_tag" USING btree (product_id);


--
-- Name: BaseBillet_product_tag_tag_id_68675245; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_tag_tag_id_68675245" ON billetistan."BaseBillet_product_tag" USING btree (tag_id);


--
-- Name: BaseBillet_productsold_event_id_c817df43; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_productsold_event_id_c817df43" ON billetistan."BaseBillet_productsold" USING btree (event_id);


--
-- Name: BaseBillet_productsold_product_id_afb2fb6e; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_productsold_product_id_afb2fb6e" ON billetistan."BaseBillet_productsold" USING btree (product_id);


--
-- Name: BaseBillet_reservation_event_id_7404fad0; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_event_id_7404fad0" ON billetistan."BaseBillet_reservation" USING btree (event_id);


--
-- Name: BaseBillet_reservation_options_optiongenerale_id_bc5048ee; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_options_optiongenerale_id_bc5048ee" ON billetistan."BaseBillet_reservation_options" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_reservation_options_reservation_id_bf305174; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_options_reservation_id_bf305174" ON billetistan."BaseBillet_reservation_options" USING btree (reservation_id);


--
-- Name: BaseBillet_reservation_user_commande_id_2a3fe1fd; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_user_commande_id_2a3fe1fd" ON billetistan."BaseBillet_reservation" USING btree (user_commande_id);


--
-- Name: BaseBillet_tag_name_faabf7e0; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_tag_name_faabf7e0" ON billetistan."BaseBillet_tag" USING btree (name);


--
-- Name: BaseBillet_tag_name_faabf7e0_like; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_tag_name_faabf7e0_like" ON billetistan."BaseBillet_tag" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_ticket_pricesold_id_1984d9e4; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_ticket_pricesold_id_1984d9e4" ON billetistan."BaseBillet_ticket" USING btree (pricesold_id);


--
-- Name: BaseBillet_ticket_reservation_id_226cfb21; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_ticket_reservation_id_226cfb21" ON billetistan."BaseBillet_ticket" USING btree (reservation_id);


--
-- Name: rest_framework_api_key_apikey_created_c61872d9; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_created_c61872d9 ON billetistan.rest_framework_api_key_apikey USING btree (created);


--
-- Name: rest_framework_api_key_apikey_id_6e07e68e_like; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_id_6e07e68e_like ON billetistan.rest_framework_api_key_apikey USING btree (id varchar_pattern_ops);


--
-- Name: rest_framework_api_key_apikey_prefix_4e0db5f8_like; Type: INDEX; Schema: billetistan; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_prefix_4e0db5f8_like ON billetistan.rest_framework_api_key_apikey USING btree (prefix varchar_pattern_ops);


--
-- Name: BaseBillet_apikey_name_77c0c277_like; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_apikey_name_77c0c277_like" ON demo."BaseBillet_externalapikey" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_artist_on_event_artist_id_fd91cee9; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_artist_on_event_artist_id_fd91cee9" ON demo."BaseBillet_artist_on_event" USING btree (artist_id);


--
-- Name: BaseBillet_artist_on_event_event_id_29dd03f1; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_artist_on_event_event_id_29dd03f1" ON demo."BaseBillet_artist_on_event" USING btree (event_id);


--
-- Name: BaseBillet_configuration_o_configuration_id_2e19f154; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_configuration_id_2e19f154" ON demo."BaseBillet_configuration_option_generale_radio" USING btree (configuration_id);


--
-- Name: BaseBillet_configuration_o_configuration_id_bbe225a5; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_configuration_id_bbe225a5" ON demo."BaseBillet_configuration_option_generale_checkbox" USING btree (configuration_id);


--
-- Name: BaseBillet_configuration_o_optiongenerale_id_7e69c71b; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_optiongenerale_id_7e69c71b" ON demo."BaseBillet_configuration_option_generale_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_configuration_o_optiongenerale_id_83c65e17; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_optiongenerale_id_83c65e17" ON demo."BaseBillet_configuration_option_generale_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_configuration_organisation_8d66658d; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_organisation_8d66658d" ON demo."BaseBillet_configuration" USING btree (organisation);


--
-- Name: BaseBillet_configuration_organisation_8d66658d_like; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_organisation_8d66658d_like" ON demo."BaseBillet_configuration" USING btree (organisation varchar_pattern_ops);


--
-- Name: BaseBillet_configuration_slug_7b38f49e; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_slug_7b38f49e" ON demo."BaseBillet_configuration" USING btree (slug);


--
-- Name: BaseBillet_configuration_slug_7b38f49e_like; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_slug_7b38f49e_like" ON demo."BaseBillet_configuration" USING btree (slug varchar_pattern_ops);


--
-- Name: BaseBillet_event_options_checkbox_event_id_6389bff4; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_checkbox_event_id_6389bff4" ON demo."BaseBillet_event_options_checkbox" USING btree (event_id);


--
-- Name: BaseBillet_event_options_checkbox_optiongenerale_id_b5d7c04b; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_checkbox_optiongenerale_id_b5d7c04b" ON demo."BaseBillet_event_options_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio_event_id_172366cc; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_radio_event_id_172366cc" ON demo."BaseBillet_event_options_radio" USING btree (event_id);


--
-- Name: BaseBillet_event_options_radio_optiongenerale_id_0dd0f546; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_radio_optiongenerale_id_0dd0f546" ON demo."BaseBillet_event_options_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_event_products_event_id_e8b98de0; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_products_event_id_e8b98de0" ON demo."BaseBillet_event_products" USING btree (event_id);


--
-- Name: BaseBillet_event_products_product_id_cdec0e20; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_products_product_id_cdec0e20" ON demo."BaseBillet_event_products" USING btree (product_id);


--
-- Name: BaseBillet_event_recurrent_event_id_0656b7d1; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_recurrent_event_id_0656b7d1" ON demo."BaseBillet_event_recurrent" USING btree (event_id);


--
-- Name: BaseBillet_event_recurrent_weekday_id_130a2743; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_recurrent_weekday_id_130a2743" ON demo."BaseBillet_event_recurrent" USING btree (weekday_id);


--
-- Name: BaseBillet_event_slug_5bdd3465_like; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_slug_5bdd3465_like" ON demo."BaseBillet_event" USING btree (slug varchar_pattern_ops);


--
-- Name: BaseBillet_event_tag_event_id_70d3f9f4; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_tag_event_id_70d3f9f4" ON demo."BaseBillet_event_tag" USING btree (event_id);


--
-- Name: BaseBillet_event_tag_tag_id_42dafd42; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_tag_tag_id_42dafd42" ON demo."BaseBillet_event_tag" USING btree (tag_id);


--
-- Name: BaseBillet_externalapikey_key_id_f5eff8fe_like; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_externalapikey_key_id_f5eff8fe_like" ON demo."BaseBillet_externalapikey" USING btree (key_id varchar_pattern_ops);


--
-- Name: BaseBillet_lignearticle_carte_id_8ab02e3c; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_carte_id_8ab02e3c" ON demo."BaseBillet_lignearticle" USING btree (carte_id);


--
-- Name: BaseBillet_lignearticle_paiement_stripe_id_82b4a0d3; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_paiement_stripe_id_82b4a0d3" ON demo."BaseBillet_lignearticle" USING btree (paiement_stripe_id);


--
-- Name: BaseBillet_lignearticle_pricesold_id_fc351d3d; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_pricesold_id_fc351d3d" ON demo."BaseBillet_lignearticle" USING btree (pricesold_id);


--
-- Name: BaseBillet_membership_first_name_80925438; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_first_name_80925438" ON demo."BaseBillet_membership" USING btree (first_name);


--
-- Name: BaseBillet_membership_first_name_80925438_like; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_first_name_80925438_like" ON demo."BaseBillet_membership" USING btree (first_name varchar_pattern_ops);


--
-- Name: BaseBillet_membership_opti_optiongenerale_id_87513e51; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_opti_optiongenerale_id_87513e51" ON demo."BaseBillet_membership_option_generale" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_membership_option_generale_membership_id_d255b3ce; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_option_generale_membership_id_d255b3ce" ON demo."BaseBillet_membership_option_generale" USING btree (membership_id);


--
-- Name: BaseBillet_membership_price_id_a4571820; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_price_id_a4571820" ON demo."BaseBillet_membership" USING btree (price_id);


--
-- Name: BaseBillet_membership_user_id_2b02a750; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_user_id_2b02a750" ON demo."BaseBillet_membership" USING btree (user_id);


--
-- Name: BaseBillet_optiongenerale_name_d6fb0195_like; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_optiongenerale_name_d6fb0195_like" ON demo."BaseBillet_optiongenerale" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_paiement_stripe_reservation_id_9643913c; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_paiement_stripe_reservation_id_9643913c" ON demo."BaseBillet_paiement_stripe" USING btree (reservation_id);


--
-- Name: BaseBillet_paiement_stripe_user_id_03041fc6; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_paiement_stripe_user_id_03041fc6" ON demo."BaseBillet_paiement_stripe" USING btree (user_id);


--
-- Name: BaseBillet_price_adhesion_obligatoire_id_043901b7; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_price_adhesion_obligatoire_id_043901b7" ON demo."BaseBillet_price" USING btree (adhesion_obligatoire_id);


--
-- Name: BaseBillet_price_product_id_a7d53d46; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_price_product_id_a7d53d46" ON demo."BaseBillet_price" USING btree (product_id);


--
-- Name: BaseBillet_pricesold_price_id_017f6621; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_pricesold_price_id_017f6621" ON demo."BaseBillet_pricesold" USING btree (price_id);


--
-- Name: BaseBillet_pricesold_productsold_id_d61e1c5f; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_pricesold_productsold_id_d61e1c5f" ON demo."BaseBillet_pricesold" USING btree (productsold_id);


--
-- Name: BaseBillet_product_option__optiongenerale_id_7714e607; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option__optiongenerale_id_7714e607" ON demo."BaseBillet_product_option_generale_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_product_option__optiongenerale_id_ded928b6; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option__optiongenerale_id_ded928b6" ON demo."BaseBillet_product_option_generale_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_checkbox_product_id_84a7c765; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option_generale_checkbox_product_id_84a7c765" ON demo."BaseBillet_product_option_generale_checkbox" USING btree (product_id);


--
-- Name: BaseBillet_product_option_generale_radio_product_id_50c10a7b; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option_generale_radio_product_id_50c10a7b" ON demo."BaseBillet_product_option_generale_radio" USING btree (product_id);


--
-- Name: BaseBillet_product_tag_product_id_00f8ae38; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_tag_product_id_00f8ae38" ON demo."BaseBillet_product_tag" USING btree (product_id);


--
-- Name: BaseBillet_product_tag_tag_id_68675245; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_tag_tag_id_68675245" ON demo."BaseBillet_product_tag" USING btree (tag_id);


--
-- Name: BaseBillet_productsold_event_id_c817df43; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_productsold_event_id_c817df43" ON demo."BaseBillet_productsold" USING btree (event_id);


--
-- Name: BaseBillet_productsold_product_id_afb2fb6e; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_productsold_product_id_afb2fb6e" ON demo."BaseBillet_productsold" USING btree (product_id);


--
-- Name: BaseBillet_reservation_event_id_7404fad0; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_event_id_7404fad0" ON demo."BaseBillet_reservation" USING btree (event_id);


--
-- Name: BaseBillet_reservation_options_optiongenerale_id_bc5048ee; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_options_optiongenerale_id_bc5048ee" ON demo."BaseBillet_reservation_options" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_reservation_options_reservation_id_bf305174; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_options_reservation_id_bf305174" ON demo."BaseBillet_reservation_options" USING btree (reservation_id);


--
-- Name: BaseBillet_reservation_user_commande_id_2a3fe1fd; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_user_commande_id_2a3fe1fd" ON demo."BaseBillet_reservation" USING btree (user_commande_id);


--
-- Name: BaseBillet_tag_name_faabf7e0; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_tag_name_faabf7e0" ON demo."BaseBillet_tag" USING btree (name);


--
-- Name: BaseBillet_tag_name_faabf7e0_like; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_tag_name_faabf7e0_like" ON demo."BaseBillet_tag" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_ticket_pricesold_id_1984d9e4; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_ticket_pricesold_id_1984d9e4" ON demo."BaseBillet_ticket" USING btree (pricesold_id);


--
-- Name: BaseBillet_ticket_reservation_id_226cfb21; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_ticket_reservation_id_226cfb21" ON demo."BaseBillet_ticket" USING btree (reservation_id);


--
-- Name: rest_framework_api_key_apikey_created_c61872d9; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_created_c61872d9 ON demo.rest_framework_api_key_apikey USING btree (created);


--
-- Name: rest_framework_api_key_apikey_id_6e07e68e_like; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_id_6e07e68e_like ON demo.rest_framework_api_key_apikey USING btree (id varchar_pattern_ops);


--
-- Name: rest_framework_api_key_apikey_prefix_4e0db5f8_like; Type: INDEX; Schema: demo; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_prefix_4e0db5f8_like ON demo.rest_framework_api_key_apikey USING btree (prefix varchar_pattern_ops);


--
-- Name: BaseBillet_apikey_name_77c0c277_like; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_apikey_name_77c0c277_like" ON meta."BaseBillet_externalapikey" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_artist_on_event_artist_id_fd91cee9; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_artist_on_event_artist_id_fd91cee9" ON meta."BaseBillet_artist_on_event" USING btree (artist_id);


--
-- Name: BaseBillet_artist_on_event_event_id_29dd03f1; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_artist_on_event_event_id_29dd03f1" ON meta."BaseBillet_artist_on_event" USING btree (event_id);


--
-- Name: BaseBillet_configuration_o_configuration_id_2e19f154; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_configuration_id_2e19f154" ON meta."BaseBillet_configuration_option_generale_radio" USING btree (configuration_id);


--
-- Name: BaseBillet_configuration_o_configuration_id_bbe225a5; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_configuration_id_bbe225a5" ON meta."BaseBillet_configuration_option_generale_checkbox" USING btree (configuration_id);


--
-- Name: BaseBillet_configuration_o_optiongenerale_id_7e69c71b; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_optiongenerale_id_7e69c71b" ON meta."BaseBillet_configuration_option_generale_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_configuration_o_optiongenerale_id_83c65e17; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_optiongenerale_id_83c65e17" ON meta."BaseBillet_configuration_option_generale_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_configuration_organisation_8d66658d; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_organisation_8d66658d" ON meta."BaseBillet_configuration" USING btree (organisation);


--
-- Name: BaseBillet_configuration_organisation_8d66658d_like; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_organisation_8d66658d_like" ON meta."BaseBillet_configuration" USING btree (organisation varchar_pattern_ops);


--
-- Name: BaseBillet_configuration_slug_7b38f49e; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_slug_7b38f49e" ON meta."BaseBillet_configuration" USING btree (slug);


--
-- Name: BaseBillet_configuration_slug_7b38f49e_like; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_slug_7b38f49e_like" ON meta."BaseBillet_configuration" USING btree (slug varchar_pattern_ops);


--
-- Name: BaseBillet_event_options_checkbox_event_id_6389bff4; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_checkbox_event_id_6389bff4" ON meta."BaseBillet_event_options_checkbox" USING btree (event_id);


--
-- Name: BaseBillet_event_options_checkbox_optiongenerale_id_b5d7c04b; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_checkbox_optiongenerale_id_b5d7c04b" ON meta."BaseBillet_event_options_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio_event_id_172366cc; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_radio_event_id_172366cc" ON meta."BaseBillet_event_options_radio" USING btree (event_id);


--
-- Name: BaseBillet_event_options_radio_optiongenerale_id_0dd0f546; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_radio_optiongenerale_id_0dd0f546" ON meta."BaseBillet_event_options_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_event_products_event_id_e8b98de0; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_products_event_id_e8b98de0" ON meta."BaseBillet_event_products" USING btree (event_id);


--
-- Name: BaseBillet_event_products_product_id_cdec0e20; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_products_product_id_cdec0e20" ON meta."BaseBillet_event_products" USING btree (product_id);


--
-- Name: BaseBillet_event_recurrent_event_id_0656b7d1; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_recurrent_event_id_0656b7d1" ON meta."BaseBillet_event_recurrent" USING btree (event_id);


--
-- Name: BaseBillet_event_recurrent_weekday_id_130a2743; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_recurrent_weekday_id_130a2743" ON meta."BaseBillet_event_recurrent" USING btree (weekday_id);


--
-- Name: BaseBillet_event_slug_5bdd3465_like; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_slug_5bdd3465_like" ON meta."BaseBillet_event" USING btree (slug varchar_pattern_ops);


--
-- Name: BaseBillet_event_tag_event_id_70d3f9f4; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_tag_event_id_70d3f9f4" ON meta."BaseBillet_event_tag" USING btree (event_id);


--
-- Name: BaseBillet_event_tag_tag_id_42dafd42; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_tag_tag_id_42dafd42" ON meta."BaseBillet_event_tag" USING btree (tag_id);


--
-- Name: BaseBillet_externalapikey_key_id_f5eff8fe_like; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_externalapikey_key_id_f5eff8fe_like" ON meta."BaseBillet_externalapikey" USING btree (key_id varchar_pattern_ops);


--
-- Name: BaseBillet_lignearticle_carte_id_8ab02e3c; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_carte_id_8ab02e3c" ON meta."BaseBillet_lignearticle" USING btree (carte_id);


--
-- Name: BaseBillet_lignearticle_paiement_stripe_id_82b4a0d3; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_paiement_stripe_id_82b4a0d3" ON meta."BaseBillet_lignearticle" USING btree (paiement_stripe_id);


--
-- Name: BaseBillet_lignearticle_pricesold_id_fc351d3d; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_pricesold_id_fc351d3d" ON meta."BaseBillet_lignearticle" USING btree (pricesold_id);


--
-- Name: BaseBillet_membership_first_name_80925438; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_first_name_80925438" ON meta."BaseBillet_membership" USING btree (first_name);


--
-- Name: BaseBillet_membership_first_name_80925438_like; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_first_name_80925438_like" ON meta."BaseBillet_membership" USING btree (first_name varchar_pattern_ops);


--
-- Name: BaseBillet_membership_opti_optiongenerale_id_87513e51; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_opti_optiongenerale_id_87513e51" ON meta."BaseBillet_membership_option_generale" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_membership_option_generale_membership_id_d255b3ce; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_option_generale_membership_id_d255b3ce" ON meta."BaseBillet_membership_option_generale" USING btree (membership_id);


--
-- Name: BaseBillet_membership_price_id_a4571820; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_price_id_a4571820" ON meta."BaseBillet_membership" USING btree (price_id);


--
-- Name: BaseBillet_membership_user_id_2b02a750; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_user_id_2b02a750" ON meta."BaseBillet_membership" USING btree (user_id);


--
-- Name: BaseBillet_optiongenerale_name_d6fb0195_like; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_optiongenerale_name_d6fb0195_like" ON meta."BaseBillet_optiongenerale" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_paiement_stripe_reservation_id_9643913c; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_paiement_stripe_reservation_id_9643913c" ON meta."BaseBillet_paiement_stripe" USING btree (reservation_id);


--
-- Name: BaseBillet_paiement_stripe_user_id_03041fc6; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_paiement_stripe_user_id_03041fc6" ON meta."BaseBillet_paiement_stripe" USING btree (user_id);


--
-- Name: BaseBillet_price_adhesion_obligatoire_id_043901b7; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_price_adhesion_obligatoire_id_043901b7" ON meta."BaseBillet_price" USING btree (adhesion_obligatoire_id);


--
-- Name: BaseBillet_price_product_id_a7d53d46; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_price_product_id_a7d53d46" ON meta."BaseBillet_price" USING btree (product_id);


--
-- Name: BaseBillet_pricesold_price_id_017f6621; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_pricesold_price_id_017f6621" ON meta."BaseBillet_pricesold" USING btree (price_id);


--
-- Name: BaseBillet_pricesold_productsold_id_d61e1c5f; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_pricesold_productsold_id_d61e1c5f" ON meta."BaseBillet_pricesold" USING btree (productsold_id);


--
-- Name: BaseBillet_product_option__optiongenerale_id_7714e607; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option__optiongenerale_id_7714e607" ON meta."BaseBillet_product_option_generale_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_product_option__optiongenerale_id_ded928b6; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option__optiongenerale_id_ded928b6" ON meta."BaseBillet_product_option_generale_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_checkbox_product_id_84a7c765; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option_generale_checkbox_product_id_84a7c765" ON meta."BaseBillet_product_option_generale_checkbox" USING btree (product_id);


--
-- Name: BaseBillet_product_option_generale_radio_product_id_50c10a7b; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option_generale_radio_product_id_50c10a7b" ON meta."BaseBillet_product_option_generale_radio" USING btree (product_id);


--
-- Name: BaseBillet_product_tag_product_id_00f8ae38; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_tag_product_id_00f8ae38" ON meta."BaseBillet_product_tag" USING btree (product_id);


--
-- Name: BaseBillet_product_tag_tag_id_68675245; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_tag_tag_id_68675245" ON meta."BaseBillet_product_tag" USING btree (tag_id);


--
-- Name: BaseBillet_productsold_event_id_c817df43; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_productsold_event_id_c817df43" ON meta."BaseBillet_productsold" USING btree (event_id);


--
-- Name: BaseBillet_productsold_product_id_afb2fb6e; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_productsold_product_id_afb2fb6e" ON meta."BaseBillet_productsold" USING btree (product_id);


--
-- Name: BaseBillet_reservation_event_id_7404fad0; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_event_id_7404fad0" ON meta."BaseBillet_reservation" USING btree (event_id);


--
-- Name: BaseBillet_reservation_options_optiongenerale_id_bc5048ee; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_options_optiongenerale_id_bc5048ee" ON meta."BaseBillet_reservation_options" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_reservation_options_reservation_id_bf305174; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_options_reservation_id_bf305174" ON meta."BaseBillet_reservation_options" USING btree (reservation_id);


--
-- Name: BaseBillet_reservation_user_commande_id_2a3fe1fd; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_user_commande_id_2a3fe1fd" ON meta."BaseBillet_reservation" USING btree (user_commande_id);


--
-- Name: BaseBillet_tag_name_faabf7e0; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_tag_name_faabf7e0" ON meta."BaseBillet_tag" USING btree (name);


--
-- Name: BaseBillet_tag_name_faabf7e0_like; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_tag_name_faabf7e0_like" ON meta."BaseBillet_tag" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_ticket_pricesold_id_1984d9e4; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_ticket_pricesold_id_1984d9e4" ON meta."BaseBillet_ticket" USING btree (pricesold_id);


--
-- Name: BaseBillet_ticket_reservation_id_226cfb21; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_ticket_reservation_id_226cfb21" ON meta."BaseBillet_ticket" USING btree (reservation_id);


--
-- Name: rest_framework_api_key_apikey_created_c61872d9; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_created_c61872d9 ON meta.rest_framework_api_key_apikey USING btree (created);


--
-- Name: rest_framework_api_key_apikey_id_6e07e68e_like; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_id_6e07e68e_like ON meta.rest_framework_api_key_apikey USING btree (id varchar_pattern_ops);


--
-- Name: rest_framework_api_key_apikey_prefix_4e0db5f8_like; Type: INDEX; Schema: meta; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_prefix_4e0db5f8_like ON meta.rest_framework_api_key_apikey USING btree (prefix varchar_pattern_ops);


--
-- Name: AuthBillet_terminalpairingtoken_user_id_097db473; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "AuthBillet_terminalpairingtoken_user_id_097db473" ON public."AuthBillet_terminalpairingtoken" USING btree (user_id);


--
-- Name: AuthBillet_tibilletuser_client_achat_client_id_e9bbb546; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "AuthBillet_tibilletuser_client_achat_client_id_e9bbb546" ON public."AuthBillet_tibilletuser_client_achat" USING btree (client_id);


--
-- Name: AuthBillet_tibilletuser_client_achat_tibilletuser_id_87ac98eb; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "AuthBillet_tibilletuser_client_achat_tibilletuser_id_87ac98eb" ON public."AuthBillet_tibilletuser_client_achat" USING btree (tibilletuser_id);


--
-- Name: AuthBillet_tibilletuser_client_admin_client_id_33204d32; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "AuthBillet_tibilletuser_client_admin_client_id_33204d32" ON public."AuthBillet_tibilletuser_client_admin" USING btree (client_id);


--
-- Name: AuthBillet_tibilletuser_client_admin_tibilletuser_id_f8e7db79; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "AuthBillet_tibilletuser_client_admin_tibilletuser_id_f8e7db79" ON public."AuthBillet_tibilletuser_client_admin" USING btree (tibilletuser_id);


--
-- Name: AuthBillet_tibilletuser_client_source_id_1134f8ae; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "AuthBillet_tibilletuser_client_source_id_1134f8ae" ON public."AuthBillet_tibilletuser" USING btree (client_source_id);


--
-- Name: AuthBillet_tibilletuser_email_17e33557_like; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "AuthBillet_tibilletuser_email_17e33557_like" ON public."AuthBillet_tibilletuser" USING btree (email varchar_pattern_ops);


--
-- Name: AuthBillet_tibilletuser_groups_group_id_09a9f9aa; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "AuthBillet_tibilletuser_groups_group_id_09a9f9aa" ON public."AuthBillet_tibilletuser_groups" USING btree (group_id);


--
-- Name: AuthBillet_tibilletuser_groups_tibilletuser_id_4ef900da; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "AuthBillet_tibilletuser_groups_tibilletuser_id_4ef900da" ON public."AuthBillet_tibilletuser_groups" USING btree (tibilletuser_id);


--
-- Name: AuthBillet_tibilletuser_us_tibilletuser_id_ad6127bc; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "AuthBillet_tibilletuser_us_tibilletuser_id_ad6127bc" ON public."AuthBillet_tibilletuser_user_permissions" USING btree (tibilletuser_id);


--
-- Name: AuthBillet_tibilletuser_user_permissions_permission_id_28d47b9d; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "AuthBillet_tibilletuser_user_permissions_permission_id_28d47b9d" ON public."AuthBillet_tibilletuser_user_permissions" USING btree (permission_id);


--
-- Name: AuthBillet_tibilletuser_username_cc6caba6_like; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "AuthBillet_tibilletuser_username_cc6caba6_like" ON public."AuthBillet_tibilletuser" USING btree (username varchar_pattern_ops);


--
-- Name: Customers_client_name_24c8f3ee_like; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "Customers_client_name_24c8f3ee_like" ON public."Customers_client" USING btree (name varchar_pattern_ops);


--
-- Name: Customers_client_schema_name_fbdeea42_like; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "Customers_client_schema_name_fbdeea42_like" ON public."Customers_client" USING btree (schema_name varchar_pattern_ops);


--
-- Name: Customers_domain_domain_b2e1cfa7_like; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "Customers_domain_domain_b2e1cfa7_like" ON public."Customers_domain" USING btree (domain varchar_pattern_ops);


--
-- Name: Customers_domain_is_primary_2ea3f7cf; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "Customers_domain_is_primary_2ea3f7cf" ON public."Customers_domain" USING btree (is_primary);


--
-- Name: Customers_domain_tenant_id_07a53c46; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "Customers_domain_tenant_id_07a53c46" ON public."Customers_domain" USING btree (tenant_id);


--
-- Name: MetaBillet_eventdirectory_artist_id_c1c4a427; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "MetaBillet_eventdirectory_artist_id_c1c4a427" ON public."MetaBillet_eventdirectory" USING btree (artist_id);


--
-- Name: MetaBillet_eventdirectory_place_id_69ceb75c; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "MetaBillet_eventdirectory_place_id_69ceb75c" ON public."MetaBillet_eventdirectory" USING btree (place_id);


--
-- Name: MetaBillet_productdirectory_place_id_885e6624; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "MetaBillet_productdirectory_place_id_885e6624" ON public."MetaBillet_productdirectory" USING btree (place_id);


--
-- Name: QrcodeCashless_asset_origin_id_5d706c12; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_asset_origin_id_5d706c12" ON public."QrcodeCashless_asset" USING btree (origin_id);


--
-- Name: QrcodeCashless_cartecashless_detail_id_374b04e5; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_cartecashless_detail_id_374b04e5" ON public."QrcodeCashless_cartecashless" USING btree (detail_id);


--
-- Name: QrcodeCashless_cartecashless_number_8ab8d15d_like; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_cartecashless_number_8ab8d15d_like" ON public."QrcodeCashless_cartecashless" USING btree (number varchar_pattern_ops);


--
-- Name: QrcodeCashless_cartecashless_tag_id_b13703c9_like; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_cartecashless_tag_id_b13703c9_like" ON public."QrcodeCashless_cartecashless" USING btree (tag_id varchar_pattern_ops);


--
-- Name: QrcodeCashless_cartecashless_user_id_95d46686; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_cartecashless_user_id_95d46686" ON public."QrcodeCashless_cartecashless" USING btree (user_id);


--
-- Name: QrcodeCashless_detail_origine_id_67e9af46; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_detail_origine_id_67e9af46" ON public."QrcodeCashless_detail" USING btree (origine_id);


--
-- Name: QrcodeCashless_detail_slug_fd250baa_like; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_detail_slug_fd250baa_like" ON public."QrcodeCashless_detail" USING btree (slug varchar_pattern_ops);


--
-- Name: QrcodeCashless_federatedcashless_asset_id_c53450b6; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_federatedcashless_asset_id_c53450b6" ON public."QrcodeCashless_federatedcashless" USING btree (asset_id);


--
-- Name: QrcodeCashless_federatedcashless_client_id_0ca720ec; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_federatedcashless_client_id_0ca720ec" ON public."QrcodeCashless_federatedcashless" USING btree (client_id);


--
-- Name: QrcodeCashless_syncfederatedlog_card_id_4df1fccb; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_syncfederatedlog_card_id_4df1fccb" ON public."QrcodeCashless_syncfederatedlog" USING btree (card_id);


--
-- Name: QrcodeCashless_syncfederatedlog_client_source_id_ebe588df; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_syncfederatedlog_client_source_id_ebe588df" ON public."QrcodeCashless_syncfederatedlog" USING btree (client_source_id);


--
-- Name: QrcodeCashless_syncfederatedlog_wallet_id_9ec97b2b; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_syncfederatedlog_wallet_id_9ec97b2b" ON public."QrcodeCashless_syncfederatedlog" USING btree (wallet_id);


--
-- Name: QrcodeCashless_wallet_asset_id_2708f2b3; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_wallet_asset_id_2708f2b3" ON public."QrcodeCashless_wallet" USING btree (asset_id);


--
-- Name: QrcodeCashless_wallet_card_id_0fdef3d5; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_wallet_card_id_0fdef3d5" ON public."QrcodeCashless_wallet" USING btree (card_id);


--
-- Name: QrcodeCashless_wallet_user_id_8796d2a0; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX "QrcodeCashless_wallet_user_id_8796d2a0" ON public."QrcodeCashless_wallet" USING btree (user_id);


--
-- Name: auth_group_name_a6ea08ec_like; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX auth_group_name_a6ea08ec_like ON public.auth_group USING btree (name varchar_pattern_ops);


--
-- Name: auth_group_permissions_group_id_b120cbf9; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX auth_group_permissions_group_id_b120cbf9 ON public.auth_group_permissions USING btree (group_id);


--
-- Name: auth_group_permissions_permission_id_84c5c92e; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX auth_group_permissions_permission_id_84c5c92e ON public.auth_group_permissions USING btree (permission_id);


--
-- Name: auth_permission_content_type_id_2f476e4b; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX auth_permission_content_type_id_2f476e4b ON public.auth_permission USING btree (content_type_id);


--
-- Name: authtoken_token_key_10f0b77e_like; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX authtoken_token_key_10f0b77e_like ON public.authtoken_token USING btree (key varchar_pattern_ops);


--
-- Name: django_admin_log_content_type_id_c4bce8eb; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX django_admin_log_content_type_id_c4bce8eb ON public.django_admin_log USING btree (content_type_id);


--
-- Name: django_admin_log_user_id_c564eba6; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX django_admin_log_user_id_c564eba6 ON public.django_admin_log USING btree (user_id);


--
-- Name: django_session_expire_date_a5c62663; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX django_session_expire_date_a5c62663 ON public.django_session USING btree (expire_date);


--
-- Name: django_session_session_key_c0390e0f_like; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX django_session_session_key_c0390e0f_like ON public.django_session USING btree (session_key varchar_pattern_ops);


--
-- Name: django_site_domain_a2e37b91_like; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX django_site_domain_a2e37b91_like ON public.django_site USING btree (domain varchar_pattern_ops);


--
-- Name: token_blacklist_outstandingtoken_jti_hex_d9bdf6f7_like; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX token_blacklist_outstandingtoken_jti_hex_d9bdf6f7_like ON public.token_blacklist_outstandingtoken USING btree (jti varchar_pattern_ops);


--
-- Name: token_blacklist_outstandingtoken_user_id_83bc629a; Type: INDEX; Schema: public; Owner: ticket_postgres_user
--

CREATE INDEX token_blacklist_outstandingtoken_user_id_83bc629a ON public.token_blacklist_outstandingtoken USING btree (user_id);


--
-- Name: BaseBillet_apikey_name_77c0c277_like; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_apikey_name_77c0c277_like" ON ziskakan."BaseBillet_externalapikey" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_artist_on_event_artist_id_fd91cee9; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_artist_on_event_artist_id_fd91cee9" ON ziskakan."BaseBillet_artist_on_event" USING btree (artist_id);


--
-- Name: BaseBillet_artist_on_event_event_id_29dd03f1; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_artist_on_event_event_id_29dd03f1" ON ziskakan."BaseBillet_artist_on_event" USING btree (event_id);


--
-- Name: BaseBillet_configuration_o_configuration_id_2e19f154; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_configuration_id_2e19f154" ON ziskakan."BaseBillet_configuration_option_generale_radio" USING btree (configuration_id);


--
-- Name: BaseBillet_configuration_o_configuration_id_bbe225a5; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_configuration_id_bbe225a5" ON ziskakan."BaseBillet_configuration_option_generale_checkbox" USING btree (configuration_id);


--
-- Name: BaseBillet_configuration_o_optiongenerale_id_7e69c71b; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_optiongenerale_id_7e69c71b" ON ziskakan."BaseBillet_configuration_option_generale_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_configuration_o_optiongenerale_id_83c65e17; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_o_optiongenerale_id_83c65e17" ON ziskakan."BaseBillet_configuration_option_generale_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_configuration_organisation_8d66658d; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_organisation_8d66658d" ON ziskakan."BaseBillet_configuration" USING btree (organisation);


--
-- Name: BaseBillet_configuration_organisation_8d66658d_like; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_organisation_8d66658d_like" ON ziskakan."BaseBillet_configuration" USING btree (organisation varchar_pattern_ops);


--
-- Name: BaseBillet_configuration_slug_7b38f49e; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_slug_7b38f49e" ON ziskakan."BaseBillet_configuration" USING btree (slug);


--
-- Name: BaseBillet_configuration_slug_7b38f49e_like; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_configuration_slug_7b38f49e_like" ON ziskakan."BaseBillet_configuration" USING btree (slug varchar_pattern_ops);


--
-- Name: BaseBillet_event_options_checkbox_event_id_6389bff4; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_checkbox_event_id_6389bff4" ON ziskakan."BaseBillet_event_options_checkbox" USING btree (event_id);


--
-- Name: BaseBillet_event_options_checkbox_optiongenerale_id_b5d7c04b; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_checkbox_optiongenerale_id_b5d7c04b" ON ziskakan."BaseBillet_event_options_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_event_options_radio_event_id_172366cc; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_radio_event_id_172366cc" ON ziskakan."BaseBillet_event_options_radio" USING btree (event_id);


--
-- Name: BaseBillet_event_options_radio_optiongenerale_id_0dd0f546; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_options_radio_optiongenerale_id_0dd0f546" ON ziskakan."BaseBillet_event_options_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_event_products_event_id_e8b98de0; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_products_event_id_e8b98de0" ON ziskakan."BaseBillet_event_products" USING btree (event_id);


--
-- Name: BaseBillet_event_products_product_id_cdec0e20; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_products_product_id_cdec0e20" ON ziskakan."BaseBillet_event_products" USING btree (product_id);


--
-- Name: BaseBillet_event_recurrent_event_id_0656b7d1; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_recurrent_event_id_0656b7d1" ON ziskakan."BaseBillet_event_recurrent" USING btree (event_id);


--
-- Name: BaseBillet_event_recurrent_weekday_id_130a2743; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_recurrent_weekday_id_130a2743" ON ziskakan."BaseBillet_event_recurrent" USING btree (weekday_id);


--
-- Name: BaseBillet_event_slug_5bdd3465_like; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_slug_5bdd3465_like" ON ziskakan."BaseBillet_event" USING btree (slug varchar_pattern_ops);


--
-- Name: BaseBillet_event_tag_event_id_70d3f9f4; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_tag_event_id_70d3f9f4" ON ziskakan."BaseBillet_event_tag" USING btree (event_id);


--
-- Name: BaseBillet_event_tag_tag_id_42dafd42; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_event_tag_tag_id_42dafd42" ON ziskakan."BaseBillet_event_tag" USING btree (tag_id);


--
-- Name: BaseBillet_externalapikey_key_id_f5eff8fe_like; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_externalapikey_key_id_f5eff8fe_like" ON ziskakan."BaseBillet_externalapikey" USING btree (key_id varchar_pattern_ops);


--
-- Name: BaseBillet_lignearticle_carte_id_8ab02e3c; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_carte_id_8ab02e3c" ON ziskakan."BaseBillet_lignearticle" USING btree (carte_id);


--
-- Name: BaseBillet_lignearticle_paiement_stripe_id_82b4a0d3; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_paiement_stripe_id_82b4a0d3" ON ziskakan."BaseBillet_lignearticle" USING btree (paiement_stripe_id);


--
-- Name: BaseBillet_lignearticle_pricesold_id_fc351d3d; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_lignearticle_pricesold_id_fc351d3d" ON ziskakan."BaseBillet_lignearticle" USING btree (pricesold_id);


--
-- Name: BaseBillet_membership_first_name_80925438; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_first_name_80925438" ON ziskakan."BaseBillet_membership" USING btree (first_name);


--
-- Name: BaseBillet_membership_first_name_80925438_like; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_first_name_80925438_like" ON ziskakan."BaseBillet_membership" USING btree (first_name varchar_pattern_ops);


--
-- Name: BaseBillet_membership_opti_optiongenerale_id_87513e51; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_opti_optiongenerale_id_87513e51" ON ziskakan."BaseBillet_membership_option_generale" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_membership_option_generale_membership_id_d255b3ce; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_option_generale_membership_id_d255b3ce" ON ziskakan."BaseBillet_membership_option_generale" USING btree (membership_id);


--
-- Name: BaseBillet_membership_price_id_a4571820; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_price_id_a4571820" ON ziskakan."BaseBillet_membership" USING btree (price_id);


--
-- Name: BaseBillet_membership_user_id_2b02a750; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_membership_user_id_2b02a750" ON ziskakan."BaseBillet_membership" USING btree (user_id);


--
-- Name: BaseBillet_optiongenerale_name_d6fb0195_like; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_optiongenerale_name_d6fb0195_like" ON ziskakan."BaseBillet_optiongenerale" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_paiement_stripe_reservation_id_9643913c; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_paiement_stripe_reservation_id_9643913c" ON ziskakan."BaseBillet_paiement_stripe" USING btree (reservation_id);


--
-- Name: BaseBillet_paiement_stripe_user_id_03041fc6; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_paiement_stripe_user_id_03041fc6" ON ziskakan."BaseBillet_paiement_stripe" USING btree (user_id);


--
-- Name: BaseBillet_price_adhesion_obligatoire_id_043901b7; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_price_adhesion_obligatoire_id_043901b7" ON ziskakan."BaseBillet_price" USING btree (adhesion_obligatoire_id);


--
-- Name: BaseBillet_price_product_id_a7d53d46; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_price_product_id_a7d53d46" ON ziskakan."BaseBillet_price" USING btree (product_id);


--
-- Name: BaseBillet_pricesold_price_id_017f6621; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_pricesold_price_id_017f6621" ON ziskakan."BaseBillet_pricesold" USING btree (price_id);


--
-- Name: BaseBillet_pricesold_productsold_id_d61e1c5f; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_pricesold_productsold_id_d61e1c5f" ON ziskakan."BaseBillet_pricesold" USING btree (productsold_id);


--
-- Name: BaseBillet_product_option__optiongenerale_id_7714e607; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option__optiongenerale_id_7714e607" ON ziskakan."BaseBillet_product_option_generale_radio" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_product_option__optiongenerale_id_ded928b6; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option__optiongenerale_id_ded928b6" ON ziskakan."BaseBillet_product_option_generale_checkbox" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_product_option_generale_checkbox_product_id_84a7c765; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option_generale_checkbox_product_id_84a7c765" ON ziskakan."BaseBillet_product_option_generale_checkbox" USING btree (product_id);


--
-- Name: BaseBillet_product_option_generale_radio_product_id_50c10a7b; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_option_generale_radio_product_id_50c10a7b" ON ziskakan."BaseBillet_product_option_generale_radio" USING btree (product_id);


--
-- Name: BaseBillet_product_tag_product_id_00f8ae38; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_tag_product_id_00f8ae38" ON ziskakan."BaseBillet_product_tag" USING btree (product_id);


--
-- Name: BaseBillet_product_tag_tag_id_68675245; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_product_tag_tag_id_68675245" ON ziskakan."BaseBillet_product_tag" USING btree (tag_id);


--
-- Name: BaseBillet_productsold_event_id_c817df43; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_productsold_event_id_c817df43" ON ziskakan."BaseBillet_productsold" USING btree (event_id);


--
-- Name: BaseBillet_productsold_product_id_afb2fb6e; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_productsold_product_id_afb2fb6e" ON ziskakan."BaseBillet_productsold" USING btree (product_id);


--
-- Name: BaseBillet_reservation_event_id_7404fad0; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_event_id_7404fad0" ON ziskakan."BaseBillet_reservation" USING btree (event_id);


--
-- Name: BaseBillet_reservation_options_optiongenerale_id_bc5048ee; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_options_optiongenerale_id_bc5048ee" ON ziskakan."BaseBillet_reservation_options" USING btree (optiongenerale_id);


--
-- Name: BaseBillet_reservation_options_reservation_id_bf305174; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_options_reservation_id_bf305174" ON ziskakan."BaseBillet_reservation_options" USING btree (reservation_id);


--
-- Name: BaseBillet_reservation_user_commande_id_2a3fe1fd; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_reservation_user_commande_id_2a3fe1fd" ON ziskakan."BaseBillet_reservation" USING btree (user_commande_id);


--
-- Name: BaseBillet_tag_name_faabf7e0; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_tag_name_faabf7e0" ON ziskakan."BaseBillet_tag" USING btree (name);


--
-- Name: BaseBillet_tag_name_faabf7e0_like; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_tag_name_faabf7e0_like" ON ziskakan."BaseBillet_tag" USING btree (name varchar_pattern_ops);


--
-- Name: BaseBillet_ticket_pricesold_id_1984d9e4; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_ticket_pricesold_id_1984d9e4" ON ziskakan."BaseBillet_ticket" USING btree (pricesold_id);


--
-- Name: BaseBillet_ticket_reservation_id_226cfb21; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX "BaseBillet_ticket_reservation_id_226cfb21" ON ziskakan."BaseBillet_ticket" USING btree (reservation_id);


--
-- Name: rest_framework_api_key_apikey_created_c61872d9; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_created_c61872d9 ON ziskakan.rest_framework_api_key_apikey USING btree (created);


--
-- Name: rest_framework_api_key_apikey_id_6e07e68e_like; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_id_6e07e68e_like ON ziskakan.rest_framework_api_key_apikey USING btree (id varchar_pattern_ops);


--
-- Name: rest_framework_api_key_apikey_prefix_4e0db5f8_like; Type: INDEX; Schema: ziskakan; Owner: ticket_postgres_user
--

CREATE INDEX rest_framework_api_key_apikey_prefix_4e0db5f8_like ON ziskakan.rest_framework_api_key_apikey USING btree (prefix varchar_pattern_ops);


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_user_id_c99e3878_fk_AuthBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_user_id_c99e3878_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_artist_id_fd91cee9_fk_Customers; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_artist_id_fd91cee9_fk_Customers" FOREIGN KEY (artist_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_event_id_29dd03f1_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_event_id_29dd03f1_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES "balaphonik-sound-system"."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configura_configuration_id_2e19f154_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configura_configuration_id_2e19f154_fk_BaseBille" FOREIGN KEY (configuration_id) REFERENCES "balaphonik-sound-system"."BaseBillet_configuration"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configura_configuration_id_bbe225a5_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configura_configuration_id_bbe225a5_fk_BaseBille" FOREIGN KEY (configuration_id) REFERENCES "balaphonik-sound-system"."BaseBillet_configuration"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configura_optiongenerale_id_7e69c71b_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configura_optiongenerale_id_7e69c71b_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES "balaphonik-sound-system"."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configura_optiongenerale_id_83c65e17_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configura_optiongenerale_id_83c65e17_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES "balaphonik-sound-system"."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_opt_event_id_172366cc_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_opt_event_id_172366cc_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES "balaphonik-sound-system"."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_opt_event_id_6389bff4_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_opt_event_id_6389bff4_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES "balaphonik-sound-system"."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_opt_optiongenerale_id_0dd0f546_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_opt_optiongenerale_id_0dd0f546_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES "balaphonik-sound-system"."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_opt_optiongenerale_id_b5d7c04b_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_opt_optiongenerale_id_b5d7c04b_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES "balaphonik-sound-system"."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_products BaseBillet_event_pro_event_id_e8b98de0_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_pro_event_id_e8b98de0_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES "balaphonik-sound-system"."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_products BaseBillet_event_pro_product_id_cdec0e20_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_pro_product_id_cdec0e20_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES "balaphonik-sound-system"."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_rec_event_id_0656b7d1_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_rec_event_id_0656b7d1_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES "balaphonik-sound-system"."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_rec_weekday_id_130a2743_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_rec_weekday_id_130a2743_fk_BaseBille" FOREIGN KEY (weekday_id) REFERENCES "balaphonik-sound-system"."BaseBillet_weekday"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_event_id_70d3f9f4_fk_BaseBillet_event_uuid; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_event_id_70d3f9f4_fk_BaseBillet_event_uuid" FOREIGN KEY (event_id) REFERENCES "balaphonik-sound-system"."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_tag_id_42dafd42_fk_BaseBillet_tag_uuid; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_tag_id_42dafd42_fk_BaseBillet_tag_uuid" FOREIGN KEY (tag_id) REFERENCES "balaphonik-sound-system"."BaseBillet_tag"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_externalapikey BaseBillet_externala_key_id_f5eff8fe_fk_rest_fram; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_externala_key_id_f5eff8fe_fk_rest_fram" FOREIGN KEY (key_id) REFERENCES "balaphonik-sound-system".rest_framework_api_key_apikey(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_carte_id_8ab02e3c_fk_QrcodeCas; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_carte_id_8ab02e3c_fk_QrcodeCas" FOREIGN KEY (carte_id) REFERENCES public."QrcodeCashless_cartecashless"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_paiement_stripe_id_82b4a0d3_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_paiement_stripe_id_82b4a0d3_fk_BaseBille" FOREIGN KEY (paiement_stripe_id) REFERENCES "balaphonik-sound-system"."BaseBillet_paiement_stripe"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_pricesold_id_fc351d3d_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_pricesold_id_fc351d3d_fk_BaseBille" FOREIGN KEY (pricesold_id) REFERENCES "balaphonik-sound-system"."BaseBillet_pricesold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membershi_membership_id_d255b3ce_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membershi_membership_id_d255b3ce_fk_BaseBille" FOREIGN KEY (membership_id) REFERENCES "balaphonik-sound-system"."BaseBillet_membership"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membershi_optiongenerale_id_87513e51_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membershi_optiongenerale_id_87513e51_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES "balaphonik-sound-system"."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership BaseBillet_membershi_price_id_a4571820_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membershi_price_id_a4571820_fk_BaseBille" FOREIGN KEY (price_id) REFERENCES "balaphonik-sound-system"."BaseBillet_price"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership BaseBillet_membershi_user_id_2b02a750_fk_AuthBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membershi_user_id_2b02a750_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement__reservation_id_9643913c_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement__reservation_id_9643913c_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES "balaphonik-sound-system"."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement__user_id_03041fc6_fk_AuthBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement__user_id_03041fc6_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_price BaseBillet_price_adhesion_obligatoire_043901b7_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_adhesion_obligatoire_043901b7_fk_BaseBille" FOREIGN KEY (adhesion_obligatoire_id) REFERENCES "balaphonik-sound-system"."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_price BaseBillet_price_product_id_a7d53d46_fk_BaseBillet_product_uuid; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_product_id_a7d53d46_fk_BaseBillet_product_uuid" FOREIGN KEY (product_id) REFERENCES "balaphonik-sound-system"."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_price_id_017f6621_fk_BaseBillet_price_uuid; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_price_id_017f6621_fk_BaseBillet_price_uuid" FOREIGN KEY (price_id) REFERENCES "balaphonik-sound-system"."BaseBillet_price"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_productsold_id_d61e1c5f_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_productsold_id_d61e1c5f_fk_BaseBille" FOREIGN KEY (productsold_id) REFERENCES "balaphonik-sound-system"."BaseBillet_productsold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_o_optiongenerale_id_7714e607_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_o_optiongenerale_id_7714e607_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES "balaphonik-sound-system"."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_o_optiongenerale_id_ded928b6_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_o_optiongenerale_id_ded928b6_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES "balaphonik-sound-system"."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_o_product_id_50c10a7b_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_o_product_id_50c10a7b_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES "balaphonik-sound-system"."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_o_product_id_84a7c765_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_o_product_id_84a7c765_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES "balaphonik-sound-system"."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_tag BaseBillet_product_t_product_id_00f8ae38_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_t_product_id_00f8ae38_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES "balaphonik-sound-system"."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_tag_id_68675245_fk_BaseBillet_tag_uuid; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_tag_id_68675245_fk_BaseBillet_tag_uuid" FOREIGN KEY (tag_id) REFERENCES "balaphonik-sound-system"."BaseBillet_tag"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_productsold BaseBillet_productso_event_id_c817df43_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productso_event_id_c817df43_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES "balaphonik-sound-system"."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_productsold BaseBillet_productso_product_id_afb2fb6e_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productso_product_id_afb2fb6e_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES "balaphonik-sound-system"."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation BaseBillet_reservati_event_id_7404fad0_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservati_event_id_7404fad0_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES "balaphonik-sound-system"."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation_options BaseBillet_reservati_optiongenerale_id_bc5048ee_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservati_optiongenerale_id_bc5048ee_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES "balaphonik-sound-system"."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation_options BaseBillet_reservati_reservation_id_bf305174_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservati_reservation_id_bf305174_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES "balaphonik-sound-system"."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation BaseBillet_reservati_user_commande_id_2a3fe1fd_fk_AuthBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservati_user_commande_id_2a3fe1fd_fk_AuthBille" FOREIGN KEY (user_commande_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_ticket BaseBillet_ticket_pricesold_id_1984d9e4_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_pricesold_id_1984d9e4_fk_BaseBille" FOREIGN KEY (pricesold_id) REFERENCES "balaphonik-sound-system"."BaseBillet_pricesold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_ticket BaseBillet_ticket_reservation_id_226cfb21_fk_BaseBille; Type: FK CONSTRAINT; Schema: balaphonik-sound-system; Owner: ticket_postgres_user
--

ALTER TABLE ONLY "balaphonik-sound-system"."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_reservation_id_226cfb21_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES "balaphonik-sound-system"."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_user_id_c99e3878_fk_AuthBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_user_id_c99e3878_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_artist_id_fd91cee9_fk_Customers; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_artist_id_fd91cee9_fk_Customers" FOREIGN KEY (artist_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_event_id_29dd03f1_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_event_id_29dd03f1_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES billetistan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configura_configuration_id_2e19f154_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configura_configuration_id_2e19f154_fk_BaseBille" FOREIGN KEY (configuration_id) REFERENCES billetistan."BaseBillet_configuration"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configura_configuration_id_bbe225a5_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configura_configuration_id_bbe225a5_fk_BaseBille" FOREIGN KEY (configuration_id) REFERENCES billetistan."BaseBillet_configuration"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configura_optiongenerale_id_7e69c71b_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configura_optiongenerale_id_7e69c71b_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES billetistan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configura_optiongenerale_id_83c65e17_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configura_optiongenerale_id_83c65e17_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES billetistan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_opt_event_id_172366cc_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_opt_event_id_172366cc_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES billetistan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_opt_event_id_6389bff4_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_opt_event_id_6389bff4_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES billetistan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_opt_optiongenerale_id_0dd0f546_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_opt_optiongenerale_id_0dd0f546_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES billetistan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_opt_optiongenerale_id_b5d7c04b_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_opt_optiongenerale_id_b5d7c04b_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES billetistan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_products BaseBillet_event_pro_event_id_e8b98de0_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_pro_event_id_e8b98de0_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES billetistan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_products BaseBillet_event_pro_product_id_cdec0e20_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_pro_product_id_cdec0e20_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES billetistan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_rec_event_id_0656b7d1_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_rec_event_id_0656b7d1_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES billetistan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_rec_weekday_id_130a2743_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_rec_weekday_id_130a2743_fk_BaseBille" FOREIGN KEY (weekday_id) REFERENCES billetistan."BaseBillet_weekday"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_event_id_70d3f9f4_fk_BaseBillet_event_uuid; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_event_id_70d3f9f4_fk_BaseBillet_event_uuid" FOREIGN KEY (event_id) REFERENCES billetistan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_tag_id_42dafd42_fk_BaseBillet_tag_uuid; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_tag_id_42dafd42_fk_BaseBillet_tag_uuid" FOREIGN KEY (tag_id) REFERENCES billetistan."BaseBillet_tag"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_externalapikey BaseBillet_externala_key_id_f5eff8fe_fk_rest_fram; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_externala_key_id_f5eff8fe_fk_rest_fram" FOREIGN KEY (key_id) REFERENCES billetistan.rest_framework_api_key_apikey(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_carte_id_8ab02e3c_fk_QrcodeCas; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_carte_id_8ab02e3c_fk_QrcodeCas" FOREIGN KEY (carte_id) REFERENCES public."QrcodeCashless_cartecashless"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_paiement_stripe_id_82b4a0d3_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_paiement_stripe_id_82b4a0d3_fk_BaseBille" FOREIGN KEY (paiement_stripe_id) REFERENCES billetistan."BaseBillet_paiement_stripe"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_pricesold_id_fc351d3d_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_pricesold_id_fc351d3d_fk_BaseBille" FOREIGN KEY (pricesold_id) REFERENCES billetistan."BaseBillet_pricesold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membershi_membership_id_d255b3ce_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membershi_membership_id_d255b3ce_fk_BaseBille" FOREIGN KEY (membership_id) REFERENCES billetistan."BaseBillet_membership"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membershi_optiongenerale_id_87513e51_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membershi_optiongenerale_id_87513e51_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES billetistan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership BaseBillet_membershi_price_id_a4571820_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membershi_price_id_a4571820_fk_BaseBille" FOREIGN KEY (price_id) REFERENCES billetistan."BaseBillet_price"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership BaseBillet_membershi_user_id_2b02a750_fk_AuthBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membershi_user_id_2b02a750_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement__reservation_id_9643913c_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement__reservation_id_9643913c_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES billetistan."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement__user_id_03041fc6_fk_AuthBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement__user_id_03041fc6_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_price BaseBillet_price_adhesion_obligatoire_043901b7_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_adhesion_obligatoire_043901b7_fk_BaseBille" FOREIGN KEY (adhesion_obligatoire_id) REFERENCES billetistan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_price BaseBillet_price_product_id_a7d53d46_fk_BaseBillet_product_uuid; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_product_id_a7d53d46_fk_BaseBillet_product_uuid" FOREIGN KEY (product_id) REFERENCES billetistan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_price_id_017f6621_fk_BaseBillet_price_uuid; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_price_id_017f6621_fk_BaseBillet_price_uuid" FOREIGN KEY (price_id) REFERENCES billetistan."BaseBillet_price"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_productsold_id_d61e1c5f_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_productsold_id_d61e1c5f_fk_BaseBille" FOREIGN KEY (productsold_id) REFERENCES billetistan."BaseBillet_productsold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_o_optiongenerale_id_7714e607_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_o_optiongenerale_id_7714e607_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES billetistan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_o_optiongenerale_id_ded928b6_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_o_optiongenerale_id_ded928b6_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES billetistan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_o_product_id_50c10a7b_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_o_product_id_50c10a7b_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES billetistan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_o_product_id_84a7c765_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_o_product_id_84a7c765_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES billetistan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_tag BaseBillet_product_t_product_id_00f8ae38_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_t_product_id_00f8ae38_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES billetistan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_tag_id_68675245_fk_BaseBillet_tag_uuid; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_tag_id_68675245_fk_BaseBillet_tag_uuid" FOREIGN KEY (tag_id) REFERENCES billetistan."BaseBillet_tag"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_productsold BaseBillet_productso_event_id_c817df43_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productso_event_id_c817df43_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES billetistan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_productsold BaseBillet_productso_product_id_afb2fb6e_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productso_product_id_afb2fb6e_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES billetistan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation BaseBillet_reservati_event_id_7404fad0_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservati_event_id_7404fad0_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES billetistan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation_options BaseBillet_reservati_optiongenerale_id_bc5048ee_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservati_optiongenerale_id_bc5048ee_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES billetistan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation_options BaseBillet_reservati_reservation_id_bf305174_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservati_reservation_id_bf305174_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES billetistan."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation BaseBillet_reservati_user_commande_id_2a3fe1fd_fk_AuthBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservati_user_commande_id_2a3fe1fd_fk_AuthBille" FOREIGN KEY (user_commande_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_ticket BaseBillet_ticket_pricesold_id_1984d9e4_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_pricesold_id_1984d9e4_fk_BaseBille" FOREIGN KEY (pricesold_id) REFERENCES billetistan."BaseBillet_pricesold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_ticket BaseBillet_ticket_reservation_id_226cfb21_fk_BaseBille; Type: FK CONSTRAINT; Schema: billetistan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY billetistan."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_reservation_id_226cfb21_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES billetistan."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_user_id_c99e3878_fk_AuthBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_user_id_c99e3878_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_artist_id_fd91cee9_fk_Customers; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_artist_id_fd91cee9_fk_Customers" FOREIGN KEY (artist_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_event_id_29dd03f1_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_event_id_29dd03f1_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES demo."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configura_configuration_id_2e19f154_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configura_configuration_id_2e19f154_fk_BaseBille" FOREIGN KEY (configuration_id) REFERENCES demo."BaseBillet_configuration"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configura_configuration_id_bbe225a5_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configura_configuration_id_bbe225a5_fk_BaseBille" FOREIGN KEY (configuration_id) REFERENCES demo."BaseBillet_configuration"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configura_optiongenerale_id_7e69c71b_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configura_optiongenerale_id_7e69c71b_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES demo."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configura_optiongenerale_id_83c65e17_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configura_optiongenerale_id_83c65e17_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES demo."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_opt_event_id_172366cc_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_opt_event_id_172366cc_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES demo."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_opt_event_id_6389bff4_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_opt_event_id_6389bff4_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES demo."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_opt_optiongenerale_id_0dd0f546_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_opt_optiongenerale_id_0dd0f546_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES demo."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_opt_optiongenerale_id_b5d7c04b_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_opt_optiongenerale_id_b5d7c04b_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES demo."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_products BaseBillet_event_pro_event_id_e8b98de0_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_pro_event_id_e8b98de0_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES demo."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_products BaseBillet_event_pro_product_id_cdec0e20_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_pro_product_id_cdec0e20_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES demo."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_rec_event_id_0656b7d1_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_rec_event_id_0656b7d1_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES demo."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_rec_weekday_id_130a2743_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_rec_weekday_id_130a2743_fk_BaseBille" FOREIGN KEY (weekday_id) REFERENCES demo."BaseBillet_weekday"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_event_id_70d3f9f4_fk_BaseBillet_event_uuid; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_event_id_70d3f9f4_fk_BaseBillet_event_uuid" FOREIGN KEY (event_id) REFERENCES demo."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_tag_id_42dafd42_fk_BaseBillet_tag_uuid; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_tag_id_42dafd42_fk_BaseBillet_tag_uuid" FOREIGN KEY (tag_id) REFERENCES demo."BaseBillet_tag"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_externalapikey BaseBillet_externala_key_id_f5eff8fe_fk_rest_fram; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_externala_key_id_f5eff8fe_fk_rest_fram" FOREIGN KEY (key_id) REFERENCES demo.rest_framework_api_key_apikey(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_carte_id_8ab02e3c_fk_QrcodeCas; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_carte_id_8ab02e3c_fk_QrcodeCas" FOREIGN KEY (carte_id) REFERENCES public."QrcodeCashless_cartecashless"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_paiement_stripe_id_82b4a0d3_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_paiement_stripe_id_82b4a0d3_fk_BaseBille" FOREIGN KEY (paiement_stripe_id) REFERENCES demo."BaseBillet_paiement_stripe"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_pricesold_id_fc351d3d_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_pricesold_id_fc351d3d_fk_BaseBille" FOREIGN KEY (pricesold_id) REFERENCES demo."BaseBillet_pricesold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membershi_membership_id_d255b3ce_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membershi_membership_id_d255b3ce_fk_BaseBille" FOREIGN KEY (membership_id) REFERENCES demo."BaseBillet_membership"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membershi_optiongenerale_id_87513e51_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membershi_optiongenerale_id_87513e51_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES demo."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership BaseBillet_membershi_price_id_a4571820_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membershi_price_id_a4571820_fk_BaseBille" FOREIGN KEY (price_id) REFERENCES demo."BaseBillet_price"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership BaseBillet_membershi_user_id_2b02a750_fk_AuthBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membershi_user_id_2b02a750_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement__reservation_id_9643913c_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement__reservation_id_9643913c_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES demo."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement__user_id_03041fc6_fk_AuthBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement__user_id_03041fc6_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_price BaseBillet_price_adhesion_obligatoire_043901b7_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_adhesion_obligatoire_043901b7_fk_BaseBille" FOREIGN KEY (adhesion_obligatoire_id) REFERENCES demo."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_price BaseBillet_price_product_id_a7d53d46_fk_BaseBillet_product_uuid; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_product_id_a7d53d46_fk_BaseBillet_product_uuid" FOREIGN KEY (product_id) REFERENCES demo."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_price_id_017f6621_fk_BaseBillet_price_uuid; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_price_id_017f6621_fk_BaseBillet_price_uuid" FOREIGN KEY (price_id) REFERENCES demo."BaseBillet_price"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_productsold_id_d61e1c5f_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_productsold_id_d61e1c5f_fk_BaseBille" FOREIGN KEY (productsold_id) REFERENCES demo."BaseBillet_productsold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_o_optiongenerale_id_7714e607_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_o_optiongenerale_id_7714e607_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES demo."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_o_optiongenerale_id_ded928b6_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_o_optiongenerale_id_ded928b6_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES demo."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_o_product_id_50c10a7b_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_o_product_id_50c10a7b_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES demo."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_o_product_id_84a7c765_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_o_product_id_84a7c765_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES demo."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_tag BaseBillet_product_t_product_id_00f8ae38_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_t_product_id_00f8ae38_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES demo."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_tag_id_68675245_fk_BaseBillet_tag_uuid; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_tag_id_68675245_fk_BaseBillet_tag_uuid" FOREIGN KEY (tag_id) REFERENCES demo."BaseBillet_tag"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_productsold BaseBillet_productso_event_id_c817df43_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productso_event_id_c817df43_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES demo."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_productsold BaseBillet_productso_product_id_afb2fb6e_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productso_product_id_afb2fb6e_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES demo."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation BaseBillet_reservati_event_id_7404fad0_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservati_event_id_7404fad0_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES demo."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation_options BaseBillet_reservati_optiongenerale_id_bc5048ee_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservati_optiongenerale_id_bc5048ee_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES demo."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation_options BaseBillet_reservati_reservation_id_bf305174_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservati_reservation_id_bf305174_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES demo."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation BaseBillet_reservati_user_commande_id_2a3fe1fd_fk_AuthBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservati_user_commande_id_2a3fe1fd_fk_AuthBille" FOREIGN KEY (user_commande_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_ticket BaseBillet_ticket_pricesold_id_1984d9e4_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_pricesold_id_1984d9e4_fk_BaseBille" FOREIGN KEY (pricesold_id) REFERENCES demo."BaseBillet_pricesold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_ticket BaseBillet_ticket_reservation_id_226cfb21_fk_BaseBille; Type: FK CONSTRAINT; Schema: demo; Owner: ticket_postgres_user
--

ALTER TABLE ONLY demo."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_reservation_id_226cfb21_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES demo."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_user_id_c99e3878_fk_AuthBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_user_id_c99e3878_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_artist_id_fd91cee9_fk_Customers; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_artist_id_fd91cee9_fk_Customers" FOREIGN KEY (artist_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_event_id_29dd03f1_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_event_id_29dd03f1_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES meta."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configura_configuration_id_2e19f154_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configura_configuration_id_2e19f154_fk_BaseBille" FOREIGN KEY (configuration_id) REFERENCES meta."BaseBillet_configuration"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configura_configuration_id_bbe225a5_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configura_configuration_id_bbe225a5_fk_BaseBille" FOREIGN KEY (configuration_id) REFERENCES meta."BaseBillet_configuration"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configura_optiongenerale_id_7e69c71b_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configura_optiongenerale_id_7e69c71b_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES meta."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configura_optiongenerale_id_83c65e17_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configura_optiongenerale_id_83c65e17_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES meta."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_opt_event_id_172366cc_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_opt_event_id_172366cc_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES meta."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_opt_event_id_6389bff4_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_opt_event_id_6389bff4_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES meta."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_opt_optiongenerale_id_0dd0f546_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_opt_optiongenerale_id_0dd0f546_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES meta."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_opt_optiongenerale_id_b5d7c04b_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_opt_optiongenerale_id_b5d7c04b_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES meta."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_products BaseBillet_event_pro_event_id_e8b98de0_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_pro_event_id_e8b98de0_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES meta."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_products BaseBillet_event_pro_product_id_cdec0e20_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_pro_product_id_cdec0e20_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES meta."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_rec_event_id_0656b7d1_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_rec_event_id_0656b7d1_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES meta."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_rec_weekday_id_130a2743_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_rec_weekday_id_130a2743_fk_BaseBille" FOREIGN KEY (weekday_id) REFERENCES meta."BaseBillet_weekday"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_event_id_70d3f9f4_fk_BaseBillet_event_uuid; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_event_id_70d3f9f4_fk_BaseBillet_event_uuid" FOREIGN KEY (event_id) REFERENCES meta."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_tag_id_42dafd42_fk_BaseBillet_tag_uuid; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_tag_id_42dafd42_fk_BaseBillet_tag_uuid" FOREIGN KEY (tag_id) REFERENCES meta."BaseBillet_tag"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_externalapikey BaseBillet_externala_key_id_f5eff8fe_fk_rest_fram; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_externala_key_id_f5eff8fe_fk_rest_fram" FOREIGN KEY (key_id) REFERENCES meta.rest_framework_api_key_apikey(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_carte_id_8ab02e3c_fk_QrcodeCas; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_carte_id_8ab02e3c_fk_QrcodeCas" FOREIGN KEY (carte_id) REFERENCES public."QrcodeCashless_cartecashless"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_paiement_stripe_id_82b4a0d3_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_paiement_stripe_id_82b4a0d3_fk_BaseBille" FOREIGN KEY (paiement_stripe_id) REFERENCES meta."BaseBillet_paiement_stripe"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_pricesold_id_fc351d3d_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_pricesold_id_fc351d3d_fk_BaseBille" FOREIGN KEY (pricesold_id) REFERENCES meta."BaseBillet_pricesold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membershi_membership_id_d255b3ce_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membershi_membership_id_d255b3ce_fk_BaseBille" FOREIGN KEY (membership_id) REFERENCES meta."BaseBillet_membership"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membershi_optiongenerale_id_87513e51_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membershi_optiongenerale_id_87513e51_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES meta."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership BaseBillet_membershi_price_id_a4571820_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membershi_price_id_a4571820_fk_BaseBille" FOREIGN KEY (price_id) REFERENCES meta."BaseBillet_price"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership BaseBillet_membershi_user_id_2b02a750_fk_AuthBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membershi_user_id_2b02a750_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement__reservation_id_9643913c_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement__reservation_id_9643913c_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES meta."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement__user_id_03041fc6_fk_AuthBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement__user_id_03041fc6_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_price BaseBillet_price_adhesion_obligatoire_043901b7_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_adhesion_obligatoire_043901b7_fk_BaseBille" FOREIGN KEY (adhesion_obligatoire_id) REFERENCES meta."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_price BaseBillet_price_product_id_a7d53d46_fk_BaseBillet_product_uuid; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_product_id_a7d53d46_fk_BaseBillet_product_uuid" FOREIGN KEY (product_id) REFERENCES meta."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_price_id_017f6621_fk_BaseBillet_price_uuid; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_price_id_017f6621_fk_BaseBillet_price_uuid" FOREIGN KEY (price_id) REFERENCES meta."BaseBillet_price"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_productsold_id_d61e1c5f_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_productsold_id_d61e1c5f_fk_BaseBille" FOREIGN KEY (productsold_id) REFERENCES meta."BaseBillet_productsold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_o_optiongenerale_id_7714e607_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_o_optiongenerale_id_7714e607_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES meta."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_o_optiongenerale_id_ded928b6_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_o_optiongenerale_id_ded928b6_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES meta."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_o_product_id_50c10a7b_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_o_product_id_50c10a7b_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES meta."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_o_product_id_84a7c765_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_o_product_id_84a7c765_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES meta."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_tag BaseBillet_product_t_product_id_00f8ae38_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_t_product_id_00f8ae38_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES meta."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_tag_id_68675245_fk_BaseBillet_tag_uuid; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_tag_id_68675245_fk_BaseBillet_tag_uuid" FOREIGN KEY (tag_id) REFERENCES meta."BaseBillet_tag"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_productsold BaseBillet_productso_event_id_c817df43_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productso_event_id_c817df43_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES meta."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_productsold BaseBillet_productso_product_id_afb2fb6e_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productso_product_id_afb2fb6e_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES meta."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation BaseBillet_reservati_event_id_7404fad0_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservati_event_id_7404fad0_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES meta."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation_options BaseBillet_reservati_optiongenerale_id_bc5048ee_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservati_optiongenerale_id_bc5048ee_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES meta."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation_options BaseBillet_reservati_reservation_id_bf305174_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservati_reservation_id_bf305174_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES meta."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation BaseBillet_reservati_user_commande_id_2a3fe1fd_fk_AuthBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservati_user_commande_id_2a3fe1fd_fk_AuthBille" FOREIGN KEY (user_commande_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_ticket BaseBillet_ticket_pricesold_id_1984d9e4_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_pricesold_id_1984d9e4_fk_BaseBille" FOREIGN KEY (pricesold_id) REFERENCES meta."BaseBillet_pricesold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_ticket BaseBillet_ticket_reservation_id_226cfb21_fk_BaseBille; Type: FK CONSTRAINT; Schema: meta; Owner: ticket_postgres_user
--

ALTER TABLE ONLY meta."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_reservation_id_226cfb21_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES meta."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: AuthBillet_terminalpairingtoken AuthBillet_terminalp_user_id_097db473_fk_AuthBille; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_terminalpairingtoken"
    ADD CONSTRAINT "AuthBillet_terminalp_user_id_097db473_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: AuthBillet_tibilletuser_client_admin AuthBillet_tibilletu_client_id_33204d32_fk_Customers; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_client_admin"
    ADD CONSTRAINT "AuthBillet_tibilletu_client_id_33204d32_fk_Customers" FOREIGN KEY (client_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: AuthBillet_tibilletuser_client_achat AuthBillet_tibilletu_client_id_e9bbb546_fk_Customers; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_client_achat"
    ADD CONSTRAINT "AuthBillet_tibilletu_client_id_e9bbb546_fk_Customers" FOREIGN KEY (client_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: AuthBillet_tibilletuser AuthBillet_tibilletu_client_source_id_1134f8ae_fk_Customers; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser"
    ADD CONSTRAINT "AuthBillet_tibilletu_client_source_id_1134f8ae_fk_Customers" FOREIGN KEY (client_source_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: AuthBillet_tibilletuser_groups AuthBillet_tibilletu_group_id_09a9f9aa_fk_auth_grou; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_groups"
    ADD CONSTRAINT "AuthBillet_tibilletu_group_id_09a9f9aa_fk_auth_grou" FOREIGN KEY (group_id) REFERENCES public.auth_group(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: AuthBillet_tibilletuser_user_permissions AuthBillet_tibilletu_permission_id_28d47b9d_fk_auth_perm; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_user_permissions"
    ADD CONSTRAINT "AuthBillet_tibilletu_permission_id_28d47b9d_fk_auth_perm" FOREIGN KEY (permission_id) REFERENCES public.auth_permission(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: AuthBillet_tibilletuser_groups AuthBillet_tibilletu_tibilletuser_id_4ef900da_fk_AuthBille; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_groups"
    ADD CONSTRAINT "AuthBillet_tibilletu_tibilletuser_id_4ef900da_fk_AuthBille" FOREIGN KEY (tibilletuser_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: AuthBillet_tibilletuser_client_achat AuthBillet_tibilletu_tibilletuser_id_87ac98eb_fk_AuthBille; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_client_achat"
    ADD CONSTRAINT "AuthBillet_tibilletu_tibilletuser_id_87ac98eb_fk_AuthBille" FOREIGN KEY (tibilletuser_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: AuthBillet_tibilletuser_user_permissions AuthBillet_tibilletu_tibilletuser_id_ad6127bc_fk_AuthBille; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_user_permissions"
    ADD CONSTRAINT "AuthBillet_tibilletu_tibilletuser_id_ad6127bc_fk_AuthBille" FOREIGN KEY (tibilletuser_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: AuthBillet_tibilletuser_client_admin AuthBillet_tibilletu_tibilletuser_id_f8e7db79_fk_AuthBille; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."AuthBillet_tibilletuser_client_admin"
    ADD CONSTRAINT "AuthBillet_tibilletu_tibilletuser_id_f8e7db79_fk_AuthBille" FOREIGN KEY (tibilletuser_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: Customers_domain Customers_domain_tenant_id_07a53c46_fk_Customers_client_uuid; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."Customers_domain"
    ADD CONSTRAINT "Customers_domain_tenant_id_07a53c46_fk_Customers_client_uuid" FOREIGN KEY (tenant_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: MetaBillet_eventdirectory MetaBillet_eventdire_artist_id_c1c4a427_fk_Customers; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."MetaBillet_eventdirectory"
    ADD CONSTRAINT "MetaBillet_eventdire_artist_id_c1c4a427_fk_Customers" FOREIGN KEY (artist_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: MetaBillet_eventdirectory MetaBillet_eventdire_place_id_69ceb75c_fk_Customers; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."MetaBillet_eventdirectory"
    ADD CONSTRAINT "MetaBillet_eventdire_place_id_69ceb75c_fk_Customers" FOREIGN KEY (place_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: MetaBillet_productdirectory MetaBillet_productdi_place_id_885e6624_fk_Customers; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."MetaBillet_productdirectory"
    ADD CONSTRAINT "MetaBillet_productdi_place_id_885e6624_fk_Customers" FOREIGN KEY (place_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: QrcodeCashless_asset QrcodeCashless_asset_origin_id_5d706c12_fk_Customers; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_asset"
    ADD CONSTRAINT "QrcodeCashless_asset_origin_id_5d706c12_fk_Customers" FOREIGN KEY (origin_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: QrcodeCashless_cartecashless QrcodeCashless_carte_detail_id_374b04e5_fk_QrcodeCas; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_cartecashless"
    ADD CONSTRAINT "QrcodeCashless_carte_detail_id_374b04e5_fk_QrcodeCas" FOREIGN KEY (detail_id) REFERENCES public."QrcodeCashless_detail"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: QrcodeCashless_cartecashless QrcodeCashless_carte_user_id_95d46686_fk_AuthBille; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_cartecashless"
    ADD CONSTRAINT "QrcodeCashless_carte_user_id_95d46686_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: QrcodeCashless_detail QrcodeCashless_detai_origine_id_67e9af46_fk_Customers; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_detail"
    ADD CONSTRAINT "QrcodeCashless_detai_origine_id_67e9af46_fk_Customers" FOREIGN KEY (origine_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: QrcodeCashless_federatedcashless QrcodeCashless_feder_asset_id_c53450b6_fk_QrcodeCas; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_federatedcashless"
    ADD CONSTRAINT "QrcodeCashless_feder_asset_id_c53450b6_fk_QrcodeCas" FOREIGN KEY (asset_id) REFERENCES public."QrcodeCashless_asset"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: QrcodeCashless_federatedcashless QrcodeCashless_feder_client_id_0ca720ec_fk_Customers; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_federatedcashless"
    ADD CONSTRAINT "QrcodeCashless_feder_client_id_0ca720ec_fk_Customers" FOREIGN KEY (client_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: QrcodeCashless_syncfederatedlog QrcodeCashless_syncf_card_id_4df1fccb_fk_QrcodeCas; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_syncfederatedlog"
    ADD CONSTRAINT "QrcodeCashless_syncf_card_id_4df1fccb_fk_QrcodeCas" FOREIGN KEY (card_id) REFERENCES public."QrcodeCashless_cartecashless"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: QrcodeCashless_syncfederatedlog QrcodeCashless_syncf_client_source_id_ebe588df_fk_Customers; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_syncfederatedlog"
    ADD CONSTRAINT "QrcodeCashless_syncf_client_source_id_ebe588df_fk_Customers" FOREIGN KEY (client_source_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: QrcodeCashless_syncfederatedlog QrcodeCashless_syncf_wallet_id_9ec97b2b_fk_QrcodeCas; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_syncfederatedlog"
    ADD CONSTRAINT "QrcodeCashless_syncf_wallet_id_9ec97b2b_fk_QrcodeCas" FOREIGN KEY (wallet_id) REFERENCES public."QrcodeCashless_wallet"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: QrcodeCashless_wallet QrcodeCashless_walle_asset_id_2708f2b3_fk_QrcodeCas; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_wallet"
    ADD CONSTRAINT "QrcodeCashless_walle_asset_id_2708f2b3_fk_QrcodeCas" FOREIGN KEY (asset_id) REFERENCES public."QrcodeCashless_asset"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: QrcodeCashless_wallet QrcodeCashless_walle_card_id_0fdef3d5_fk_QrcodeCas; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_wallet"
    ADD CONSTRAINT "QrcodeCashless_walle_card_id_0fdef3d5_fk_QrcodeCas" FOREIGN KEY (card_id) REFERENCES public."QrcodeCashless_cartecashless"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: QrcodeCashless_wallet QrcodeCashless_walle_user_id_8796d2a0_fk_AuthBille; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public."QrcodeCashless_wallet"
    ADD CONSTRAINT "QrcodeCashless_walle_user_id_8796d2a0_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_group_permissions auth_group_permissio_permission_id_84c5c92e_fk_auth_perm; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissio_permission_id_84c5c92e_fk_auth_perm FOREIGN KEY (permission_id) REFERENCES public.auth_permission(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_group_permissions auth_group_permissions_group_id_b120cbf9_fk_auth_group_id; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissions_group_id_b120cbf9_fk_auth_group_id FOREIGN KEY (group_id) REFERENCES public.auth_group(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_permission auth_permission_content_type_id_2f476e4b_fk_django_co; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.auth_permission
    ADD CONSTRAINT auth_permission_content_type_id_2f476e4b_fk_django_co FOREIGN KEY (content_type_id) REFERENCES public.django_content_type(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: authtoken_token authtoken_token_user_id_35299eff_fk_AuthBillet_tibilletuser_id; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.authtoken_token
    ADD CONSTRAINT "authtoken_token_user_id_35299eff_fk_AuthBillet_tibilletuser_id" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: django_admin_log django_admin_log_content_type_id_c4bce8eb_fk_django_co; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.django_admin_log
    ADD CONSTRAINT django_admin_log_content_type_id_c4bce8eb_fk_django_co FOREIGN KEY (content_type_id) REFERENCES public.django_content_type(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: django_admin_log django_admin_log_user_id_c564eba6_fk_AuthBillet_tibilletuser_id; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.django_admin_log
    ADD CONSTRAINT "django_admin_log_user_id_c564eba6_fk_AuthBillet_tibilletuser_id" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: token_blacklist_blacklistedtoken token_blacklist_blacklistedtoken_token_id_3cc7fe56_fk; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.token_blacklist_blacklistedtoken
    ADD CONSTRAINT token_blacklist_blacklistedtoken_token_id_3cc7fe56_fk FOREIGN KEY (token_id) REFERENCES public.token_blacklist_outstandingtoken(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: token_blacklist_outstandingtoken token_blacklist_outs_user_id_83bc629a_fk_AuthBille; Type: FK CONSTRAINT; Schema: public; Owner: ticket_postgres_user
--

ALTER TABLE ONLY public.token_blacklist_outstandingtoken
    ADD CONSTRAINT "token_blacklist_outs_user_id_83bc629a_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_externalapikey BaseBillet_apikey_user_id_c99e3878_fk_AuthBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_apikey_user_id_c99e3878_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_artist_id_fd91cee9_fk_Customers; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_artist_id_fd91cee9_fk_Customers" FOREIGN KEY (artist_id) REFERENCES public."Customers_client"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_artist_on_event BaseBillet_artist_on_event_id_29dd03f1_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_artist_on_event"
    ADD CONSTRAINT "BaseBillet_artist_on_event_id_29dd03f1_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES ziskakan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configura_configuration_id_2e19f154_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configura_configuration_id_2e19f154_fk_BaseBille" FOREIGN KEY (configuration_id) REFERENCES ziskakan."BaseBillet_configuration"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configura_configuration_id_bbe225a5_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configura_configuration_id_bbe225a5_fk_BaseBille" FOREIGN KEY (configuration_id) REFERENCES ziskakan."BaseBillet_configuration"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_radio BaseBillet_configura_optiongenerale_id_7e69c71b_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_configuration_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_configura_optiongenerale_id_7e69c71b_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES ziskakan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_configuration_option_generale_checkbox BaseBillet_configura_optiongenerale_id_83c65e17_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_configuration_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_configura_optiongenerale_id_83c65e17_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES ziskakan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_opt_event_id_172366cc_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_opt_event_id_172366cc_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES ziskakan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_opt_event_id_6389bff4_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_opt_event_id_6389bff4_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES ziskakan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_radio BaseBillet_event_opt_optiongenerale_id_0dd0f546_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_options_radio"
    ADD CONSTRAINT "BaseBillet_event_opt_optiongenerale_id_0dd0f546_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES ziskakan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_options_checkbox BaseBillet_event_opt_optiongenerale_id_b5d7c04b_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_options_checkbox"
    ADD CONSTRAINT "BaseBillet_event_opt_optiongenerale_id_b5d7c04b_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES ziskakan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_products BaseBillet_event_pro_event_id_e8b98de0_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_pro_event_id_e8b98de0_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES ziskakan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_products BaseBillet_event_pro_product_id_cdec0e20_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_products"
    ADD CONSTRAINT "BaseBillet_event_pro_product_id_cdec0e20_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES ziskakan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_rec_event_id_0656b7d1_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_rec_event_id_0656b7d1_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES ziskakan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_recurrent BaseBillet_event_rec_weekday_id_130a2743_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_recurrent"
    ADD CONSTRAINT "BaseBillet_event_rec_weekday_id_130a2743_fk_BaseBille" FOREIGN KEY (weekday_id) REFERENCES ziskakan."BaseBillet_weekday"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_event_id_70d3f9f4_fk_BaseBillet_event_uuid; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_event_id_70d3f9f4_fk_BaseBillet_event_uuid" FOREIGN KEY (event_id) REFERENCES ziskakan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_event_tag BaseBillet_event_tag_tag_id_42dafd42_fk_BaseBillet_tag_uuid; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_event_tag"
    ADD CONSTRAINT "BaseBillet_event_tag_tag_id_42dafd42_fk_BaseBillet_tag_uuid" FOREIGN KEY (tag_id) REFERENCES ziskakan."BaseBillet_tag"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_externalapikey BaseBillet_externala_key_id_f5eff8fe_fk_rest_fram; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_externalapikey"
    ADD CONSTRAINT "BaseBillet_externala_key_id_f5eff8fe_fk_rest_fram" FOREIGN KEY (key_id) REFERENCES ziskakan.rest_framework_api_key_apikey(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_carte_id_8ab02e3c_fk_QrcodeCas; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_carte_id_8ab02e3c_fk_QrcodeCas" FOREIGN KEY (carte_id) REFERENCES public."QrcodeCashless_cartecashless"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_paiement_stripe_id_82b4a0d3_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_paiement_stripe_id_82b4a0d3_fk_BaseBille" FOREIGN KEY (paiement_stripe_id) REFERENCES ziskakan."BaseBillet_paiement_stripe"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_lignearticle BaseBillet_lignearti_pricesold_id_fc351d3d_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_lignearticle"
    ADD CONSTRAINT "BaseBillet_lignearti_pricesold_id_fc351d3d_fk_BaseBille" FOREIGN KEY (pricesold_id) REFERENCES ziskakan."BaseBillet_pricesold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membershi_membership_id_d255b3ce_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membershi_membership_id_d255b3ce_fk_BaseBille" FOREIGN KEY (membership_id) REFERENCES ziskakan."BaseBillet_membership"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership_option_generale BaseBillet_membershi_optiongenerale_id_87513e51_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_membership_option_generale"
    ADD CONSTRAINT "BaseBillet_membershi_optiongenerale_id_87513e51_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES ziskakan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership BaseBillet_membershi_price_id_a4571820_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membershi_price_id_a4571820_fk_BaseBille" FOREIGN KEY (price_id) REFERENCES ziskakan."BaseBillet_price"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_membership BaseBillet_membershi_user_id_2b02a750_fk_AuthBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_membership"
    ADD CONSTRAINT "BaseBillet_membershi_user_id_2b02a750_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement__reservation_id_9643913c_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement__reservation_id_9643913c_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES ziskakan."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_paiement_stripe BaseBillet_paiement__user_id_03041fc6_fk_AuthBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_paiement_stripe"
    ADD CONSTRAINT "BaseBillet_paiement__user_id_03041fc6_fk_AuthBille" FOREIGN KEY (user_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_price BaseBillet_price_adhesion_obligatoire_043901b7_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_adhesion_obligatoire_043901b7_fk_BaseBille" FOREIGN KEY (adhesion_obligatoire_id) REFERENCES ziskakan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_price BaseBillet_price_product_id_a7d53d46_fk_BaseBillet_product_uuid; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_price"
    ADD CONSTRAINT "BaseBillet_price_product_id_a7d53d46_fk_BaseBillet_product_uuid" FOREIGN KEY (product_id) REFERENCES ziskakan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_price_id_017f6621_fk_BaseBillet_price_uuid; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_price_id_017f6621_fk_BaseBillet_price_uuid" FOREIGN KEY (price_id) REFERENCES ziskakan."BaseBillet_price"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_pricesold BaseBillet_pricesold_productsold_id_d61e1c5f_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_pricesold"
    ADD CONSTRAINT "BaseBillet_pricesold_productsold_id_d61e1c5f_fk_BaseBille" FOREIGN KEY (productsold_id) REFERENCES ziskakan."BaseBillet_productsold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_o_optiongenerale_id_7714e607_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_o_optiongenerale_id_7714e607_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES ziskakan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_o_optiongenerale_id_ded928b6_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_o_optiongenerale_id_ded928b6_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES ziskakan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_radio BaseBillet_product_o_product_id_50c10a7b_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_option_generale_radio"
    ADD CONSTRAINT "BaseBillet_product_o_product_id_50c10a7b_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES ziskakan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_option_generale_checkbox BaseBillet_product_o_product_id_84a7c765_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_option_generale_checkbox"
    ADD CONSTRAINT "BaseBillet_product_o_product_id_84a7c765_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES ziskakan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_tag BaseBillet_product_t_product_id_00f8ae38_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_t_product_id_00f8ae38_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES ziskakan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_product_tag BaseBillet_product_tag_tag_id_68675245_fk_BaseBillet_tag_uuid; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_product_tag"
    ADD CONSTRAINT "BaseBillet_product_tag_tag_id_68675245_fk_BaseBillet_tag_uuid" FOREIGN KEY (tag_id) REFERENCES ziskakan."BaseBillet_tag"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_productsold BaseBillet_productso_event_id_c817df43_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productso_event_id_c817df43_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES ziskakan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_productsold BaseBillet_productso_product_id_afb2fb6e_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_productsold"
    ADD CONSTRAINT "BaseBillet_productso_product_id_afb2fb6e_fk_BaseBille" FOREIGN KEY (product_id) REFERENCES ziskakan."BaseBillet_product"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation BaseBillet_reservati_event_id_7404fad0_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservati_event_id_7404fad0_fk_BaseBille" FOREIGN KEY (event_id) REFERENCES ziskakan."BaseBillet_event"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation_options BaseBillet_reservati_optiongenerale_id_bc5048ee_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservati_optiongenerale_id_bc5048ee_fk_BaseBille" FOREIGN KEY (optiongenerale_id) REFERENCES ziskakan."BaseBillet_optiongenerale"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation_options BaseBillet_reservati_reservation_id_bf305174_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_reservation_options"
    ADD CONSTRAINT "BaseBillet_reservati_reservation_id_bf305174_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES ziskakan."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_reservation BaseBillet_reservati_user_commande_id_2a3fe1fd_fk_AuthBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_reservation"
    ADD CONSTRAINT "BaseBillet_reservati_user_commande_id_2a3fe1fd_fk_AuthBille" FOREIGN KEY (user_commande_id) REFERENCES public."AuthBillet_tibilletuser"(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_ticket BaseBillet_ticket_pricesold_id_1984d9e4_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_pricesold_id_1984d9e4_fk_BaseBille" FOREIGN KEY (pricesold_id) REFERENCES ziskakan."BaseBillet_pricesold"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: BaseBillet_ticket BaseBillet_ticket_reservation_id_226cfb21_fk_BaseBille; Type: FK CONSTRAINT; Schema: ziskakan; Owner: ticket_postgres_user
--

ALTER TABLE ONLY ziskakan."BaseBillet_ticket"
    ADD CONSTRAINT "BaseBillet_ticket_reservation_id_226cfb21_fk_BaseBille" FOREIGN KEY (reservation_id) REFERENCES ziskakan."BaseBillet_reservation"(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- PostgreSQL database dump complete
--

--
-- PostgreSQL database cluster dump complete
--

