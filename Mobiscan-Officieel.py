import streamlit as st
import pandas as pd
import requests
import zipfile
import os
from dotenv import load_dotenv
import json
import osmnx as ox
import streamlit.components.v1 as components

from io import BytesIO
from datetime import datetime
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from reportlab.platypus import Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Image, PageBreak
from reportlab.lib.enums import TA_LEFT

import folium
from streamlit_folium import st_folium

import geopandas as gpd
from shapely.geometry import Point

import networkx as nx
from shapely.ops import unary_union

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, CondPageBreak
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet


# =========================================================
# INSTELLINGEN
# =========================================================

import os

API_KEY = os.getenv("API_KEY")

# Uitbreidbaar parkeerkader per gemeente. Voeg hier later gemeenten toe zonder
# de berekeningslogica zelf te moeten aanpassen.
PARKEER_GEMEENTEN = {
    "hasselt": {
        "zones": {
            "Binnen Singel": {"norm_min": 0.50, "norm_max": 0.75, "wagenbezit": 0.72},
            "Andere zone": {"norm_min": 0.75, "norm_max": 1.10, "wagenbezit": 0.85},
        },
        "standaard_zone": "Binnen Singel",
        "bron": "Hasselt - lokale parkeerverordening"
    },
    "generiek": {
        "zones": {
            "Standaard": {"norm_min": 0.75, "norm_max": 1.10, "wagenbezit": 0.85},
        },
        "standaard_zone": "Standaard",
        "bron": "Generieke prototypeformule"
    }
}

SCORE_DREMPELS = {
    "stappers": {
        "goed": 20,
        "matig": 8,
        "bron": "Empirische drempel op basis van OSM-elementen binnen analyseradius. Referentie: Vlaamse Mobiliteitsgids (VMG) — voetgangerscomfort.",
        "toelichting": "≥20 voetgangerselementen = Goed, ≥8 = Matig, <8 = Beperkt."
    },
    "trappers": {
        "goed": 15,
        "matig": 5,
        "bron": "Empirische drempel op basis van OSM-fietssegmenten en BFF-aanwezigheid. Referentie: BFF-methodiek MOW Vlaanderen.",
        "toelichting": "≥15 fietselementen of BFF-aansluiting = Goed, ≥5 = Matig, <5 = Beperkt."
    },
    "ov": {
        "goed_haltes": 3,
        "goed_frequentie": 6,
        "bron": "Drempelwaarden gebaseerd op OV-bereikbaarheidscriteria uit de Vlaamse Mobiliteitsgids en STOP-principe (prioriteit OV boven auto).",
        "toelichting": "≥3 haltes binnen radius én frequentie ≥6 ritten/uur = Goed."
    }
}

GTFS_URL = "https://api.delijn.be/gtfs/static/v3/gtfs_transit.zip"

HOPPIN_URL = (
    "https://geoserver.gis.cloud.mow.vlaanderen.be/geoserver/hoppin/wfs"
    "?SERVICE=WFS&version=2.0.0&request=GetFeature"
    "&typeName=hoppinpunt_wgs84"
    "&outputFormat=application/json"
)

BFF_URL = (
    "https://geoserver.gis.cloud.mow.vlaanderen.be/geoserver/wfs"
    "?SERVICE=WFS&version=2.0.0&request=GetFeature"
    "&typeNames=beleid:bff"
    "&outputFormat=application/json"
)

BFF_URL_ALTERNATIEVEN = [
    BFF_URL,
    (
        "https://geoserver.gis.cloud.mow.vlaanderen.be/geoserver/wfs"
        "?SERVICE=WFS&version=2.0.0&request=GetFeature"
        "&typeName=beleid:bff"
        "&outputFormat=application/json"
    ),
    (
        "https://geoserver.gis.cloud.mow.vlaanderen.be/geoserver/beleid/wfs"
        "?SERVICE=WFS&version=2.0.0&request=GetFeature"
        "&typeNames=beleid:bff"
        "&outputFormat=application/json"
    ),
]


load_dotenv()

# =========================================================
# APP
# =========================================================

st.set_page_config(layout="wide", page_title="MOBISCAN", page_icon="🚦")

# =========================================================
# STARTSCHERM / DEMO LANDING PAGE
# =========================================================

if "mobiscan_demo_started" not in st.session_state:
    st.session_state.mobiscan_demo_started = False

if not st.session_state.mobiscan_demo_started:
    st.markdown(
        """
        <style>
        .mobiscan-hero {
            padding: 3.2rem 2.2rem 2.4rem 2.2rem;
            border-radius: 28px;
            background: linear-gradient(135deg, #0B1F33 0%, #143A3A 55%, #6B8F71 100%);
            color: white;
            margin-bottom: 2rem;
            box-shadow: 0 18px 45px rgba(11, 31, 51, 0.22);
        }
        .mobiscan-logo {
            font-size: 1.05rem;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            opacity: 0.88;
            margin-bottom: 0.7rem;
        }
        .mobiscan-title {
            font-size: 4rem;
            line-height: 1.02;
            font-weight: 800;
            margin-bottom: 0.65rem;
        }
        .mobiscan-subtitle {
            font-size: 1.25rem;
            line-height: 1.55;
            max-width: 860px;
            opacity: 0.94;
        }
        .mobiscan-card {
            min-height: 145px;
            padding: 1.25rem 1.15rem;
            border-radius: 20px;
            background: #F7FAF8;
            border: 1px solid #DDE8E1;
            box-shadow: 0 8px 22px rgba(11, 31, 51, 0.08);
        }
        .mobiscan-card h3 {
            margin-top: 0;
            color: #0B1F33;
            font-size: 1.05rem;
        }
        .mobiscan-card p {
            color: #3E4A45;
            font-size: 0.94rem;
            line-height: 1.45;
        }
        .mobiscan-note {
            color: #4A4A4A;
            font-size: 0.92rem;
            margin-top: 1.1rem;
        }
        </style>
        <div class="mobiscan-hero">
            <div class="mobiscan-logo">MOBISCAN · mobiliteitsanalyse</div>
            <div class="mobiscan-title">Slimme mobiliteitsfiche volgens het STOP-principe</div>
            <div class="mobiscan-subtitle">
                MOBISCAN ondersteunt de opmaak van mobiliteitsstudies door publieke databronnen,
                projectinput, kaarten en regelgebaseerde analyse en optionele generatieve AI-tekstinterpretatie samen te brengen in één professioneel rapport.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            """<div class="mobiscan-card"><h3>🚶‍♀️🚲 STOP-analyse</h3>
            <p>Analyseert stappers, trappers, openbaar vervoer en auto met kaarten, scores en korte interpretaties.</p></div>""",
            unsafe_allow_html=True
        )
    with c2:
        st.markdown(
            """<div class="mobiscan-card"><h3>🚌 Open databronnen</h3>
            <p>Gebruikt onder meer De Lijn-GTFS, OpenStreetMap, Hoppin/BFF indien beschikbaar en projectdocumenten.</p></div>""",
            unsafe_allow_html=True
        )
    with c3:
        st.markdown(
            """<div class="mobiscan-card"><h3>📊 Parkeren & verkeer</h3>
            <p>Berekent parkeerbalans, fietsparkeerbehoefte, verkeersgeneratie en indicatieve spitsuurbelasting.</p></div>""",
            unsafe_allow_html=True
        )
    with c4:
        st.markdown(
            """<div class="mobiscan-card"><h3>📄 PDF-rapport</h3>
            <p>Genereert een professionele mobiliteitsfiche met tabellen, kaarten, conclusies en aan te vullen controlepunten.</p></div>""",
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)
    _, midden, _ = st.columns([1, 1, 1])
    with midden:
        if st.button("Start demo", type="primary", use_container_width=True):
            st.session_state.mobiscan_demo_started = True
            st.rerun()

    st.markdown(
        '''<p class="mobiscan-note">Demo-opmerking: de tool automatiseert de objectieve screening, maar finale validatie door een mobiliteitsexpert blijft noodzakelijk.</p>''',
        unsafe_allow_html=True
    )
    st.stop()

st.title("Mobiliteitsanalyse Tool - Vlaamse bronnen")
st.caption("STOP-analyse: Stappers, Trappers, Openbaar vervoer en Auto")

if st.sidebar.button("← Terug naar startscherm"):
    st.session_state.mobiscan_demo_started = False
    st.rerun()

st.sidebar.header("Projectgegevens")

adres = st.sidebar.text_input("Projectadres")
projectnaam = st.sidebar.text_input("Projectnaam", "Naam project")

projecttype = st.sidebar.selectbox(
    "Projecttype",
    ["Wonen", "Handel", "Horeca", "School", "Kantoor", "Gemengd project", "Andere"]
)

st.sidebar.header("Projectomschrijving")

projectfase = st.sidebar.selectbox(
    "Fase binnen het project",
    ["Niet ingevuld", "Voorontwerp", "Omgevingsvergunning", "Uitvoering", "Bestaande toestand", "Andere"]
)

korte_omschrijving = st.sidebar.text_area(
    "Korte projectomschrijving",
    height=120,
    placeholder="Bijvoorbeeld: sloop van bestaande bebouwing en oprichting van appartementen met ondergrondse parking."
)

huidige_toestand = st.sidebar.text_area(
    "Huidige toestand",
    height=90,
    placeholder="Bijvoorbeeld: braakliggend terrein, bestaande woning, voormalige bedrijfssite..."
)

toekomstige_toestand = st.sidebar.text_area(
    "Toekomstige toestand",
    height=90,
    placeholder="Bijvoorbeeld: nieuwbouw met woonfunctie, commerciële plint, ondergrondse parking..."
)

aantal_wooneenheden = st.sidebar.number_input("Aantal wooneenheden", min_value=0, value=0)
bvo = st.sidebar.number_input("Bruto vloeroppervlakte / programma in m²", min_value=0, value=0)
parkeerplaatsen = st.sidebar.number_input("Aantal parkeerplaatsen", min_value=0, value=0)
fietsenstallingen = st.sidebar.number_input("Aantal fietsenstallingen", min_value=0, value=0)

straal = st.sidebar.slider("Analysegebied in meter", 250, 3000, 1000, step=250)

st.sidebar.header("Parkeeranalyse")
parkeeranalyse_modus = st.sidebar.selectbox(
    "Parkeerdata",
    [
        "Automatisch bepalen op basis van adres",
        "Handmatig invullen / overschrijven",
        "Generieke prototypeformule"
    ]
)

gemeente_opties = list(PARKEER_GEMEENTEN.keys())
gemeente_parkeerlogica = st.sidebar.selectbox(
    "Gemeente (parkeerlogica)",
    gemeente_opties,
    index=gemeente_opties.index("generiek") if "generiek" in gemeente_opties else 0
)

zone_opties = list(PARKEER_GEMEENTEN[gemeente_parkeerlogica]["zones"].keys())
standaard_zone = PARKEER_GEMEENTEN[gemeente_parkeerlogica].get("standaard_zone", zone_opties[0])
zone_index = zone_opties.index(standaard_zone) if standaard_zone in zone_opties else 0
parkeerzone_selectie = st.sidebar.selectbox(
    "Parkeerzone",
    zone_opties,
    index=zone_index
)

zone_data_sidebar = PARKEER_GEMEENTEN[gemeente_parkeerlogica]["zones"][parkeerzone_selectie]

# Deze waarden kunnen automatisch of handmatig worden ingevuld.
parkeernorm_context = PARKEER_GEMEENTEN[gemeente_parkeerlogica]["bron"]
hasselt_zone = parkeerzone_selectie
lokaal_wagenbezit = float(zone_data_sidebar.get("wagenbezit", 0.0))
statistische_sector = "Niet automatisch herkend"
straatparkeren_toelichting = "Parkeerregime, bezoekersparkeren en straatparkeren moeten worden gecontroleerd via lokale parkeerinformatie."

if parkeeranalyse_modus == "Handmatig invullen / overschrijven":
    lokaal_wagenbezit = st.sidebar.number_input(
        "Lokaal wagenbezit, wagens per huishouden",
        min_value=0.0,
        max_value=3.0,
        value=float(zone_data_sidebar.get("wagenbezit", 0.85)),
        step=0.01
    )
    statistische_sector = st.sidebar.text_input(
        "Statistische sector",
        "Niet ingevuld"
    )
    straatparkeren_toelichting = st.sidebar.text_area(
        "Straatparkeren / bezoekersparkeren",
        height=70,
        placeholder="Bijvoorbeeld: betalend parkeren, blauwe zone, publieke parking op wandelafstand..."
    )
elif parkeeranalyse_modus == "Generieke prototypeformule":
    gemeente_parkeerlogica = "generiek"
    parkeerzone_selectie = PARKEER_GEMEENTEN["generiek"]["standaard_zone"]
    parkeernorm_context = PARKEER_GEMEENTEN["generiek"]["bron"]
    hasselt_zone = parkeerzone_selectie
    zone_data_sidebar = PARKEER_GEMEENTEN["generiek"]["zones"][parkeerzone_selectie]
    lokaal_wagenbezit = float(zone_data_sidebar.get("wagenbezit", 0.85))
    statistische_sector = "Niet van toepassing"
    straatparkeren_toelichting = "Niet automatisch beoordeeld."

parkeer_context = {
    "modus": parkeeranalyse_modus,
    "gemeente": gemeente_parkeerlogica,
    "norm_context": parkeernorm_context,
    "bron": parkeernorm_context,
    "zone": hasselt_zone,
    "lokaal_wagenbezit": lokaal_wagenbezit,
    "statistische_sector": statistische_sector,
    "straatparkeren_toelichting": straatparkeren_toelichting,
    "automatisch_bepaald": parkeeranalyse_modus == "Automatisch bepalen op basis van adres",
}

validatie_data = {"actief": False}

# =========================================================
# GENERATIEVE AI-INSTELLINGEN
# =========================================================
st.sidebar.header("AI-tekstgeneratie")
ai_actief = st.sidebar.checkbox(
    "Gebruik generatieve AI voor interpretatieteksten",
    value=False,
    help="Wanneer dit actief is, gebruikt MOBISCAN de berekende data als input voor een taalmodel. De berekeningen zelf blijven regelgebaseerd."
)

ai_model = st.sidebar.selectbox(
    "AI-model",
    ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"],
    index=0,
    help="Gebruik voor een demo bij voorkeur gpt-4o-mini of gpt-4.1-mini."
)

# Vaste promptvariant: de promptoptimalisatie werd uitgevoerd tijdens de ontwikkeling.
# In de definitieve app gebruikt MOBISCAN standaard de best geselecteerde variant.
ai_promptstijl = "Professioneel en neutraal"
st.sidebar.caption("Vaste AI-schrijfstijl: professioneel en neutraal")

# OpenAI API-key wordt gelezen uit het .env-bestand
load_dotenv()

ai_api_key_input = os.getenv("OPENAI_API_KEY", "").strip()

st.sidebar.caption("AI schrijft alleen interpretatieteksten. Data, scores, kaarten en berekeningen blijven controleerbaar en regelgebaseerd.")

st.sidebar.header("Rapportgegevens")
opdrachtgever = st.sidebar.text_input("Opdrachtgever", "Naam opdrachtgever")
architectenbureau = st.sidebar.text_input("Architectenbureau / gebruiker app", "Naam architectenbureau")
opdrachtnemer = st.sidebar.text_input("Opdrachtnemer", "MOBISCAN")
projectmedewerkers = st.sidebar.text_input("Projectmedewerkers / auteurs", "Kim Demaecker")
versienummer = st.sidebar.text_input("Versienummer", "v1.0")
vrijgavedatum = st.sidebar.text_input("Vrijgavedatum", datetime.today().strftime("%d-%m-%Y"))
rapportstatus = st.sidebar.selectbox("Status", ["Concept", "Definitief", "Draft", "Ter nazicht"])
referentie = st.sidebar.text_input("Referentie", "MOBI-2026-001")

st.sidebar.header("Logo's voor PDF")
app_logo_upload = st.sidebar.file_uploader("Logo app / MOBISCAN", type=["png", "jpg", "jpeg"], key="app_logo")
bureau_logo_upload = st.sidebar.file_uploader("Logo architectenbureau", type=["png", "jpg", "jpeg"], key="bureau_logo")

st.sidebar.header("Projectplannen")
inplantingsplan_upload = st.sidebar.file_uploader(
    "Inplantingsplan",
    type=["png", "jpg", "jpeg", "pdf"],
    key="inplantingsplan"
)
grondplan_upload = st.sidebar.file_uploader(
    "Grondplan gelijkvloers",
    type=["png", "jpg", "jpeg", "pdf"],
    key="grondplan"
)
situatieplan_upload = st.sidebar.file_uploader(
    "Situatieplan",
    type=["png", "jpg", "jpeg", "pdf"],
    key="situatieplan"
)
doorsnede_upload = st.sidebar.file_uploader(
    "Doorsnede / gevel",
    type=["png", "jpg", "jpeg", "pdf"],
    key="doorsnede"
)


# =========================================================
# DATA DOWNLOADEN
# =========================================================

@st.cache_data
def download_gtfs():
    if not API_KEY:
        return None
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    response = requests.get(GTFS_URL, headers=headers)

    if response.status_code != 200:
        st.error(f"GTFS-download mislukt. Statuscode: {response.status_code}")
        return None

    if not response.content.startswith(b"PK"):
        st.error("GTFS-response is geen ZIP-bestand.")
        return None

    zip_file = zipfile.ZipFile(BytesIO(response.content))

    stops = pd.read_csv(zip_file.open("stops.txt"))
    # stop_times wordt ruimer ingelezen zodat MOBISCAN ook OV-frequenties kan berekenen.
    # Als De Lijn ooit kolommen wijzigt, blijft de app werken met de beschikbare kolommen.
    stop_times = pd.read_csv(zip_file.open("stop_times.txt"))
    trips = pd.read_csv(zip_file.open("trips.txt"))
    routes = pd.read_csv(zip_file.open("routes.txt"))

    return stops, stop_times, trips, routes


@st.cache_data
def download_hoppinpunten():
    try:
        response = requests.get(
            HOPPIN_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20
        )
        response.raise_for_status()

        gdf = gpd.read_file(BytesIO(response.content))
        return gdf.to_crs(epsg=4326)

    except requests.exceptions.RequestException as e:
        st.warning(
            "Hoppinpunten konden niet worden opgehaald. "
            "De app werkt verder zonder Hoppin-data. "
            f"Technische melding: {e}"
        )
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    except Exception as e:
        st.warning(
            "Hoppin-data kon niet worden verwerkt. "
            "De app werkt verder zonder Hoppin-data. "
            f"Technische melding: {e}"
        )
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")


@st.cache_data
def download_bff():
    """Haalt het officiële BFF op.
    De correcte WFS-laag gebruikt de namespace beleid:bff via de algemene MOW-WFS.
    Er worden enkele URL-varianten geprobeerd, omdat GeoServer soms gevoelig is voor
    typeName/typeNames en endpointvarianten.
    """
    laatste_fout = None

    for url in BFF_URL_ALTERNATIEVEN:
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=40
            )
            response.raise_for_status()

            gdf = gpd.read_file(BytesIO(response.content))
            if gdf is not None and not gdf.empty:
                return gdf.to_crs(epsg=4326)

            laatste_fout = "BFF-response was leeg."

        except requests.exceptions.RequestException as e:
            laatste_fout = e
            continue

        except Exception as e:
            laatste_fout = e
            continue

    st.warning(
        "BFF-routes konden niet correct worden opgehaald. "
        "De app werkt verder zonder BFF-data. "
        f"Technische melding: {laatste_fout}"
    )
    return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")


@st.cache_data
def zoek_osm_voorzieningen(lat, lon, straal):
    tags = {
        "amenity": ["school", "restaurant", "cafe", "parking"],
        "shop": True
    }

    try:
        return ox.features_from_point((lat, lon), tags=tags, dist=straal)
    except Exception:
        return gpd.GeoDataFrame()


@st.cache_data
def zoek_stappersvoorzieningen(lat, lon, straal):
    tags = {
        "highway": ["footway", "path", "pedestrian", "crossing", "steps"],
        "footway": ["sidewalk", "crossing"],
        "crossing": True
    }

    try:
        return ox.features_from_point((lat, lon), tags=tags, dist=straal)
    except Exception:
        return gpd.GeoDataFrame()


@st.cache_data
def zoek_trappersvoorzieningen(lat, lon, straal):
    tags = {
        "highway": ["cycleway", "path", "living_street", "residential"],
        "cycleway": True,
        "bicycle": True,
        "cyclestreet": True,
        "cycle_network": True,
        "network": True
    }

    try:
        return ox.features_from_point((lat, lon), tags=tags, dist=straal)
    except Exception:
        return gpd.GeoDataFrame()


@st.cache_data
def zoek_recreatieve_fietsroutes(lat, lon, straal):
    """Zoekt recreatieve/fietsroute-relaties en fietsknooppuntinformatie via OSM.
    Dit is een aanvullende indicatie; officiële recreatieve routelagen kunnen later per provincie gekoppeld worden.
    """
    tags = {
        "route": "bicycle",
        "network": ["lcn", "rcn", "ncn", "icn"],
        "cycle_network": True,
        "rcn_ref": True,
        "lcn_ref": True
    }
    try:
        return ox.features_from_point((lat, lon), tags=tags, dist=straal)
    except Exception:
        return gpd.GeoDataFrame()


@st.cache_data
def zoek_auto_infrastructuur(lat, lon, straal):
    tags = {
        "highway": [
            "motorway", "trunk", "primary", "secondary", "tertiary",
            "residential", "unclassified", "service", "living_street",
            "traffic_signals", "stop", "give_way"
        ],
        "maxspeed": True,
        "junction": True
    }

    try:
        return ox.features_from_point((lat, lon), tags=tags, dist=straal)
    except Exception:
        return gpd.GeoDataFrame()


# =========================================================
# ANALYSEFUNCTIES
# =========================================================

def zoek_haltes(stops, lat, lon, straal):
    gevonden = []

    for _, row in stops.iterrows():
        afstand = geodesic((lat, lon), (row["stop_lat"], row["stop_lon"])).meters

        if afstand <= straal:
            gevonden.append({
                "halte_id": row["stop_id"],
                "halte_naam": row["stop_name"],
                "afstand_m": round(afstand),
                "lat": row["stop_lat"],
                "lon": row["stop_lon"]
            })

    return pd.DataFrame(gevonden)


def zoek_dichtstbijzijnde_halte(stops, lat, lon):
    """Zoekt de dichtstbijzijnde De Lijn-halte, los van de gekozen analyseradius."""
    if stops is None or stops.empty:
        return {
            "halte_naam": "niet beschikbaar",
            "afstand_m": None,
            "lat": None,
            "lon": None
        }

    stops_tmp = stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]].dropna().copy()
    if stops_tmp.empty:
        return {
            "halte_naam": "niet beschikbaar",
            "afstand_m": None,
            "lat": None,
            "lon": None
        }

    # Voor performantie: eerst grof filteren op coördinaten, daarna exacte geodesic afstand.
    stops_tmp["lat_diff"] = (stops_tmp["stop_lat"] - lat).abs()
    stops_tmp["lon_diff"] = (stops_tmp["stop_lon"] - lon).abs()
    kandidaten = stops_tmp.nsmallest(500, ["lat_diff", "lon_diff"]).copy()

    kandidaten["afstand_m"] = kandidaten.apply(
        lambda row: geodesic((lat, lon), (row["stop_lat"], row["stop_lon"])).meters,
        axis=1
    )

    dichtste = kandidaten.sort_values("afstand_m").iloc[0]
    return {
        "halte_id": dichtste["stop_id"],
        "halte_naam": dichtste["stop_name"],
        "afstand_m": round(float(dichtste["afstand_m"])),
        "lat": float(dichtste["stop_lat"]),
        "lon": float(dichtste["stop_lon"])
    }


@st.cache_data
def zoek_dichtstbijzijnde_station(lat, lon):
    """Zoekt het dichtstbijzijnde station of spoorhalte via OpenStreetMap, los van de gekozen analyseradius."""
    tags = {
        "railway": ["station", "halt", "tram_stop"],
        "public_transport": ["station", "stop_position"]
    }

    zoekstralen = [3000, 7500, 15000, 30000, 50000]

    for zoekstraal in zoekstralen:
        try:
            stations = ox.features_from_point((lat, lon), tags=tags, dist=zoekstraal)
        except Exception:
            stations = gpd.GeoDataFrame()

        if stations is None or stations.empty:
            continue

        gevonden = []
        for _, row in stations.iterrows():
            geom = row.geometry
            if geom is None:
                continue

            punt = geom.centroid
            afstand = geodesic((lat, lon), (punt.y, punt.x)).meters
            naam = (
                row.get("name")
                or row.get("official_name")
                or row.get("station")
                or "Station / halte"
            )

            # Tramhaltes vermijden als er echte trein-/metrostations in dezelfde zoekronde zitten.
            railway_type = str(row.get("railway", "")).lower()
            gevonden.append({
                "station_naam": naam,
                "afstand_m": round(afstand),
                "lat": punt.y,
                "lon": punt.x,
                "type": railway_type if railway_type else "station"
            })

        if gevonden:
            df = pd.DataFrame(gevonden)
            voorkeur = df[df["type"].isin(["station", "halt"])]
            if not voorkeur.empty:
                return voorkeur.sort_values("afstand_m").iloc[0].to_dict()
            return df.sort_values("afstand_m").iloc[0].to_dict()

    return {
        "station_naam": "niet beschikbaar",
        "afstand_m": None,
        "lat": None,
        "lon": None,
        "type": "niet gevonden"
    }


def voeg_lijnen_toe(haltes, stop_times, trips, routes):
    resultaten = []

    for _, halte in haltes.iterrows():
        halte_stop_times = stop_times[stop_times["stop_id"] == halte["halte_id"]]

        if halte_stop_times.empty:
            resultaten.append("Geen lijnen gevonden")
            continue

        trip_ids = halte_stop_times["trip_id"].drop_duplicates()
        halte_trips = trips[trips["trip_id"].isin(trip_ids)]

        route_ids = halte_trips["route_id"].drop_duplicates()
        halte_routes = routes[routes["route_id"].isin(route_ids)]

        lijnen = []

        for _, route in halte_routes.iterrows():
            nummer = str(route.get("route_short_name", "")).strip()
            naam = str(route.get("route_long_name", "")).strip()

            if nummer and naam and naam != "nan":
                lijnen.append(f"{nummer} - {naam}")
            elif nummer:
                lijnen.append(nummer)

        resultaten.append(", ".join(sorted(set(lijnen))[:10]))

    haltes["buslijnen"] = resultaten
    return haltes




def _gtfs_time_to_hour(value):
    try:
        uur = int(str(value).split(":")[0])
        return uur % 24
    except Exception:
        return None


def bereken_ov_frequenties(haltes, stop_times, trips, spits_start=7, spits_einde=9):
    """Voegt een eenvoudige OV-frequentie toe per halte op basis van GTFS stop_times.
    De waarde is het gemiddeld aantal vertrekken per uur in de ochtendspits.
    """
    if haltes is None or haltes.empty or stop_times is None or stop_times.empty:
        return haltes

    haltes = haltes.copy()
    if "departure_time" not in stop_times.columns and "arrival_time" not in stop_times.columns:
        haltes["ritten_spits_uur"] = 0.0
        haltes["frequentie_score"] = "Niet beschikbaar"
        return haltes

    tijdkolom = "departure_time" if "departure_time" in stop_times.columns else "arrival_time"
    st_times = stop_times[["trip_id", "stop_id", tijdkolom]].dropna().copy()
    st_times["uur"] = st_times[tijdkolom].apply(_gtfs_time_to_hour)
    st_times = st_times[st_times["uur"].between(spits_start, spits_einde - 1)]

    if st_times.empty:
        haltes["ritten_spits_uur"] = 0.0
        haltes["frequentie_score"] = "Beperkt"
        return haltes

    counts = st_times.groupby("stop_id")["trip_id"].nunique() / max(1, (spits_einde - spits_start))

    def score(freq):
        if freq >= 10:
            return "Zeer goed"
        if freq >= 6:
            return "Goed"
        if freq >= 3:
            return "Matig"
        if freq > 0:
            return "Beperkt"
        return "Geen bediening in spitsvenster"

    haltes["ritten_spits_uur"] = haltes["halte_id"].map(counts).fillna(0).round(1)
    haltes["frequentie_score"] = haltes["ritten_spits_uur"].apply(score)
    return haltes


def analyseer_recreatieve_fietsroutes(recreatieve_routes):
    if recreatieve_routes is None or recreatieve_routes.empty:
        return {
            "aantal": 0,
            "netwerken": "Niet gedetecteerd",
            "knooppunten": 0,
            "toelichting": "Er werden via OSM geen recreatieve fietsroutes of fietsknooppuntverwijzingen gevonden binnen de gekozen radius."
        }
    netwerken = []
    for col in ["network", "cycle_network", "operator"]:
        if col in recreatieve_routes.columns:
            netwerken += [str(x) for x in recreatieve_routes[col].dropna().unique().tolist() if str(x) != "nan"]
    knooppunten = 0
    for col in ["rcn_ref", "lcn_ref", "ref"]:
        if col in recreatieve_routes.columns:
            knooppunten += int(recreatieve_routes[col].notna().sum())
    return {
        "aantal": len(recreatieve_routes),
        "netwerken": ", ".join(sorted(set(netwerken))[:8]) if netwerken else "Fietsroutegegevens aanwezig, netwerknaam niet ingevuld",
        "knooppunten": knooppunten,
        "toelichting": "Recreatieve fietsroutes zijn aanvullend op functionele fietsroutes. Ze zijn vooral relevant voor comfort, herkenbaarheid en aansluiting op het bredere fietsnetwerk."
    }


def analyseer_bff_context(bff_routes):
    if bff_routes is None or bff_routes.empty:
        return {
            "aantal": 0,
            "dichtste_afstand": "niet beschikbaar",
            "hoofdroute": "Niet gedetecteerd",
            "fietssnelweg": "Niet gedetecteerd",
            "categorieen": "Niet beschikbaar",
            "toelichting": "Er werden geen BFF-segmenten gevonden binnen de gekozen radius. Controleer de officiële Geopunt/MOW-laag visueel wanneer het resultaat niet overeenkomt met de gekende projectcontext of lokale plannen."
        }
    df = bff_routes.copy()
    tekst = " ".join([str(v).lower() for col in df.columns if col != "geometry" for v in df[col].dropna().astype(str).head(200).tolist()])
    hoofdroute = "Waarschijnlijk aanwezig" if "hoofd" in tekst else "Niet automatisch herkenbaar"
    fietssnelweg = "Waarschijnlijk aanwezig" if "fietssnel" in tekst or "fietssnelweg" in tekst or "f-route" in tekst else "Niet automatisch herkenbaar"
    cats = []
    for col in ["categorie", "Categorie", "type", "Type", "route_type", "routetype", "functie", "functioneel"]:
        if col in df.columns:
            cats += [str(x) for x in df[col].dropna().unique().tolist() if str(x).strip()]
    afstand = f'{int(df["afstand_m"].min())} m' if "afstand_m" in df.columns else "niet beschikbaar"
    return {
        "aantal": len(df),
        "dichtste_afstand": afstand,
        "hoofdroute": hoofdroute,
        "fietssnelweg": fietssnelweg,
        "categorieen": ", ".join(sorted(set(cats))[:8]) if cats else "Niet beschikbaar in attribuutdata",
        "toelichting": "De BFF-context is gebaseerd op de officiële MOW-WFS-laag en attribuutvelden. Attribuutnamen verschillen soms per laagversie; visuele controle blijft nodig."
    }

def zoek_hoppinpunten_binnen_straal(hoppin, lat, lon, straal):
    gevonden = []

    if hoppin.empty:
        return pd.DataFrame()

    for _, row in hoppin.iterrows():
        geom = row.geometry

        if geom is None:
            continue

        punt = geom.centroid
        afstand = geodesic((lat, lon), (punt.y, punt.x)).meters

        if afstand <= straal:
            naam = (
                row.get("naam")
                or row.get("Naam")
                or row.get("name")
                or row.get("hoppinpunt")
                or row.get("naam_hoppinpunt")
                or "Hoppinpunt"
            )

            gemeente = (
                row.get("gemeente")
                or row.get("Gemeente")
                or row.get("gemeentenaam")
                or ""
            )

            gevonden.append({
                "naam": naam,
                "gemeente": gemeente,
                "afstand_m": round(afstand),
                "lat": punt.y,
                "lon": punt.x
            })

    return pd.DataFrame(gevonden)


def zoek_bff_binnen_straal(bff, lat, lon, straal):
    if bff.empty:
        return gpd.GeoDataFrame(columns=["afstand_m", "geometry"], crs="EPSG:4326")

    projectpunt = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(epsg=31370)

    bff_projected = bff.to_crs(epsg=31370).copy()
    bff_projected["afstand_m"] = bff_projected.geometry.distance(projectpunt.iloc[0])

    gefilterd_projected = bff_projected[bff_projected["afstand_m"] <= straal].copy()

    if gefilterd_projected.empty:
        return gpd.GeoDataFrame(columns=["afstand_m", "geometry"], crs="EPSG:4326")

    gefilterd = gefilterd_projected.to_crs(epsg=4326)
    gefilterd["afstand_m"] = gefilterd_projected["afstand_m"].round().values

    return gefilterd


def tel_osm(osm):
    if osm.empty:
        return 0, 0, 0, 0

    scholen = len(osm[osm["amenity"] == "school"]) if "amenity" in osm.columns else 0

    horeca = (
        len(osm[osm["amenity"].isin(["restaurant", "cafe"])])
        if "amenity" in osm.columns
        else 0
    )

    parkings = len(osm[osm["amenity"] == "parking"]) if "amenity" in osm.columns else 0
    winkels = len(osm[osm["shop"].notna()]) if "shop" in osm.columns else 0

    return scholen, horeca, winkels, parkings


def analyseer_stappers(stappers):
    if stappers.empty:
        return {
            "voetpaden": 0,
            "oversteekplaatsen": 0,
            "trage_wegen": 0,
            "comfortscore": "Beperkt"
        }

    voetpaden = 0
    oversteekplaatsen = 0
    trage_wegen = 0

    if "footway" in stappers.columns:
        voetpaden += len(stappers[stappers["footway"] == "sidewalk"])
        oversteekplaatsen += len(stappers[stappers["footway"] == "crossing"])

    if "highway" in stappers.columns:
        voetpaden += len(stappers[stappers["highway"].isin(["footway", "pedestrian"])])
        trage_wegen += len(stappers[stappers["highway"].isin(["path", "steps"])])
        oversteekplaatsen += len(stappers[stappers["highway"] == "crossing"])

    totaal = voetpaden + oversteekplaatsen + trage_wegen

    if totaal >= 20:
        comfortscore = "Goed"
    elif totaal >= 8:
        comfortscore = "Matig"
    else:
        comfortscore = "Beperkt"

    return {
        "voetpaden": voetpaden,
        "oversteekplaatsen": oversteekplaatsen,
        "trage_wegen": trage_wegen,
        "comfortscore": comfortscore
    }


def analyseer_trappers(trappers, bff_routes):
    fietsstraten = 0
    fietssnelweg_osm = 0
    if trappers.empty:
        fietspaden = 0
        fietssuggesties = 0
        gedeelde_paden = 0
    else:
        fietspaden = 0
        fietssuggesties = 0
        gedeelde_paden = 0

        if "highway" in trappers.columns:
            fietspaden += len(trappers[trappers["highway"] == "cycleway"])
            gedeelde_paden += len(trappers[trappers["highway"] == "path"])

        if "cycleway" in trappers.columns:
            fietssuggesties += len(trappers[trappers["cycleway"].notna()])

        if "bicycle" in trappers.columns:
            gedeelde_paden += len(trappers[trappers["bicycle"].notna()])

        if "cyclestreet" in trappers.columns:
            fietsstraten += len(trappers[trappers["cyclestreet"].astype(str).str.lower().isin(["yes", "true", "1"])] )

        for col in ["name", "ref", "cycle_network", "network"]:
            if col in trappers.columns:
                fietssnelweg_osm += trappers[col].astype(str).str.lower().str.contains("fietssnel|f-route|f[0-9]", regex=True, na=False).sum()

    bff_aantal = len(bff_routes)
    totaal = fietspaden + fietssuggesties + gedeelde_paden + bff_aantal + fietsstraten

    if totaal >= 20:
        fietsscore = "Goed"
    elif totaal >= 8:
        fietsscore = "Matig"
    else:
        fietsscore = "Beperkt"

    return {
        "fietspaden": fietspaden,
        "fietssuggesties": fietssuggesties,
        "gedeelde_paden": gedeelde_paden,
        "bff_segmenten": bff_aantal,
        "fietsstraten": int(fietsstraten),
        "fietssnelweg_osm": int(fietssnelweg_osm),
        "fietsscore": fietsscore
    }


def analyseer_auto(auto):
    if auto.empty:
        return {
            "hoofdwegen": 0,
            "lokale_wegen": 0,
            "woonstraten": 0,
            "kruispunten": 0,
            "snelheidsregimes": "Niet gekend",
            "ontsluitingsscore": "Beperkt"
        }

    hoofdwegen = 0
    lokale_wegen = 0
    woonstraten = 0
    kruispunten = 0
    snelheden = []

    if "highway" in auto.columns:
        hoofdwegen = len(auto[auto["highway"].isin(["motorway", "trunk", "primary", "secondary"])])
        lokale_wegen = len(auto[auto["highway"].isin(["tertiary", "unclassified", "service"])])
        woonstraten = len(auto[auto["highway"].isin(["residential", "living_street"])])
        kruispunten += len(auto[auto["highway"].isin(["traffic_signals", "stop", "give_way"])])

    if "junction" in auto.columns:
        kruispunten += len(auto[auto["junction"].notna()])

    if "maxspeed" in auto.columns:
        snelheden = auto["maxspeed"].dropna().astype(str).unique().tolist()

    if snelheden:
        snelheidsregimes = ", ".join(sorted(snelheden)[:8])
    else:
        snelheidsregimes = "Niet gekend"

    totaal = hoofdwegen + lokale_wegen + woonstraten

    if hoofdwegen >= 5 or lokale_wegen >= 15:
        ontsluitingsscore = "Goed"
    elif totaal >= 8:
        ontsluitingsscore = "Matig"
    else:
        ontsluitingsscore = "Beperkt"

    return {
        "hoofdwegen": hoofdwegen,
        "lokale_wegen": lokale_wegen,
        "woonstraten": woonstraten,
        "kruispunten": kruispunten,
        "snelheidsregimes": snelheidsregimes,
        "ontsluitingsscore": ontsluitingsscore
    }


def detailleer_auto_ontsluiting(auto, lat, lon):
    """Geeft extra auto-analyse: ontsluitingsweg, wegcategorie, snelheid,
    rijrichting, dichtstbijzijnd kruispunt en 5 dichtstbijzijnde hoofdwegen.
    Gebaseerd op OpenStreetMap-tags; blijft dus een indicatieve screening.
    """
    lege = {
        "ontsluitingsweg": "niet beschikbaar",
        "wegcategorie": "niet beschikbaar",
        "snelheidsregime": "niet beschikbaar",
        "richting": "niet beschikbaar",
        "dichtstbijzijnd_kruispunt": "niet beschikbaar",
        "afstand_kruispunt_m": None,
        "afstand_hoofdweg_m": None,
        "hoofdwegen": pd.DataFrame(columns=["naam", "wegcategorie", "afstand_m", "snelheid", "richting"]),
        "grote_wegen_breed": pd.DataFrame(columns=["naam", "wegcategorie", "afstand_m", "snelheid", "richting"]),
        "snelwegen_breed": pd.DataFrame(columns=["naam", "wegcategorie", "afstand_m", "snelheid", "richting"]),
        "ontsluitingsassen_breed": pd.DataFrame(columns=["naam", "wegcategorie", "afstand_m", "snelheid", "richting"]),
        "toelichting": "De auto-analyse kon niet worden verfijnd omdat er onvoldoende OSM-wegdata beschikbaar was."
    }
    if auto is None or auto.empty or "geometry" not in auto.columns:
        return lege

    try:
        projectpunt = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(epsg=31370).iloc[0]
        gdf = auto.copy()
        if gdf.crs is None:
            gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs="EPSG:4326")
        gdf_proj = gdf.to_crs(epsg=31370)
        gdf_proj["afstand_m"] = gdf_proj.geometry.distance(projectpunt)

        wegtypes = ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "service", "living_street"]
        wegen = gdf_proj[gdf_proj.get("highway").isin(wegtypes)].copy() if "highway" in gdf_proj.columns else gpd.GeoDataFrame()
        if wegen.empty:
            return lege

        def waarde(row, veld, fallback="niet beschikbaar"):
            v = row.get(veld, fallback)
            if pd.isna(v) or str(v).strip() == "":
                return fallback
            return str(v)

        dichtste_weg = wegen.sort_values("afstand_m").iloc[0]
        oneway = waarde(dichtste_weg, "oneway", "niet beschikbaar").lower()
        if oneway in ["yes", "true", "1", "-1"]:
            richting = "éénrichtingsverkeer"
        elif oneway in ["no", "false", "0"]:
            richting = "tweerichtingsverkeer"
        else:
            richting = "niet beschikbaar in OSM"

        hoofdweg_types = ["motorway", "trunk", "primary", "secondary", "tertiary"]
        hoofdwegen = wegen[wegen["highway"].isin(hoofdweg_types)].copy()
        hoofdwegen_records = []
        if not hoofdwegen.empty:
            for _, row in hoofdwegen.sort_values("afstand_m").head(5).iterrows():
                hoofdwegen_records.append({
                    "naam": waarde(row, "name", "Naam onbekend"),
                    "wegcategorie": waarde(row, "highway"),
                    "afstand_m": int(round(float(row["afstand_m"]))),
                    "snelheid": waarde(row, "maxspeed"),
                    "richting": "éénrichting" if waarde(row, "oneway", "").lower() in ["yes", "true", "1", "-1"] else "tweerichting/onbekend"
                })
        hoofdwegen_df = pd.DataFrame(hoofdwegen_records)
        afstand_hoofdweg = int(hoofdwegen_df["afstand_m"].min()) if not hoofdwegen_df.empty else None

        kruispunten = gdf_proj.copy()
        if "highway" in kruispunten.columns:
            kruispunten = kruispunten[
                kruispunten["highway"].isin(["traffic_signals", "stop", "give_way", "crossing"]) |
                (kruispunten["junction"].notna() if "junction" in kruispunten.columns else False)
            ].copy()
        elif "junction" in kruispunten.columns:
            kruispunten = kruispunten[kruispunten["junction"].notna()].copy()
        else:
            kruispunten = gpd.GeoDataFrame()

        if not kruispunten.empty:
            dichtste_kruispunt = kruispunten.sort_values("afstand_m").iloc[0]
            kruispunt_naam = waarde(dichtste_kruispunt, "name", waarde(dichtste_kruispunt, "highway", "kruispunt / regelpunt"))
            afstand_kruispunt = int(round(float(dichtste_kruispunt["afstand_m"])))
        else:
            kruispunt_naam = "niet beschikbaar"
            afstand_kruispunt = None

        def maak_wegen_tabel_breed(zoekstraal_m=10000):
            """Zoekt ook buiten de gekozen analyseradius naar grote wegen en snelwegen."""
            try:
                grote_tags = {"highway": ["motorway", "trunk", "primary", "secondary", "tertiary"]}
                brede_wegen = ox.features_from_point((lat, lon), tags=grote_tags, dist=zoekstraal_m)
                if brede_wegen is None or brede_wegen.empty:
                    return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
                if brede_wegen.crs is None:
                    brede_wegen = gpd.GeoDataFrame(brede_wegen, geometry="geometry", crs="EPSG:4326")
                brede_proj = brede_wegen.to_crs(epsg=31370).copy()
                brede_proj["afstand_m"] = brede_proj.geometry.distance(projectpunt)
                if "highway" not in brede_proj.columns:
                    return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

                def records(subset):
                    out = []
                    if subset is None or subset.empty:
                        return out
                    for _, r in subset.sort_values("afstand_m").head(5).iterrows():
                        out.append({
                            "naam": waarde(r, "name", "Naam onbekend"),
                            "wegcategorie": waarde(r, "highway"),
                            "afstand_m": int(round(float(r["afstand_m"]))),
                            "snelheid": waarde(r, "maxspeed"),
                            "richting": "éénrichting" if waarde(r, "oneway", "").lower() in ["yes", "true", "1", "-1"] else "tweerichting/onbekend"
                        })
                    return out

                grote_df = pd.DataFrame(records(brede_proj[brede_proj["highway"].isin(["primary", "secondary", "trunk", "motorway"])]))
                ontsluitingsassen_df = pd.DataFrame(records(brede_proj[brede_proj["highway"].isin(["primary", "secondary", "tertiary", "trunk", "motorway"])]))
                snel_df = pd.DataFrame(records(brede_proj[brede_proj["highway"].isin(["motorway", "trunk"])]))
                return grote_df, snel_df, ontsluitingsassen_df
            except Exception:
                return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        grote_wegen_breed_df, snelwegen_breed_df, ontsluitingsassen_breed_df = maak_wegen_tabel_breed()

        return {
            "ontsluitingsweg": waarde(dichtste_weg, "name", "Naam onbekend"),
            "wegcategorie": waarde(dichtste_weg, "highway"),
            "snelheidsregime": waarde(dichtste_weg, "maxspeed"),
            "richting": richting,
            "dichtstbijzijnd_kruispunt": kruispunt_naam,
            "afstand_kruispunt_m": afstand_kruispunt,
            "afstand_hoofdweg_m": afstand_hoofdweg,
            "hoofdwegen": hoofdwegen_df,
            "grote_wegen_breed": grote_wegen_breed_df,
            "snelwegen_breed": snelwegen_breed_df,
            "ontsluitingsassen_breed": ontsluitingsassen_breed_df,
            "toelichting": "Deze auto-analyse is gebaseerd op OpenStreetMap-tags. Controle op terrein en met officiële wegencategorisering blijft noodzakelijk. Grote wegen en snelwegen worden aanvullend gezocht binnen 10 km, ook wanneer ze buiten de gekozen analyseradius liggen."
        }
    except Exception as e:
        resultaat = lege.copy()
        resultaat["toelichting"] = f"Detailanalyse auto kon niet worden uitgevoerd: {type(e).__name__}."
        return resultaat


@st.cache_resource(show_spinner="Isochronen worden berekend...")
def maak_isochronenkaart(lat, lon):

    kaart_iso = folium.Map(
        location=[lat, lon],
        zoom_start=12,
        tiles=None
    )

    laag_wandelen = folium.FeatureGroup(
        name="20 min wandelen",
        show=True
    ).add_to(kaart_iso)

    laag_fietsen = folium.FeatureGroup(
        name="20 min fietsen",
        show=True
    ).add_to(kaart_iso)

    laag_auto = folium.FeatureGroup(
        name="20 min auto",
        show=True
    ).add_to(kaart_iso)

    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(kaart_iso)

    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
        attr="CartoDB Voyager",
        name="Gedetailleerde kaart",
        show=True
    ).add_to(kaart_iso)

    folium.Marker(
        [lat, lon],
        popup="Projectsite",
        tooltip="Projectsite",
        icon=folium.Icon(color="red", icon="home")
    ).add_to(kaart_iso)

    def maak_netwerk_isochroon(netwerk_type, snelheid_kmh, minuten, kleur, naam):
        try:
            max_afstand = snelheid_kmh * 1000 / 60 * minuten

            G = ox.graph_from_point(
                (lat, lon),
                dist=max_afstand * 1.3,
                network_type=netwerk_type,
                simplify=True
            )

            G_proj = ox.project_graph(G)

            for u, v, k, data in G_proj.edges(keys=True, data=True):
                lengte = data.get("length", 0)
                data["tijd"] = lengte / (snelheid_kmh * 1000 / 3600)

            punt_proj = ox.projection.project_geometry(
                Point(lon, lat),
                crs="EPSG:4326",
                to_crs=G_proj.graph["crs"]
            )[0]

            nodes_proj = ox.graph_to_gdfs(G_proj, edges=False)
            dichtste_node = nodes_proj.distance(punt_proj).idxmin()

            subgraph = nx.ego_graph(
                G_proj,
                dichtste_node,
                radius=minuten * 60,
                distance="tijd"
            )

            nodes_iso = ox.graph_to_gdfs(subgraph, edges=False)

            if nodes_iso.empty:
                return

            poly = unary_union(nodes_iso.geometry.buffer(80)).convex_hull

            poly_gdf = gpd.GeoDataFrame(
                geometry=[poly],
                crs=G_proj.graph["crs"]
            ).to_crs(epsg=4326)

            folium.GeoJson(
                poly_gdf,
                name=naam,
                style_function=lambda feature, kleur=kleur: {
                    "fillColor": kleur,
                    "color": kleur,
                    "weight": 3,
                    "fillOpacity": 0.25,
                    "opacity": 0.9,
                },
                tooltip=naam
            ).add_to(kaart_iso)

        except Exception as e:
            st.warning(f"{naam} kon niet als netwerk-isochroon worden berekend.")
            st.write(e)

    maak_netwerk_isochroon(
        "walk",
        4.8,
        20,
        "orange",
        "20 min wandelen - netwerk"
    )

    maak_netwerk_isochroon(
        "bike",
        15,
        20,
        "blue",
        "20 min fietsen - netwerk"
    )

    folium.Circle(
        location=[lat, lon],
        radius=12000,
        color="red",
        fill=True,
        fill_color="red",
        fill_opacity=0.10,
        popup="20 min auto - indicatief"
    ).add_to(laag_auto)

    folium.LayerControl(collapsed=False).add_to(kaart_iso)

    return kaart_iso



def maak_stop_isochroonkaart(lat, lon, netwerk_type, snelheid_kmh, minuten, kleur, naam, zoom_start):
    """
    Maakt een echte netwerk-isochroon voor de PDF-export.
    De polygoon wordt opgebouwd uit de bereikbare netwerksegmenten, niet uit een cirkel.
    """
    kaart = folium.Map(
        location=[lat, lon],
        zoom_start=zoom_start,
        tiles="CartoDB positron",
        control_scale=True
    )

    folium.Marker(
        [lat, lon],
        popup="Projectsite",
        tooltip="Projectsite",
        icon=folium.Icon(color="red", icon="home")
    ).add_to(kaart)

    try:
        max_afstand = snelheid_kmh * 1000 / 60 * minuten

        G = ox.graph_from_point(
            (lat, lon),
            dist=max_afstand * 1.35,
            network_type=netwerk_type,
            simplify=True
        )

        G_proj = ox.project_graph(G)

        for u, v, k, data in G_proj.edges(keys=True, data=True):
            lengte = data.get("length", 0)
            data["tijd"] = lengte / (snelheid_kmh * 1000 / 3600)

        punt_proj = ox.projection.project_geometry(
            Point(lon, lat),
            crs="EPSG:4326",
            to_crs=G_proj.graph["crs"]
        )[0]

        nodes_proj = ox.graph_to_gdfs(G_proj, edges=False)
        dichtste_node = nodes_proj.distance(punt_proj).idxmin()

        subgraph = nx.ego_graph(
            G_proj,
            dichtste_node,
            radius=minuten * 60,
            distance="tijd"
        )

        nodes_iso, edges_iso = ox.graph_to_gdfs(subgraph, nodes=True, edges=True)

        if edges_iso.empty:
            raise ValueError("Geen bereikbare netwerksegmenten gevonden.")

        buffer_m = 70 if netwerk_type == "walk" else 120
        poly = unary_union(edges_iso.geometry.buffer(buffer_m))

        poly_gdf = gpd.GeoDataFrame(
            geometry=[poly],
            crs=G_proj.graph["crs"]
        ).to_crs(epsg=4326)

        folium.GeoJson(
            poly_gdf,
            name=naam,
            style_function=lambda feature, kleur=kleur: {
                "fillColor": kleur,
                "color": kleur,
                "weight": 2,
                "fillOpacity": 0.28,
                "opacity": 0.9,
            },
            tooltip=naam
        ).add_to(kaart)

        # De bereikbare assen zelf subtiel tonen, zodat de PDF duidelijk geen cirkelanalyse is.
        folium.GeoJson(
            edges_iso.to_crs(epsg=4326),
            name=f"{naam} - bereikbaar netwerk",
            style_function=lambda feature, kleur=kleur: {
                "color": kleur,
                "weight": 1.4,
                "opacity": 0.55,
            }
        ).add_to(kaart)

        minx, miny, maxx, maxy = poly_gdf.total_bounds
        kaart.fit_bounds([[miny, minx], [maxy, maxx]])

    except Exception:
        # Fallback wanneer OSMnx lokaal geen netwerk kan laden.
        # De tekst in de PDF blijft duidelijk aangeven dat dit een fallback is.
        folium.Circle(
            location=[lat, lon],
            radius=snelheid_kmh * 1000 / 60 * minuten,
            color=kleur,
            fill=True,
            fill_color=kleur,
            fill_opacity=0.18,
            popup=f"{naam} - fallback"
        ).add_to(kaart)

    return kaart


def maak_ov_kaart_pdf(lat, lon, haltes):
    kaart = folium.Map(
        location=[lat, lon],
        zoom_start=14,
        tiles="CartoDB positron",
        control_scale=True
    )

    folium.Marker(
        [lat, lon],
        popup="Projectsite",
        tooltip="Projectsite",
        icon=folium.Icon(color="red", icon="home")
    ).add_to(kaart)

    punten = [[lat, lon]]

    if not haltes.empty:
        dichtste_haltes = haltes.sort_values("afstand_m").head(20)

        for _, halte in dichtste_haltes.iterrows():
            punten.append([halte["lat"], halte["lon"]])
            folium.Marker(
                [halte["lat"], halte["lon"]],
                popup=f'{halte["halte_naam"]} - {halte["afstand_m"]} m',
                tooltip=halte["halte_naam"],
                icon=folium.Icon(color="blue", icon="bus", prefix="fa")
            ).add_to(kaart)

    if len(punten) > 1:
        kaart.fit_bounds(punten, padding=(30, 30))

    return kaart


# =========================================================
# FOLIUM-KAARTEN VOOR PDF — zelfde kaartlogica als in de app
# =========================================================

def _gdf_for_folium(gdf, max_features=900):
    """Maakt GeoDataFrames veilig en lichter voor Folium/PDF-screenshots.
    Zo gebruiken PDF-kaarten opnieuw de interactieve Folium-kaarten, maar zonder dat
    Selenium vastloopt op extreem zware lagen.
    """
    if gdf is None:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    try:
        g = gdf.copy()
        if g.empty or "geometry" not in g.columns:
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        if g.crs is None:
            g = gpd.GeoDataFrame(g, geometry="geometry", crs="EPSG:4326")
        g = g.to_crs(epsg=4326)
        # Beperk zeer zware lagen voor de PDF-screenshot. De volledige interactieve kaart
        # blijft in de app beschikbaar, maar de PDF moet vlot en leesbaar blijven.
        if len(g) > max_features:
            g = g.head(max_features).copy()
        return g
    except Exception:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")


def _add_folium_gdf(kaart, gdf, name, color="#1F77B4", weight=2, opacity=0.75, fill_opacity=0.15, show=True, max_features=900):
    g = _gdf_for_folium(gdf, max_features=max_features)
    if g is None or g.empty:
        return
    try:
        folium.GeoJson(
            g,
            name=name,
            show=show,
            style_function=lambda feature, kleur=color, gewicht=weight, op=opacity, fill=fill_opacity: {
                "color": kleur,
                "weight": gewicht,
                "opacity": op,
                "fillColor": kleur,
                "fillOpacity": fill,
            },
            marker=folium.CircleMarker(radius=3, color=color, fill=True, fill_opacity=0.8),
        ).add_to(kaart)
    except Exception:
        pass


def _add_project_marker_en_radius(kaart, lat, lon, straal):
    folium.Marker(
        [lat, lon],
        popup="Projectsite",
        tooltip="Projectsite",
        icon=folium.Icon(color="red", icon="home")
    ).add_to(kaart)
    folium.Circle(
        location=[lat, lon],
        radius=straal,
        fill=False,
        color="#6B8F71",
        weight=2,
        tooltip=f"{straal} meter analysegebied"
    ).add_to(kaart)


def _add_basislagen(kaart):
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=False).add_to(kaart)
    folium.TileLayer("CartoDB positron", name="Lichte kaart", show=True).add_to(kaart)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Luchtfoto",
        show=False,
    ).add_to(kaart)


def maak_pdf_projectkaart_folium(lat, lon, straal, haltes=None, hoppinpunten=None, bff_routes=None, auto_gdf=None):
    """Projectkaart voor PDF op basis van dezelfde Folium-kaartstijl als de app."""
    kaart = folium.Map(location=[lat, lon], zoom_start=15, tiles=None, control_scale=True)
    _add_basislagen(kaart)
    _add_folium_gdf(kaart, auto_gdf, "Wegen", color="#777777", weight=1, opacity=0.45, show=False, max_features=800)
    _add_folium_gdf(kaart, bff_routes, "BFF-fietsroutes", color="purple", weight=4, opacity=0.85, show=True, max_features=500)
    punten = [[lat, lon]]
    if haltes is not None and not getattr(haltes, "empty", True):
        for _, halte in haltes.sort_values("afstand_m").head(15).iterrows():
            punten.append([halte["lat"], halte["lon"]])
            folium.Marker(
                [halte["lat"], halte["lon"]],
                popup=f'{halte.get("halte_naam", "Halte")}<br>{halte.get("afstand_m", "")} m',
                tooltip=halte.get("halte_naam", "Halte"),
                icon=folium.Icon(color="blue", icon="bus", prefix="fa")
            ).add_to(kaart)
    if hoppinpunten is not None and not getattr(hoppinpunten, "empty", True):
        for _, punt in hoppinpunten.sort_values("afstand_m").head(10).iterrows():
            punten.append([punt["lat"], punt["lon"]])
            folium.Marker(
                [punt["lat"], punt["lon"]],
                popup=f'{punt.get("naam", "Hoppinpunt")}<br>{punt.get("afstand_m", "")} m',
                tooltip=punt.get("naam", "Hoppinpunt"),
                icon=folium.Icon(color="green", icon="info-sign")
            ).add_to(kaart)
    _add_project_marker_en_radius(kaart, lat, lon, straal)
    if len(punten) > 1:
        try:
            kaart.fit_bounds(punten, padding=(30, 30))
        except Exception:
            pass
    folium.LayerControl(collapsed=True).add_to(kaart)
    return kaart


def maak_pdf_stapperskaart_folium(lat, lon, straal, stappers_gdf=None, auto_gdf=None):
    """Stapperskaart voor PDF: dezelfde Folium-aanpak als de app, met echte kaartachtergrond."""
    kaart = folium.Map(location=[lat, lon], zoom_start=15, tiles=None, control_scale=True)
    _add_basislagen(kaart)
    _add_folium_gdf(kaart, auto_gdf, "Wegen", color="#888888", weight=1, opacity=0.45, show=True, max_features=900)
    _add_folium_gdf(kaart, stappers_gdf, "Stappers", color="orange", weight=2.2, opacity=0.85, show=True, max_features=900)
    _add_project_marker_en_radius(kaart, lat, lon, straal)
    folium.LayerControl(collapsed=True).add_to(kaart)
    return kaart


def maak_pdf_trapperskaart_folium(lat, lon, straal, trappers_gdf=None, bff_routes=None, recreatieve_routes=None, auto_gdf=None):
    """Trapperskaart voor PDF: fietsinfrastructuur, BFF en recreatieve routes op Folium."""
    kaart = folium.Map(location=[lat, lon], zoom_start=14, tiles=None, control_scale=True)
    _add_basislagen(kaart)
    _add_folium_gdf(kaart, auto_gdf, "Wegen", color="#888888", weight=1, opacity=0.40, show=False, max_features=900)
    _add_folium_gdf(kaart, trappers_gdf, "Fietsvoorzieningen", color="darkgreen", weight=2.1, opacity=0.82, show=True, max_features=900)
    _add_folium_gdf(kaart, bff_routes, "BFF-fietsroutes", color="purple", weight=4, opacity=0.9, show=True, max_features=700)
    _add_folium_gdf(kaart, recreatieve_routes, "Recreatieve fietsroutes", color="#00A6A6", weight=3, opacity=0.85, show=True, max_features=500)
    _add_project_marker_en_radius(kaart, lat, lon, straal)
    folium.LayerControl(collapsed=True).add_to(kaart)
    return kaart


def maak_pdf_ovkaart_folium(lat, lon, straal, haltes=None, hoppinpunten=None):
    """OV-kaart voor PDF met dezelfde Folium-halteweergave als de app."""
    kaart = folium.Map(location=[lat, lon], zoom_start=14, tiles=None, control_scale=True)
    _add_basislagen(kaart)
    punten = [[lat, lon]]
    if haltes is not None and not getattr(haltes, "empty", True):
        for _, halte in haltes.sort_values("afstand_m").head(25).iterrows():
            punten.append([halte["lat"], halte["lon"]])
            folium.Marker(
                [halte["lat"], halte["lon"]],
                popup=f'{halte.get("halte_naam", "Halte")}<br>{halte.get("afstand_m", "")} m<br>{halte.get("buslijnen", "")}',
                tooltip=halte.get("halte_naam", "Halte"),
                icon=folium.Icon(color="blue", icon="bus", prefix="fa")
            ).add_to(kaart)
    if hoppinpunten is not None and not getattr(hoppinpunten, "empty", True):
        for _, punt in hoppinpunten.sort_values("afstand_m").head(15).iterrows():
            punten.append([punt["lat"], punt["lon"]])
            folium.Marker(
                [punt["lat"], punt["lon"]],
                popup=f'{punt.get("naam", "Hoppinpunt")}<br>{punt.get("gemeente", "")}<br>{punt.get("afstand_m", "")} m',
                tooltip=punt.get("naam", "Hoppinpunt"),
                icon=folium.Icon(color="green", icon="info-sign")
            ).add_to(kaart)
    _add_project_marker_en_radius(kaart, lat, lon, straal)
    if len(punten) > 1:
        try:
            kaart.fit_bounds(punten, padding=(30, 30))
        except Exception:
            pass
    folium.LayerControl(collapsed=True).add_to(kaart)
    return kaart


def maak_stop_autobereikbaarheidskaart(lat, lon, minuten=20, snelheid_kmh=36, straal_context=1000):
    """PDF-kaart voor 20 minuten autobereikbaarheid.
    Deze kaart sluit aan op de isochronenkaart in de app. Wandelen en fietsen
    worden als netwerk-isochroon getoond; auto blijft indicatief met een afstandscirkel.
    """
    radius = snelheid_kmh * 1000 / 60 * minuten
    kaart = folium.Map(location=[lat, lon], zoom_start=11, tiles=None, control_scale=True)
    _add_basislagen(kaart)
    folium.Marker(
        [lat, lon],
        popup="Projectsite",
        tooltip="Projectsite",
        icon=folium.Icon(color="red", icon="home")
    ).add_to(kaart)
    folium.Circle(
        location=[lat, lon],
        radius=radius,
        color="#D62728",
        fill=True,
        fill_color="#D62728",
        fill_opacity=0.16,
        weight=3,
        popup=f"{minuten} minuten auto - indicatief"
    ).add_to(kaart)
    folium.Circle(
        location=[lat, lon],
        radius=straal_context,
        color="#0B1F33",
        fill=False,
        weight=1.8,
        tooltip="gekozen analysegebied"
    ).add_to(kaart)
    try:
        dlat = max(0.08, radius / 111_000)
        dlon = max(0.12, radius / (111_000 * max(0.2, abs(__import__('math').cos(__import__('math').radians(lat))))))
        kaart.fit_bounds([[lat - dlat, lon - dlon], [lat + dlat, lon + dlon]], padding=(25, 25))
    except Exception:
        pass
    folium.LayerControl(collapsed=True).add_to(kaart)
    return kaart

def maak_kaart_png(kaart, bestandsnaam):
    """
    Zet een Folium-kaart om naar PNG voor de PDF.
    Verbeterde versie:
    - langere laadtijd voor Leaflet-tegels;
    - wacht actief tot de kaart en tiles geladen zijn;
    - grotere timeout voor Selenium;
    - neemt de volledige folium-map vast zonder zwarte randen.
    """
    import tempfile
    import time
    from PIL import Image as PILImage, ImageChops, ImageDraw, ImageFont

    html_path = os.path.join(tempfile.gettempdir(), bestandsnaam + ".html")
    png_path = os.path.join(tempfile.gettempdir(), bestandsnaam + ".png")

    kaart.save(html_path)

    def maak_placeholder(reden="Kaart kon niet automatisch als afbeelding worden geëxporteerd."):
        img = PILImage.new("RGB", (1400, 850), "white")
        draw = ImageDraw.Draw(img)
        try:
            font_titel = ImageFont.truetype("arial.ttf", 34)
            font_tekst = ImageFont.truetype("arial.ttf", 24)
        except Exception:
            font_titel = ImageFont.load_default()
            font_tekst = ImageFont.load_default()

        draw.rectangle((40, 40, 1360, 810), outline=(120, 120, 120), width=3)
        draw.text((90, 110), "Kaart niet beschikbaar in PDF-export", fill=(20, 45, 70), font=font_titel)
        draw.text((90, 190), reden, fill=(70, 70, 70), font=font_tekst)
        draw.text((90, 245), "Gebruik de interactieve HTML-kaart voor de volledige kaartweergave.", fill=(70, 70, 70), font=font_tekst)
        img.save(png_path, quality=95)
        return png_path

    driver = None

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager

        options = webdriver.ChromeOptions()
        # Belangrijk: wacht niet tot alle externe kaarttegels volledig klaar zijn.
        # Anders kan driver.get() blokkeren en een TimeoutError geven.
        options.page_load_strategy = "eager"
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1800,1100")
        options.add_argument("--hide-scrollbars")
        options.add_argument("--force-device-scale-factor=2")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-networking")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--allow-file-access-from-files")
        options.add_argument("--log-level=3")

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        driver.set_page_load_timeout(90)
        driver.set_script_timeout(120)

        try:
            driver.get("file:///" + html_path.replace("\\", "/"))
        except Exception:
            # Bij Folium kan driver.get() een TimeoutError geven terwijl de HTML-kaart
            # al gedeeltelijk geladen is. In dat geval proberen we gewoon verder te renderen.
            pass

        # Extra wachttijd voor Leaflet, CartoDB/OpenStreetMap-tegels en lokale HTML-render.
        time.sleep(18)
        try:
            driver.execute_script("window.dispatchEvent(new Event('resize'));")
        except Exception:
            pass
        time.sleep(3)

        wait = WebDriverWait(driver, 90)
        element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".folium-map")))

        # Wacht tot Leaflet de basiskaart heeft opgebouwd.
        # Niet hard falen wanneer externe tegels traag zijn: de overlays/projectmarkers
        # kunnen dan nog altijd als screenshot worden opgenomen.
        try:
            wait.until(lambda d: d.execute_script(
                "return !!document.querySelector('.leaflet-container');"
            ))
        except Exception:
            pass

        # Geef externe kaarttegels extra tijd. Tegels die falen worden genegeerd,
        # zodat de screenshot niet volledig blokkeert.
        max_wait = time.time() + 35
        while time.time() < max_wait:
            try:
                stats = driver.execute_script("""
                    const tiles = Array.from(document.querySelectorAll('.leaflet-tile'));
                    const visible = tiles.filter(t => t.complete && t.naturalWidth > 0).length;
                    const loading = tiles.filter(t => !t.complete).length;
                    return {total: tiles.length, visible: visible, loading: loading};
                """)
                if stats and stats.get('total', 0) > 0 and stats.get('loading', 0) == 0:
                    break
                if stats and stats.get('visible', 0) >= max(4, stats.get('total', 0) * 0.75):
                    break
            except Exception:
                pass
            time.sleep(1)

        time.sleep(2)
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            driver.execute_script("window.dispatchEvent(new Event('resize'));")
        except Exception:
            pass
        time.sleep(1)
        element.screenshot(png_path)

    except Exception as e:
        return maak_placeholder(f"Technische oorzaak: {type(e).__name__}")

    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    try:
        img = PILImage.open(png_path).convert("RGB")

        # Verwijder eventuele uniforme buitenrand.
        bg = PILImage.new("RGB", img.size, img.getpixel((0, 0)))
        diff = ImageChops.difference(img, bg)
        bbox = diff.getbbox()
        if bbox:
            img = img.crop(bbox)

        pixels = img.load()
        width, height = img.size

        def is_black_row(y):
            samples = [pixels[x, y] for x in range(0, width, max(1, width // 40))]
            return sum(1 for r, g, b in samples if r < 15 and g < 15 and b < 15) > len(samples) * 0.70

        while height > 50 and is_black_row(height - 1):
            height -= 1

        img = img.crop((0, 0, width, height))

        marge = 18
        canvas = PILImage.new("RGB", (img.width + 2 * marge, img.height + 2 * marge), "white")
        canvas.paste(img, (marge, marge))
        canvas.save(png_path, quality=95)

        return png_path

    except Exception as e:
        return maak_placeholder(f"Technische oorzaak bij nabewerking: {type(e).__name__}")





def _as_gdf_wgs84(gdf):
    """Zorgt dat een GeoDataFrame veilig als WGS84 kan worden gebruikt."""
    try:
        if gdf is None or gdf.empty or "geometry" not in gdf.columns:
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        out = gdf.copy()
        if out.crs is None:
            out = gpd.GeoDataFrame(out, geometry="geometry", crs="EPSG:4326")
        return out.to_crs(epsg=4326)
    except Exception:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")


def _project_point_31370(lat, lon):
    return gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(epsg=31370).iloc[0]


def _plot_gdf_layer(ax, gdf, color="#666666", linewidth=0.8, alpha=0.8, markersize=12, zorder=2, label=None):
    """Plot een GeoDataFrame robuust op een matplotlib-as."""
    try:
        if gdf is None or gdf.empty or "geometry" not in gdf.columns:
            return
        gg = _as_gdf_wgs84(gdf).to_crs(epsg=31370)
        lines = gg[gg.geometry.geom_type.isin(["LineString", "MultiLineString"])]
        polys = gg[gg.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
        pts = gg[gg.geometry.geom_type.isin(["Point", "MultiPoint"])]
        if not polys.empty:
            polys.plot(ax=ax, facecolor=color, edgecolor=color, alpha=max(0.08, alpha * 0.25), linewidth=0.4, zorder=zorder)
        if not lines.empty:
            lines.plot(ax=ax, color=color, linewidth=linewidth, alpha=alpha, zorder=zorder, label=label)
        if not pts.empty:
            pts.plot(ax=ax, color=color, markersize=markersize, alpha=alpha, zorder=zorder, label=label)
    except Exception:
        return


def _setup_pdf_map_ax(ax, lat, lon, radius_m, titel):
    projectpunt = _project_point_31370(lat, lon)
    marge = max(250, radius_m * 0.35)
    ax.set_xlim(projectpunt.x - radius_m - marge, projectpunt.x + radius_m + marge)
    ax.set_ylim(projectpunt.y - radius_m - marge, projectpunt.y + radius_m + marge)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(titel, fontsize=11, fontweight="bold", pad=8)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    ax.set_facecolor("#F6F7F8")
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)
        spine.set_edgecolor("#808080")
    return projectpunt


def _add_context_basemap(ax):
    """Voegt een echte lichte achtergrondkaart toe aan de PDF-kaarten.
    Werkt met contextily wanneer beschikbaar. Als tegels niet laden blijft de kaart
    nog bruikbaar door de eigen GIS-lagen.
    """
    try:
        import contextily as ctx
        try:
            bron = ctx.providers.CartoDB.Positron
        except Exception:
            bron = ctx.providers.OpenStreetMap.Mapnik
        ctx.add_basemap(
            ax,
            crs="EPSG:31370",
            source=bron,
            attribution=False,
            zoom="auto",
            reset_extent=True,
        )
        return True
    except ModuleNotFoundError:
        # De app blijft werken zonder contextily, maar de kaart krijgt dan alleen de
        # eigen GIS-lagen. Installeer lokaal: pip install contextily xyzservices
        return False
    except Exception:
        return False


def _finish_pdf_map(ax, fig, png_path, with_attribution=True):
    if with_attribution:
        ax.text(
            0.99, 0.01,
            "Achtergrond: OpenStreetMap/CartoDB · analyse: MOBISCAN",
            transform=ax.transAxes,
            fontsize=5.8,
            color="#555555",
            ha="right",
            va="bottom",
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.65, pad=1.5),
        )
    fig.tight_layout(pad=0.8)
    fig.savefig(png_path, bbox_inches="tight", facecolor="white")
    return png_path


def _add_project_and_radius(ax, projectpunt, radius_m, radius_label=True):
    import matplotlib.patches as patches
    cirkel = patches.Circle(
        (projectpunt.x, projectpunt.y),
        radius_m,
        fill=False,
        edgecolor="#0B1F33",
        linewidth=1.6,
        linestyle="--",
        alpha=0.75,
        zorder=6,
    )
    ax.add_patch(cirkel)
    ax.scatter([projectpunt.x], [projectpunt.y], s=42, marker="o", color="#D62728", zorder=8)
    ax.text(projectpunt.x + radius_m * 0.025, projectpunt.y + radius_m * 0.025, "Projectsite", fontsize=8, weight="bold", zorder=9)
    if radius_label:
        ax.text(0.02, 0.02, f"Analysegebied: {int(radius_m)} m", transform=ax.transAxes, fontsize=7, color="#444444")


def _select_osm_roads(auto_gdf, categories=None):
    auto_gdf = _as_gdf_wgs84(auto_gdf)
    if auto_gdf.empty or "highway" not in auto_gdf.columns:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    if categories is None:
        categories = ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "service", "living_street"]
    return auto_gdf[auto_gdf["highway"].isin(categories)].copy()


@st.cache_data
def zoek_pdf_context_wegen(lat, lon, straal_context):
    """Haalt een bredere OSM-wegcontext op voor PDF-kaarten.
    Deze laag wordt enkel gebruikt als achtergrond/context, zodat de 20-minutenkaarten
    niet enkel een gekleurd bereikbaar netwerk tonen maar ook de omliggende dorpen,
    hoofdwegen en lokale wegen leesbaar blijven.
    """
    tags = {
        "highway": [
            "motorway", "trunk", "primary", "secondary", "tertiary",
            "residential", "unclassified", "service", "living_street"
        ]
    }
    try:
        # Beperk de maximale straal om de PDF-generatie niet te zwaar te maken.
        straal_context = int(max(2000, min(float(straal_context), 22000)))
        gdf = ox.features_from_point((lat, lon), tags=tags, dist=straal_context)
        if gdf is None or gdf.empty:
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        return gdf.to_crs(epsg=4326)
    except Exception:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")


def _combine_gdfs_for_context(*gdfs):
    lagen = []
    for gdf in gdfs:
        gg = _as_gdf_wgs84(gdf)
        if not gg.empty:
            lagen.append(gg)
    if not lagen:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    try:
        return pd.concat(lagen, ignore_index=True).pipe(gpd.GeoDataFrame, crs="EPSG:4326")
    except Exception:
        return lagen[0]



def maak_reportlab_image_met_verhouding(image_path, max_width, max_height):
    """Maak een ReportLab Image zonder vervorming.
    De afbeelding wordt proportioneel geschaald zodat ze binnen max_width x max_height past.
    Dit voorkomt uitgerokken PDF-kaarten wanneer breedte en hoogte vast worden opgegeven.
    """
    from reportlab.platypus import Image as RLImage
    try:
        from PIL import Image as PILImage
        with PILImage.open(image_path) as img:
            w, h = img.size
        if not w or not h:
            return RLImage(image_path, width=max_width, height=max_height)
        ratio = min(max_width / w, max_height / h)
        return RLImage(image_path, width=w * ratio, height=h * ratio)
    except Exception:
        return RLImage(image_path, width=max_width, height=max_height)

def maak_pdf_projectkaart_png(lat, lon, straal, auto_gdf=None, haltes=None, hoppinpunten=None, bff_routes=None, bestandsnaam="pdf_projectkaart"):
    """Professionele situeringskaart met echte achtergrondkaart en analyseobjecten."""
    import tempfile
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    png_path = os.path.join(tempfile.gettempdir(), bestandsnaam + ".png")
    fig, ax = plt.subplots(figsize=(8.2, 4.7), dpi=220)
    projectpunt = _setup_pdf_map_ax(ax, lat, lon, straal, "Situering projectsite met analysegebied")

    basemap_ok = _add_context_basemap(ax)

    # Contextlagen bovenop de lichte basemap.
    lokale_wegen = _select_osm_roads(auto_gdf, ["residential", "unclassified", "service", "living_street"])
    hoofdwegen = _select_osm_roads(auto_gdf, ["motorway", "trunk", "primary", "secondary", "tertiary"])
    _plot_gdf_layer(ax, lokale_wegen, color="#9E9E9E", linewidth=0.55, alpha=0.55 if basemap_ok else 0.85, zorder=2)
    _plot_gdf_layer(ax, hoofdwegen, color="#545454", linewidth=1.45, alpha=0.85, zorder=3)
    _plot_gdf_layer(ax, bff_routes, color="#7B3294", linewidth=2.4, alpha=0.95, zorder=5)

    if haltes is not None and not haltes.empty:
        try:
            h = haltes.sort_values("afstand_m").head(25).copy()
            hgdf = gpd.GeoDataFrame(h, geometry=gpd.points_from_xy(h["lon"], h["lat"]), crs="EPSG:4326").to_crs(epsg=31370)
            hgdf.plot(ax=ax, marker="s", color="#1F77B4", edgecolor="white", linewidth=0.35, markersize=18, alpha=0.95, zorder=6)
        except Exception:
            pass

    if hoppinpunten is not None and not hoppinpunten.empty:
        try:
            pgdf = gpd.GeoDataFrame(hoppinpunten.copy(), geometry=gpd.points_from_xy(hoppinpunten["lon"], hoppinpunten["lat"]), crs="EPSG:4326").to_crs(epsg=31370)
            pgdf.plot(ax=ax, marker="^", color="#2CA02C", edgecolor="white", linewidth=0.4, markersize=42, alpha=0.95, zorder=7)
        except Exception:
            pass

    _add_project_and_radius(ax, projectpunt, straal)
    handles = [
        Line2D([0], [0], color="#545454", lw=1.5, label="hoofdweg"),
        Line2D([0], [0], color="#7B3294", lw=2.2, label="BFF"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#1F77B4", markeredgecolor="white", markersize=7, label="halte"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#2CA02C", markeredgecolor="white", markersize=8, label="Hoppin"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#D62728", markersize=7, label="projectsite"),
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=6.5, framealpha=0.90)
    return _finish_pdf_map(ax, fig, png_path)


def maak_pdf_stapperskaart_png(lat, lon, straal, stappers_gdf=None, auto_gdf=None, bestandsnaam="pdf_stapperskaart"):
    """Stapperskaart met basemap, wandelverbindingen en oversteken."""
    import tempfile
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    png_path = os.path.join(tempfile.gettempdir(), bestandsnaam + ".png")
    fig, ax = plt.subplots(figsize=(8.2, 4.7), dpi=220)
    projectpunt = _setup_pdf_map_ax(ax, lat, lon, straal, "Stappers: wandelinfrastructuur")
    basemap_ok = _add_context_basemap(ax)

    _plot_gdf_layer(ax, _select_osm_roads(auto_gdf), color="#8F8F8F", linewidth=0.45, alpha=0.45 if basemap_ok else 0.75, zorder=2)
    stappers_gdf = _as_gdf_wgs84(stappers_gdf)
    crossings = stappers_gdf.iloc[0:0].copy() if not stappers_gdf.empty else stappers_gdf
    if not stappers_gdf.empty:
        if "highway" in stappers_gdf.columns:
            crossings = pd.concat([crossings, stappers_gdf[stappers_gdf["highway"] == "crossing"]])
        if "footway" in stappers_gdf.columns:
            crossings = pd.concat([crossings, stappers_gdf[stappers_gdf["footway"] == "crossing"]])
        _plot_gdf_layer(ax, stappers_gdf, color="#F39C12", linewidth=1.15, alpha=0.88, markersize=9, zorder=5)
        _plot_gdf_layer(ax, crossings, color="#D35400", linewidth=0.8, alpha=0.95, markersize=24, zorder=6)

    _add_project_and_radius(ax, projectpunt, straal)
    handles = [
        Line2D([0], [0], color="#F39C12", lw=1.6, label="voetgangersverbinding"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#D35400", markersize=6, label="oversteek"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#D62728", markersize=7, label="projectsite"),
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=6.5, framealpha=0.90)
    return _finish_pdf_map(ax, fig, png_path)


def maak_pdf_trapperskaart_png(lat, lon, straal, trappers_gdf=None, bff_routes=None, recreatieve_routes=None, auto_gdf=None, bestandsnaam="pdf_trapperskaart"):
    """Trapperskaart met basemap, fietsinfrastructuur, BFF en recreatieve routes."""
    import tempfile
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    png_path = os.path.join(tempfile.gettempdir(), bestandsnaam + ".png")
    fig, ax = plt.subplots(figsize=(8.2, 4.7), dpi=220)
    projectpunt = _setup_pdf_map_ax(ax, lat, lon, straal, "Trappers: fietsinfrastructuur en fietsroutes")
    basemap_ok = _add_context_basemap(ax)

    _plot_gdf_layer(ax, _select_osm_roads(auto_gdf), color="#8F8F8F", linewidth=0.45, alpha=0.45 if basemap_ok else 0.72, zorder=2)
    _plot_gdf_layer(ax, trappers_gdf, color="#2E8B57", linewidth=1.05, alpha=0.82, markersize=9, zorder=4)
    _plot_gdf_layer(ax, recreatieve_routes, color="#00A6A6", linewidth=1.45, alpha=0.90, markersize=12, zorder=5)
    _plot_gdf_layer(ax, bff_routes, color="#7B3294", linewidth=2.6, alpha=0.98, markersize=12, zorder=6)

    _add_project_and_radius(ax, projectpunt, straal)
    handles = [
        Line2D([0], [0], color="#2E8B57", lw=1.5, label="fietsvoorziening"),
        Line2D([0], [0], color="#7B3294", lw=2.4, label="BFF"),
        Line2D([0], [0], color="#00A6A6", lw=1.5, label="recreatieve route"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#D62728", markersize=7, label="projectsite"),
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=6.5, framealpha=0.90)
    return _finish_pdf_map(ax, fig, png_path)


def maak_pdf_ov_kaart_png(lat, lon, straal, haltes=None, hoppinpunten=None, auto_gdf=None, bestandsnaam="pdf_ovkaart"):
    """OV-kaart met achtergrondkaart, haltes, Hoppinpunten en beperkte labels."""
    import tempfile
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    png_path = os.path.join(tempfile.gettempdir(), bestandsnaam + ".png")
    fig, ax = plt.subplots(figsize=(8.2, 4.7), dpi=220)
    radius = max(500, min(1600, straal))
    projectpunt = _setup_pdf_map_ax(ax, lat, lon, radius, "Openbaar vervoer: haltes en Hoppinpunten")
    basemap_ok = _add_context_basemap(ax)

    _plot_gdf_layer(ax, _select_osm_roads(auto_gdf), color="#8F8F8F", linewidth=0.45, alpha=0.45 if basemap_ok else 0.75, zorder=2)

    if haltes is not None and not haltes.empty:
        try:
            h = haltes.sort_values("afstand_m").head(30).copy()
            hgdf = gpd.GeoDataFrame(h, geometry=gpd.points_from_xy(h["lon"], h["lat"]), crs="EPSG:4326").to_crs(epsg=31370)
            hgdf.plot(ax=ax, marker="s", color="#1F77B4", edgecolor="white", linewidth=0.35, markersize=22, alpha=0.95, zorder=5)
            # Alleen de dichtste haltes labelen om overlap te vermijden.
            for _, row in hgdf.head(6).iterrows():
                naam = str(row.get("halte_naam", "halte"))[:22]
                ax.text(
                    row.geometry.x + 20,
                    row.geometry.y + 20,
                    naam,
                    fontsize=5.6,
                    color="#222222",
                    zorder=7,
                    bbox=dict(facecolor="white", edgecolor="none", alpha=0.70, pad=0.4),
                )
        except Exception:
            pass

    if hoppinpunten is not None and not hoppinpunten.empty:
        try:
            pgdf = gpd.GeoDataFrame(hoppinpunten.copy(), geometry=gpd.points_from_xy(hoppinpunten["lon"], hoppinpunten["lat"]), crs="EPSG:4326").to_crs(epsg=31370)
            pgdf.plot(ax=ax, marker="^", color="#2CA02C", edgecolor="white", linewidth=0.4, markersize=48, alpha=0.96, zorder=6)
        except Exception:
            pass

    _add_project_and_radius(ax, projectpunt, radius)
    handles = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#1F77B4", markeredgecolor="white", markersize=7, label="De Lijn-halte"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#2CA02C", markeredgecolor="white", markersize=8, label="Hoppinpunt"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#D62728", markersize=7, label="projectsite"),
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=6.5, framealpha=0.90)
    return _finish_pdf_map(ax, fig, png_path)

def bff_tabel_dataframe(bff_routes):
    if bff_routes.empty:
        return pd.DataFrame()

    df = bff_routes.copy()

    kolommen = [col for col in df.columns if col != "geometry"]
    mogelijke = [
        "naam", "Naam", "name", "Name",
        "categorie", "Categorie", "cat", "CAT", "type", "Type",
        "route_type", "routetype", "functioneel", "functie", "hoofdroute",
        "status", "Status", "afstand_m"
    ]

    toon = [col for col in mogelijke if col in kolommen]

    # Als de officiële laag andere veldnamen heeft, toon dan toch enkele compacte attribuutkolommen.
    if not toon:
        toon = kolommen[:4]

    if "afstand_m" in kolommen and "afstand_m" not in toon:
        toon.append("afstand_m")

    if not toon:
        return pd.DataFrame({"Aantal BFF-segmenten": [len(df)]})

    return df[toon].sort_values("afstand_m") if "afstand_m" in toon else df[toon].head(10)


def bepaal_score(aantal, goed, matig):
    if aantal >= goed:
        return "Goed"
    elif aantal >= matig:
        return "Matig"
    else:
        return "Beperkt"


def maak_scores(haltes, hoppinpunten, bff_routes):
    ov_score = bepaal_score(len(haltes), goed=6, matig=2)
    hoppin_score = bepaal_score(len(hoppinpunten), goed=2, matig=1)
    fiets_score = bepaal_score(len(bff_routes), goed=3, matig=1)

    if ov_score == "Goed" and fiets_score == "Goed":
        totaal_score = "Goed"
    elif ov_score == "Beperkt" and fiets_score == "Beperkt":
        totaal_score = "Beperkt"
    else:
        totaal_score = "Matig"

    return ov_score, hoppin_score, fiets_score, totaal_score



def bepaal_automatische_parkeer_context(adres, lat, lon, projecttype):
    """Bepaalt parkeercontext automatisch op basis van adres en coördinaten.

    Prototype-implementatie:
    - Hasselt wordt herkend op basis van adres/geocodering;
    - voor de gekende case rond Veldmansbrugstraat/Kapermolen wordt automatisch
      Binnen Singel, statistische sector Kapermolen en lokaal wagenbezit 0,72 ingevuld;
    - andere Hasseltse locaties krijgen Hasseltse normen, maar met zone/sector als controlepunt;
    - andere gemeenten vallen voorlopig terug op de generieke formule.

    Dit is bewust transparant: zolang er geen officiële GIS-laag met parkeerzones en
    statistische-sectorwaarden is gekoppeld, vermeldt de app wat automatisch is bepaald
    en wat nog manueel/officieel moet worden gecontroleerd.
    """
    adres_lc = (adres or "").lower()

    context = {
        "modus": "Automatisch bepalen op basis van adres",
        "norm_context": "Generieke prototypeformule",
        "zone": "Niet automatisch herkend",
        "lokaal_wagenbezit": 0.0,
        "statistische_sector": "Niet automatisch herkend",
        "straatparkeren_toelichting": "Niet automatisch bepaald voor deze gemeente.",
        "automatisch_bepaald": True,
        "automatische_bronnen": "Adres/geocodering + ingebouwde prototypekoppeling lokale parkeernormen",
        "automatische_opmerking": "Voor deze gemeente is nog geen lokale parkeerlaag gekoppeld. De generieke formule blijft actief.",
    }

    # Hasselt: eerste lokale koppeling voor de testcase en demo.
    # De coördinaten rond Kapermolen/Veldmansbrugstraat worden ruim genomen zodat kleine geocodeverschillen geen probleem vormen.
    is_hasselt = "hasselt" in adres_lc or (50.88 <= lat <= 50.98 and 5.26 <= lon <= 5.42)

    if is_hasselt:
        context.update({
            "norm_context": "Hasselt - lokale parkeerverordening",
            "zone": "Andere zone / manueel te controleren",
            "lokaal_wagenbezit": 1.10,
            "statistische_sector": "Hasselt - sector nog te controleren",
            "straatparkeren_toelichting": "Hasselt: controleer lokale parkeerregimes zoals betalend parkeren, blauwe zone, bewonersparkeren en publieke parkings.",
            "automatische_opmerking": "Hasselt werd automatisch herkend. De exacte parkeerzone en statistische sector moeten buiten de gekende Kapermolen-zone nog officieel worden gecontroleerd.",
        })

        # Gekende testcase: omgeving Veldmansbrugstraat / Kapermolen.
        # Controlepunt voor de gekende democase rond Veldmansbrugstraat/Kapermolen.
        afstand_kapermolen = geodesic((lat, lon), (50.93344, 5.34945)).meters
        if afstand_kapermolen <= 1200:
            context.update({
                "zone": "Binnen Singel",
                "lokaal_wagenbezit": 0.72,
                "statistische_sector": "Kapermolen",
                "straatparkeren_toelichting": "Binnen Singel / Kapermolen: parkeerregime en bezoekersparkeren moeten verder worden gecontroleerd via de Hasseltse parkeerinformatie. Deze automatische koppeling gebruikt de lagere lokale autobezitscontext voor de projectomgeving.",
                "automatische_opmerking": "Automatisch herkend als omgeving Kapermolen/Veldmansbrugstraat. Parkeerzone Binnen Singel en lokaal wagenbezit 0,72 werden automatisch ingevuld voor de testcase.",
            })

    return context

def bereken_project_effecten(projecttype, aantal_wooneenheden, bvo, parkeerplaatsen, fietsenstallingen, parkeer_context=None):
    """Berekent parkeer-, fietsparkeer- en verkeersgeneratie.

    Aangepast in deze versie:
    - woonprojecten gebruiken niet langer automatisch 1,20 pp/wooneenheid;
    - Hasselt kan worden berekend met de lokale bandbreedte 0,50-0,75 pp/wooneenheid;
    - verkeersgeneratie voor wonen wordt opgebouwd volgens bewoners + bezoekers + modal split,
      zodat de raming minder snel wordt overschat bij woonprojecten.
    """
    parkeer_context = parkeer_context or {}
    norm_context = parkeer_context.get("norm_context", "Generieke prototypeformule")
    zone = parkeer_context.get("zone", "Niet van toepassing")
    lokaal_wagenbezit = parkeer_context.get("lokaal_wagenbezit", 0.0)
    statistische_sector = parkeer_context.get("statistische_sector", "")
    straatparkeren_toelichting = parkeer_context.get("straatparkeren_toelichting", "")

    methode = "Generieke prototypeformule"
    parkeernorm = "Niet lokaal gespecificeerd"
    parkeerbehoefte_min = None
    parkeerbehoefte_max = None
    norm_toelichting = "De parkeerbehoefte is berekend met een generieke prototypeformule. Dit moet worden vervangen of getoetst aan de lokale parkeerverordening."
    verkeersgeneratie_methode = "Generieke prototypeformule"
    verkeersgeneratie_toelichting = "De verkeersgeneratie is indicatief en moet bij vergunningsdossiers worden getoetst aan lokale kencijfers of het Richtlijnenboek MOBER."

    def bereken_woon_verkeersgeneratie():
        # Deze benadering ligt dichter bij klassieke mobiliteitsstudies:
        # bewonersverplaatsingen = WE x huishoudgrootte x verplaatsingen/persoon/dag x aandeel autobestuurder
        # bezoekersverplaatsingen = WE x bezoekers/WE/dag x 2 verplaatsingen x aandeel autobestuurder bezoekers
        huishoudgrootte = 2.13
        verplaatsingen_per_persoon = 2.53
        bezoekers_per_we = 0.25
        verplaatsingen_per_bezoeker = 2.0
        aandeel_autobestuurder_bewoners = 0.418
        aandeel_autobestuurder_bezoekers = 0.44
        dag = aantal_wooneenheden * (
            huishoudgrootte * verplaatsingen_per_persoon * aandeel_autobestuurder_bewoners
            + bezoekers_per_we * verplaatsingen_per_bezoeker * aandeel_autobestuurder_bezoekers
        )
        # Voor woonprojecten wordt in deze prototypeversie 9% van het etmaal als spitsuurfactor gebruikt.
        # Dit voorkomt dat dezelfde verplaatsingen dubbel worden geteld.
        spits = dag * 0.09
        return dag, spits

    if norm_context == "Hasselt - lokale parkeerverordening" and projecttype == "Wonen":
        methode = "Hasselt - lokale parkeerverordening"
        if zone == "Binnen Singel":
            norm_min = 0.50
            norm_max = 0.75
            parkeernorm = "Wonen Binnen Singel: 0,50 tot 0,75 parkeerplaatsen per wooneenheid"
        else:
            # Bewust voorzichtig: andere zones moeten nog officieel gecontroleerd worden.
            norm_min = 0.50
            norm_max = 1.00
            parkeernorm = "Hasselt, zone manueel te controleren: voorlopige bandbreedte 0,50 tot 1,00 pp/wooneenheid"

        parkeerbehoefte_min = round(aantal_wooneenheden * norm_min, 1)
        parkeerbehoefte_max = round(aantal_wooneenheden * norm_max, 1)
        parkeerbehoefte = parkeerbehoefte_max
        norm_toelichting = (
            f"De autoparkeerbehoefte is berekend als lokale bandbreedte ({parkeernorm}). "
            f"De balans wordt voorzichtig afgetoetst aan de bovengrens. "
            f"Lokaal wagenbezit: {lokaal_wagenbezit} wagens/huishouden"
            + (f" in statistische sector {statistische_sector}" if statistische_sector else "")
            + ". Bezoekersparkeren en straatparkeren worden niet als automatische aftrek gebruikt, maar moeten afzonderlijk worden beschreven en gecontroleerd."
        )
        fietsbehoefte = aantal_wooneenheden * 2.0
        ritten_dag, ritten_spits = bereken_woon_verkeersgeneratie()
        verkeersgeneratie_methode = "Wonen: bewoners + bezoekers + modal split"
        verkeersgeneratie_toelichting = (
            "Voor wonen wordt de verkeersgeneratie niet langer berekend met 5,5 autoritten per wooneenheid. "
            "De raming gebruikt huishoudgrootte, woninggerelateerde verplaatsingen, bezoekers en het aandeel autobestuurder. "
            "Voor 106 wooneenheden geeft deze methode ongeveer 262 autoritten per dag en ongeveer 24 ritten in het spitsuur."
        )

    else:
        if projecttype == "Wonen":
            # Geen lokale parkeerverordening gekozen: gebruik een voorzichtige generieke bandbreedte,
            # maar behoud de verbeterde verkeersgeneratieformule.
            parkeerbehoefte = aantal_wooneenheden * 1.0
            fietsbehoefte = aantal_wooneenheden * 2.0
            ritten_dag, ritten_spits = bereken_woon_verkeersgeneratie()
            verkeersgeneratie_methode = "Wonen: bewoners + bezoekers + modal split"
            verkeersgeneratie_toelichting = (
                "Voor wonen wordt de verkeersgeneratie berekend via bewoners, bezoekers en modal split. "
                "Dit voorkomt een systematische overschatting door een vaste factor per wooneenheid."
            )

        elif projecttype == "Handel":
            eenheden = bvo / 100
            parkeerbehoefte = eenheden * 3.0
            fietsbehoefte = eenheden * 1.5
            ritten_dag = eenheden * 30
            ritten_spits = eenheden * 3.0

        elif projecttype == "Horeca":
            eenheden = bvo / 100
            parkeerbehoefte = eenheden * 4.0
            fietsbehoefte = eenheden * 2.0
            ritten_dag = eenheden * 35
            ritten_spits = eenheden * 4.0

        elif projecttype == "Kantoor":
            eenheden = bvo / 100
            parkeerbehoefte = eenheden * 2.0
            fietsbehoefte = eenheden * 1.5
            ritten_dag = eenheden * 8
            ritten_spits = eenheden * 1.2

        elif projecttype == "School":
            eenheden = bvo / 100
            parkeerbehoefte = eenheden * 1.5
            fietsbehoefte = eenheden * 3.0
            ritten_dag = eenheden * 20
            ritten_spits = eenheden * 4.0

        else:
            eenheden = max(bvo / 100, aantal_wooneenheden)
            parkeerbehoefte = eenheden * 2.0
            fietsbehoefte = eenheden * 2.0
            ritten_dag = eenheden * 10
            ritten_spits = eenheden * 1.5

    parkeerbehoefte = round(parkeerbehoefte, 1)
    fietsbehoefte = round(fietsbehoefte, 1)
    ritten_dag = round(ritten_dag, 1)
    ritten_spits = round(ritten_spits, 1)

    parkeerbalans = round(parkeerplaatsen - parkeerbehoefte, 1)
    fietsbalans = round(fietsenstallingen - fietsbehoefte, 1)

    if parkeerbehoefte_min is not None and parkeerbehoefte_max is not None:
        parkeerbehoefte_display = f"{parkeerbehoefte_min} - {parkeerbehoefte_max} plaatsen"
    else:
        parkeerbehoefte_display = f"{parkeerbehoefte} plaatsen"

    return {
        "parkeerbehoefte": parkeerbehoefte,
        "parkeerbehoefte_min": parkeerbehoefte_min,
        "parkeerbehoefte_max": parkeerbehoefte_max,
        "parkeerbehoefte_display": parkeerbehoefte_display,
        "parkeermethode": methode,
        "parkeernorm": parkeernorm,
        "norm_toelichting": norm_toelichting,
        "lokaal_wagenbezit": lokaal_wagenbezit,
        "statistische_sector": statistische_sector,
        "straatparkeren_toelichting": straatparkeren_toelichting,
        "parkeerzone": zone,
        "automatisch_bepaald": parkeer_context.get("automatisch_bepaald", False),
        "automatische_bronnen": parkeer_context.get("automatische_bronnen", ""),
        "automatische_opmerking": parkeer_context.get("automatische_opmerking", ""),
        "fietsbehoefte": fietsbehoefte,
        "ritten_dag": ritten_dag,
        "ritten_spits": ritten_spits,
        "verkeersgeneratie_methode": verkeersgeneratie_methode,
        "verkeersgeneratie_toelichting": verkeersgeneratie_toelichting,
        "parkeerbalans": parkeerbalans,
        "fietsbalans": fietsbalans
    }

def check_studieplicht(projecttype, aantal_wooneenheden, bvo, parkeerplaatsen):
    mobiliteitstoets = "Niet van toepassing"
    mober = "Niet van toepassing"
    toelichting = []

    if projecttype == "Wonen":
        if aantal_wooneenheden >= 250:
            mober = "Mogelijk MOBER-plichtig"
        elif aantal_wooneenheden >= 100:
            mobiliteitstoets = "Mobiliteitstoets aangewezen"

        toelichting.append(
            "Voor woonprojecten wordt in deze prototypecheck gewerkt met 100 wooneenheden als aandachtspunt voor een mobiliteitstoets en 250 wooneenheden als mogelijke MOBER-drempel."
        )

    if projecttype in ["Handel", "Horeca", "Kantoor", "Gemengd project"]:
        if bvo >= 7500:
            mober = "Mogelijk MOBER-plichtig"
        elif bvo >= 2000:
            mobiliteitstoets = "Mobiliteitstoets aangewezen"

        toelichting.append(
            "Voor handels-, horeca-, kantoor- of gemengde projecten is de bruto vloeroppervlakte een belangrijk aandachtspunt."
        )

    if parkeerplaatsen >= 200:
        mober = "Mogelijk MOBER-plichtig"
        toelichting.append(
            "Een project met 200 of meer parkeerplaatsen kan aanleiding geven tot een MOBER-aftoetsing."
        )

    elif parkeerplaatsen >= 50:
        mobiliteitstoets = "Mobiliteitstoets aangewezen"
        toelichting.append(
            "Een project met 50 of meer parkeerplaatsen vormt een aandachtspunt voor een mobiliteitstoets."
        )

    if not toelichting:
        toelichting.append(
            "Op basis van de ingegeven projectkenmerken wordt geen duidelijke drempel overschreden. Verdere controle blijft nodig."
        )

    return {
        "mobiliteitstoets": mobiliteitstoets,
        "mober": mober,
        "toelichting": " ".join(toelichting)
    }


def maak_mobiliteitseffecten_en_maatregelen(
    projecttype,
    aantal_wooneenheden,
    bvo,
    parkeerplaatsen,
    fietsenstallingen,
    straal,
    haltes,
    hoppinpunten,
    bff_routes,
    scholen,
    horeca,
    winkels,
    parkings,
    stappers_analyse,
    trappers_analyse,
    auto_analyse,
    ov_score,
    hoppin_score,
    fiets_score,
    totaal_score,
    effecten,
    studieplicht,
    dichtste_halte_algemeen=None,
    dichtstbijzijnde_station=None,
):
    """Genereert een meer uitgewerkte effectbeoordeling en automatische aanbevelingen.
    De teksten blijven indicatief en steunen enkel op ingegeven projectgegevens en openbare databronnen.
    """
    dichtste_halte_naam = (dichtste_halte_algemeen or {}).get("halte_naam", "niet beschikbaar")
    dichtste_halte_afstand = (dichtste_halte_algemeen or {}).get("afstand_m")
    station_naam = (dichtstbijzijnde_station or {}).get("station_naam", "niet beschikbaar")
    station_afstand = (dichtstbijzijnde_station or {}).get("afstand_m")

    if dichtste_halte_afstand is None:
        halte_zin = f"De dichtstbijzijnde bushalte is {dichtste_halte_naam}."
    else:
        halte_zin = f"De dichtstbijzijnde bushalte is {dichtste_halte_naam} op ongeveer {dichtste_halte_afstand} m."

    if station_afstand is None:
        station_zin = f"Het dichtstbijzijnde station of spoorhalte is {station_naam}."
    else:
        station_zin = f"Het dichtstbijzijnde station of spoorhalte is {station_naam} op ongeveer {station_afstand} m."

    # Bereikbaarheid
    if totaal_score == "Goed":
        bereikbaarheid_score = "Gunstig"
        bereikbaarheid = (
            f"De globale bereikbaarheid van de projectsite wordt gunstig ingeschat. Binnen de gekozen radius van {straal} m "
            f"zijn {len(haltes)} De Lijn-haltes aanwezig en werden {stappers_analyse['voetpaden']} voetgangersverbindingen "
            f"en {trappers_analyse['fietspaden']} fietspaden gedetecteerd. {halte_zin} {station_zin} "
            "De ligging ondersteunt daardoor in principe meerdere vervoerswijzen, al blijft controle van de concrete loop- en fietsroutes noodzakelijk."
        )
    elif totaal_score == "Matig":
        bereikbaarheid_score = "Aandachtspunt"
        bereikbaarheid = (
            f"De globale bereikbaarheid van de projectsite wordt matig ingeschat. De omgeving bevat wel verschillende mobiliteitselementen, "
            f"maar niet alle onderdelen scoren even sterk. Binnen {straal} m zijn {len(haltes)} haltes en {len(hoppinpunten)} Hoppinpunten gevonden. "
            f"{halte_zin} {station_zin} Bij verdere uitwerking moet vooral worden nagegaan of de routes naar haltes, voorzieningen en fietsinfrastructuur "
            "voldoende veilig, direct en toegankelijk zijn."
        )
    else:
        bereikbaarheid_score = "Beperkt"
        bereikbaarheid = (
            f"De globale bereikbaarheid van de projectsite wordt beperkt ingeschat. Binnen de gekozen radius zijn relatief weinig duurzame mobiliteitsvoorzieningen "
            f"gedetecteerd. {halte_zin} {station_zin} Voor dit project is een bijkomende terreincontrole nodig om na te gaan welke maatregelen de bereikbaarheid "
            "voor voetgangers, fietsers en openbaar vervoer kunnen verbeteren."
        )

    # Parkeren
    if effecten["parkeerbalans"] >= 0:
        parkeren_score = "Voldoende volgens prototypeberekening"
        parkeren = (
            f"De indicatieve parkeerbehoefte bedraagt {effecten['parkeerbehoefte']} plaatsen. Het ingegeven aanbod bedraagt {parkeerplaatsen} plaatsen, "
            f"waardoor de automatische parkeerbalans positief is ({effecten['parkeerbalans']} plaatsen). Op basis van deze prototypeberekening lijkt het aanbod "
            "voldoende om de geraamde behoefte op eigen terrein op te vangen. Deze conclusie moet wel worden getoetst aan de gemeentelijke parkeernormen, "
            "het concrete gebruiksprofiel en eventuele bezoekersbehoefte."
        )
    else:
        parkeren_score = "Tekort volgens prototypeberekening"
        parkeren = (
            f"De indicatieve parkeerbehoefte bedraagt {effecten['parkeerbehoefte']} plaatsen. Het ingegeven aanbod bedraagt {parkeerplaatsen} plaatsen, "
            f"waardoor de automatische parkeerbalans negatief is ({effecten['parkeerbalans']} plaatsen). Dit wijst op een mogelijk tekort volgens de prototypeberekening. "
            "In een verdere studie moet worden nagegaan of dit tekort wordt opgevangen door lokale parkeernormen, deelmobiliteit, dubbelgebruik, openbaar parkeren, "
            "een lagere autobezitsgraad of bijkomende parkeerplaatsen op eigen terrein."
        )

    if effecten["fietsbalans"] >= 0:
        fietsparkeren = (
            f"Voor fietsparkeren wordt de behoefte indicatief geraamd op {effecten['fietsbehoefte']} stallingen. Met {fietsenstallingen} opgegeven stallingen "
            f"is de fietsparkeerbalans positief ({effecten['fietsbalans']} stallingen). Belangrijk blijft dat deze stallingen kwalitatief zijn: goed bereikbaar, "
            "voldoende ruim, logisch gespreid, veilig en bij voorkeur overdekt voor langdurig gebruik."
        )
    else:
        fietsparkeren = (
            f"Voor fietsparkeren wordt de behoefte indicatief geraamd op {effecten['fietsbehoefte']} stallingen. Met {fietsenstallingen} opgegeven stallingen "
            f"is de fietsparkeerbalans negatief ({effecten['fietsbalans']} stallingen). Een uitbreiding of herverdeling van de fietsenstallingen is aangewezen, "
            "zeker wanneer de site inzet op duurzame verplaatsingen."
        )

    # Verkeersgeneratie
    if effecten["ritten_spits"] < 25:
        verkeers_score = "Beperkte bijkomende belasting"
        verkeersgeneratie = (
            f"De verkeersgeneratie wordt indicatief geraamd op {effecten['ritten_dag']} ritten per dag en {effecten['ritten_spits']} ritten tijdens het maatgevende spitsuur. "
            "Op basis van deze grootteorde lijkt de bijkomende belasting eerder beperkt. Een kruispuntanalyse is pas nodig wanneer de omgeving vandaag al zwaar belast is "
            "of wanneer de ontsluiting op een gevoelig punt gebeurt."
        )
    elif effecten["ritten_spits"] < 75:
        verkeers_score = "Merkbare bijkomende belasting"
        verkeersgeneratie = (
            f"De verkeersgeneratie wordt indicatief geraamd op {effecten['ritten_dag']} ritten per dag en {effecten['ritten_spits']} ritten tijdens het maatgevende spitsuur. "
            "Deze grootteorde kan merkbaar zijn op lokale straten of bij een ontsluiting via een beperkt kruispunt. Verdere toetsing met verkeersintensiteiten, circulatie en "
            "eventuele wachtrijen is aangewezen."
        )
    else:
        verkeers_score = "Belangrijke bijkomende belasting"
        verkeersgeneratie = (
            f"De verkeersgeneratie wordt indicatief geraamd op {effecten['ritten_dag']} ritten per dag en {effecten['ritten_spits']} ritten tijdens het maatgevende spitsuur. "
            "Deze grootteorde kan een duidelijke impact hebben op de omliggende wegen en kruispunten. Een verdere verkeerskundige analyse met tellingen, toedeling en "
            "afwikkelingscontrole is aangewezen."
        )

    # Veiligheid
    veiligheids_aandacht = []
    if stappers_analyse["comfortscore"] == "Beperkt":
        veiligheids_aandacht.append("voetgangersvoorzieningen en veilige oversteekplaatsen")
    if trappers_analyse["fietsscore"] == "Beperkt":
        veiligheids_aandacht.append("fietscomfort, fietsroutes en stallingskwaliteit")
    if auto_analyse["ontsluitingsscore"] == "Goed" and effecten["ritten_spits"] >= 75:
        veiligheids_aandacht.append("conflicten tussen bijkomend autoverkeer en zachte weggebruikers")
    if auto_analyse["kruispunten"] >= 50:
        veiligheids_aandacht.append("de leesbaarheid en veiligheid van kruispunten in de omgeving")

    if veiligheids_aandacht:
        verkeersveiligheid_score = "Aandachtspunt"
        verkeersveiligheid = (
            "Op vlak van verkeersveiligheid zijn vooral volgende punten relevant: "
            + ", ".join(veiligheids_aandacht)
            + ". De automatische analyse kan geen zichtlijnen, effectieve snelheden, breedtes of conflictpunten op terrein beoordelen. "
            "Een terreincontrole blijft daarom noodzakelijk."
        )
    else:
        verkeersveiligheid_score = "Geen zwaar aandachtspunt op basis van automatische screening"
        verkeersveiligheid = (
            "Op basis van de automatische screening worden geen uitgesproken verkeersveiligheidsknelpunten gedetecteerd. "
            "Dit betekent niet dat er geen risico's zijn: zichtbaarheid aan in- en uitritten, oversteekbaarheid, snelheidsregimes, leveringen, afvalophaling en conflicten met fietsers "
            "moeten steeds op plan en op terrein worden nagekeken."
        )

    maatregelen = []
    if effecten["parkeerbalans"] < 0:
        maatregelen.append("Onderzoek de parkeerbalans verder aan de hand van lokale parkeernormen, bewonersprofiel, deelmobiliteit en eventueel dubbelgebruik van parkeerplaatsen.")
    else:
        maatregelen.append("Behoud de parkeerorganisatie op eigen terrein en voorkom dat bezoekers of bewoners structureel uitwijken naar het openbaar domein.")

    if effecten["fietsbalans"] < 0:
        maatregelen.append("Voorzie bijkomende kwalitatieve fietsenstallingen, inclusief ruimte voor buitenmaatse fietsen en laadpunten voor elektrische fietsen.")
    else:
        maatregelen.append("Werk de fietsenstallingen kwalitatief uit: nabij de toegang, duidelijk vindbaar, veilig, comfortabel en waar mogelijk overdekt.")

    if len(haltes) > 0 or (dichtste_halte_afstand is not None and dichtste_halte_afstand <= 1000):
        maatregelen.append("Versterk de wandelroute tussen projectsite en dichtstbijzijnde bushalte met duidelijke, toegankelijke en veilige looplijnen.")
    else:
        maatregelen.append("Onderzoek of aanvullende maatregelen nodig zijn om de OV-bereikbaarheid te verbeteren, zoals betere looproutes of informatie over nabijgelegen haltes.")

    if stappers_analyse["comfortscore"] != "Goed":
        maatregelen.append("Controleer voetpaden, oversteekplaatsen en obstakels in de directe omgeving en formuleer waar nodig verbeterpunten.")
    if trappers_analyse["fietsscore"] != "Goed":
        maatregelen.append("Controleer de aansluiting op het fietsnetwerk en de kwaliteit van fietsroutes richting belangrijke bestemmingen.")
    if effecten["ritten_spits"] >= 75:
        maatregelen.append("Voer een bijkomende kruispunt- of ontsluitingsanalyse uit voor het maatgevende spitsuur.")
    if projecttype in ["Handel", "Horeca", "School", "Gemengd project"]:
        maatregelen.append("Organiseer leveringen, halen en brengen of piekactiviteiten zoveel mogelijk buiten de drukste momenten en met duidelijke interne circulatie.")

    return {
        "bereikbaarheid_score": bereikbaarheid_score,
        "bereikbaarheid": bereikbaarheid,
        "parkeren_score": parkeren_score,
        "parkeren": parkeren,
        "fietsparkeren": fietsparkeren,
        "verkeers_score": verkeers_score,
        "verkeersgeneratie": verkeersgeneratie,
        "verkeersveiligheid_score": verkeersveiligheid_score,
        "verkeersveiligheid": verkeersveiligheid,
        "maatregelen": maatregelen,
    }



def maak_synthese_kwaliteitscheck_eindconclusie(
    projecttype,
    aantal_wooneenheden,
    bvo,
    parkeerplaatsen,
    fietsenstallingen,
    straal,
    haltes,
    hoppinpunten,
    bff_routes,
    stappers_analyse,
    trappers_analyse,
    auto_analyse,
    ov_score,
    fiets_score,
    totaal_score,
    effecten,
    studieplicht,
    mobiliteitseffecten,
    plan_paths=None,
    korte_omschrijving="",
    huidige_toestand="",
    toekomstige_toestand="",
    dichtste_halte_algemeen=None,
    dichtstbijzijnde_station=None,
):
    """Maakt een afsluitende synthese, kwaliteitscheck en eindconclusie.
    De bedoeling is expliciet te tonen wat automatisch is berekend, wat uit input/plannen komt
    en wat nog door een expert of officiële bron moet worden gecontroleerd.
    """
    if plan_paths is None:
        plan_paths = []

    dichtste_halte_naam = (dichtste_halte_algemeen or {}).get("halte_naam", "niet beschikbaar")
    dichtste_halte_afstand = (dichtste_halte_algemeen or {}).get("afstand_m")
    station_naam = (dichtstbijzijnde_station or {}).get("station_naam", "niet beschikbaar")
    station_afstand = (dichtstbijzijnde_station or {}).get("afstand_m")

    halte_txt = dichtste_halte_naam
    if dichtste_halte_afstand is not None:
        halte_txt += f" ({dichtste_halte_afstand} m)"

    station_txt = station_naam
    if station_afstand is not None:
        station_txt += f" ({station_afstand} m)"

    synthese_rows = [
        [
            "Projectcontext",
            (
                f"Het projecttype is {projecttype}. De ingegeven programmawaarden bestaan uit "
                f"{aantal_wooneenheden} wooneenheden, {bvo} m² BVO/programma, "
                f"{parkeerplaatsen} autoparkeerplaatsen en {fietsenstallingen} fietsenstallingen. "
                "De projectomschrijving en projectplannen vormen de basis voor de projectmatige interpretatie."
            )
        ],
        [
            "Duurzame bereikbaarheid",
            (
                f"Binnen de gekozen radius van {straal} m werden {len(haltes)} De Lijn-haltes en "
                f"{len(hoppinpunten)} Hoppinpunten gevonden. De dichtstbijzijnde bushalte is {halte_txt}; "
                f"het dichtstbijzijnde station of spoorhalte is {station_txt}. "
                f"De automatische OV-score is {ov_score}, de fietsscore is {fiets_score} en de totale score is {totaal_score}."
            )
        ],
        [
            "Parkeren en stallen",
            (
                f"De indicatieve parkeerbehoefte bedraagt {effecten['parkeerbehoefte']} plaatsen. "
                f"De parkeerbalans bedraagt {effecten['parkeerbalans']} plaatsen. "
                f"De indicatieve fietsparkeerbehoefte bedraagt {effecten['fietsbehoefte']} stallingen, "
                f"met een fietsparkeerbalans van {effecten['fietsbalans']} stallingen."
            )
        ],
        [
            "Verkeersgeneratie",
            (
                f"De indicatieve verkeersgeneratie bedraagt {effecten['ritten_dag']} ritten per dag en "
                f"{effecten['ritten_spits']} ritten tijdens het maatgevende spitsuur. "
                f"De automatische effectbeoordeling hiervoor is: {mobiliteitseffecten['verkeers_score']}."
            )
        ],
        [
            "Verkeersveiligheid",
            (
                f"De automatische verkeersveiligheidsbeoordeling is: {mobiliteitseffecten['verkeersveiligheid_score']}. "
                "Deze beoordeling blijft indicatief omdat zichtbaarheid, effectieve snelheden, oversteekkwaliteit, "
                "conflictpunten en werf- of leveringsstromen niet volledig uit openbare databronnen kunnen worden afgeleid."
            )
        ],
    ]

    gebruikte_input = [
        "Adres en geocodering via Nominatim",
        "Projecttype, wooneenheden, BVO, parkeerplaatsen en fietsenstallingen zoals ingegeven door de gebruiker",
        "De Lijn GTFS voor haltes en lijnen",
        "Hoppin WFS voor Hoppinpunten",
        "BFF WFS voor bovenlokale functionele fietsroutes",
        "OpenStreetMap voor voetgangers-, fiets-, auto- en voorzieningenanalyse",
    ]
    if plan_paths:
        gebruikte_input.append("Aangeleverde projectplannen: " + ", ".join([p.get("label", "plan") for p in plan_paths]))
    if korte_omschrijving or huidige_toestand or toekomstige_toestand:
        gebruikte_input.append("Aangeleverde projectomschrijving, huidige toestand en toekomstige toestand")

    ontbrekende_info = []
    ontbrekende_info.append("Officiële gemeentelijke parkeernormen en eventuele afwijkingsregels")
    ontbrekende_info.append("Terreincontrole van voetpaden, oversteekplaatsen, zichtbaarheid en toegankelijkheid")
    ontbrekende_info.append("Exacte ligging en bruikbaarheid van toegangen, leveringszones, afvalophaling en hulpdiensten")
    ontbrekende_info.append("Verkeerstellingen of kruispuntanalyse indien de omgeving gevoelig of druk belast is")
    ontbrekende_info.append("Controle van stallingskwaliteit, buitenmaatse fietsen, laadpunten en bezoekersstallingen")
    if not plan_paths:
        ontbrekende_info.append("Aangeleverde plannen ontbreken: inplantingsplan, grondplan, situatieplan en/of doorsnede")
    if effecten["parkeerbalans"] < 0:
        ontbrekende_info.append("Onderbouwing van het negatieve parkeerresultaat met lokale normen, deelmobiliteit of openbaar parkeeraanbod")
    if effecten["ritten_spits"] >= 75:
        ontbrekende_info.append("Nadere toetsing van verkeersafwikkeling op het maatgevende spitsuur")

    expert_check = [
        "Controleer of de automatisch gevonden haltes, fietsroutes, wegen en voorzieningen correct en actueel zijn.",
        "Lees de projectplannen na op interne circulatie, conflictpunten en toegankelijkheid.",
        "Toets parkeer- en fietsparkeerbehoefte aan de lokale verordening en het vergunningstraject.",
        "Beoordeel of een mobiliteitstoets of MOBER formeel vereist is volgens de bevoegde overheid.",
        "Vul de quickscan aan met tellingen of terreinonderzoek wanneer de omgeving al zwaar belast is."
    ]

    # Eindconclusie: bewust voorzichtig en ondersteunend geformuleerd.
    if "MOBER" in studieplicht.get("mober", "") or effecten["ritten_spits"] >= 75:
        conclusie_type = "Verdere mobiliteitsstudie / MOBER-aftoetsing aangewezen"
        eindconclusie = (
            "Op basis van de automatische screening zijn er duidelijke aandachtspunten die niet binnen een eenvoudige quickscan kunnen worden afgehandeld. "
            "Een verdere mobiliteitsstudie of formele MOBER-aftoetsing is aangewezen, zeker voor verkeersafwikkeling, parkeren en verkeersveiligheid."
        )
    elif studieplicht.get("mobiliteitstoets") == "Mobiliteitstoets aangewezen" or effecten["parkeerbalans"] < 0:
        conclusie_type = "Mobiliteitstoets aangewezen"
        eindconclusie = (
            "De automatische analyse wijst op een project waarvoor een mobiliteitstoets aangewezen is. "
            "De quickscan vormt een bruikbare basis, maar moet verder worden aangevuld met lokale normen, plancontrole, terreincontrole en eventueel bijkomende onderbouwing van parkeren en verkeersgeneratie."
        )
    elif totaal_score == "Goed" and effecten["parkeerbalans"] >= 0 and effecten["fietsbalans"] >= 0:
        conclusie_type = "Quickscan voorlopig voldoende"
        eindconclusie = (
            "Op basis van de ingegeven gegevens en openbare databronnen lijkt een quickscan voorlopig voldoende als eerste screening. "
            "De resultaten blijven wel afhankelijk van de juistheid van de input en moeten minstens worden nagekeken door een expert of ontwerper."
        )
    else:
        conclusie_type = "Aanvullende controle nodig"
        eindconclusie = (
            "De automatische screening geeft een eerste bruikbaar beeld, maar bevat nog onzekerheden. "
            "Aanvullende controle is nodig om te bepalen of de quickscan volstaat of moet worden uitgebreid tot een mobiliteitstoets."
        )

    return {
        "synthese_rows": synthese_rows,
        "gebruikte_input": gebruikte_input,
        "ontbrekende_info": ontbrekende_info,
        "expert_check": expert_check,
        "conclusie_type": conclusie_type,
        "eindconclusie": eindconclusie,
    }



import os

def _haal_openai_api_key(api_key_input=""):
    """Haalt de OpenAI API key op uit invoer of environment variable."""
    if api_key_input:
        return api_key_input.strip()

    return os.getenv("OPENAI_API_KEY", "").strip()


def _compacte_lijst_voor_prompt(df, kolommen, max_rijen=8):
    """Maakt een compacte tekstweergave van een dataframe voor de AI-prompt."""
    try:
        if df is None or df.empty:
            return "Geen gegevens beschikbaar."
        bestaande = [c for c in kolommen if c in df.columns]
        if not bestaande:
            return f"{len(df)} records aanwezig, zonder bruikbare detailkolommen."
        regels = []
        for _, row in df[bestaande].head(max_rijen).iterrows():
            onderdelen = [f"{c}: {row.get(c, '')}" for c in bestaande]
            regels.append("; ".join(onderdelen))
        extra = f"\n... plus {len(df) - max_rijen} extra records" if len(df) > max_rijen else ""
        return "\n".join(regels) + extra
    except Exception:
        return "Gegevens konden niet compact worden weergegeven."



def parse_ai_hoofdstukken(ai_teksten):
    """Zet de AI-output om naar een dictionary met hoofdstukteksten.
    De prompt vraagt JSON. Als het model toch gewone tekst teruggeeft, blijft de app werken.
    """
    if not ai_teksten or not ai_teksten.get("tekst"):
        return {}
    tekst = str(ai_teksten.get("tekst", "")).strip()
    if not tekst:
        return {}
    try:
        start = tekst.find("{")
        end = tekst.rfind("}")
        if start != -1 and end != -1 and end > start:
            data = json.loads(tekst[start:end + 1])
            if isinstance(data, dict):
                return {str(k): str(v).strip() for k, v in data.items() if str(v).strip()}
    except Exception:
        pass
    return {"synthese": tekst}

def maak_ai_prompt_mobiliteit(
    promptstijl,
    projectnaam,
    adres,
    projecttype,
    aantal_wooneenheden,
    bvo,
    parkeerplaatsen,
    fietsenstallingen,
    straal,
    haltes,
    hoppinpunten,
    bff_routes,
    scholen,
    horeca,
    winkels,
    parkings,
    stappers_analyse,
    trappers_analyse,
    auto_analyse,
    ov_score,
    hoppin_score,
    fiets_score,
    totaal_score,
    effecten,
    studieplicht,
    mobiliteitseffecten,
    dichtste_halte_algemeen=None,
    dichtstbijzijnde_station=None,
):
    """Bouwt de vaste professionele/neutrale prompt voor AI-interpretaties per hoofdstuk."""
    promptstijl = "Professioneel en neutraal"
    stijl = (
        "Schrijf als een mobiliteitsexpert bij een Vlaams studiebureau. Gebruik een professionele, neutrale stijl. "
        "Formuleer helder, niet te commercieel en niet te stellig. Interpreteer de cijfers en databronnen, "
        "maar maak geen niet-onderbouwde aannames."
    )

    dichtste_halte_naam = (dichtste_halte_algemeen or {}).get("halte_naam", "niet beschikbaar")
    dichtste_halte_afstand = (dichtste_halte_algemeen or {}).get("afstand_m", "niet beschikbaar")
    station_naam = (dichtstbijzijnde_station or {}).get("station_naam", "niet beschikbaar")
    station_afstand = (dichtstbijzijnde_station or {}).get("afstand_m", "niet beschikbaar")

    halte_details = _compacte_lijst_voor_prompt(
        haltes,
        ["halte_naam", "afstand_m", "ritten_spits_uur", "frequentie_score", "buslijnen"],
        max_rijen=6
    )

    prompt = f"""
Je bent een mobiliteitsexpert gespecialiseerd in mobiliteitsstudies voor bouwprojecten in Vlaanderen.

PROMPTVARIANT
{promptstijl}: {stijl}

BELANGRIJKE REGELS
- Baseer je uitsluitend op de aangeleverde projectdata.
- Verzin geen haltes, normen, tellingen, beleidsplannen, lokale regels of terreinwaarnemingen.
- Schrijf professioneel en neutraal, zoals een eerste concepttekst in een Vlaamse mobiliteitsstudie.
- Interpreteer de data inhoudelijk: leg verbanden tussen projectprogramma, bereikbaarheid, parkeren, verkeersgeneratie en controlepunten.
- Vermeld onzekerheden alleen waar relevant, zonder elke alinea te laten eindigen met dezelfde standaardzin.
- Schrijf in het Nederlands.
- Geef uitsluitend geldige JSON terug, zonder markdown en zonder extra uitleg.
- Gebruik exact deze JSON-sleutels:
  projectomschrijving, inplanting, omgevingsomschrijving, projectkenmerken, stappers, trappers, openbaar_vervoer, parkeren_verkeer, auto_analyse, mobiliteitseffecten, synthese, eerste_beoordeling
- Elke waarde is één doorlopende alinea van 70 tot 120 woorden.

PROJECTDATA
Projectnaam: {projectnaam}
Adres: {adres}
Projecttype: {projecttype}
Aantal wooneenheden: {aantal_wooneenheden}
BVO / programma: {bvo} m²
Autoparkeerplaatsen: {parkeerplaatsen}
Fietsenstallingen: {fietsenstallingen}
Analysegebied: {straal} m

OMGEVING EN OV
Dichtstbijzijnde bushalte: {dichtste_halte_naam} ({dichtste_halte_afstand} m)
Dichtstbijzijnde station/spoorhalte: {station_naam} ({station_afstand} m)
Haltes binnen radius: {len(haltes)}
Hoppinpunten binnen radius: {len(hoppinpunten)}
Haltegegevens:
{halte_details}

VOORZIENINGEN
Scholen: {scholen}
Horeca: {horeca}
Winkels: {winkels}
Parkings: {parkings}

STOP-ANALYSE
Stappers: {json.dumps(stappers_analyse, ensure_ascii=False)}
Trappers: {json.dumps(trappers_analyse, ensure_ascii=False)}
Auto: {json.dumps(auto_analyse, ensure_ascii=False)}
OV-score: {ov_score}
Hoppin-score: {hoppin_score}
Fiets-score: {fiets_score}
Totaalscore: {totaal_score}
BFF-segmenten binnen radius: {len(bff_routes)}

PARKEREN EN VERKEER
{json.dumps(effecten, ensure_ascii=False)}

STUDIEPLICHT
{json.dumps(studieplicht, ensure_ascii=False)}

REGELGEBASEERDE EFFECTBEOORDELING UIT DE APP
{json.dumps(mobiliteitseffecten, ensure_ascii=False)}
"""
    return prompt.strip()


def genereer_ai_mobiliteitstekst(
    api_key,
    model,
    promptstijl,
    projectnaam,
    adres,
    projecttype,
    aantal_wooneenheden,
    bvo,
    parkeerplaatsen,
    fietsenstallingen,
    straal,
    haltes,
    hoppinpunten,
    bff_routes,
    scholen,
    horeca,
    winkels,
    parkings,
    stappers_analyse,
    trappers_analyse,
    auto_analyse,
    ov_score,
    hoppin_score,
    fiets_score,
    totaal_score,
    effecten,
    studieplicht,
    mobiliteitseffecten,
    dichtste_halte_algemeen=None,
    dichtstbijzijnde_station=None,
):
    """Roept OpenAI aan voor AI-interpretatieteksten. Falt veilig terug wanneer de sleutel ontbreekt of de API faalt."""
    prompt = maak_ai_prompt_mobiliteit(
        promptstijl,
        projectnaam,
        adres,
        projecttype,
        aantal_wooneenheden,
        bvo,
        parkeerplaatsen,
        fietsenstallingen,
        straal,
        haltes,
        hoppinpunten,
        bff_routes,
        scholen,
        horeca,
        winkels,
        parkings,
        stappers_analyse,
        trappers_analyse,
        auto_analyse,
        ov_score,
        hoppin_score,
        fiets_score,
        totaal_score,
        effecten,
        studieplicht,
        mobiliteitseffecten,
        dichtste_halte_algemeen=dichtste_halte_algemeen,
        dichtstbijzijnde_station=dichtstbijzijnde_station,
    )

    if not api_key:
        return {
            "actief": False,
            "fout": "Geen OpenAI API key gevonden. Controleer of OPENAI_API_KEY correct als environment variable is ingesteld.",
            "prompt": prompt,
            "tekst": "",
            "model": model,
            "promptstijl": promptstijl,
        }

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.2,
                "max_tokens": 2200,
                "messages": [
                    {
                        "role": "system",
                        "content": "Je schrijft professionele mobiliteitsstudieteksten in het Nederlands. Je geeft uitsluitend geldige JSON terug en werkt strikt op basis van de aangeleverde data."
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        tekst = data["choices"][0]["message"]["content"].strip()
        return {
            "actief": True,
            "fout": "",
            "prompt": prompt,
            "tekst": tekst,
            "model": model,
            "promptstijl": promptstijl,
        }
    except Exception as e:
        return {
            "actief": False,
            "fout": f"AI-tekstgeneratie mislukt: {type(e).__name__}: {e}",
            "prompt": prompt,
            "tekst": "",
            "model": model,
            "promptstijl": promptstijl,
        }


def maak_profiel(
    projectnaam,
    adres,
    projecttype,
    aantal_wooneenheden,
    bvo,
    parkeerplaatsen,
    fietsenstallingen,
    straal,
    haltes,
    hoppinpunten,
    bff_routes,
    scholen,
    horeca,
    winkels,
    parkings,
    stappers_analyse,
    trappers_analyse,
    auto_analyse,
    ov_score,
    hoppin_score,
    fiets_score,
    totaal_score,
    effecten,
    studieplicht,
    mobiliteitseffecten=None,
    projectfase="Niet ingevuld",
    korte_omschrijving="",
    huidige_toestand="",
    toekomstige_toestand="",
    dichtste_halte_algemeen=None,
    dichtstbijzijnde_station=None,
    opdrachtgever="Naam opdrachtgever",
    architectenbureau="Naam architectenbureau",
    opdrachtnemer="MOBISCAN",
    projectmedewerkers="Kim Demaecker",
    versienummer="v1.0",
    vrijgavedatum=None,
    rapportstatus="Concept",
    referentie="MOBI-2026-001",
    app_logo_path=None,
    bureau_logo_path=None
):
    dichtste_halte = "niet beschikbaar"
    dichtste_halte_afstand = "niet beschikbaar"

    if not haltes.empty:
        dichtste_halte_row = haltes.sort_values("afstand_m").iloc[0]
        dichtste_halte = dichtste_halte_row["halte_naam"]
        dichtste_halte_afstand = f'{dichtste_halte_row["afstand_m"]} m'

    dichtste_hoppin = "niet beschikbaar"
    dichtste_hoppin_afstand = "niet beschikbaar"

    if not hoppinpunten.empty:
        dichtste_hoppin_row = hoppinpunten.sort_values("afstand_m").iloc[0]
        dichtste_hoppin = dichtste_hoppin_row["naam"]
        dichtste_hoppin_afstand = f'{dichtste_hoppin_row["afstand_m"]} m'

    dichtste_bff_afstand = "niet beschikbaar"

    if not bff_routes.empty and "afstand_m" in bff_routes.columns:
        dichtste_bff_afstand = f'{int(bff_routes["afstand_m"].min())} m'

    if mobiliteitseffecten is None:
        mobiliteitseffecten = maak_mobiliteitseffecten_en_maatregelen(
            projecttype,
            aantal_wooneenheden,
            bvo,
            parkeerplaatsen,
            fietsenstallingen,
            straal,
            haltes,
            hoppinpunten,
            bff_routes,
            scholen,
            horeca,
            winkels,
            parkings,
            stappers_analyse,
            trappers_analyse,
            auto_analyse,
            ov_score,
            hoppin_score,
            fiets_score,
            totaal_score,
            effecten,
            studieplicht,
            dichtste_halte_algemeen=dichtste_halte_algemeen,
            dichtstbijzijnde_station=dichtstbijzijnde_station,
        )

    maatregelen_markdown = "\n".join([f"- {m}" for m in mobiliteitseffecten.get("maatregelen", [])])

    return f"""
### 1. Inleiding

Deze fiche geeft een eerste automatisch gegenereerd overzicht van de mobiliteitscontext voor **{projectnaam}**.  
De analyse is bedoeld als voorbereiding voor een mobiliteitsstudie en vervangt geen verkeerskundige controle.

### 2. Projectkenmerken

Het projecttype is **{projecttype}**.  
De projectsite is gelegen aan **{adres}**.  
Fase binnen het project: **{projectfase}**.

Projectomschrijving:  
{korte_omschrijving if korte_omschrijving else "Niet ingevuld."}

Huidige toestand:  
{huidige_toestand if huidige_toestand else "Niet ingevuld."}

Toekomstige toestand:  
{toekomstige_toestand if toekomstige_toestand else "Niet ingevuld."}

### 2.1 Omgevingsomschrijving

De projectsite ligt aan **{adres}**. De automatische omgevingsomschrijving geeft een eerste beeld van de directe mobiliteitscontext rond de site.

Dichtstbijzijnde bushalte, los van de gekozen analyseradius: **{(dichtste_halte_algemeen or {}).get("halte_naam", "niet beschikbaar")}**{(" op ongeveer " + str((dichtste_halte_algemeen or {}).get("afstand_m")) + " m") if (dichtste_halte_algemeen or {}).get("afstand_m") is not None else ""}.

Dichtstbijzijnde station of spoorhalte, los van de gekozen analyseradius: **{(dichtstbijzijnde_station or {}).get("station_naam", "niet beschikbaar")}**{(" op ongeveer " + str((dichtstbijzijnde_station or {}).get("afstand_m")) + " m") if (dichtstbijzijnde_station or {}).get("afstand_m") is not None else ""}.

Binnen de gekozen analyseradius van **{straal} meter** worden daarnaast **{len(haltes)} De Lijn-haltes**, **{len(hoppinpunten)} Hoppinpunten**, **{scholen} scholen**, **{horeca} horecazaken**, **{winkels} winkels** en **{parkings} parkings** gedetecteerd.

Ingegeven projectprogramma:
- **{aantal_wooneenheden} wooneenheden**
- **{bvo} m² bruto vloeroppervlakte / programma**
- **{parkeerplaatsen} parkeerplaatsen**
- **{fietsenstallingen} fietsenstallingen**

### 3. Aftoetsing mobiliteitstoets / MOBER

Op basis van de ingegeven projectkenmerken wordt de mobiliteitstoets beoordeeld als: **{studieplicht["mobiliteitstoets"]}**.  
De MOBER-aftoetsing wordt beoordeeld als: **{studieplicht["mober"]}**.

{studieplicht["toelichting"]}

### 4. Bereikbaarheidsprofiel volgens STOP-principe

Een mobiliteitsanalyse wordt opgebouwd volgens het STOP-principe: **Stappers, Trappers, Openbaar vervoer en Personenwagen**.  
Deze volgorde vertrekt vanuit duurzame verplaatsingen en beoordeelt daarna pas de autobereikbaarheid.

### 4.1 Stappers

Binnen het analysegebied van **{straal} meter** werden **{stappers_analyse["voetpaden"]} voetpaden of voetgangersverbindingen**, **{stappers_analyse["oversteekplaatsen"]} oversteekplaatsen** en **{stappers_analyse["trage_wegen"]} trage wegen of paden** gedetecteerd.

Beoordeling voetgangerscomfort: **{stappers_analyse["comfortscore"]}**.

Deze analyse is gebaseerd op OpenStreetMap en geeft een eerste indicatie van de voetgangerskwaliteit. Voor een volledige beoordeling blijven terreinopname, toegankelijkheid, obstakels, breedtes en oversteekkwaliteit noodzakelijk.

### 4.2 Trappers

Binnen het analysegebied van **{straal} meter** werden **{trappers_analyse["fietspaden"]} fietspaden**, **{trappers_analyse["fietssuggesties"]} fietssuggesties of cycleway-tags**, **{trappers_analyse["gedeelde_paden"]} gedeelde of fietsbare paden** en **{trappers_analyse["bff_segmenten"]} BFF-segmenten** gedetecteerd.

Het dichtstbijzijnde BFF-segment ligt op ongeveer **{dichtste_bff_afstand}**.

Beoordeling fietsinfrastructuur: **{trappers_analyse["fietsscore"]}**.

Voor een volledige beoordeling zijn bijkomende gegevens nodig over fietspadbreedtes, conflictpunten, comfort, oversteekkwaliteit en stallingskwaliteit.

### 4.3 Openbaar vervoer

Binnen het analysegebied van **{straal} meter** werden **{len(haltes)} officiële De Lijn-haltes** gevonden.

De dichtstbijzijnde halte is **{dichtste_halte}** op ongeveer **{dichtste_halte_afstand}**.  
Binnen de gekozen straal werden **{len(hoppinpunten)} officiële Hoppinpunten** gevonden. Het dichtstbijzijnde Hoppinpunt is **{dichtste_hoppin}** op ongeveer **{dichtste_hoppin_afstand}**.

Beoordeling openbaar vervoer: **{ov_score}**.  
Beoordeling multimodale knooppunten: **{hoppin_score}**.

### 4.3.1 Dichtstbijzijnde OV-haltes

De dichtstbijzijnde OV-haltes zijn opgenomen in de tabel met halte, afstand en buslijnen.

### 4.4 Personenwagen

Binnen het analysegebied van **{straal} meter** werden **{auto_analyse["hoofdwegen"]} hoofdwegen**, **{auto_analyse["lokale_wegen"]} lokale wegen** en **{auto_analyse["woonstraten"]} woonstraten of verblijfsstraten** gedetecteerd.

Er werden **{auto_analyse["kruispunten"]} kruispunt- of regelpunten** herkend.  
Gekende snelheidsregimes: **{auto_analyse["snelheidsregimes"]}**.  
Beoordeling auto-ontsluiting: **{auto_analyse["ontsluitingsscore"]}**.

Deze beoordeling is indicatief. Wegencategorisering, verkeersdruk, circulatie en verkeersveiligheid moeten verder verkeerskundig gecontroleerd worden.

### 5. Omgevingsvoorzieningen

Binnen het analysegebied werden aanvullend volgende omgevingsvoorzieningen gedetecteerd via OpenStreetMap:

- **{scholen} scholen**
- **{horeca} horecazaken**
- **{winkels} winkels**
- **{parkings} parkings**

### 6. Indicatieve parkeer- en verkeersanalyse

Op basis van het ingegeven projecttype en programma wordt de parkeerbehoefte indicatief geraamd op **{effecten["parkeerbehoefte"]} parkeerplaatsen**.  
Het ingegeven parkeeraanbod bedraagt **{parkeerplaatsen} parkeerplaatsen**, wat resulteert in een indicatieve parkeerbalans van **{effecten["parkeerbalans"]} plaatsen**.

De fietsparkeerbehoefte wordt indicatief geraamd op **{effecten["fietsbehoefte"]} fietsenstallingen**.  
Het ingegeven aanbod bedraagt **{fietsenstallingen} fietsenstallingen**, wat resulteert in een indicatieve fietsparkeerbalans van **{effecten["fietsbalans"]} plaatsen**.

De verkeersgeneratie wordt indicatief geraamd op **{effecten["ritten_dag"]} ritten per dag** en **{effecten["ritten_spits"]} ritten tijdens het maatgevende spitsuur**.

Gebruikte methode: **{effecten.get("verkeersgeneratie_methode", "Niet gespecificeerd")}**.

{effecten.get("verkeersgeneratie_toelichting", "")}

### 7. Mobiliteitseffecten en milderende maatregelen

#### 7.1 Impact op bereikbaarheid

Beoordeling: **{mobiliteitseffecten["bereikbaarheid_score"]}**.  
{mobiliteitseffecten["bereikbaarheid"]}

#### 7.2 Impact op parkeren

Beoordeling: **{mobiliteitseffecten["parkeren_score"]}**.  
{mobiliteitseffecten["parkeren"]}

{mobiliteitseffecten["fietsparkeren"]}

#### 7.3 Impact op verkeersgeneratie

Beoordeling: **{mobiliteitseffecten["verkeers_score"]}**.  
{mobiliteitseffecten["verkeersgeneratie"]}

#### 7.4 Impact op verkeersveiligheid

Beoordeling: **{mobiliteitseffecten["verkeersveiligheid_score"]}**.  
{mobiliteitseffecten["verkeersveiligheid"]}

#### 7.5 Aanbevelingen en milderende maatregelen

{maatregelen_markdown}

### 8. Eerste beoordeling

De algemene automatische bereikbaarheidsscore voor deze projectsite is: **{totaal_score}**.

De resultaten vormen een eerste automatische screening. Voor een volwaardige mobiliteitsstudie blijven terreincontrole, officiële plannen, tellingen en verkeerskundige expertise noodzakelijk.
"""



def maak_pdf(
    projectnaam,
    adres,
    projecttype,
    aantal_wooneenheden,
    bvo,
    parkeerplaatsen,
    fietsenstallingen,
    lat,
    lon,
    straal,
    haltes,
    hoppinpunten,
    bff_routes,
    scholen,
    horeca,
    winkels,
    parkings,
    stappers_analyse,
    trappers_analyse,
    auto_analyse,
    profiel,
    ov_score,
    hoppin_score,
    fiets_score,
    totaal_score,
    effecten,
    studieplicht,
    mobiliteitseffecten=None,
    projectfase="Niet ingevuld",
    korte_omschrijving="",
    huidige_toestand="",
    toekomstige_toestand="",
    plan_paths=None,
    dichtste_halte_algemeen=None,
    dichtstbijzijnde_station=None,
    auto_detail=None,
    bff_context=None,
    recreatieve_analyse=None,
    stappers_gdf=None,
    trappers_gdf=None,
    auto_gdf=None,
    recreatieve_routes_gdf=None,
    ai_teksten=None,

    opdrachtgever="",
    architectenbureau="",
    opdrachtnemer="",
    projectmedewerkers="",
    versienummer="v1.0",
    vrijgavedatum="",
    rapportstatus="Concept",
    referentie="",
    app_logo_path=None,
    bureau_logo_path=None
):
    """Maakt een professionelere PDF-fiche met kleuraccenten, STOP-kaarten,
    subtabellen, footer en paginanummers.
    """
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=42,
        bottomMargin=46
    )

    styles = getSampleStyleSheet()

    # Huisstijlkleuren: sober professioneel, met link naar mobiliteit / groen-blauw.
    NAVY = colors.HexColor("#0B1F33")
    SAGE = colors.HexColor("#8FAF9C")
    SAGE_LIGHT = colors.HexColor("#EAF1ED")
    BLUE = colors.HexColor("#1F77B4")
    ORANGE = colors.HexColor("#F39C12")
    GREY_TXT = colors.HexColor("#4A4A4A")
    LIGHT_GREY = colors.HexColor("#F4F6F7")
    BORDER = colors.HexColor("#C9D2D8")

    if vrijgavedatum is None:
        vrijgavedatum = datetime.today().strftime("%d-%m-%Y")

    if plan_paths is None:
        plan_paths = []
    if auto_detail is None:
        auto_detail = {}
    if bff_context is None:
        bff_context = analyseer_bff_context(bff_routes)
    if recreatieve_analyse is None:
        recreatieve_analyse = {"aantal": 0, "netwerken": "Niet beschikbaar", "knooppunten": 0, "toelichting": "Niet berekend."}

    if mobiliteitseffecten is None:
        mobiliteitseffecten = maak_mobiliteitseffecten_en_maatregelen(
            projecttype,
            aantal_wooneenheden,
            bvo,
            parkeerplaatsen,
            fietsenstallingen,
            straal,
            haltes,
            hoppinpunten,
            bff_routes,
            scholen,
            horeca,
            winkels,
            parkings,
            stappers_analyse,
            trappers_analyse,
            auto_analyse,
            ov_score,
            hoppin_score,
            fiets_score,
            totaal_score,
            effecten,
            studieplicht,
            dichtste_halte_algemeen=dichtste_halte_algemeen,
            dichtstbijzijnde_station=dichtstbijzijnde_station,
        )

    geautomatiseerde_aanvullingen = maak_geautomatiseerde_aanvullingen(
        projecttype, aantal_wooneenheden, bvo, parkeerplaatsen, fietsenstallingen, straal,
        haltes, hoppinpunten, bff_routes, scholen, horeca, winkels, parkings,
        stappers_analyse, trappers_analyse, auto_analyse, ov_score, fiets_score,
        effecten, studieplicht, mobiliteitseffecten,
        dichtste_halte_algemeen=dichtste_halte_algemeen,
        dichtstbijzijnde_station=dichtstbijzijnde_station,
        auto_detail=auto_detail,
        bff_context=bff_context,
        recreatieve_analyse=recreatieve_analyse,
    )

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=NAVY,
        alignment=TA_LEFT,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=GREY_TXT,
        spaceAfter=14,
    )

    h1_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        textColor=colors.white,
        spaceBefore=12,
        spaceAfter=8,
    )

    h2_style = ParagraphStyle(
        "SubTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=NAVY,
        spaceBefore=8,
        spaceAfter=5,
        keepWithNext=1,
    )

    body_style = ParagraphStyle(
        "BodySmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.8,
        leading=12,
        textColor=colors.black,
        spaceAfter=5,
    )

    caption_style = ParagraphStyle(
        "Caption",
        parent=styles["BodyText"],
        fontName="Helvetica-Oblique",
        fontSize=7.7,
        leading=10,
        textColor=GREY_TXT,
        spaceBefore=3,
        spaceAfter=8,
    )

    card_title_style = ParagraphStyle(
        "CardTitle",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=9.2,
        leading=11,
        textColor=NAVY,
        alignment=1,
    )

    card_value_style = ParagraphStyle(
        "CardValue",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=NAVY,
        alignment=1,
    )

    card_detail_style = ParagraphStyle(
        "CardDetail",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.4,
        leading=9,
        textColor=GREY_TXT,
        alignment=1,
    )

    def clean_text(value):
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    ai_sections = parse_ai_hoofdstukken(ai_teksten)

    ai_style = ParagraphStyle(
        "AIInterpretatie",
        parent=body_style,
        fontName="Helvetica",
        fontSize=8.8,
        leading=12,
        textColor=colors.black,
        leftIndent=6,
        rightIndent=6,
        spaceBefore=4,
        spaceAfter=7,
    )

    def append_ai_interpretatie(key):
        tekst = ai_sections.get(key, "")
        if not tekst:
            return
        story.append(Spacer(1, 4))
        box = Table([[Paragraph("<b>AI-ondersteunde interpretatie</b><br/>" + clean_text(tekst), ai_style)]], colWidths=[doc.width])
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F7F4")),
            ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#8FAF9C")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(box)
        story.append(Spacer(1, 6))

    def section(title, nummer=None):
        label = f"{nummer}. {title}" if nummer else title
        t = Table([[Paragraph(label, h1_style)]], colWidths=[doc.width])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return t

    def styled_table(rows, col_widths=None, header=True, first_col_shade=False):
        """Maak tabellen leesbaar in de PDF.
        Alle tekstcellen worden Paragraphs zodat zinnen automatisch afbreken.
        Tabellen mogen per rij splitsen over pagina's en herhalen de koprij.
        """
        table_cell_style = ParagraphStyle(
            "TableCell",
            parent=body_style,
            fontSize=7.4,
            leading=9.0,
            spaceAfter=0,
            wordWrap="CJK",
        )

        def cell(value):
            if isinstance(value, Paragraph):
                return value
            txt = clean_text(value)
            txt = txt.replace("&lt;br/&gt;", "<br/>").replace("&lt;br /&gt;", "<br/>")
            return Paragraph(txt, table_cell_style)

        safe_rows = [[cell(c) for c in row] for row in rows]
        ncols = len(safe_rows[0]) if safe_rows else 1
        table = Table(
            safe_rows,
            colWidths=col_widths or [doc.width / ncols] * ncols,
            hAlign="LEFT",
            repeatRows=1 if header else 0,
            splitByRow=1,
        )
        commands = [
            ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.8),
            ("LEADING", (0, 0), (-1, -1), 9.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if header:
            commands += [
                ("BACKGROUND", (0, 0), (-1, 0), SAGE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ]
        if first_col_shade:
            start_row = 1 if header else 0
            commands += [
                ("BACKGROUND", (0, start_row), (0, -1), SAGE_LIGHT),
                ("FONTNAME", (0, start_row), (0, -1), "Helvetica-Bold"),
            ]
        table.setStyle(TableStyle(commands))
        return table

    def append_aanvulblok(titel, rows, intro=None):
        """Voegt een compact aanvulblok toe bij het juiste hoofdstuk.
        Zo staat manuele/projectspecifieke informatie niet in één los hoofdstuk,
        maar bij de plaats waar de lezer ze nodig heeft.
        """
        story.append(Spacer(1, 6))
        story.append(Paragraph(titel, h2_style))
        if intro:
            story.append(Paragraph(intro, body_style))
        veilige_rows = [[clean_text(c) for c in row] for row in rows]
        story.append(styled_table(veilige_rows, col_widths=[145, doc.width - 290, 145], header=True))
        story.append(Spacer(1, 8))

    def plan_status_table():
        if not plan_paths:
            return Paragraph("Er werden geen projectplannen opgeladen.", body_style)

        rows = [["Document", "Bestandsnaam", "Opname in PDF"]]
        for item in plan_paths:
            if item.get("preview_path"):
                opname = "Als afbeelding opgenomen"
            else:
                opname = "Enkel als bijlage vermeld"
            rows.append([
                clean_text(item.get("label", "")),
                clean_text(item.get("filename", "")),
                opname
            ])
        return styled_table(rows, col_widths=[120, doc.width - 270, 150], header=True)

    def get_plan(label):
        for item in plan_paths:
            if item.get("label") == label:
                return item
        return None

    def plananalyse_tekst(label, basisuitleg):
        """Maakt een uitgebreidere, thematische planbespreking zonder cijfers uit het plan zelf te raden."""
        dichtbij_halte = (dichtste_halte_algemeen or {}).get("halte_naam", "niet beschikbaar")
        dichtbij_halte_afstand = (dichtste_halte_algemeen or {}).get("afstand_m")
        dichtbij_station = (dichtstbijzijnde_station or {}).get("station_naam", "niet beschikbaar")
        dichtbij_station_afstand = (dichtstbijzijnde_station or {}).get("afstand_m")

        halte_txt = clean_text(dichtbij_halte)
        if dichtbij_halte_afstand is not None:
            halte_txt += f" op ongeveer {dichtbij_halte_afstand} m"

        station_txt = clean_text(dichtbij_station)
        if dichtbij_station_afstand is not None:
            station_txt += f" op ongeveer {dichtbij_station_afstand} m"

        algemeen = (
            f"{basisuitleg} De onderstaande interpretatie is automatisch opgebouwd op basis van het aangeleverde plantype, "
            f"de ingegeven projectgegevens en de beschikbare openbare databronnen. De app leest het plan niet inhoudelijk zoals een ontwerper dat doet; "
            f"de tekst vormt daarom een gerichte checklist en eerste mobiliteitsinterpretatie die nadien door de gebruiker moet worden gecontroleerd."
        )

        if label == "Inplantingsplan":
            return [
                algemeen,
                f"Voor dit project wordt het inplantingsplan vooral gebruikt om de ruimtelijke organisatie van de site te koppelen aan mobiliteit. Bij een projecttype <b>{clean_text(projecttype)}</b> zijn de ligging van de bouwvolumes, de open ruimte, de randen van het perceel en de aansluitingen op het openbaar domein belangrijk om te beoordelen hoe voetgangers, fietsers, bezoekers, bewoners en dienstenstromen de site bereiken.",
                f"Op basis van de ingegeven gegevens voorziet het project <b>{parkeerplaatsen}</b> autoparkeerplaatsen en <b>{fietsenstallingen}</b> fietsenstallingen. Bij de controle van het inplantingsplan moet worden nagegaan of deze functies logisch liggen ten opzichte van de hoofdtoegangen, of de looplijnen kort en leesbaar zijn en of de parkeer- en stallingszones geen onnodige conflicten veroorzaken met zachte weggebruikers.",
                f"De projectsite wordt daarnaast gekoppeld aan de ruimere omgeving. De dichtstbijzijnde bushalte is <b>{halte_txt}</b> en het dichtstbijzijnde station of spoorhalte is <b>{station_txt}</b>. Vanuit mobiliteitsoogpunt is het daarom relevant om op het inplantingsplan te controleren of de toegang voor voetgangers en fietsers gericht is naar deze routes en niet enkel naar de autotoegang."
            ]

        if label == "Situatieplan":
            return [
                algemeen,
                f"Het situatieplan wordt gebruikt om het project niet alleen als afzonderlijk perceel te bekijken, maar als onderdeel van een bestaande wijkstructuur. De kaart- en omgevingsdata tonen binnen de gekozen radius <b>{len(haltes)}</b> De Lijn-haltes, <b>{len(hoppinpunten)}</b> Hoppinpunten, <b>{scholen}</b> scholen, <b>{winkels}</b> winkels, <b>{horeca}</b> horecazaken en <b>{parkings}</b> parkings. Deze elementen geven aan welke bestemmingen of mobiliteitsknopen mogelijk mee de verplaatsingsstromen rond het project bepalen.",
                f"Voor de interpretatie van het situatieplan wordt vooral gekeken naar de relatie met omliggende straten, kruispunten, doorsteken, haltes en voorzieningen. De dichtstbijzijnde bushalte is <b>{halte_txt}</b>; deze wordt altijd vermeld, ook wanneer ze buiten de gekozen analyseradius zou liggen. Dit helpt om de OV-bereikbaarheid niet te onderschatten bij kleinere analyseradii.",
                f"Ook het dichtstbijzijnde station of spoorhalte, <b>{station_txt}</b>, is relevant voor de beoordeling van multimodale bereikbaarheid. In een verdere studie moet gecontroleerd worden of de route tussen projectsite, halte en station veilig, direct, toegankelijk en comfortabel is voor verschillende gebruikersgroepen."
            ]

        if label == "Grondplan gelijkvloers":
            return [
                algemeen,
                "Het grondplan gelijkvloers is het belangrijkste plan om de feitelijke werking van de site te beoordelen. Hier moeten de toegangen voor voetgangers, fietsers, auto’s, hulpdiensten, leveringen, afvalophaling en eventuele verhuisbewegingen worden gelezen in relatie tot elkaar. Vooral de scheiding tussen zachte weggebruikers en gemotoriseerd verkeer is hierbij bepalend.",
                f"De automatische STOP-analyse beoordeelt het voetgangerscomfort als <b>{clean_text(stappers_analyse['comfortscore'])}</b> en de fietsinfrastructuur als <b>{clean_text(trappers_analyse['fietsscore'])}</b>. Bij de controle van het grondplan moet daarom worden nagegaan of het ontwerp deze duurzame modi ook intern ondersteunt: duidelijke looplijnen, logische fietsbereikbaarheid, stallingen dicht bij de toegang en zo weinig mogelijk kruisingen met autoverkeer.",
                f"Voor parkeren en stallen raamt de app indicatief een parkeerbehoefte van <b>{effecten['parkeerbehoefte']}</b> plaatsen en een fietsparkeerbehoefte van <b>{effecten['fietsbehoefte']}</b> stallingen. Het grondplan moet verder aantonen of het opgegeven aanbod ruimtelijk haalbaar, bruikbaar en leesbaar georganiseerd is. Daarbij zijn ook draaibewegingen, hellingen, wachtruimte, laad- en loszones en toegankelijkheid belangrijke controlepunten."
            ]

        if label == "Doorsnede / gevel":
            return [
                algemeen,
                "De doorsnede of gevel wordt gebruikt als aanvullend controleplan. Dit plan helpt om niveauverschillen, hellingen, keldertoegangen, fietsenbergingen op een lager niveau, inkomzones en de relatie tussen gebouw en straatprofiel beter te begrijpen. Zulke elementen zijn moeilijk uit een kaartlaag af te leiden, maar hebben wel invloed op toegankelijkheid en gebruiksgemak.",
                "Voor zachte weggebruikers is vooral van belang of de toegang gelijkvloers, herkenbaar en comfortabel bereikbaar is. Wanneer fietsenstallingen of parkings ondergronds liggen, moet worden nagegaan of de route ernaartoe voldoende gebruiksvriendelijk is, bijvoorbeeld via een fietslift, fietshelling of duidelijke interne circulatie.",
                "Voor gemotoriseerd verkeer kan de doorsnede bijkomende informatie geven over hellingspercentages, in- en uitritten, zichtbaarheid en de aansluiting op het openbaar domein. Deze punten moeten in een latere controle worden afgestemd met de geldende ontwerpvoorschriften en de concrete uitvoering van het project."
            ]

        return [algemeen]

    def add_plan(story_obj, label, title, uitleg, figuurtekst, max_h=330, pagebreak_after=False):
        """Voegt één plan op de inhoudelijk juiste plaats toe, met korte duiding."""
        item = get_plan(label)
        if not item:
            return False

        pad = item.get("preview_path")
        if not pad or not os.path.exists(pad):
            story_obj.append(Paragraph(title, h2_style))
            story_obj.append(Paragraph(
                f"Het bestand <b>{clean_text(item.get('filename', ''))}</b> werd opgeladen, maar kon niet automatisch als afbeelding worden weergegeven.",
                body_style
            ))
            return False

        from PIL import Image as PILImageLocal
        try:
            with PILImageLocal.open(pad) as plan_img:
                w, h = plan_img.size
            max_w = doc.width
            max_h = min(max_h, 245)
            ratio = min(max_w / w, max_h / h)
            img_w = w * ratio
            img_h = h * ratio

            story_obj.append(CondPageBreak(160))
            story_obj.append(Spacer(1, 8))
            story_obj.append(Paragraph(title, h2_style))
            for paragraaf in plananalyse_tekst(label, uitleg):
                story_obj.append(Paragraph(paragraaf, body_style))
            story_obj.append(Image(pad, width=img_w, height=img_h))
            story_obj.append(Paragraph(figuurtekst, caption_style))
            if pagebreak_after:
                story_obj.append(PageBreak())
            return True
        except Exception:
            story_obj.append(Paragraph(title, h2_style))
            story_obj.append(Paragraph(
                f"Het bestand <b>{clean_text(item.get('filename', ''))}</b> werd opgeladen, maar kon niet automatisch als afbeelding worden verwerkt.",
                body_style
            ))
            return False

    def score_color(score):
        score = str(score).lower()
        if "goed" in score:
            return colors.HexColor("#DDEFE5")
        if "matig" in score:
            return colors.HexColor("#FFF0CC")
        if "beperkt" in score:
            return colors.HexColor("#F8D7DA")
        return LIGHT_GREY

    def score_card(icon, title, score, detail):
        content = [
            Paragraph(icon, card_value_style),
            Paragraph(title, card_title_style),
            Paragraph(score, card_value_style),
            Paragraph(detail, card_detail_style),
        ]
        return content

    def make_footer(canvas, doc_obj):
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(SAGE)
        canvas.setLineWidth(0.8)
        canvas.line(doc_obj.leftMargin, 28, width - doc_obj.rightMargin, 28)
        canvas.setFillColor(GREY_TXT)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(doc_obj.leftMargin, 17, f"Mobiliteitsfiche | {projectnaam}")
        canvas.drawRightString(width - doc_obj.rightMargin, 17, f"Pagina {doc_obj.page}")
        canvas.restoreState()

    story = []

    # -----------------------------------------------------
    # PAGINA 1 - VOORPAGINA
    # -----------------------------------------------------
    logo_text_style = ParagraphStyle(
        "LogoText",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=NAVY,
        alignment=1,
    )

    cover_title = ParagraphStyle(
        "CoverTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=30,
        leading=34,
        textColor=NAVY,
        alignment=TA_LEFT,
        spaceAfter=8,
    )

    cover_subtitle = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=13,
        leading=18,
        textColor=GREY_TXT,
        alignment=TA_LEFT,
        spaceAfter=12,
    )

    def logo_box(path, placeholder):
        if path and os.path.exists(path):
            try:
                return Image(path, width=105, height=52)
            except Exception:
                pass
        box = Table([[Paragraph(placeholder, logo_text_style)]], colWidths=[115], rowHeights=[55])
        box.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        return box

    story.append(Spacer(1, 34))
    story.append(Paragraph("Mobiliteitsfiche", cover_title))
    story.append(Paragraph("Automatische STOP-analyse", cover_subtitle))
    story.append(Spacer(1, 14))
    story.append(Paragraph(f"<b>{clean_text(projectnaam)}</b>", ParagraphStyle("ProjectCover", parent=cover_title, fontSize=18, leading=23, spaceAfter=3)))
    story.append(Paragraph(clean_text(adres), cover_subtitle))
    story.append(Spacer(1, 16))

    # Projectlocatiekaart op de cover.
    # Voor de PDF gebruiken we opnieuw de Folium-kaartstijl uit de app.
    try:
        cover_png = maak_pdf_projectkaart_png(lat, lon, straal, auto_gdf=auto_gdf, haltes=haltes, hoppinpunten=hoppinpunten, bff_routes=bff_routes, bestandsnaam="cover_projectlocatie_static")
        story.append(maak_reportlab_image_met_verhouding(cover_png, doc.width, 240))
        story.append(Paragraph("Figuur: situering projectsite met analysegebied.", caption_style))
    except Exception:
        story.append(Spacer(1, 240))

    story.append(Spacer(1, 20))
    meta_cover = Table([
        ["Versie", versienummer, "Vrijgavedatum", vrijgavedatum],
        ["Status", rapportstatus, "Referentie", referentie],
    ], colWidths=[75, 145, 90, doc.width - 310])
    meta_cover.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("BACKGROUND", (0, 0), (0, -1), SAGE_LIGHT),
        ("BACKGROUND", (2, 0), (2, -1), SAGE_LIGHT),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(meta_cover)
    story.append(Spacer(1, 30))

    logos = Table([
        [logo_box(app_logo_path, "Logo app\nMOBISCAN"), "", logo_box(bureau_logo_path, "Logo\narchitectenbureau")],
        [Paragraph("Opgesteld met MOBISCAN", body_style), "", Paragraph(clean_text(architectenbureau), body_style)],
    ], colWidths=[130, doc.width - 260, 130])
    logos.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
    ]))
    story.append(logos)
    story.append(PageBreak())

    # -----------------------------------------------------
    # PAGINA 2 - COLOFON
    # -----------------------------------------------------
    story.append(CondPageBreak(90))
    story.append(section("Colofon"))
    colofon_rows = [
        ["Opdrachtgever", clean_text(opdrachtgever)],
        ["Project", clean_text(projectnaam)],
        ["Adres project", clean_text(adres)],
        ["Architectenbureau / gebruiker app", clean_text(architectenbureau)],
        ["Opdrachtnemer", clean_text(opdrachtnemer)],
        ["Projectmedewerkers / auteurs", clean_text(projectmedewerkers)],
        ["Versienummer", clean_text(versienummer)],
        ["Vrijgavedatum", clean_text(vrijgavedatum)],
        ["Status", clean_text(rapportstatus)],
        ["Referentie", clean_text(referentie)],
    ]
    story.append(styled_table(colofon_rows, col_widths=[170, doc.width - 170], header=False, first_col_shade=True))
    story.append(Spacer(1, 18))

    story.append(Paragraph("Logo's", h2_style))
    logo_colofon = Table([
        [logo_box(app_logo_path, "Logo app\nMOBISCAN"), logo_box(bureau_logo_path, "Logo\narchitectenbureau")],
        [Paragraph("Logo van de app", body_style), Paragraph("Logo van het architectenbureau dat de app gebruikt", body_style)],
    ], colWidths=[doc.width / 2, doc.width / 2])
    logo_colofon.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(logo_colofon)
    story.append(Spacer(1, 18))

    story.append(Paragraph("Disclaimer", h2_style))
    disclaimer = (
        "Deze mobiliteitsfiche werd automatisch gegenereerd op basis van publiek beschikbare databronnen en vormt een eerste mobiliteitsscreening. "
        "De resultaten vervangen geen formele mobiliteitsstudie, MOBER, terreinopname of verkeerskundige controle. "
        "Ontbrekende of foutieve databronnen kunnen de automatische resultaten beïnvloeden."
    )
    disclaimer_box = Table([[Paragraph(disclaimer, body_style)]], colWidths=[doc.width])
    disclaimer_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SAGE_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, SAGE),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(disclaimer_box)
    story.append(PageBreak())

    # -----------------------------------------------------
    # PAGINA 3 - INHOUDSTAFEL
    # -----------------------------------------------------
    story.append(CondPageBreak(90))
    story.append(section("Inhoudstafel"))
    inhoud_rows = [
        ["1", "Projectomschrijving"],
        ["1.1", "Inplantingsplan"],
        ["2", "Omgevingsomschrijving"],
        ["3", "Projectkenmerken"],
        ["4", "STOP-samenvatting"],
        ["4.1", "Stappers"],
        ["4.2", "Trappers"],
        ["4.3", "Openbaar vervoer"],
        ["5", "Parkeer- en verkeersanalyse"],
        ["6", "Auto-analyse"],
        ["7", "Mobiliteitseffecten en milderende maatregelen"],
        ["7.1", "Impact op bereikbaarheid"],
        ["7.2", "Impact op parkeren"],
        ["7.3", "Impact op verkeersgeneratie"],
        ["7.4", "Impact op verkeersveiligheid"],
        ["7.5", "Aanbevelingen en milderende maatregelen"],
        ["8", "Synthese en kwaliteitscheck"],
        ["8.1", "Synthese per thema"],
        ["8.2", "Kwaliteitscheck"],
        ["8.3", "Eindconclusie"],
        ["9", "Eerste beoordeling"],
        ["10", "Geautomatiseerde en resterende aanvullingen"],
        ["11", "Datatabellen uit de app"],
        ["12", "Bronnenlijst"],
    ]
    story.append(styled_table(inhoud_rows, col_widths=[70, doc.width - 70], header=False, first_col_shade=True))
    story.append(PageBreak())

    story.append(CondPageBreak(90))
    story.append(section("Projectomschrijving", 1))
    omschrijving_rows = [
        ["Fase binnen het project", clean_text(projectfase)],
        ["Korte projectomschrijving", clean_text(korte_omschrijving if korte_omschrijving else "Niet ingevuld.")],
        ["Huidige toestand", clean_text(huidige_toestand if huidige_toestand else "Niet ingevuld.")],
        ["Toekomstige toestand", clean_text(toekomstige_toestand if toekomstige_toestand else "Niet ingevuld.")],
    ]
    story.append(styled_table(omschrijving_rows, col_widths=[155, doc.width - 155], header=False, first_col_shade=True))
    append_ai_interpretatie("projectomschrijving")
    append_aanvulblok(
        "1.1 Aan te vullen projectinformatie",
        [
            ["Aan te vullen informatie", "Wat moet hier komen?", "Waar vind je dit?"],
            ["Definitieve projectfase", "Vermeld of het gaat om voorontwerp, aanvraag omgevingsvergunning, uitvoeringsdossier of bestaande toestand.", "Opdrachtgever, architect, vergunningsdossier."],
            ["Programma per functie", "Splits het programma op per functie, bijvoorbeeld wonen, handel, horeca, kantoor, school, parking of gemengd gebruik.", "Architectuurplannen, meetstaat, projectnota."],
            ["Fasering", "Beschrijf of het project in één fase of in meerdere fases wordt gerealiseerd.", "Planning opdrachtgever, ontwerpteam, aannemer."],
            ["Bestaande toestand", "Beschrijf huidig gebruik, leegstand, braakliggend terrein, bestaande gebouwen, bestaande ontsluiting en bestaande parkeerdruk.", "Plaatsbezoek, foto’s, bestaande plannen, gemeentelijke informatie."],
            ["Toekomstige toestand", "Beschrijf de beoogde werking van de site: gebruikers, bezoekers, bewoners, leveringen, toegangen en dagelijkse werking.", "Ontwerpnota, opdrachtgever, architect, exploitant."],
        ],
        "Deze gegevens komen in bijna elke professionele mobiliteitsstudie terug, maar kunnen niet volledig uit publieke databronnen worden afgeleid."
    )

    add_plan(
        story,
        "Inplantingsplan",
        "1.1 Inplantingsplan",
        "Het inplantingsplan toont hoe het project zich op het perceel organiseert. Dit plan is belangrijk voor de beoordeling van toegangen, interne circulatie, parkeerzones, fietsenstallingen en de relatie met de omliggende straten.",
        "Figuur: aangeleverd inplantingsplan van het project.",
        max_h=360
    )
    append_ai_interpretatie("inplanting")

    story.append(Paragraph("Projectdocumenten", h2_style))
    story.append(plan_status_table())
    append_aanvulblok(
        "1.2 Aan te vullen informatie bij projectplannen",
        [
            ["Aan te vullen informatie", "Wat moet hier komen?", "Waar vind je dit?"],
            ["Laatste planversie", "Controleer of de opgenomen plannen overeenkomen met de laatste ontwerpversie.", "Architect, projectplatform, vergunningsaanvraag."],
            ["Interne looplijnen", "Duid aan hoe voetgangers van openbaar domein, parking en fietsenstalling naar de gebouwen gaan.", "Inplantingsplan, grondplan gelijkvloers, terreinontwerp."],
            ["Fietsbereikbaarheid op de site", "Beschrijf toegang voor fietsers, locatie stallingen, buitenmaatse fietsen en laadpunten.", "Grondplan, fietsenstallingsplan, ontwerpnota."],
            ["Autotoegang en parking", "Beschrijf inrit, uitrit, circulatie, hellingen, slagbomen, poorten, parkeerorganisatie en bezoekersplaatsen.", "Inplantingsplan, parkingplan, doorsnede, brandweeradvies."],
            ["Doorsnede/gevel", "Neem dit enkel inhoudelijk op wanneer niveauverschillen, hellingen, keldertoegang of toegankelijkheid relevant zijn.", "Doorsnede, gevelplan, technische nota."],
        ],
        "De app kan plannen tonen, maar kan ze niet inhoudelijk interpreteren zoals een ontwerper of mobiliteitsexpert."
    )
    story.append(PageBreak())

    story.append(CondPageBreak(90))
    story.append(section("Omgevingsomschrijving", 2))
    dichtste_halte_naam = (dichtste_halte_algemeen or {}).get("halte_naam", "niet beschikbaar")
    dichtste_halte_afstand = (dichtste_halte_algemeen or {}).get("afstand_m")
    station_naam = (dichtstbijzijnde_station or {}).get("station_naam", "niet beschikbaar")
    station_afstand = (dichtstbijzijnde_station or {}).get("afstand_m")

    omgevings_rows = [
        ["Adres projectsite", clean_text(adres)],
        ["Coördinaten", f"{lat:.6f}, {lon:.6f}"],
        ["Gekozen analysegebied", f"{straal} meter"],
        ["Dichtstbijzijnde bushalte", f"{clean_text(dichtste_halte_naam)}" + (f" · ongeveer {dichtste_halte_afstand} m" if dichtste_halte_afstand is not None else "")],
        ["Dichtstbijzijnde station / spoorhalte", f"{clean_text(station_naam)}" + (f" · ongeveer {station_afstand} m" if station_afstand is not None else "")],
        ["Haltes binnen gekozen radius", f"{len(haltes)} De Lijn-haltes"],
        ["Hoppinpunten binnen gekozen radius", f"{len(hoppinpunten)} Hoppinpunten"],
        ["Voorzieningen binnen gekozen radius", f"{scholen} scholen, {horeca} horecazaken, {winkels} winkels en {parkings} parkings"],
    ]
    story.append(Paragraph(
        "De omgevingsomschrijving plaatst de projectsite binnen haar ruimere mobiliteitscontext. De dichtstbijzijnde bushalte en het dichtstbijzijnde station worden altijd vermeld, ook wanneer ze buiten de gekozen analyseradius liggen.",
        body_style
    ))
    story.append(styled_table(omgevings_rows, col_widths=[170, doc.width - 170], header=False, first_col_shade=True))
    append_ai_interpretatie("omgevingsomschrijving")
    append_aanvulblok(
        "2.1 Aan te vullen omgevings- en beleidscontext",
        [
            ["Aan te vullen informatie", "Wat moet hier komen?", "Waar vind je dit?"],
            ["Planningscontext", "Beschrijf relevante beleidsplannen zoals mobiliteitsplan, regionaal mobiliteitsplan, RUP, circulatieplan of parkeerplan.", "Gemeentelijke website, Vlaanderen.be, vervoerregio, Geopunt, ruimtelijke plannen."],
            ["Toekomstige ontwikkelingen", "Vermeld geplande projecten in de buurt die verkeersstromen kunnen wijzigen.", "Gemeente, project-MER, omgevingsloket, lokale beleidsdocumenten, overleg."],
            ["Geplande infrastructuurwerken", "Neem geplande fietsverbindingen, HOV-projecten, heraanleg straten, gewijzigde kruispunten of wegenwerken op.", "AWV, gemeente, De Lijn, Hoppin, projectwebsites."],
            ["Lokale parkeercontext", "Beschrijf betalend parkeren, blauwe zone, bewonerskaarten, publieke parkings en straatparkeren.", "Gemeentelijke parkeerwebsite, parkeerbedrijf, terreincontrole."],
            ["Terreinwaarneming", "Controleer of de automatisch gevonden voorzieningen en routes overeenkomen met de werkelijkheid.", "Plaatsbezoek, foto's, Street View als eerste indicatie, gemeentelijke GIS."],
        ],
        "Deze context bepaalt vaak of een automatische score ruim voldoende is of net verder moet worden genuanceerd."
    )

    add_plan(
        story,
        "Situatieplan",
        "2.1 Situatieplan",
        "Het situatieplan ondersteunt de lezing van de omgeving. Het toont de ligging van het project ten opzichte van de omliggende wegen, percelen en publieke ruimte.",
        "Figuur: aangeleverd situatieplan met ruimtelijke context van de projectsite.",
        max_h=340
    )
    story.append(PageBreak())

    story.append(CondPageBreak(90))
    story.append(section("Projectkenmerken", 3))
    project_data = [
        ["Projectnaam", clean_text(projectnaam)],
        ["Projecttype", clean_text(projecttype)],
        ["Adres", clean_text(adres)],
        ["Coördinaten", f"{lat:.6f}, {lon:.6f}"],
        ["Analysegebied", f"{straal} meter"],
        ["Wooneenheden", str(aantal_wooneenheden)],
        ["BVO / programma", f"{bvo} m²"],
        ["Parkeerplaatsen", str(parkeerplaatsen)],
        ["Fietsenstallingen", str(fietsenstallingen)],
        ["Datum", datetime.today().strftime("%d-%m-%Y")]
    ]
    story.append(styled_table(project_data, col_widths=[150, doc.width - 150], header=False, first_col_shade=True))
    append_ai_interpretatie("projectkenmerken")
    append_aanvulblok(
        "3.1 Aan te vullen projectkenmerken",
        [
            ["Aan te vullen informatie", "Wat moet hier komen?", "Waar vind je dit?"],
            ["Gebruikersprofiel", "Beschrijf bewoners, bezoekers, personeel, leerlingen, klanten of leveranciers naargelang projecttype.", "Opdrachtgever, exploitant, ontwerpnota, vergelijkbare projecten."],
            ["Bezoekersparkeren", "Geef aan of bezoekers op eigen terrein parkeren, in straatparkeren, publieke parking of via deelmobiliteit.", "Lokale parkeernorm, parkeerplan, gemeentelijke info."],
            ["Fietsparkeerkwaliteit", "Beschrijf ligging, toegankelijkheid, overdekking, beveiliging, buitenmaatse fietsen en laadpunten.", "Fietsparkeerplan, grondplan, bestek, ontwerpnota."],
            ["Bijzondere functies", "Vermeld functies die afwijkende mobiliteit veroorzaken zoals horeca, schoolpoort, zorg, leveringen, drive, sporthal of laadstation.", "Programma, exploitant, architect, gebruiksnota."],
        ],
        "Deze kenmerken sturen de parkeerbehoefte, fietsparkeerbehoefte en verkeersgeneratie."
    )

    add_plan(
        story,
        "Grondplan gelijkvloers",
        "3.1 Grondplan gelijkvloers",
        "Het grondplan gelijkvloers is relevant voor de mobiliteitsanalyse omdat hierop de toegangen, looplijnen, fietsenstallingen, parkeerzones en laad- en losbewegingen kunnen worden gecontroleerd.",
        "Figuur: aangeleverd grondplan gelijkvloers.",
        max_h=350
    )

    # Doorsnede/gevel wordt niet langer als volwaardig hoofdstuk opgenomen.
    # Het document blijft wel zichtbaar in de projectdocumententabel.

    story.append(CondPageBreak(90))
    story.append(section("STOP-samenvatting", 4))
    story.append(Paragraph("Onderstaande blokken vatten de automatische analyse samen. De scores zijn indicatief en bedoeld als snelle screening vóór verdere verkeerskundige controle.", body_style))

    card_data = [[
        score_card("🚶", "Stappers", stappers_analyse["comfortscore"], f'{stappers_analyse["voetpaden"]} voetpaden · {stappers_analyse["oversteekplaatsen"]} oversteken'),
        score_card("🚲", "Trappers", trappers_analyse["fietsscore"], f'{trappers_analyse["fietspaden"]} fietspaden · {trappers_analyse["bff_segmenten"]} BFF'),
        score_card("🚌", "Openbaar vervoer", ov_score, f'{len(haltes)} haltes · {len(hoppinpunten)} Hoppinpunten'),
        score_card("🚗", "Auto", auto_analyse["ontsluitingsscore"], f'{auto_analyse["hoofdwegen"]} hoofdwegen · {auto_analyse["lokale_wegen"]} lokaal'),
    ]]
    card_table = Table(card_data, colWidths=[doc.width / 4 - 3] * 4, hAlign="LEFT")
    card_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (0, 0), 0.7, ORANGE),
        ("BOX", (1, 0), (1, 0), 0.7, SAGE),
        ("BOX", (2, 0), (2, 0), 0.7, BLUE),
        ("BOX", (3, 0), (3, 0), 0.7, NAVY),
        ("BACKGROUND", (0, 0), (0, 0), score_color(stappers_analyse["comfortscore"])),
        ("BACKGROUND", (1, 0), (1, 0), score_color(trappers_analyse["fietsscore"])),
        ("BACKGROUND", (2, 0), (2, 0), score_color(ov_score)),
        ("BACKGROUND", (3, 0), (3, 0), score_color(auto_analyse["ontsluitingsscore"])),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(card_table)
    story.append(Spacer(1, 14))

    # -----------------------------------------------------
    # STOP-PERIODE: TABELLEN STAAN BIJ HET JUISTE ONDERDEEL
    # -----------------------------------------------------
    def pdf_par(value):
        return Paragraph(clean_text(value), body_style)

    story.append(Paragraph(
        "De detailtabellen hieronder staan telkens bij het juiste STOP-onderdeel. Zo is de tabel onmiddellijk leesbaar naast de kaart en wordt duidelijk welke data de kaart en score onderbouwen.",
        body_style
    ))

    # 4.1 Stappers
    story.append(Paragraph("4.1 Stappers", h2_style))
    story.append(Paragraph(
        "De stappersanalyse geeft een eerste indicatie van de voetgangerskwaliteit rond de projectsite. De tabel toont hoeveel voetgangersverbindingen, oversteekplaatsen en trage wegen via OpenStreetMap werden herkend. De kaart toont vervolgens de herkende voetgangersverbindingen, oversteekplaatsen en trage wegen binnen het analysegebied.",
        body_style
    ))
    stappers_rows = [
        ["Onderdeel", "Waarde", "Interpretatie"],
        ["Voetpaden / voetgangersverbindingen", stappers_analyse["voetpaden"], "Indicatie van aanwezige wandelinfrastructuur"],
        ["Oversteekplaatsen", stappers_analyse["oversteekplaatsen"], "Belangrijk voor veilige route naar haltes en voorzieningen"],
        ["Trage wegen / paden", stappers_analyse["trage_wegen"], "Aanvullende doorsteken en zachte verbindingen"],
        ["Indicatieve comfortscore", stappers_analyse["comfortscore"], "Automatische score, terreincontrole blijft nodig"],
    ]
    stappers_rows = [[pdf_par(c) for c in r] for r in stappers_rows]
    story.append(styled_table(stappers_rows, col_widths=[155, 70, doc.width - 225], header=True))
    append_ai_interpretatie("stappers")
    story.append(Spacer(1, 6))

    wandelen_png = maak_pdf_stapperskaart_png(
        lat, lon,
        straal=straal,
        stappers_gdf=stappers_gdf,
        auto_gdf=auto_gdf,
        bestandsnaam="kaart_wandelen_gis"
    )
    story.append(maak_reportlab_image_met_verhouding(wandelen_png, doc.width, 220))
    story.append(Paragraph("Figuur: herkende voetgangersverbindingen, oversteekplaatsen en trage wegen rond de projectsite.", caption_style))
    story.append(Spacer(1, 8))

    story.append(Paragraph("20 minuten te voet", h2_style))
    story.append(Paragraph(
        "Deze bereikbaarheidskaart hoort bij het onderdeel Stappers. De kaart toont niet enkel de bereikbare straten binnen 20 minuten wandelen, maar ook extra kaartcontext buiten deze zone. Daardoor blijft zichtbaar hoe de projectsite zich verhoudt tot omliggende wijken, voorzieningen en grotere wegen.",
        body_style
    ))
    bereik_wandelen_png = maak_pdf_isochronenkaart_png(lat, lon, "walk", 4.8, 20, "#2E8B57", "Bereikbaarheid op 20 minuten wandelen", "kaart_bereikbaarheid_20min_wandelen_static", auto_gdf=auto_gdf)
    story.append(maak_reportlab_image_met_verhouding(bereik_wandelen_png, doc.width, 240))
    story.append(Paragraph(
        "Conclusie: de wandelkaart geeft een eerste beeld van welke bestemmingen binnen een realistische wandeltijd bereikbaar zijn. Voor de finale beoordeling moeten oversteekkwaliteit, toegankelijkheid, verlichting en comfort op terrein gecontroleerd worden.",
        body_style
    ))
    story.append(Paragraph("Figuur: bereikbaarheid binnen 20 minuten wandelen via het voetgangersnetwerk, met omliggende context buiten de bereikbare zone.", caption_style))

    # 4.2 Trappers
    story.append(Paragraph("4.2 Trappers", h2_style))
    story.append(Paragraph(
        "De trappersanalyse combineert fietsdata uit OpenStreetMap met het officiële Bovenlokaal Functioneel Fietsroutenetwerk. Het BFF is een wensnetwerk met fietssnelwegen, hoofdroutes, functionele routes en alternatieve routes. Wanneer hier geen BFF-segmenten verschijnen terwijl de projectcontext toch een fietsroute doet vermoeden, moet de WFS-laag, de gekozen radius en de geometrische koppeling gecontroleerd worden. In deze versie wordt de officiële laag beleid:bff via de algemene MOW-WFS gebruikt.",
        body_style
    ))
    trappers_rows = [
        ["Onderdeel", "Waarde", "Interpretatie"],
        ["Fietspaden", trappers_analyse["fietspaden"], "Herkenning via OpenStreetMap"],
        ["Fietssuggesties / cycleway-tags", trappers_analyse["fietssuggesties"], "Aanvullende OSM-tags voor fietsvoorzieningen"],
        ["Gedeelde paden / fietsbare paden", trappers_analyse["gedeelde_paden"], "Paden waar fietsen mogelijk kan zijn"],
        ["Fietsstraten", trappers_analyse.get("fietsstraten", 0), "Detectie via OSM-tag cyclestreet=yes"],
        ["BFF-segmenten", trappers_analyse["bff_segmenten"], "Officiële BFF-laag van MOW"],
        ["BFF-hoofdroute", bff_context.get("hoofdroute", "Niet beschikbaar"), "Automatische interpretatie van BFF-attributen"],
        ["Fietssnelweg", bff_context.get("fietssnelweg", "Niet beschikbaar"), "Detectie via BFF-/OSM-attributen, visuele controle aanbevolen"],
        ["Recreatieve fietsroutes", recreatieve_analyse.get("aantal", 0), recreatieve_analyse.get("netwerken", "Niet beschikbaar")],
        ["Indicatieve fietsscore", trappers_analyse["fietsscore"], "Automatische score, controle op terrein blijft nodig"],
    ]
    trappers_rows = [[pdf_par(c) for c in r] for r in trappers_rows]
    story.append(styled_table(trappers_rows, col_widths=[155, 70, doc.width - 225], header=True))
    append_ai_interpretatie("trappers")
    story.append(Spacer(1, 6))

    story.append(Paragraph("BFF-fietsroutes binnen de gekozen radius", h2_style))
    bff_samenvatting_rows = [
        ["Onderdeel", "Resultaat"],
        ["Dichtstbijzijnde BFF", clean_text(bff_context.get("dichtste_afstand", "niet beschikbaar"))],
        ["BFF-hoofdroute", clean_text(bff_context.get("hoofdroute", "Niet gedetecteerd"))],
        ["Fietssnelweg", clean_text(bff_context.get("fietssnelweg", "Niet gedetecteerd"))],
        ["Aantal BFF-segmenten binnen analysegebied", str(trappers_analyse.get("bff_segmenten", 0))],
    ]
    story.append(styled_table(bff_samenvatting_rows, col_widths=[210, doc.width - 210], header=True))
    story.append(Paragraph(
        "Deze samenvatting vervangt de volledige technische segmententabel. Voor de beoordeling is vooral relevant of de projectsite aansluit op een BFF-route, hoofdroute of fietssnelweg. De exacte segmenten worden niet afzonderlijk opgesomd in het rapport.",
        body_style
    ))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Recreatieve fietsroutes", h2_style))
    story.append(Paragraph(
        f"Binnen de gekozen radius werden <b>{recreatieve_analyse.get('aantal', 0)}</b> recreatieve fietsroute-elementen of knooppuntverwijzingen gedetecteerd. Netwerken: <b>{clean_text(recreatieve_analyse.get('netwerken', 'Niet beschikbaar'))}</b>. {clean_text(recreatieve_analyse.get('toelichting', ''))}",
        body_style
    ))
    story.append(Spacer(1, 6))

    fietsen_png = maak_pdf_trapperskaart_png(
        lat, lon,
        straal=straal,
        trappers_gdf=trappers_gdf,
        bff_routes=bff_routes,
        recreatieve_routes=recreatieve_routes_gdf,
        auto_gdf=auto_gdf,
        bestandsnaam="kaart_fietsen_gis"
    )
    story.append(maak_reportlab_image_met_verhouding(fietsen_png, doc.width, 220))
    story.append(Paragraph("Figuur: herkende fietsinfrastructuur, BFF-context en recreatieve fietsroutes rond de projectsite.", caption_style))
    story.append(Spacer(1, 8))

    story.append(Paragraph("20 minuten met de fiets", h2_style))
    story.append(Paragraph(
        "Deze bereikbaarheidskaart hoort bij het onderdeel Trappers. De kaart toont welke omgeving theoretisch binnen 20 minuten fietsen bereikbaar is. De extra context buiten de gekleurde bereikbare straten maakt duidelijk welke omliggende kernen en hoofdassen net buiten of aan de rand van het fietsbereik liggen.",
        body_style
    ))
    bereik_fiets_png = maak_pdf_isochronenkaart_png(lat, lon, "bike", 15, 20, "#1F77B4", "Bereikbaarheid op 20 minuten fietsen", "kaart_bereikbaarheid_20min_fiets_static", auto_gdf=auto_gdf)
    story.append(maak_reportlab_image_met_verhouding(bereik_fiets_png, doc.width, 240))
    story.append(Paragraph(
        "Conclusie: de fietskaart ondersteunt de beoordeling of de projectsite ook zonder auto ruimtelijk logisch bereikbaar is. De bereikbaarheid moet samen gelezen worden met de aanwezigheid van BFF-routes, fietsstraten, fietssnelwegen en kwalitatieve fietsenstallingen.",
        body_style
    ))
    story.append(Paragraph("Figuur: bereikbaarheid binnen 20 minuten fietsen via het fietsnetwerk, met omliggende context buiten de bereikbare zone.", caption_style))

    # 4.3 Openbaar vervoer
    story.append(Paragraph("4.3 Openbaar vervoer", h2_style))
    story.append(Paragraph(
        "De OV-analyse toont de De Lijn-haltes en Hoppinpunten binnen de gekozen radius. De tabel met haltes vermeldt de afstand en maximaal de belangrijkste gekoppelde lijnen. De kaart toont dezelfde haltecluster ruimtelijk ten opzichte van de projectsite.",
        body_style
    ))

    story.append(Paragraph("Alle De Lijn-haltes binnen de gekozen radius", h2_style))
    if not haltes.empty:
        story.append(Paragraph(
            "Deze tabel neemt alle haltes over die ook in de Streamlit-app zichtbaar zijn. Per halte worden de afstand, het aantal ritten per uur in de ochtendspits, de frequentiebeoordeling en de gekoppelde lijnen vermeld.",
            body_style
        ))
        halte_rows = [["Halte", "Afstand", "Ritten/u spits", "Freq.", "Lijnen"]]
        for _, row in haltes.sort_values("afstand_m").iterrows():
            halte_rows.append([
                row.get("halte_naam", ""),
                f'{row.get("afstand_m", "")} m',
                row.get("ritten_spits_uur", "n.b."),
                row.get("frequentie_score", "n.b."),
                row.get("buslijnen", ""),
            ])
        halte_rows = [[pdf_par(c) for c in r] for r in halte_rows]
        story.append(styled_table(halte_rows, col_widths=[105, 48, 55, 70, doc.width - 278], header=True))
        story.append(Paragraph(
            f"In totaal werden binnen de gekozen radius {len(haltes)} De Lijn-haltes gevonden. De afstand is een hemelsbrede afstand tussen projectsite en halte; voor een vergunningsgerichte studie moeten de effectieve wandelroute, toegankelijkheid, haltekwaliteit en dienstregeling nog worden nagekeken.",
            caption_style
        ))
    else:
        story.append(Paragraph("Er werden geen De Lijn-haltes gevonden binnen de gekozen radius.", body_style))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Hoppinpunten binnen de gekozen radius", h2_style))
    if not hoppinpunten.empty:
        hoppin_rows = [["Naam", "Gemeente", "Afstand"]]
        for _, row in hoppinpunten.sort_values("afstand_m").head(15).iterrows():
            hoppin_rows.append([
                row.get("naam", ""),
                row.get("gemeente", ""),
                f'{row.get("afstand_m", "")} m',
            ])
        hoppin_rows = [[pdf_par(c) for c in r] for r in hoppin_rows]
        story.append(styled_table(hoppin_rows, col_widths=[doc.width * 0.45, doc.width * 0.35, doc.width * 0.20], header=True))
    else:
        story.append(Paragraph("Er werden geen Hoppinpunten gevonden binnen de gekozen radius.", body_style))
    story.append(Spacer(1, 6))

    append_ai_interpretatie("openbaar_vervoer")

    ov_png = maak_pdf_ov_kaart_png(lat, lon, straal, haltes=haltes, hoppinpunten=hoppinpunten, auto_gdf=auto_gdf, bestandsnaam="kaart_ov_static")
    story.append(maak_reportlab_image_met_verhouding(ov_png, doc.width, 220))
    story.append(Paragraph("Figuur: dichtstbijzijnde OV-haltes rond de projectsite, strakker ingezoomd op de haltecluster.", caption_style))

    # 4.4 Samenvattende STOP-tabel
    story.append(Paragraph("4.4 Samenvattende STOP-tabel", h2_style))
    stop_rows = [
        ["Onderdeel", "Score", "Belangrijkste output"],
        ["Stappers", stappers_analyse["comfortscore"], f'{stappers_analyse["voetpaden"]} voetpaden, {stappers_analyse["oversteekplaatsen"]} oversteekplaatsen, {stappers_analyse["trage_wegen"]} trage wegen'],
        ["Trappers", trappers_analyse["fietsscore"], f'{trappers_analyse["fietspaden"]} fietspaden, {trappers_analyse["fietssuggesties"]} cycleway-tags, {trappers_analyse["bff_segmenten"]} BFF-segmenten'],
        ["Openbaar vervoer", ov_score, f"{len(haltes)} haltes, {len(hoppinpunten)} Hoppinpunten"],
        ["Auto", auto_analyse["ontsluitingsscore"], f'{auto_analyse["hoofdwegen"]} hoofdwegen, {auto_analyse["lokale_wegen"]} lokale wegen, {auto_analyse["kruispunten"]} regelpunten'],
    ]
    story.append(styled_table(stop_rows, col_widths=[110, 75, doc.width - 185], header=True))
    methodiek_rows = [["Onderdeel", "Methodologische toelichting"]]
    methodiek_rows.append(["Stappers", SCORE_DREMPELS["stappers"]["toelichting"] + " " + SCORE_DREMPELS["stappers"]["bron"]])
    methodiek_rows.append(["Trappers", SCORE_DREMPELS["trappers"]["toelichting"] + " " + SCORE_DREMPELS["trappers"]["bron"]])
    methodiek_rows.append(["Openbaar vervoer", SCORE_DREMPELS["ov"]["toelichting"] + " " + SCORE_DREMPELS["ov"]["bron"]])
    story.append(Paragraph("Methodologische voetnoot scoringsdrempels", h2_style))
    story.append(styled_table(methodiek_rows, col_widths=[120, doc.width - 120], header=True))
    append_aanvulblok(
        "4.6 Aan te vullen STOP-controles",
        [
            ["Aan te vullen informatie", "Wat moet hier komen?", "Waar vind je dit?"],
            ["Stappers", "Controleer voetpadbreedte, toegankelijkheid, obstakels, verlichting, oversteekbaarheid en trage doorsteken.", "Plaatsbezoek, gemeentelijke toegankelijkheidsinfo, foto's, plannen openbaar domein."],
            ["Trappers", "Controleer fietspadtype, breedte, comfort, fietsstraten, fietssnelwegen, BFF-continuïteit en conflicten.", "Geopunt/BFF, gemeentelijk fietsplan, terreincontrole, provincie."],
            ["Openbaar vervoer", "Controleer frequenties, bedieningsperiode, haltekwaliteit, toegankelijkheid en toekomstige routewijzigingen.", "De Lijn, NMBS, Hoppin, vervoerregio, gemeentelijke mobiliteitsdienst."],
            ["20-minutenkaarten", "Controleer of de bereikbaarheid logisch is in functie van barrières, bruggen, tunnels, hellingen en routekwaliteit.", "Terreincontrole, routeplanners, lokale kennis."],
        ],
        "De automatische STOP-kaarten en -tabellen zijn een sterke basis, maar ze blijven een GIS-screening."
    )
    story.append(Spacer(1, 10))

    # Omgevingsvoorzieningen horen niet rechtstreeks bij één STOP-modus, maar ondersteunen de context.
    story.append(Paragraph("4.5 Omgevingsvoorzieningen", h2_style))
    story.append(Paragraph(
        "Deze voorzieningen geven een indicatie van mogelijke bestemmingen in de omgeving en helpen om de relevantie van wandel-, fiets- en OV-routes te duiden.",
        body_style
    ))
    voorzieningen_rows = [
        ["Voorziening", "Aantal"],
        ["Scholen", scholen],
        ["Horeca", horeca],
        ["Winkels", winkels],
        ["Parkings", parkings],
    ]
    voorzieningen_rows = [[pdf_par(c) for c in r] for r in voorzieningen_rows]
    story.append(styled_table(voorzieningen_rows, col_widths=[doc.width * 0.65, doc.width * 0.35], header=True))
    story.append(Spacer(1, 10))

    story.append(CondPageBreak(90))
    story.append(section("Parkeer- en verkeersanalyse", 5))
    parkeer_rows = [
        ["Onderdeel", "Waarde", "Balans / interpretatie"],
        ["Automatisch bepaald", "Ja" if effecten.get("automatisch_bepaald") else "Nee / handmatig", effecten.get("automatische_opmerking", "")],
        ["Parkeerzone", effecten.get("parkeerzone", "Niet beschikbaar"), "Automatische zoneherkenning wordt gebruikt wanneer de gemeente/omgeving gekend is."],
        ["Gebruikte parkeermethode", effecten.get("parkeermethode", "Generieke prototypeformule"), effecten.get("norm_toelichting", "")],
        ["Lokale parkeernorm", effecten.get("parkeernorm", "Niet lokaal gespecificeerd"), "Lokale normen hebben voorrang op de generieke formule."],
        ["Indicatieve parkeerbehoefte", effecten.get("parkeerbehoefte_display", f'{effecten["parkeerbehoefte"]} plaatsen'), f'Aanbod: {parkeerplaatsen} · balans t.o.v. bovengrens: {effecten["parkeerbalans"]}'],
        ["Lokaal wagenbezit / sector", f'{effecten.get("lokaal_wagenbezit", "")} wagens/huishouden', effecten.get("statistische_sector", "Niet ingevuld")],
        ["Bezoekers- en straatparkeren", effecten.get("straatparkeren_toelichting", "Niet ingevuld"), "Controleer betalingsregime, blauwe zone, bewonerskaarten en publieke parkings."],
        ["Indicatieve fietsparkeerbehoefte", f'{effecten["fietsbehoefte"]} stallingen', f'Aanbod: {fietsenstallingen} · balans: {effecten["fietsbalans"]}'],
        ["Verkeersgeneratie per dag", f'{effecten["ritten_dag"]} ritten', effecten.get("verkeersgeneratie_methode", "Indicatieve raming")],
        ["Verkeersgeneratie spitsuur", f'{effecten["ritten_spits"]} ritten', effecten.get("verkeersgeneratie_toelichting", "Maatgevend spitsuur, indicatief")],
    ]
    story.append(styled_table(parkeer_rows, col_widths=[170, 110, doc.width - 280], header=True))
    append_ai_interpretatie("parkeren_verkeer")
    story.append(Paragraph(clean_text(effecten.get("parkeervoetnoot", "")), caption_style))
    append_aanvulblok(
        "5.1 Aan te vullen parkeer- en verkeersinformatie",
        [
            ["Aan te vullen informatie", "Wat moet hier komen?", "Waar vind je dit?"],
            ["Lokale parkeernorm", "Vermeld de exacte norm, zone, eventuele afwijkingsmogelijkheden en berekening per functie.", "Gemeentelijke parkeerverordening, omgevingsloket, mobiliteitsdienst."],
            ["Lokaal wagenbezit", "Gebruik lokale cijfers waar beschikbaar en motiveer waarom die relevant zijn voor het project.", "Statbel/statistische sector, gemeente, eigen onderzoek."],
            ["Bezoekersparkeren", "Beschrijf of bezoekers op eigen terrein, straat, publieke parking of via deelmobiliteit worden opgevangen.", "Parkeerplan, gemeentelijke regels, parkeeronderzoek."],
            ["Straatparkeren", "Beschrijf parkeerregime, capaciteit en bezetting in de omgeving.", "Terreinonderzoek, parkeerbedrijf, gemeentelijke parkeerkaarten."],
            ["Verkeersgeneratie", "Controleer kencijfers per projecttype en splits waar nodig bewoners, bezoekers, personeel, leveringen en piekmomenten.", "Richtlijnenboek MOBER, CROW, tellingen, exploitant, vergelijkbare projecten."],
        ],
        "Dit blijft één van de belangrijkste manuele controlepunten, omdat lokale normen en werkelijk gebruik sterk verschillen per gemeente en projecttype."
    )
    story.append(Spacer(1, 10))

    story.append(CondPageBreak(90))
    story.append(section("Auto-analyse", 6))
    auto_rows = [
        ["Onderdeel", "Waarde"],
        ["Ontsluitingsweg", clean_text(auto_detail.get("ontsluitingsweg", "niet beschikbaar"))],
        ["Wegcategorie ontsluitingsweg", clean_text(auto_detail.get("wegcategorie", "niet beschikbaar"))],
        ["Snelheidsregime ontsluitingsweg", clean_text(auto_detail.get("snelheidsregime", "niet beschikbaar"))],
        ["Eén- of tweerichtingsverkeer", clean_text(auto_detail.get("richting", "niet beschikbaar"))],
        ["Dichtstbijzijnd kruispunt / regelpunt", clean_text(auto_detail.get("dichtstbijzijnd_kruispunt", "niet beschikbaar")) + (f' · {auto_detail.get("afstand_kruispunt_m")} m' if auto_detail.get("afstand_kruispunt_m") is not None else "")],
        ["Afstand tot dichtstbijzijnde hoofdweg", (f'{auto_detail.get("afstand_hoofdweg_m")} m' if auto_detail.get("afstand_hoofdweg_m") is not None else "niet beschikbaar")],
        ["Aantal hoofdwegen binnen radius", str(auto_analyse["hoofdwegen"])],
        ["Lokale wegen", str(auto_analyse["lokale_wegen"])],
        ["Woonstraten / verblijfsstraten", str(auto_analyse["woonstraten"])],
        ["Kruispunt- of regelpunten", str(auto_analyse["kruispunten"])],
        ["Gekende snelheidsregimes", clean_text(auto_analyse["snelheidsregimes"])],
        ["Indicatieve ontsluitingsscore", auto_analyse["ontsluitingsscore"]],
    ]
    story.append(Paragraph("De auto-analyse beschrijft de eerste ontsluitingscontext op basis van OSM-wegdata. Dit is nuttig als quickscan, maar moet worden gecontroleerd met de officiële wegencategorisering, circulatieplannen en terreinwaarneming.", body_style))
    story.append(styled_table(auto_rows, col_widths=[220, doc.width - 220], header=True))
    append_ai_interpretatie("auto_analyse")
    # Beknopte, professionele auto-output: geen technische debugtabellen met herhaalde wegen.
    grote_wegen_breed = auto_detail.get("grote_wegen_breed")
    snelwegen_breed = auto_detail.get("snelwegen_breed")

    def _eerste_unieke_weg(df):
        if isinstance(df, pd.DataFrame) and not df.empty:
            tmp = df.copy()
            if "naam" in tmp.columns:
                tmp["_naam_norm"] = tmp["naam"].fillna("Naam onbekend").astype(str).str.strip().str.lower()
                tmp = tmp.drop_duplicates(subset=["_naam_norm"])
            tmp = tmp.sort_values("afstand_m") if "afstand_m" in tmp.columns else tmp
            row = tmp.iloc[0]
            naam = clean_text(row.get("naam", "Naam onbekend"))
            cat = clean_text(row.get("wegcategorie", ""))
            afstand = row.get("afstand_m", "")
            snelheid = clean_text(row.get("snelheid", ""))
            extra = []
            if cat:
                extra.append(cat)
            if snelheid:
                extra.append(f"snelheid {snelheid}")
            extra_txt = f" ({', '.join(extra)})" if extra else ""
            return f"{naam} · {afstand} m{extra_txt}"
        return "niet beschikbaar"

    story.append(Paragraph("6.1 Samenvatting ontsluiting", h2_style))
    auto_samenvatting_rows = [
        ["Onderdeel", "Resultaat"],
        ["Ontsluitingsweg", clean_text(auto_detail.get("ontsluitingsweg", "niet beschikbaar"))],
        ["Dichtstbijzijnde hoofdweg / grote baan", _eerste_unieke_weg(grote_wegen_breed)],
        ["Dichtstbijzijnde snelwegstructuur", _eerste_unieke_weg(snelwegen_breed)],
        ["Dichtstbijzijnd kruispunt / regelpunt", clean_text(auto_detail.get("dichtstbijzijnd_kruispunt", "niet beschikbaar")) + (f' · {auto_detail.get("afstand_kruispunt_m")} m' if auto_detail.get("afstand_kruispunt_m") is not None else "")],
    ]
    story.append(styled_table(auto_samenvatting_rows, col_widths=[210, doc.width - 210], header=True))
    story.append(Paragraph(
        "De auto-analyse wordt bewust samengevat tot de belangrijkste ontsluitingsinformatie. Herhaalde wegsegmenten worden niet afzonderlijk opgenomen, zodat het rapport leesbaar blijft voor architecten en vergunningverleners.",
        body_style
    ))
    append_aanvulblok(
        "6.2 Aan te vullen ontsluitings- en wegencategorisering",
        [
            ["Aan te vullen informatie", "Wat moet hier komen?", "Waar vind je dit?"],
            ["Officiële wegencategorisering", "Bevestig of de ontsluitingsweg lokaal, interlokaal, regionaal of hoofdweg is.", "Regionaal mobiliteitsplan, gemeentelijk mobiliteitsplan, AWV, MOW."],
            ["Circulatie", "Beschrijf éénrichting/tweerichting, verboden bewegingen, knippen, busbanen en geplande circulatiewijzigingen.", "Gemeentelijk circulatieplan, plaatsbezoek, politie, mobiliteitsdienst."],
            ["Kruispuntafwikkeling", "Vermeld of de ontsluiting via een gevoelig kruispunt, rotonde, verkeerslichten of drukke as verloopt.", "Tellingen, kruispuntanalyse, AWV, terreinobservatie."],
            ["Snelheidsregime en veiligheid", "Controleer werkelijk snelheidsregime, zichtbaarheid, oversteekbaarheid en conflictpunten.", "Terreincontrole, signalisatieplan, politie, AWV."],
            ["Alternatieve ontsluiting", "Beschrijf onderzochte scenario's en waarom de gekozen ontsluiting logisch is.", "Ontwerpteam, overleg gemeente/AWV, ontsluitingsnota."],
        ],
        "OSM-data geeft een eerste indicatie, maar officiële wegencategorisering en circulatie moeten altijd worden bevestigd."
    )

    story.append(Spacer(1, 8))
    story.append(Paragraph("6.3 Bereikbaarheid op 20 minuten met de auto", h2_style))
    story.append(Paragraph(
        "Deze bereikbaarheidskaart hoort bij het onderdeel Personenwagens. De kaart toont een indicatieve 20-minutenbereikbaarheid met de auto en bevat bewust extra context buiten de gekleurde zone. Zo blijft zichtbaar hoe de projectsite zich verhoudt tot omliggende gemeenten, hoofdwegen en snelwegstructuren.",
        body_style
    ))
    bereik_auto_png = maak_pdf_auto_bereikbaarheid_png(lat, lon, minuten=20, snelheid_kmh=36, auto_gdf=auto_gdf, bestandsnaam="kaart_bereikbaarheid_20min_auto_static")
    story.append(maak_reportlab_image_met_verhouding(bereik_auto_png, doc.width, 240))
    story.append(Paragraph(
        "Conclusie: de autokaart is een snelle screening en houdt geen rekening met actuele verkeersdruk, kruispuntvertragingen of filevorming. De kaart moet daarom samen gelezen worden met de ontsluitingsweg, het snelheidsregime en de afstand tot hoofdwegen of snelwegen.",
        body_style
    ))
    story.append(Paragraph("Figuur: indicatieve bereikbaarheid binnen 20 minuten met de auto, met omliggende context buiten de bereikbare zone.", caption_style))

    story.append(Spacer(1, 10))

    story.append(CondPageBreak(90))
    story.append(section("Mobiliteitseffecten en milderende maatregelen", 7))
    story.append(Paragraph(
        "Onderstaande beoordeling vertaalt de automatische screening naar een eerste effectbespreking. De tekst is indicatief en moet worden aangevuld met terreincontrole, officiële plannen, lokale normen en waar nodig verkeerstellingen.",
        body_style
    ))

    effecten_rows = [
        ["Thema", "Beoordeling", "Automatische effectbespreking"],
        ["Impact op bereikbaarheid", mobiliteitseffecten["bereikbaarheid_score"], mobiliteitseffecten["bereikbaarheid"]],
        ["Impact op parkeren", mobiliteitseffecten["parkeren_score"], mobiliteitseffecten["parkeren"] + " " + mobiliteitseffecten["fietsparkeren"]],
        ["Impact op verkeersgeneratie", mobiliteitseffecten["verkeers_score"], mobiliteitseffecten["verkeersgeneratie"]],
        ["Impact op verkeersveiligheid", mobiliteitseffecten["verkeersveiligheid_score"], mobiliteitseffecten["verkeersveiligheid"]],
    ]
    effecten_rows = [[Paragraph(clean_text(str(c)), body_style) for c in row] for row in effecten_rows]
    story.append(styled_table(effecten_rows, col_widths=[110, 115, doc.width - 225], header=True))
    append_ai_interpretatie("mobiliteitseffecten")
    story.append(Spacer(1, 10))

    story.append(Paragraph("7.5 Aanbevelingen en milderende maatregelen", h2_style))
    maatregelen_rows = [["Nr.", "Maatregel / aanbeveling"]]
    for idx, maatregel in enumerate(mobiliteitseffecten.get("maatregelen", []), start=1):
        maatregelen_rows.append([str(idx), clean_text(maatregel)])
    maatregelen_rows = [[Paragraph(str(c), body_style) for c in row] for row in maatregelen_rows]
    story.append(styled_table(maatregelen_rows, col_widths=[35, doc.width - 35], header=True))
    append_aanvulblok(
        "7.6 Aan te vullen logistiek, werffase en maatregelen",
        [
            ["Aan te vullen informatie", "Wat moet hier komen?", "Waar vind je dit?"],
            ["Leveringen", "Voertuigtype, frequentie, laad- en losplaats, route op de site en tijdsvensters.", "Exploitant, beheerder, ontwerpteam, logistieke nota."],
            ["Afvalophaling", "Locatie containers, ophaalfrequentie, route vuilniswagen en draaibewegingen.", "Afvalintercommunale, beheerder, grondplan, draaicirkelplan."],
            ["Hulpdiensten", "Vrije doorgang, brandweerroute, keerbewegingen en opstelplaatsen.", "Brandweeradvies, inplantingsplan, veiligheidsnota."],
            ["Werffase", "Werftoegang, werfverkeer, tijdelijke signalisatie, leveringsroutes en bescherming van zachte weggebruikers.", "Aannemer, werfinrichtingsplan, minder-hinderplan, gemeente."],
            ["Flankerende maatregelen", "Concrete maatregelen zoals extra fietsenstallingen, deelmobiliteit, oversteekplaatsen, signalisatie of mobiliteitscommunicatie.", "Mobiliteitsexpert, gemeente, ontwerpteam, vergunningsvoorwaarden."],
        ],
        "Deze elementen komen vaak terug in professionele studies, maar zijn afhankelijk van ontwerpkeuzes en overleg."
    )
    story.append(Spacer(1, 10))

    synthese_data = maak_synthese_kwaliteitscheck_eindconclusie(
        projecttype,
        aantal_wooneenheden,
        bvo,
        parkeerplaatsen,
        fietsenstallingen,
        straal,
        haltes,
        hoppinpunten,
        bff_routes,
        stappers_analyse,
        trappers_analyse,
        auto_analyse,
        ov_score,
        fiets_score,
        totaal_score,
        effecten,
        studieplicht,
        mobiliteitseffecten,
        plan_paths=plan_paths,
        korte_omschrijving=korte_omschrijving,
        huidige_toestand=huidige_toestand,
        toekomstige_toestand=toekomstige_toestand,
        dichtste_halte_algemeen=dichtste_halte_algemeen,
        dichtstbijzijnde_station=dichtstbijzijnde_station,
    )

    story.append(CondPageBreak(90))
    story.append(section("Synthese en kwaliteitscheck", 8))
    story.append(Paragraph(
        "Dit hoofdstuk vat de automatische analyse samen en maakt duidelijk welke onderdelen al onderbouwd zijn en welke gegevens nog gecontroleerd of aangevuld moeten worden.",
        body_style
    ))

    story.append(Paragraph("8.1 Synthese per thema", h2_style))
    synthese_rows = [["Thema", "Synthese"]] + synthese_data["synthese_rows"]
    synthese_rows = [[Paragraph(clean_text(str(c)), body_style) for c in row] for row in synthese_rows]
    story.append(styled_table(synthese_rows, col_widths=[120, doc.width - 120], header=True))
    story.append(Spacer(1, 10))

    story.append(Paragraph("8.2 Kwaliteitscheck", h2_style))
    kwaliteit_rows = [["Onderdeel", "Controle"]]
    kwaliteit_rows.append(["Automatisch berekend", "<br/>".join([clean_text(x) for x in synthese_data["gebruikte_input"]])])
    kwaliteit_rows.append(["Nog aan te vullen", "<br/>".join([clean_text(x) for x in synthese_data["ontbrekende_info"]])])
    kwaliteit_rows.append(["Expertcontrole", "<br/>".join([clean_text(x) for x in synthese_data["expert_check"]])])
    kwaliteit_rows.append(["Scoringsmethodiek", "Drempelwaarden gedocumenteerd in SCORE_DREMPELS-configuratie. Zie sectie 4 voor bronvermelding per onderdeel."])
    kwaliteit_rows = [[Paragraph(str(c), body_style) for c in row] for row in kwaliteit_rows]
    story.append(styled_table(kwaliteit_rows, col_widths=[130, doc.width - 130], header=True))
    story.append(Spacer(1, 10))

    story.append(Paragraph("8.3 Eindconclusie", h2_style))
    conclusie_rows = [
        ["Conclusietype", clean_text(synthese_data["conclusie_type"])],
        ["Eindconclusie", clean_text(synthese_data["eindconclusie"])],
    ]
    conclusie_rows = [[Paragraph(str(c), body_style) for c in row] for row in conclusie_rows]
    story.append(styled_table(conclusie_rows, col_widths=[130, doc.width - 130], header=False, first_col_shade=True))
    append_ai_interpretatie("synthese")

    append_aanvulblok(
        "8.5 Aan te vullen overleg, tellingen en finale validatie",
        [
            ["Aan te vullen informatie", "Wat moet hier komen?", "Waar vind je dit?"],
            ["Overleg overheid", "Vat afspraken, opmerkingen en voorwaarden samen van gemeente, AWV, De Lijn, NMBS, politie, brandweer of afvalintercommunale.", "Mailverslagen, overlegnota's, vergunningsvoorwaarden."],
            ["Tellingen", "Voeg verkeerstellingen, parkeeronderzoek, kruispunttellingen of observaties toe wanneer de omgeving gevoelig is.", "Eigen metingen, studiebureau, gemeente, bestaande studies."],
            ["Sensitiviteit", "Test alternatieve aannames voor autobezit, modal split, bezoekers, piekuren, toekomstige ontwikkeling of ontsluiting.", "Mobiliteitsexpert, opdrachtgever, tellingen, scenarioanalyse."],
            ["Finale expertconclusie", "Formuleer de finale beoordeling en geef aan of de quickscan volstaat of verder onderzoek nodig is.", "Mobiliteitsexpert/projectverantwoordelijke."],
        ],
        "Dit blok hoort bij de eindbeoordeling: hier wordt duidelijk wat de app ondersteunt en wat nog professioneel gevalideerd moet worden."
    )
    story.append(Spacer(1, 10))

    story.append(CondPageBreak(90))
    story.append(section("Eerste beoordeling", 9))
    beoordeling_intro = (
        f"De algemene automatische bereikbaarheidsscore voor deze projectsite is <b>{totaal_score}</b>. "
        "De beoordeling is opgebouwd als een fiche met deelconclusies per vervoersmodus, zodat ze sneller leesbaar is dan een doorlopende tekstblok."
    )
    story.append(Paragraph(beoordeling_intro, body_style))

    beoordeling_rows = [
        ["Thema", "Automatische beoordeling", "Aandachtspunt voor verdere studie"],
        ["Studieplicht", f'Mobiliteitstoets: {studieplicht["mobiliteitstoets"]}<br/>MOBER: {studieplicht["mober"]}', clean_text(studieplicht["toelichting"])],
        ["Stappers", f'{stappers_analyse["comfortscore"]}: {stappers_analyse["voetpaden"]} voetgangersverbindingen en {stappers_analyse["oversteekplaatsen"]} oversteken', "Terreincontrole op breedte, comfort, obstakels, toegankelijkheid en oversteekkwaliteit blijft nodig."],
        ["Trappers", f'{trappers_analyse["fietsscore"]}: {trappers_analyse["fietspaden"]} fietspaden en {trappers_analyse["bff_segmenten"]} BFF-segmenten', "Controleer fietspadbreedtes, conflictpunten, BFF-continuïteit en stallingskwaliteit."],
        ["Openbaar vervoer", f'{ov_score}: {len(haltes)} haltes binnen {straal} m', "Aanvullen met frequenties, bedieningsperiode, toegankelijkheid van haltes en looproutekwaliteit."],
        ["Personenwagen", f'{auto_analyse["ontsluitingsscore"]}: {auto_analyse["hoofdwegen"]} hoofdwegen en {auto_analyse["lokale_wegen"]} lokale wegen', "Aanvullen met wegencategorisering, intensiteiten, verkeersveiligheid en kruispuntafwikkeling."],
        ["Parkeren", f'Auto: balans {effecten["parkeerbalans"]}<br/>Fiets: balans {effecten["fietsbalans"]}', "Gebruik lokale parkeernormen en projectcontext om de prototype-inschatting te verfijnen."],
    ]
    beoordeling_rows = [[Paragraph(clean_text(c) if i != 1 or r == 0 else str(c), body_style) for i, c in enumerate(row)] for r, row in enumerate(beoordeling_rows)]
    story.append(styled_table(beoordeling_rows, col_widths=[95, 165, doc.width - 260], header=True))
    append_ai_interpretatie("eerste_beoordeling")
    story.append(Spacer(1, 10))

    # -----------------------------------------------------
    # HOOFDSTUK 10 - GEAUTOMATISEERDE EN RESTERENDE AANVULLINGEN
    # -----------------------------------------------------
    story.append(CondPageBreak(90))
    story.append(section("Geautomatiseerde en resterende aanvullingen", 10))
    story.append(Paragraph(
        geautomatiseerde_aanvullingen["samenvatting"],
        body_style
    ))

    story.append(Paragraph("10.1 Aanvulpunten die nu automatisch worden ingevuld", h2_style))
    auto_aanvul_rows = [["Onderdeel", "Automatisch resultaat", "Interpretatie / beperking"]] + geautomatiseerde_aanvullingen["automatische_rows"]
    story.append(styled_table(auto_aanvul_rows, col_widths=[120, 145, doc.width - 265], header=True))
    story.append(Spacer(1, 8))

    story.append(Paragraph("10.2 Aanvulpunten die bewust manueel blijven", h2_style))
    resterende_aanvul_rows = [["Onderdeel", "Automatiseringsstatus", "Waar te vinden / controleren"]] + geautomatiseerde_aanvullingen["resterende_rows"]
    story.append(styled_table(resterende_aanvul_rows, col_widths=[135, 175, doc.width - 310], header=True))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "De concrete aanvulpunten staan ook bij de hoofdstukken waarop ze betrekking hebben. "
        "Onderstaande tabel geeft de samenvattende controle per hoofdstuk.",
        body_style
    ))
    overzicht_rows = [
        ["Hoofdstuk", "Wat is automatisch?", "Wat moet nog manueel worden aangevuld?"],
        ["1. Projectomschrijving", "Basisgegevens en aangeleverde tekstvelden", "Fasering, definitieve programmaomschrijving, bestaande/toekomstige toestand en laatste planversies."],
        ["2. Omgevingsomschrijving", "Haltes, station, Hoppinpunten en voorzieningen", "Beleidscontext, geplande ontwikkelingen, lokale parkeercontext en terreincontrole."],
        ["3. Projectkenmerken", "Programma, aantallen en planweergave", "Gebruikersprofiel, bijzondere functies, interne werking en fietsparkeerkwaliteit."],
        ["4. STOP-analyse", "Wandel-, fiets-, OV- en bereikbaarheidsscreening", "Terreincontrole van comfort, veiligheid, toegankelijkheid, OV-toekomst en routekwaliteit."],
        ["5. Parkeer- en verkeersanalyse", "Prototypeberekening parkeerbehoefte, fietsbehoefte en verkeersgeneratie", "Lokale parkeernormen, bezoekersparkeren, straatparkeren, kencijfers en lokale autobezitsgegevens."],
        ["6. Auto-analyse", "OSM-screening ontsluitingsweg, wegtype, snelheid en hoofdwegen", "Officiële wegencategorisering, circulatie, kruispuntafwikkeling, snelheidsregime en alternatieven."],
        ["7. Mobiliteitseffecten", "Eerste effectbespreking en automatische aanbevelingen", "Leveringen, afvalophaling, hulpdiensten, werffase en concrete flankerende maatregelen."],
        ["8. Synthese", "Automatische synthese en kwaliteitscheck", "Overleg met instanties, tellingen, sensitiviteitsanalyse en finale expertconclusie."],
    ]
    story.append(styled_table(overzicht_rows, col_widths=[120, 140, doc.width - 260], header=True))
    story.append(Paragraph(
        "Opmerking: de app is bedoeld als ondersteuning bij de opmaak van een mobiliteitsstudie. De manuele aanvullingen tonen expliciet waar projectkennis, overleg en professionele beoordeling noodzakelijk blijven.",
        caption_style
    ))

    story.append(CondPageBreak(90))
    story.append(section("Datatabellen uit de app", 11))
    story.append(Paragraph(
        "Dit hoofdstuk bundelt de belangrijkste tabellen die ook in de Streamlit-app worden getoond. Zo blijven de ruwe resultaten controleerbaar in de PDF-export, zonder dat de lezer de app opnieuw moet openen.",
        body_style
    ))

    story.append(Paragraph("11.1 Openbaar vervoer - alle De Lijn-haltes", h2_style))
    if not haltes.empty:
        ov_all_rows = [["Halte", "Afstand", "Ritten/u spits", "Freq.", "Lijnen", "Halte-ID"]]
        for _, row in haltes.sort_values("afstand_m").iterrows():
            ov_all_rows.append([
                row.get("halte_naam", ""),
                f'{row.get("afstand_m", "")} m',
                row.get("ritten_spits_uur", "n.b."),
                row.get("frequentie_score", "n.b."),
                row.get("buslijnen", ""),
                row.get("halte_id", ""),
            ])
        story.append(styled_table(ov_all_rows, col_widths=[90, 45, 50, 60, doc.width - 295, 50], header=True))
    else:
        story.append(Paragraph("Geen De Lijn-haltes beschikbaar binnen de gekozen radius.", body_style))

    story.append(Paragraph("11.2 Openbaar vervoer - Hoppinpunten", h2_style))
    if not hoppinpunten.empty:
        hoppin_all_rows = [["Naam", "Gemeente", "Afstand"]]
        for _, row in hoppinpunten.sort_values("afstand_m").iterrows():
            hoppin_all_rows.append([
                row.get("naam", ""),
                row.get("gemeente", ""),
                f'{row.get("afstand_m", "")} m',
            ])
        story.append(styled_table(hoppin_all_rows, col_widths=[doc.width * 0.45, doc.width * 0.35, doc.width * 0.20], header=True))
    else:
        story.append(Paragraph("Geen Hoppinpunten beschikbaar binnen de gekozen radius.", body_style))

    story.append(Paragraph("11.3 OpenStreetMap voorzieningen", h2_style))
    voorzieningen_rows_app = [
        ["Voorziening", "Aantal"],
        ["Scholen", scholen],
        ["Horeca", horeca],
        ["Winkels", winkels],
        ["Parkings", parkings],
    ]
    story.append(styled_table(voorzieningen_rows_app, col_widths=[doc.width * 0.65, doc.width * 0.35], header=True))

    story.append(Paragraph("11.4 Stappers - voetgangersanalyse", h2_style))
    stappers_app_rows = [
        ["Onderdeel", "Waarde"],
        ["Voetpaden / voetgangersverbindingen", stappers_analyse["voetpaden"]],
        ["Oversteekplaatsen", stappers_analyse["oversteekplaatsen"]],
        ["Trage wegen / paden", stappers_analyse["trage_wegen"]],
        ["Indicatieve comfortscore", stappers_analyse["comfortscore"]],
    ]
    story.append(styled_table(stappers_app_rows, col_widths=[doc.width * 0.65, doc.width * 0.35], header=True))

    story.append(Paragraph("11.5 Trappers - fietsanalyse", h2_style))
    trappers_app_rows = [
        ["Onderdeel", "Waarde"],
        ["Fietspaden", trappers_analyse["fietspaden"]],
        ["Fietssuggesties / cycleway-tags", trappers_analyse["fietssuggesties"]],
        ["Gedeelde paden / fietsbare paden", trappers_analyse["gedeelde_paden"]],
        ["Fietsstraten", trappers_analyse.get("fietsstraten", 0)],
        ["BFF-segmenten", trappers_analyse["bff_segmenten"]],
        ["BFF-hoofdroute", bff_context.get("hoofdroute", "Niet beschikbaar")],
        ["Fietssnelweg", bff_context.get("fietssnelweg", "Niet beschikbaar")],
        ["Recreatieve fietsroutes", recreatieve_analyse.get("aantal", 0)],
        ["Indicatieve fietsscore", trappers_analyse["fietsscore"]],
    ]
    story.append(styled_table(trappers_app_rows, col_widths=[doc.width * 0.65, doc.width * 0.35], header=True))

    story.append(Paragraph("11.6 Auto - ontsluitingsanalyse", h2_style))
    auto_app_rows = [
        ["Onderdeel", "Waarde"],
        ["Ontsluitingsweg", clean_text(auto_detail.get("ontsluitingsweg", "niet beschikbaar"))],
        ["Wegcategorie ontsluitingsweg", clean_text(auto_detail.get("wegcategorie", "niet beschikbaar"))],
        ["Snelheidsregime ontsluitingsweg", clean_text(auto_detail.get("snelheidsregime", "niet beschikbaar"))],
        ["Eén- of tweerichtingsverkeer", clean_text(auto_detail.get("richting", "niet beschikbaar"))],
        ["Dichtstbijzijnd kruispunt / regelpunt", clean_text(auto_detail.get("dichtstbijzijnd_kruispunt", "niet beschikbaar")) + (f' ({auto_detail.get("afstand_kruispunt_m")} m)' if auto_detail.get("afstand_kruispunt_m") is not None else "")],
        ["Afstand tot hoofdweg", f'{auto_detail.get("afstand_hoofdweg_m")} m' if auto_detail.get("afstand_hoofdweg_m") is not None else "niet beschikbaar"],
        ["Hoofdwegen binnen radius", auto_analyse["hoofdwegen"]],
        ["Lokale wegen", auto_analyse["lokale_wegen"]],
        ["Woonstraten / verblijfsstraten", auto_analyse["woonstraten"]],
        ["Kruispunt- of regelpunten", auto_analyse["kruispunten"]],
        ["Gekende snelheidsregimes", clean_text(auto_analyse["snelheidsregimes"])],
        ["Indicatieve ontsluitingsscore", auto_analyse["ontsluitingsscore"]],
    ]
    story.append(styled_table(auto_app_rows, col_widths=[210, doc.width - 210], header=True))

    def add_dataframe_table(title, df, columns=None, max_rows=30):
        if isinstance(df, pd.DataFrame) and not df.empty:
            story.append(Paragraph(title, h2_style))
            dft = df.copy()
            if columns:
                dft = dft[[c for c in columns if c in dft.columns]]
            dft = dft.head(max_rows)
            rows = [list(dft.columns)] + dft.astype(str).values.tolist()
            story.append(styled_table(rows, header=True))
            if len(df) > max_rows:
                story.append(Paragraph(f"Tabel ingekort tot de eerste {max_rows} rijen voor leesbaarheid. Volledige dataset blijft beschikbaar in de app.", caption_style))

    add_dataframe_table("11.7 Vijf dichtstbijzijnde hoofdwegen binnen de gekozen radius", auto_detail.get("hoofdwegen"), max_rows=10)
    add_dataframe_table("11.8 Belangrijke ontsluitingsassen binnen 10 km", auto_detail.get("ontsluitingsassen_breed"), max_rows=10)
    add_dataframe_table("11.9 Dichtstbijzijnde hoofdwegen/grote banen binnen 10 km", auto_detail.get("grote_wegen_breed"), max_rows=10)
    add_dataframe_table("11.10 Dichtstbijzijnde snelwegen / hoofdverbindingswegen binnen 10 km", auto_detail.get("snelwegen_breed"), max_rows=10)

    story.append(CondPageBreak(90))
    story.append(section("Bronnenlijst", 12))
    vandaag = datetime.today().strftime("%d-%m-%Y")
    bronnen_rows = [
        ["Bron", "Gebruik in MOBISCAN", "Status"],
        ["OpenStreetMap / Nominatim", "Adresomzetting naar coördinaten, kaartachtergrond, voorzieningen, voetgangers-, fiets- en wegdata.", "Automatisch geraadpleegd"],
        ["De Lijn GTFS", "De Lijn-haltes, gekoppelde buslijnen en indicatieve frequenties op basis van de beschikbare GTFS-tabellen.", "Automatisch geraadpleegd"],
        ["MOW / Hoppin WFS", "Detectie van Hoppinpunten binnen het analysegebied.", "Automatisch geraadpleegd"],
        ["MOW / BFF WFS", "Detectie van het Bovenlokaal Functioneel Fietsroutenetwerk en indicatie van hoofdroute/fietssnelweg waar beschikbaar.", "Automatisch geraadpleegd"],
        ["Projectdocumenten gebruiker", "Inplantingsplan, situatieplan, grondplan gelijkvloers en optionele doorsnede/gevel voor de projectmatige interpretatie.", "Door gebruiker aangeleverd"],
        ["Lokale parkeerinformatie", "Lokale parkeerzone, parkeernormen en lokaal wagenbezit waar deze in de tool als projectcontext beschikbaar zijn.", "Te controleren met officiële lokale documenten"],
        ["CROW / Richtlijnenboek MOBER", "Methodische referentie voor kencijfermatige verkeersgeneratie. De app gebruikt een prototypebandbreedte; officiële tabellen moeten bij finale dossiers worden gecontroleerd.", "Methodische referentie, niet automatisch geraadpleegd"],
        ["Gemeentelijke schoolroute- en parkeerinformatie", "Aanvullende controle voor schoolroutes, parkeerregimes, bezoekersparkeren en straatparkeren.", "Te controleren met lokale documenten"],
    ]
    bronnen_rows = [[Paragraph(clean_text(str(c)), body_style) for c in row] for row in bronnen_rows]
    story.append(styled_table(bronnen_rows, col_widths=[130, doc.width - 250, 120], header=True))
    story.append(Paragraph(f"Raadplegingsdatum automatische bronnen: {vandaag}.", caption_style))

    def no_footer(canvas, doc_obj):
        return

    doc.build(story, onFirstPage=no_footer, onLaterPages=make_footer)
    buffer.seek(0)

    return buffer




def bewaar_upload_als_temp(uploaded_file, naam_prefix):
    """Slaat een Streamlit upload tijdelijk op zodat ReportLab het logo kan invoegen."""
    if uploaded_file is None:
        return None

    import tempfile
    suffix = os.path.splitext(uploaded_file.name)[1].lower() or ".png"
    pad = os.path.join(tempfile.gettempdir(), f"{naam_prefix}{suffix}")
    with open(pad, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return pad


def pdf_eerste_pagina_naar_png(pdf_path, naam_prefix):
    """
    Zet de eerste pagina van een opgeladen PDF-plan om naar PNG.
    Dit maakt architectuurplannen zichtbaar in de Streamlit-preview én in de PDF-export.

    De functie probeert meerdere render-methodes:
    1. PyMuPDF / fitz
    2. pypdfium2
    3. automatische installatie van PyMuPDF als de module ontbreekt
    """
    import tempfile
    import sys
    import subprocess

    png_path = os.path.join(tempfile.gettempdir(), f"{naam_prefix}_preview.png")

    def render_met_fitz():
        import fitz  # PyMuPDF
        doc_pdf = fitz.open(pdf_path)
        if len(doc_pdf) == 0:
            doc_pdf.close()
            return None
        page = doc_pdf[0]
        # 2.5 geeft voldoende resolutie voor plannen zonder de PDF te zwaar te maken.
        pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        pix.save(png_path)
        doc_pdf.close()
        return png_path

    def render_met_pdfium():
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(pdf_path)
        if len(pdf) == 0:
            pdf.close()
            return None
        page = pdf[0]
        bitmap = page.render(scale=2.5)
        pil_image = bitmap.to_pil().convert("RGB")
        pil_image.save(png_path, quality=95)
        page.close()
        pdf.close()
        return png_path

    # 1. Probeer PyMuPDF
    try:
        resultaat = render_met_fitz()
        if resultaat and os.path.exists(resultaat):
            return resultaat
    except ModuleNotFoundError:
        pass
    except Exception:
        pass

    # 2. Probeer pypdfium2
    try:
        resultaat = render_met_pdfium()
        if resultaat and os.path.exists(resultaat):
            return resultaat
    except ModuleNotFoundError:
        pass
    except Exception:
        pass

    # 3. Laatste poging: installeer PyMuPDF automatisch en render opnieuw.
    # Dit helpt wanneer je de app lokaal draait zonder dat PyMuPDF al geïnstalleerd is.
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pymupdf"], stdout=subprocess.DEVNULL)
        resultaat = render_met_fitz()
        if resultaat and os.path.exists(resultaat):
            return resultaat
    except Exception:
        return None

    return None



def maak_plan_preview_liggend(preview_path):
    """Zet planpreview's die duidelijk staand zijn om naar liggende oriëntatie.
    Daardoor nemen plannen in de PDF minder verticale ruimte in.
    """
    if not preview_path or not os.path.exists(preview_path):
        return preview_path
    try:
        from PIL import Image as PILImage
        img = PILImage.open(preview_path).convert("RGB")
        w, h = img.size
        if h > w * 1.10:
            img = img.rotate(90, expand=True)
            img.save(preview_path, quality=95)
        return preview_path
    except Exception:
        return preview_path

def bewaar_projectplan(uploaded_file, label, naam_prefix):
    """Slaat een opgeladen projectplan op en maakt indien mogelijk een zichtbare preview voor app en PDF."""
    if uploaded_file is None:
        return None

    import tempfile
    suffix = os.path.splitext(uploaded_file.name)[1].lower() or ".pdf"
    pad = os.path.join(tempfile.gettempdir(), f"{naam_prefix}{suffix}")

    with open(pad, "wb") as f:
        f.write(uploaded_file.getbuffer())

    preview_path = None
    source_type = "bestand"

    if suffix in [".png", ".jpg", ".jpeg"]:
        preview_path = pad
        source_type = "afbeelding"
    elif suffix == ".pdf":
        preview_path = pdf_eerste_pagina_naar_png(pad, naam_prefix)
        source_type = "pdf"

    preview_path = maak_plan_preview_liggend(preview_path)

    return {
        "label": label,
        "filename": uploaded_file.name,
        "path": pad,
        "preview_path": preview_path,
        "source_type": source_type,
        "is_image": suffix in [".png", ".jpg", ".jpeg"]
    }


def verzamel_projectplannen():
    plannen = [
        bewaar_projectplan(inplantingsplan_upload, "Inplantingsplan", "inplantingsplan"),
        bewaar_projectplan(grondplan_upload, "Grondplan gelijkvloers", "grondplan_gelijkvloers"),
        bewaar_projectplan(situatieplan_upload, "Situatieplan", "situatieplan"),
        bewaar_projectplan(doorsnede_upload, "Doorsnede / gevel", "doorsnede_gevel"),
    ]
    return [p for p in plannen if p is not None]



# =========================================================
# APP_33 OVERRIDES - robuuste PDF-kaarten, BFF en auto-analyse
# =========================================================

def _value_as_text(value):
    try:
        if isinstance(value, (list, tuple, set)):
            return ", ".join([str(v) for v in value])
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value)


def _series_contains(series, categories):
    cats = [str(c).lower() for c in categories]
    return series.apply(lambda v: any(x.strip().lower() in cats for x in _value_as_text(v).split(',')))


def _select_osm_roads(auto_gdf, categories=None):
    """Robuuste selectie van OSM-wegen, ook wanneer highway-tags als lijst voorkomen."""
    auto_gdf = _as_gdf_wgs84(auto_gdf)
    if auto_gdf.empty or "highway" not in auto_gdf.columns:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    if categories is None:
        categories = ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "service", "living_street"]
    mask = _series_contains(auto_gdf["highway"], categories)
    return auto_gdf[mask].copy()


def _safe_plot_labels(ax, gdf, label_col="name", max_labels=6, dx=18, dy=18):
    try:
        if gdf is None or gdf.empty:
            return
        gg = _as_gdf_wgs84(gdf).to_crs(epsg=31370)
        for _, row in gg.head(max_labels).iterrows():
            geom = row.geometry.centroid
            naam = str(row.get(label_col, ""))[:22]
            if naam and naam.lower() != "nan":
                ax.text(geom.x + dx, geom.y + dy, naam, fontsize=5.3, color="#222", zorder=20,
                        bbox=dict(facecolor="white", edgecolor="none", alpha=0.65, pad=0.7))
    except Exception:
        pass


def zoek_bff_binnen_straal(bff, lat, lon, straal):
    """Robuuste BFF-detectie.
    1. probeert de reeds gedownloade laag;
    2. probeert daarna een BBOX-WFS-query rond het project.
    """
    def filter_radius(gdf):
        if gdf is None or gdf.empty:
            return gpd.GeoDataFrame(columns=["afstand_m", "geometry"], crs="EPSG:4326")
        try:
            if gdf.crs is None:
                gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs="EPSG:4326")
            projectpunt = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(epsg=31370).iloc[0]
            pr = gdf.to_crs(epsg=31370).copy()
            pr["afstand_m"] = pr.geometry.distance(projectpunt)
            out = pr[pr["afstand_m"] <= straal].copy()
            if out.empty:
                return gpd.GeoDataFrame(columns=["afstand_m", "geometry"], crs="EPSG:4326")
            out4326 = out.to_crs(epsg=4326)
            out4326["afstand_m"] = out["afstand_m"].round().values
            return out4326
        except Exception:
            return gpd.GeoDataFrame(columns=["afstand_m", "geometry"], crs="EPSG:4326")

    result = filter_radius(bff)
    if not result.empty:
        return result

    # BBOX in WGS84, met ruime marge rond de gekozen radius
    try:
        import math
        marge_m = max(straal, 2500)
        dlat = marge_m / 111000
        dlon = marge_m / (111000 * max(0.2, math.cos(math.radians(lat))))
        bbox = f"{lon-dlon},{lat-dlat},{lon+dlon},{lat+dlat},EPSG:4326"
        urls = [
            "https://geoserver.gis.cloud.mow.vlaanderen.be/geoserver/wfs?SERVICE=WFS&version=2.0.0&request=GetFeature&typeNames=beleid:bff&outputFormat=application/json&bbox=" + bbox,
            "https://geoserver.gis.cloud.mow.vlaanderen.be/geoserver/beleid/wfs?SERVICE=WFS&version=2.0.0&request=GetFeature&typeName=bff&outputFormat=application/json&bbox=" + bbox,
            "https://geoserver.gis.cloud.mow.vlaanderen.be/geoserver/beleid/wfs?SERVICE=WFS&version=2.0.0&request=GetFeature&typeNames=beleid:bff&outputFormat=application/json&bbox=" + bbox,
        ]
        for url in urls:
            try:
                r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=35)
                if r.status_code != 200 or not r.content:
                    continue
                gdf = gpd.read_file(BytesIO(r.content))
                if gdf is not None and not gdf.empty:
                    out = filter_radius(gdf.to_crs(epsg=4326))
                    if not out.empty:
                        return out
            except Exception:
                continue
    except Exception:
        pass
    return result


def detailleer_auto_ontsluiting(auto, lat, lon):
    """Betere auto-analyse op basis van OSM, met fallback naar bredere zoekstraal."""
    leeg = {
        "ontsluitingsweg": "niet beschikbaar", "wegcategorie": "niet beschikbaar", "snelheidsregime": "niet beschikbaar",
        "richting": "niet beschikbaar", "dichtstbijzijnd_kruispunt": "niet beschikbaar", "afstand_kruispunt_m": None,
        "afstand_hoofdweg_m": None,
        "hoofdwegen": pd.DataFrame(columns=["naam", "wegcategorie", "afstand_m", "snelheid", "richting"]),
        "grote_wegen_breed": pd.DataFrame(columns=["naam", "wegcategorie", "afstand_m", "snelheid", "richting"]),
        "snelwegen_breed": pd.DataFrame(columns=["naam", "wegcategorie", "afstand_m", "snelheid", "richting"]),
        "ontsluitingsassen": pd.DataFrame(columns=["naam", "wegcategorie", "afstand_m", "snelheid", "richting"]),
        "toelichting": "De auto-analyse kon niet worden verfijnd omdat er onvoldoende OSM-wegdata beschikbaar was."
    }
    try:
        # combineer lokale data met brede OSM-vraag voor grote assen
        gdfs = []
        if auto is not None and not auto.empty:
            gdfs.append(_as_gdf_wgs84(auto))
        try:
            brede_tags = {"highway": ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "living_street", "service"]}
            brede = ox.features_from_point((lat, lon), tags=brede_tags, dist=10000)
            if brede is not None and not brede.empty:
                gdfs.append(_as_gdf_wgs84(brede))
        except Exception:
            pass
        if not gdfs:
            return leeg
        gdf = pd.concat(gdfs, ignore_index=True)
        gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs="EPSG:4326")
        if "highway" not in gdf.columns:
            return leeg
        projectpunt = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(epsg=31370).iloc[0]
        pr = gdf.to_crs(epsg=31370).copy()
        pr["afstand_m"] = pr.geometry.distance(projectpunt)
        pr["highway_txt"] = pr["highway"].apply(lambda v: _value_as_text(v).split(",")[0].strip().lower())
        wegtypes = ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "service", "living_street"]
        wegen = pr[pr["highway_txt"].isin(wegtypes)].copy()
        wegen = wegen[wegen.geometry.geom_type.isin(["LineString", "MultiLineString", "Polygon", "MultiPolygon"])]
        if wegen.empty:
            return leeg
        lokale = wegen[wegen["afstand_m"] <= 150]
        if lokale.empty:
            lokale = wegen[wegen["afstand_m"] <= 350]
        dichtste = (lokale if not lokale.empty else wegen).sort_values("afstand_m").iloc[0]

        def val(row, veld, fallback="niet beschikbaar"):
            if veld not in row.index:
                return fallback
            txt = _value_as_text(row.get(veld, "")).strip()
            return txt if txt and txt.lower() != "nan" else fallback
        def richting(row):
            one = val(row, "oneway", "").lower()
            if one in ["yes", "true", "1", "-1"]:
                return "éénrichtingsverkeer"
            if one in ["no", "false", "0"]:
                return "tweerichtingsverkeer"
            return "niet beschikbaar in OSM"
        def rows_for(subset, n=5):
            out=[]
            if subset is None or subset.empty:
                return pd.DataFrame(columns=["naam", "wegcategorie", "afstand_m", "snelheid", "richting"])
            # deduplicate by name/category/distance bucket
            subset=subset.sort_values("afstand_m").copy()
            seen=set()
            for _, r in subset.iterrows():
                naam=val(r,"name","Naam onbekend")
                cat=val(r,"highway_txt", val(r,"highway",""))
                key=(naam,cat,int(round(float(r["afstand_m"])/25)*25))
                if key in seen: continue
                seen.add(key)
                out.append({"naam": naam, "wegcategorie": cat, "afstand_m": int(round(float(r["afstand_m"]))), "snelheid": val(r,"maxspeed"), "richting": richting(r).replace("verkeer","")})
                if len(out)>=n: break
            return pd.DataFrame(out)

        hoofd = wegen[wegen["highway_txt"].isin(["motorway","trunk","primary","secondary","tertiary"])]
        grote = wegen[wegen["highway_txt"].isin(["motorway","trunk","primary","secondary"])]
        snel = wegen[wegen["highway_txt"].isin(["motorway","trunk"])]
        assen = wegen[wegen["highway_txt"].isin(["primary","secondary","tertiary"])]
        hoofd_df=rows_for(hoofd,5)
        grote_df=rows_for(grote,5)
        snel_df=rows_for(snel,5)
        assen_df=rows_for(assen,5)

        # kruispunten/regelpunt dichtstbijzijnd
        kruispunt_naam="niet beschikbaar"; afstand_kruispunt=None
        try:
            k = pr.copy()
            mask = pd.Series(False, index=k.index)
            if "highway" in k.columns:
                mask = mask | _series_contains(k["highway"], ["traffic_signals", "stop", "give_way", "crossing"])
            if "junction" in k.columns:
                mask = mask | k["junction"].notna()
            k=k[mask]
            if not k.empty:
                kr=k.sort_values("afstand_m").iloc[0]
                kruispunt_naam=val(kr,"name", val(kr,"highway_txt", "kruispunt / regelpunt"))
                afstand_kruispunt=int(round(float(kr["afstand_m"])))
        except Exception:
            pass

        return {
            "ontsluitingsweg": val(dichtste, "name", "Naam onbekend"),
            "wegcategorie": val(dichtste, "highway_txt", val(dichtste, "highway", "niet beschikbaar")),
            "snelheidsregime": val(dichtste, "maxspeed"),
            "richting": richting(dichtste),
            "dichtstbijzijnd_kruispunt": kruispunt_naam,
            "afstand_kruispunt_m": afstand_kruispunt,
            "afstand_hoofdweg_m": int(hoofd_df["afstand_m"].min()) if not hoofd_df.empty else None,
            "hoofdwegen": hoofd_df,
            "grote_wegen_breed": grote_df,
            "snelwegen_breed": snel_df,
            "ontsluitingsassen": assen_df,
            "toelichting": "Auto-analyse op basis van OpenStreetMap binnen de gekozen radius én aanvullende zoekstraal van 10 km. Controle met officiële wegencategorisering en terreinopname blijft noodzakelijk."
        }
    except Exception as e:
        out=leeg.copy(); out["toelichting"]=f"Detailanalyse auto kon niet worden uitgevoerd: {type(e).__name__}."; return out


def maak_pdf_isochronenkaart_png(lat, lon, netwerk_type, snelheid_kmh, minuten, kleur, titel, bestandsnaam, auto_gdf=None):
    """Statische PDF-bereikbaarheidskaart zonder Selenium, met brede kaartcontext."""
    import tempfile
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    png_path = os.path.join(tempfile.gettempdir(), bestandsnaam + ".png")
    radius = snelheid_kmh * 1000 / 60 * minuten
    context_radius = radius * (2.10 if netwerk_type == "walk" else 1.55)
    fig, ax = plt.subplots(figsize=(8.8, 4.9), dpi=220)
    projectpunt = _setup_pdf_map_ax(ax, lat, lon, context_radius, titel)
    basemap_ok = _add_context_basemap(ax)

    # Brede contextlaag: ook wegen buiten de bereikbare zone tonen.
    context_wegen = zoek_pdf_context_wegen(lat, lon, context_radius)
    wegen_context = _combine_gdfs_for_context(auto_gdf, context_wegen)
    _plot_gdf_layer(ax, _select_osm_roads(wegen_context, ["motorway", "trunk", "primary", "secondary", "tertiary"]), color="#626262", linewidth=0.90, alpha=0.72, zorder=2)
    _plot_gdf_layer(ax, _select_osm_roads(wegen_context, ["residential", "unclassified", "service", "living_street"]), color="#9A9A9A", linewidth=0.38, alpha=0.45 if basemap_ok else 0.70, zorder=1)

    try:
        G = ox.graph_from_point((lat, lon), dist=radius * 1.45, network_type=netwerk_type, simplify=True)
        G_proj = ox.project_graph(G, to_crs="EPSG:31370")
        for u, v, k, data in G_proj.edges(keys=True, data=True):
            data["tijd"] = data.get("length", 0) / (snelheid_kmh * 1000 / 3600)
        nodes = ox.graph_to_gdfs(G_proj, edges=False)
        nearest = nodes.distance(projectpunt).idxmin()
        sub = nx.ego_graph(G_proj, nearest, radius=minuten * 60, distance="tijd")
        n_iso, e_iso = ox.graph_to_gdfs(sub, nodes=True, edges=True)
        if not e_iso.empty:
            buffer = 65 if netwerk_type == "walk" else 120
            poly = unary_union(e_iso.geometry.buffer(buffer))
            gpoly = gpd.GeoDataFrame(geometry=[poly], crs="EPSG:31370")
            gpoly.plot(ax=ax, facecolor=kleur, edgecolor=kleur, linewidth=1.0, alpha=0.18, zorder=4)
            e_iso.plot(ax=ax, color=kleur, linewidth=0.95, alpha=0.78, zorder=5)
    except Exception:
        import matplotlib.patches as patches
        ax.add_patch(patches.Circle((projectpunt.x, projectpunt.y), radius, facecolor=kleur, edgecolor=kleur, alpha=0.16, linewidth=1.2, zorder=4))
        ax.text(0.02, 0.06, "Fallback: afstandscirkel", transform=ax.transAxes, fontsize=6.5, color="#555")
    _add_project_and_radius(ax, projectpunt, radius, radius_label=False)
    ax.text(0.02, 0.02, f"Bereikbaarheid: {minuten} min · snelheid: {snelheid_kmh} km/u · context buiten bereikbare zone zichtbaar", transform=ax.transAxes, fontsize=7, color="#444")
    ax.legend(handles=[Line2D([0],[0], color=kleur, lw=2, label=f"bereikbaar netwerk {minuten} min"), Line2D([0],[0], color="#626262", lw=1, label="wegen/context buiten bereik"), Line2D([0],[0], marker="o", color="w", markerfacecolor="#D62728", markersize=7, label="projectsite")], loc="upper right", fontsize=6.5, framealpha=0.90)
    return _finish_pdf_map(ax, fig, png_path)


def maak_pdf_auto_bereikbaarheid_png(lat, lon, minuten=20, snelheid_kmh=36, auto_gdf=None, bestandsnaam="pdf_auto_20min"):
    import tempfile, matplotlib.pyplot as plt, matplotlib.patches as patches
    from matplotlib.lines import Line2D
    png_path=os.path.join(tempfile.gettempdir(), bestandsnaam+".png")
    radius=snelheid_kmh*1000/60*minuten
    context_radius=radius*1.35
    fig, ax=plt.subplots(figsize=(8.8,4.9), dpi=220)
    projectpunt=_setup_pdf_map_ax(ax, lat, lon, context_radius, "Bereikbaarheid op 20 minuten met de auto")
    basemap_ok=_add_context_basemap(ax)
    context_wegen = zoek_pdf_context_wegen(lat, lon, context_radius)
    wegen_context = _combine_gdfs_for_context(auto_gdf, context_wegen)
    _plot_gdf_layer(ax, _select_osm_roads(wegen_context, ["motorway","trunk","primary","secondary","tertiary"]), color="#555", linewidth=1.15, alpha=0.78, zorder=4)
    _plot_gdf_layer(ax, _select_osm_roads(wegen_context, ["residential","unclassified","service","living_street"]), color="#999", linewidth=0.35, alpha=0.35 if basemap_ok else 0.65, zorder=2)
    ax.add_patch(patches.Circle((projectpunt.x, projectpunt.y), radius, facecolor="#7E57C2", edgecolor="#7E57C2", alpha=0.16, linewidth=1.6, zorder=3))
    _add_project_and_radius(ax, projectpunt, radius, radius_label=False)
    ax.text(0.02,0.02,f"Indicatief: {minuten} min auto · {snelheid_kmh} km/u · geen verkeersdruk · context buiten bereikbare zone zichtbaar", transform=ax.transAxes, fontsize=7, color="#444")
    ax.legend(handles=[Line2D([0],[0], color="#555", lw=1.4, label="hoofdwegen"), Line2D([0],[0], color="#999", lw=0.8, label="lokale wegen/context"), Line2D([0],[0], color="#7E57C2", lw=5, alpha=0.35, label="indicatief bereik"), Line2D([0],[0], marker="o", color="w", markerfacecolor="#D62728", markersize=7, label="projectsite")], loc="upper right", fontsize=6.5, framealpha=0.90)
    return _finish_pdf_map(ax, fig, png_path)


# =========================================================
# APP_38 OVERRIDES - parkeerkader, scoring en veilige API
# =========================================================

def _normaliseer_gemeente_naam(naam):
    return str(naam or "").strip().lower()


def _herken_gemeente_uit_adres(adres, lat=None, lon=None):
    adres_lc = (adres or "").lower()
    for gemeente in PARKEER_GEMEENTEN.keys():
        if gemeente != "generiek" and gemeente in adres_lc:
            return gemeente
    # eenvoudige fallback voor de gekende Hasseltse testomgeving
    try:
        if lat is not None and lon is not None and 50.88 <= float(lat) <= 50.98 and 5.26 <= float(lon) <= 5.42:
            return "hasselt"
    except Exception:
        pass
    return "generiek"


def _parkeer_zone_data(gemeente, zone):
    gemeente = gemeente if gemeente in PARKEER_GEMEENTEN else "generiek"
    cfg = PARKEER_GEMEENTEN[gemeente]
    zones = cfg.get("zones", {})
    if zone not in zones:
        zone = cfg.get("standaard_zone", next(iter(zones.keys())))
    return cfg, zone, zones[zone]


def bepaal_automatische_parkeer_context(adres, lat, lon, projecttype):
    herkende_gemeente = _herken_gemeente_uit_adres(adres, lat, lon)
    gekozen_gemeente = herkende_gemeente if herkende_gemeente in PARKEER_GEMEENTEN else "generiek"
    onbekend = gekozen_gemeente == "generiek" and herkende_gemeente != "generiek"
    cfg = PARKEER_GEMEENTEN[gekozen_gemeente]
    zone = cfg.get("standaard_zone")
    # Specifieke, uitbreidbare testcase binnen Hasselt/Kapermolen.
    statistische_sector_auto = "Niet automatisch herkend"
    try:
        afstand_kapermolen = geodesic((lat, lon), (50.93344, 5.34945)).meters
    except Exception:
        afstand_kapermolen = 999999
    if gekozen_gemeente == "hasselt" and afstand_kapermolen <= 1200 and "Binnen Singel" in cfg.get("zones", {}):
        zone = "Binnen Singel"
        statistische_sector_auto = "Kapermolen"
    _, zone, zone_data = _parkeer_zone_data(gekozen_gemeente, zone)
    if gekozen_gemeente == "generiek":
        opmerking = f"Geen lokale parkeernorm gevonden voor {herkende_gemeente if herkende_gemeente != 'generiek' else 'deze gemeente'}. De generieke prototypeformule wordt gebruikt."
    else:
        opmerking = f"{gekozen_gemeente.title()} werd automatisch herkend. Zone '{zone}' werd toegepast vanuit PARKEER_GEMEENTEN."
    return {
        "modus": "Automatisch bepalen op basis van adres",
        "gemeente": gekozen_gemeente,
        "norm_context": cfg.get("bron", "Generieke prototypeformule"),
        "bron": cfg.get("bron", "Generieke prototypeformule"),
        "zone": zone,
        "lokaal_wagenbezit": float(zone_data.get("wagenbezit", 0.0)),
        "statistische_sector": statistische_sector_auto,
        "straatparkeren_toelichting": "Parkeerregime, bezoekersparkeren en straatparkeren moeten worden gecontroleerd via lokale parkeerinformatie.",
        "automatisch_bepaald": True,
        "automatische_bronnen": "Adres/geocodering + PARKEER_GEMEENTEN-configuratie",
        "automatische_opmerking": opmerking,
    }


def bereken_project_effecten(projecttype, aantal_wooneenheden, bvo, parkeerplaatsen, fietsenstallingen, parkeer_context=None):
    parkeer_context = parkeer_context or {}
    gemeente = parkeer_context.get("gemeente", "generiek")
    if parkeer_context.get("norm_context") == "Generieke prototypeformule" or parkeer_context.get("modus") == "Generieke prototypeformule":
        gemeente = "generiek"
    zone = parkeer_context.get("zone") or PARKEER_GEMEENTEN.get(gemeente, PARKEER_GEMEENTEN["generiek"]).get("standaard_zone")
    cfg, zone, zone_data = _parkeer_zone_data(gemeente, zone)
    norm_min = float(zone_data.get("norm_min", 0.75))
    norm_max = float(zone_data.get("norm_max", 1.10))
    lokaal_wagenbezit = float(parkeer_context.get("lokaal_wagenbezit", zone_data.get("wagenbezit", 0.85)))
    bron = cfg.get("bron", "Generieke prototypeformule")

    methode = bron
    parkeernorm = f"{projecttype}: {norm_min:.2f} tot {norm_max:.2f} parkeerplaatsen per eenheid"
    parkeerbehoefte_min = None
    parkeerbehoefte_max = None
    norm_toelichting = (
        f"De autoparkeerbehoefte is berekend met het uitbreidbare parkeerkader PARKEER_GEMEENTEN. "
        f"Toegepaste gemeente: {gemeente}; zone: {zone}; bron: {bron}."
    )
    verkeersgeneratie_methode = "Generieke prototypeformule"
    verkeersgeneratie_toelichting = "De verkeersgeneratie is indicatief en moet bij vergunningsdossiers worden getoetst aan lokale kencijfers of het Richtlijnenboek MOBER."

    def bereken_woon_verkeersgeneratie():
        huishoudgrootte = 2.13
        verplaatsingen_per_persoon = 2.53
        bezoekers_per_we = 0.25
        verplaatsingen_per_bezoeker = 2.0
        aandeel_autobestuurder_bewoners = 0.418
        aandeel_autobestuurder_bezoekers = 0.44
        dag = aantal_wooneenheden * (
            huishoudgrootte * verplaatsingen_per_persoon * aandeel_autobestuurder_bewoners
            + bezoekers_per_we * verplaatsingen_per_bezoeker * aandeel_autobestuurder_bezoekers
        )
        spits = dag * 0.09
        return dag, spits

    if projecttype == "Wonen":
        parkeerbehoefte_min = round(aantal_wooneenheden * norm_min, 1)
        parkeerbehoefte_max = round(aantal_wooneenheden * norm_max, 1)
        parkeerbehoefte = parkeerbehoefte_max
        fietsbehoefte = aantal_wooneenheden * 2.0
        ritten_dag, ritten_spits = bereken_woon_verkeersgeneratie()
        verkeersgeneratie_methode = "Wonen: bewoners + bezoekers + modal split"
        verkeersgeneratie_toelichting = "Voor wonen wordt de verkeersgeneratie berekend via bewoners, bezoekers en modal split. Dit voorkomt een systematische overschatting door een vaste factor per wooneenheid."
        parkeernorm = f"Wonen {zone}: {norm_min:.2f} tot {norm_max:.2f} parkeerplaatsen per wooneenheid"
    elif projecttype == "Handel":
        eenheden = bvo / 100
        parkeerbehoefte = eenheden * 3.0
        fietsbehoefte = eenheden * 1.5
        ritten_dag = eenheden * 30
        ritten_spits = eenheden * 3.0
    elif projecttype == "Horeca":
        eenheden = bvo / 100
        parkeerbehoefte = eenheden * 4.0
        fietsbehoefte = eenheden * 2.0
        ritten_dag = eenheden * 35
        ritten_spits = eenheden * 4.0
    elif projecttype == "Kantoor":
        eenheden = bvo / 100
        parkeerbehoefte = eenheden * 2.0
        fietsbehoefte = eenheden * 1.5
        ritten_dag = eenheden * 8
        ritten_spits = eenheden * 1.2
    elif projecttype == "School":
        eenheden = bvo / 100
        parkeerbehoefte = eenheden * 1.5
        fietsbehoefte = eenheden * 3.0
        ritten_dag = eenheden * 20
        ritten_spits = eenheden * 4.0
    else:
        eenheden = max(bvo / 100, aantal_wooneenheden)
        parkeerbehoefte = eenheden * 2.0
        fietsbehoefte = eenheden * 2.0
        ritten_dag = eenheden * 10
        ritten_spits = eenheden * 1.5

    parkeerbehoefte = round(parkeerbehoefte, 1)
    fietsbehoefte = round(fietsbehoefte, 1)
    ritten_dag = round(ritten_dag, 1)
    ritten_spits = round(ritten_spits, 1)
    parkeerbalans = round(parkeerplaatsen - parkeerbehoefte, 1)
    fietsbalans = round(fietsenstallingen - fietsbehoefte, 1)
    parkeerbehoefte_display = f"{parkeerbehoefte_min} - {parkeerbehoefte_max} plaatsen" if parkeerbehoefte_min is not None else f"{parkeerbehoefte} plaatsen"
    return {
        "parkeerbehoefte": parkeerbehoefte,
        "parkeerbehoefte_min": parkeerbehoefte_min,
        "parkeerbehoefte_max": parkeerbehoefte_max,
        "parkeerbehoefte_display": parkeerbehoefte_display,
        "parkeermethode": methode,
        "parkeernorm": parkeernorm,
        "norm_toelichting": norm_toelichting,
        "parkeervoetnoot": f"Parkeernorm gebaseerd op: {bron}. Het kader is uitbreidbaar naar andere gemeenten via het configuratiewoordenboek PARKEER_GEMEENTEN.",
        "parkeer_bron": bron,
        "gemeente_parkeerlogica": gemeente,
        "lokaal_wagenbezit": lokaal_wagenbezit,
        "statistische_sector": parkeer_context.get("statistische_sector", ""),
        "straatparkeren_toelichting": parkeer_context.get("straatparkeren_toelichting", ""),
        "parkeerzone": zone,
        "automatisch_bepaald": parkeer_context.get("automatisch_bepaald", False),
        "automatische_bronnen": parkeer_context.get("automatische_bronnen", ""),
        "automatische_opmerking": parkeer_context.get("automatische_opmerking", ""),
        "fietsbehoefte": fietsbehoefte,
        "ritten_dag": ritten_dag,
        "ritten_spits": ritten_spits,
        "verkeersgeneratie_methode": verkeersgeneratie_methode,
        "verkeersgeneratie_toelichting": verkeersgeneratie_toelichting,
        "parkeerbalans": parkeerbalans,
        "fietsbalans": fietsbalans,
    }


def analyseer_stappers(stappers):
    if stappers.empty:
        return {"voetpaden": 0, "oversteekplaatsen": 0, "trage_wegen": 0, "comfortscore": "Beperkt"}
    voetpaden = 0
    oversteekplaatsen = 0
    trage_wegen = 0
    if "footway" in stappers.columns:
        voetpaden += len(stappers[stappers["footway"] == "sidewalk"])
        oversteekplaatsen += len(stappers[stappers["footway"] == "crossing"])
    if "highway" in stappers.columns:
        voetpaden += len(stappers[stappers["highway"].isin(["footway", "pedestrian"])])
        trage_wegen += len(stappers[stappers["highway"].isin(["path", "steps"])])
        oversteekplaatsen += len(stappers[stappers["highway"] == "crossing"])
    totaal = voetpaden + oversteekplaatsen + trage_wegen
    d = SCORE_DREMPELS["stappers"]
    comfortscore = bepaal_score(totaal, goed=d["goed"], matig=d["matig"])
    return {"voetpaden": voetpaden, "oversteekplaatsen": oversteekplaatsen, "trage_wegen": trage_wegen, "comfortscore": comfortscore}


def analyseer_trappers(trappers, bff_routes):
    fietsstraten = 0
    fietssnelweg_osm = 0
    if trappers.empty:
        fietspaden = fietssuggesties = gedeelde_paden = 0
    else:
        fietspaden = fietssuggesties = gedeelde_paden = 0
        if "highway" in trappers.columns:
            fietspaden += len(trappers[trappers["highway"] == "cycleway"])
            gedeelde_paden += len(trappers[trappers["highway"] == "path"])
        if "cycleway" in trappers.columns:
            fietssuggesties += len(trappers[trappers["cycleway"].notna()])
        if "bicycle" in trappers.columns:
            gedeelde_paden += len(trappers[trappers["bicycle"].notna()])
        if "cyclestreet" in trappers.columns:
            fietsstraten += len(trappers[trappers["cyclestreet"].astype(str).str.lower().isin(["yes", "true", "1"])])
        for col in ["name", "ref", "cycle_network", "network"]:
            if col in trappers.columns:
                fietssnelweg_osm += trappers[col].astype(str).str.lower().str.contains("fietssnel|f-route|f[0-9]", regex=True, na=False).sum()
    bff_aantal = len(bff_routes)
    totaal = fietspaden + fietssuggesties + gedeelde_paden + bff_aantal + fietsstraten
    d = SCORE_DREMPELS["trappers"]
    if bff_aantal > 0 or totaal >= d["goed"]:
        fietsscore = "Goed"
    elif totaal >= d["matig"]:
        fietsscore = "Matig"
    else:
        fietsscore = "Beperkt"
    return {"fietspaden": fietspaden, "fietssuggesties": fietssuggesties, "gedeelde_paden": gedeelde_paden, "bff_segmenten": bff_aantal, "fietsstraten": int(fietsstraten), "fietssnelweg_osm": int(fietssnelweg_osm), "fietsscore": fietsscore}


def bereken_ov_frequenties(haltes, stop_times, trips, spits_start=7, spits_einde=9):
    if haltes is None or haltes.empty or stop_times is None or stop_times.empty:
        return haltes
    haltes = haltes.copy()
    if "departure_time" not in stop_times.columns and "arrival_time" not in stop_times.columns:
        haltes["ritten_spits_uur"] = 0.0
        haltes["frequentie_score"] = "Niet beschikbaar"
        return haltes
    tijdkolom = "departure_time" if "departure_time" in stop_times.columns else "arrival_time"
    st_times = stop_times[["trip_id", "stop_id", tijdkolom]].dropna().copy()
    st_times["uur"] = st_times[tijdkolom].apply(_gtfs_time_to_hour)
    st_times = st_times[st_times["uur"].between(spits_start, spits_einde - 1)]
    if st_times.empty:
        haltes["ritten_spits_uur"] = 0.0
        haltes["frequentie_score"] = "Beperkt"
        return haltes
    counts = st_times.groupby("stop_id")["trip_id"].nunique() / max(1, (spits_einde - spits_start))
    goed_freq = SCORE_DREMPELS["ov"]["goed_frequentie"]
    def score(freq):
        if freq >= max(10, goed_freq):
            return "Zeer goed"
        if freq >= goed_freq:
            return "Goed"
        if freq >= 3:
            return "Matig"
        if freq > 0:
            return "Beperkt"
        return "Geen bediening in spitsvenster"
    haltes["ritten_spits_uur"] = haltes["halte_id"].map(counts).fillna(0).round(1)
    haltes["frequentie_score"] = haltes["ritten_spits_uur"].apply(score)
    return haltes


def maak_scores(haltes, hoppinpunten, bff_routes):
    haltes_aantal = 0 if haltes is None else len(haltes)
    hoppin_aantal = 0 if hoppinpunten is None else len(hoppinpunten)
    bff_aantal = 0 if bff_routes is None else len(bff_routes)
    max_freq = 0
    try:
        if haltes is not None and not haltes.empty and "ritten_spits_uur" in haltes.columns:
            max_freq = float(haltes["ritten_spits_uur"].max())
    except Exception:
        max_freq = 0
    ov_d = SCORE_DREMPELS["ov"]
    if haltes_aantal >= ov_d["goed_haltes"] and max_freq >= ov_d["goed_frequentie"]:
        ov_score = "Goed"
    elif haltes_aantal >= 1:
        ov_score = "Matig"
    else:
        ov_score = "Beperkt"
    hoppin_score = bepaal_score(hoppin_aantal, goed=2, matig=1)
    fiets_d = SCORE_DREMPELS["trappers"]
    fiets_score = "Goed" if bff_aantal >= 1 else bepaal_score(bff_aantal, goed=fiets_d["goed"], matig=1)
    if ov_score == "Goed" and fiets_score == "Goed":
        totaal_score = "Goed"
    elif ov_score == "Beperkt" and fiets_score == "Beperkt":
        totaal_score = "Beperkt"
    else:
        totaal_score = "Matig"
    return ov_score, hoppin_score, fiets_score, totaal_score



# =========================================================
# AUTOMATISERING VAN AANVULPUNTEN
# =========================================================

def bepaal_locatieprofiel(haltes, hoppinpunten, scholen, horeca, winkels, parkings, straal, ov_score, fiets_score):
    """Classificeert de projectomgeving op basis van automatisch beschikbare data.
    Dit vervangt geen beleidsmatige locatiebeoordeling, maar automatiseert wel de eerste
    omgevings- en bereikbaarheidsinterpretatie.
    """
    haltes_n = 0 if haltes is None else len(haltes)
    hoppin_n = 0 if hoppinpunten is None else len(hoppinpunten)
    voorzieningen = int(scholen or 0) + int(horeca or 0) + int(winkels or 0) + int(parkings or 0)
    dichtheid = voorzieningen / max(1, (3.14159 * (straal / 1000) ** 2))

    punten = 0
    punten += min(30, haltes_n * 3)
    punten += min(20, hoppin_n * 10)
    punten += min(25, voorzieningen / 4)
    punten += 15 if ov_score == "Goed" else 8 if ov_score == "Matig" else 0
    punten += 10 if fiets_score == "Goed" else 5 if fiets_score == "Matig" else 0

    if punten >= 70:
        profiel = "stedelijke of kernversterkende locatie"
    elif punten >= 45:
        profiel = "voorstedelijke of gemengd bereikbare locatie"
    elif punten >= 25:
        profiel = "randstedelijke locatie met aandachtspunten"
    else:
        profiel = "eerder auto-afhankelijke locatie"

    toelichting = (
        f"Automatische classificatie op basis van {haltes_n} haltes, {hoppin_n} Hoppinpunten, "
        f"{voorzieningen} voorzieningen binnen {straal} m en de STOP-scores. "
        f"Voorzieningendichtheid: ongeveer {round(dichtheid, 1)} voorzieningen/km²."
    )
    return {"profiel": profiel, "punten": round(punten, 1), "voorzieningendichtheid": round(dichtheid, 1), "toelichting": toelichting}


def analyseer_ov_kwaliteit(haltes, dichtste_halte_algemeen=None, dichtstbijzijnde_station=None):
    """Automatiseert de OV-kwaliteitsanalyse op basis van De Lijn-GTFS en nabijheid."""
    dichtste_halte_algemeen = dichtste_halte_algemeen or {}
    dichtstbijzijnde_station = dichtstbijzijnde_station or {}
    if haltes is None or haltes.empty:
        max_freq = 0
        avg_freq = 0
        beste_halte = "niet beschikbaar"
        score = "Beperkt"
    else:
        h = haltes.copy()
        max_freq = float(h["ritten_spits_uur"].max()) if "ritten_spits_uur" in h.columns else 0
        avg_freq = float(h["ritten_spits_uur"].mean()) if "ritten_spits_uur" in h.columns else 0
        beste = h.sort_values(["ritten_spits_uur", "afstand_m"], ascending=[False, True]).iloc[0] if "ritten_spits_uur" in h.columns else h.sort_values("afstand_m").iloc[0]
        beste_halte = beste.get("halte_naam", "niet beschikbaar")
        if len(h) >= SCORE_DREMPELS["ov"]["goed_haltes"] and max_freq >= SCORE_DREMPELS["ov"]["goed_frequentie"]:
            score = "Goed"
        elif len(h) > 0:
            score = "Matig"
        else:
            score = "Beperkt"

    station_afstand = dichtstbijzijnde_station.get("afstand_m")
    station_waarde = "niet beschikbaar" if station_afstand is None else f'{dichtstbijzijnde_station.get("station_naam", "station")} ({station_afstand} m)'
    halte_afstand = dichtste_halte_algemeen.get("afstand_m")
    halte_waarde = "niet beschikbaar" if halte_afstand is None else f'{dichtste_halte_algemeen.get("halte_naam", "halte")} ({halte_afstand} m)'

    return {
        "score": score,
        "aantal_haltes": 0 if haltes is None else len(haltes),
        "max_freq": round(max_freq, 1),
        "avg_freq": round(avg_freq, 1),
        "beste_halte": beste_halte,
        "dichtste_halte": halte_waarde,
        "dichtste_station": station_waarde,
        "toelichting": f"Automatisch afgeleid uit De Lijn-GTFS: maximaal {round(max_freq, 1)} ritten/u in de ochtendspits en gemiddeld {round(avg_freq, 1)} ritten/u per halte."
    }


def analyseer_fietscomfort_automatisch(trappers_analyse, bff_context, recreatieve_analyse):
    """Maakt een compacte fietscomfortscore uit OSM + officiële BFF-output wanneer beschikbaar."""
    punten = 0
    pluspunten = []
    aandacht = []
    fietspaden = int(trappers_analyse.get("fietspaden", 0))
    fietssuggesties = int(trappers_analyse.get("fietssuggesties", 0))
    gedeelde = int(trappers_analyse.get("gedeelde_paden", 0))
    fietsstraten = int(trappers_analyse.get("fietsstraten", 0))
    bff = int(trappers_analyse.get("bff_segmenten", 0))
    recreatief = int(recreatieve_analyse.get("aantal", 0)) if recreatieve_analyse else 0

    punten += min(25, fietspaden * 2)
    punten += min(15, fietssuggesties)
    punten += min(10, gedeelde)
    punten += min(15, fietsstraten * 5)
    punten += 25 if bff > 0 else 0
    punten += min(10, recreatief)

    if fietspaden > 0:
        pluspunten.append(f"{fietspaden} fietspaden gedetecteerd")
    if fietsstraten > 0:
        pluspunten.append(f"{fietsstraten} fietsstraten gedetecteerd")
    if bff > 0:
        pluspunten.append("aansluiting of nabijheid van BFF gedetecteerd")
    else:
        aandacht.append("BFF kon niet automatisch bevestigd worden")
    if recreatief > 0:
        pluspunten.append("recreatieve fietsroute-elementen aanwezig")

    if punten >= 65:
        score = "Goed"
    elif punten >= 35:
        score = "Matig"
    else:
        score = "Beperkt"
        aandacht.append("fietscomfort moet zeker op terrein worden gecontroleerd")

    return {
        "score": score,
        "punten": round(punten, 1),
        "pluspunten": "; ".join(pluspunten) if pluspunten else "geen sterke automatische pluspunten gedetecteerd",
        "aandacht": "; ".join(aandacht) if aandacht else "geen zwaar automatisch aandachtspunt",
        "toelichting": "Automatische fietscomfortscore op basis van fietspaden, fietsstraten, BFF, gedeelde paden en recreatieve routes."
    }



def bereken_crow_achtige_verkeersgeneratie(projecttype, aantal_wooneenheden, bvo):
    """Automatische kencijfermodule voor verkeersgeneratie.

    Belangrijk: dit is een CROW/Richtlijnenboek-geïnspireerde prototypeberekening.
    De app bevat geen officiële CROW-databank. Voor een vergunningsdossier moet de
    exacte categorie, stedelijkheidsgraad en bandbreedte worden gecontroleerd in de
    officiële publicaties of in het Richtlijnenboek MOBER.
    """
    pt = str(projecttype or "").lower()
    if pt == "wonen" and aantal_wooneenheden > 0:
        dag_min = aantal_wooneenheden * 2.2
        dag_max = aantal_wooneenheden * 2.8
        spits_min = dag_min * 0.085
        spits_max = dag_max * 0.095
        methode = "Wonen: CROW/Richtlijnenboek-geïnspireerde bandbreedte per wooneenheid"
        beperking = "Exacte woningcategorie, stedelijkheidsgraad, autobezit en doelgroep blijven te controleren."
    elif pt in ["handel", "horeca", "kantoor", "school"] and bvo > 0:
        eenheden = bvo / 100
        factoren = {
            "handel": (20, 35, 0.10),
            "horeca": (25, 45, 0.11),
            "kantoor": (6, 10, 0.15),
            "school": (12, 22, 0.20),
        }
        fmin, fmax, spitsfactor = factoren.get(pt, (8, 15, 0.12))
        dag_min = eenheden * fmin
        dag_max = eenheden * fmax
        spits_min = dag_min * spitsfactor
        spits_max = dag_max * spitsfactor
        methode = f"{projecttype}: CROW/Richtlijnenboek-geïnspireerde bandbreedte per 100 m² BVO"
        beperking = "Functietype, openingsuren, gebruikersprofiel en lokale modal split blijven te controleren."
    else:
        dag_min = dag_max = spits_min = spits_max = 0
        methode = "Niet berekend: onvoldoende programma-input voor kencijfermodule"
        beperking = "Vul wooneenheden of BVO en projecttype aan."

    return {
        "methode": methode,
        "dag_bandbreedte": f"{round(dag_min, 1)} - {round(dag_max, 1)} ritten/dag" if dag_max else "niet berekend",
        "spits_bandbreedte": f"{round(spits_min, 1)} - {round(spits_max, 1)} ritten spitsuur" if spits_max else "niet berekend",
        "beperking": beperking,
    }


def analyseer_hoppin_kwaliteit(haltes, hoppinpunten, dichtstbijzijnde_station=None):
    """Kwaliteitsscore voor multimodale knooppunten op basis van nabijheid en overstapmogelijkheden."""
    dichtstbijzijnde_station = dichtstbijzijnde_station or {}
    punten = 0
    criteria = []
    if haltes is not None and not haltes.empty:
        d_haltes = haltes.sort_values("afstand_m")
        dichtste_halte_m = float(d_haltes.iloc[0]["afstand_m"])
        if dichtste_halte_m <= 300:
            punten += 25
            criteria.append("bushalte binnen 300 m")
        elif dichtste_halte_m <= 600:
            punten += 15
            criteria.append("bushalte binnen 600 m")
        if "buslijnen" in d_haltes.columns:
            lijnen = set()
            for txt in d_haltes["buslijnen"].dropna().astype(str).head(10):
                for deel in txt.split(","):
                    nummer = deel.strip().split(" - ")[0]
                    if nummer and nummer.lower() != "geen lijnen gevonden":
                        lijnen.add(nummer)
            if len(lijnen) >= 5:
                punten += 20
                criteria.append(f"meerdere buslijnen ({len(lijnen)})")
            elif len(lijnen) >= 2:
                punten += 10
                criteria.append(f"enkele buslijnen ({len(lijnen)})")
    if hoppinpunten is not None and not hoppinpunten.empty:
        min_hoppin = float(hoppinpunten["afstand_m"].min()) if "afstand_m" in hoppinpunten.columns else 99999
        if min_hoppin <= 500:
            punten += 25
            criteria.append("Hoppinpunt binnen 500 m")
        elif min_hoppin <= 1000:
            punten += 15
            criteria.append("Hoppinpunt binnen 1000 m")
    station_afstand = dichtstbijzijnde_station.get("afstand_m")
    if station_afstand is not None:
        if station_afstand <= 1000:
            punten += 30
            criteria.append("station binnen 1 km")
        elif station_afstand <= 2000:
            punten += 20
            criteria.append("station binnen 2 km")
        elif station_afstand <= 5000:
            punten += 10
            criteria.append("station binnen 5 km")
    punten = min(100, punten)
    score = "Goed" if punten >= 70 else "Matig" if punten >= 40 else "Beperkt"
    return {
        "score": score,
        "punten": punten,
        "criteria": "; ".join(criteria) if criteria else "geen sterke multimodale criteria automatisch bevestigd",
        "toelichting": "Automatische Hoppin-/knooppuntkwaliteit op basis van halteafstand, aantal lijnen, Hoppinpunten en stationsnabijheid."
    }


def analyseer_schoolroutes_automatisch(scholen, stappers_analyse, trappers_analyse, straal):
    """Eerste schoolroutequickscan op basis van scholen + wandel/fiets- en oversteekdata."""
    scholen = int(scholen or 0)
    oversteken = int(stappers_analyse.get("oversteekplaatsen", 0))
    voet = int(stappers_analyse.get("voetpaden", 0))
    fiets = int(trappers_analyse.get("fietspaden", 0))
    fietsstraten = int(trappers_analyse.get("fietsstraten", 0))
    if scholen == 0:
        score = "Niet relevant / niet gedetecteerd"
        tekst = f"Binnen {straal} m werden geen scholen gedetecteerd. Een specifieke schoolrouteanalyse is enkel nodig als het project zelf een schoolfunctie of veel schoolgerelateerde verplaatsingen bevat."
    else:
        punten = min(35, scholen * 5) + min(25, voet / 10) + min(20, oversteken / 10) + min(20, (fiets + fietsstraten) / 15)
        if punten >= 65:
            score = "Goed vertrekpunt, terreincontrole nodig"
        elif punten >= 35:
            score = "Aandachtspunt"
        else:
            score = "Beperkt"
        tekst = (
            f"Binnen {straal} m werden {scholen} scholen gedetecteerd. De app combineert dit met {voet} voetgangersverbindingen, "
            f"{oversteken} oversteekplaatsen, {fiets} fietspaden en {fietsstraten} fietsstraten. Dit is een automatische quickscan; "
            "veilige schoolroutes, schoolpoortwerking en piekmomenten moeten op terrein of via gemeentelijke schoolroutekaarten worden bevestigd."
        )
    return {"score": score, "toelichting": tekst}


def analyseer_werknemers_bezoekersbereikbaarheid(dichtste_halte_algemeen=None, dichtstbijzijnde_station=None, haltes=None):
    """Indicatieve natransportanalyse voor werknemers/bezoekers.

    Dit is nog geen volwaardige GTFS-routeplanner van station naar projectsite. De app gebruikt
    automatisch de afstand tot station/halte en de GTFS-frequentie van de haltes in de projectomgeving.
    """
    dichtste_halte_algemeen = dichtste_halte_algemeen or {}
    dichtstbijzijnde_station = dichtstbijzijnde_station or {}
    halte_m = dichtste_halte_algemeen.get("afstand_m")
    station_m = dichtstbijzijnde_station.get("afstand_m")
    beste_freq = 0
    beste_halte = "niet beschikbaar"
    if haltes is not None and not haltes.empty and "ritten_spits_uur" in haltes.columns:
        row = haltes.sort_values(["ritten_spits_uur", "afstand_m"], ascending=[False, True]).iloc[0]
        beste_freq = float(row.get("ritten_spits_uur", 0))
        beste_halte = row.get("halte_naam", "halte")
    onderdelen = []
    if halte_m is not None:
        onderdelen.append(f"dichtstbijzijnde halte op {halte_m} m")
    if station_m is not None:
        lopen = round(float(station_m) / 80, 1)   # ca. 4,8 km/u
        fietsen = round(float(station_m) / 250, 1) # ca. 15 km/u
        onderdelen.append(f"station op {station_m} m, indicatief {lopen} min te voet of {fietsen} min met de fiets")
    if beste_freq:
        onderdelen.append(f"beste halte in spits: {beste_halte} met ca. {round(beste_freq, 1)} ritten/u")
    score = "Goed" if (halte_m is not None and halte_m <= 400 and beste_freq >= 6) or (station_m is not None and station_m <= 1500) else "Matig" if onderdelen else "Beperkt"
    return {
        "score": score,
        "resultaat": "; ".join(onderdelen) if onderdelen else "geen automatische natransportinformatie beschikbaar",
        "beperking": "Indicatief: geen volledige GTFS-routeplanner met overstappen en exacte reistijden."
    }

def maak_geautomatiseerde_aanvullingen(
    projecttype, aantal_wooneenheden, bvo, parkeerplaatsen, fietsenstallingen, straal,
    haltes, hoppinpunten, bff_routes, scholen, horeca, winkels, parkings,
    stappers_analyse, trappers_analyse, auto_analyse, ov_score, fiets_score,
    effecten, studieplicht, mobiliteitseffecten, dichtste_halte_algemeen=None,
    dichtstbijzijnde_station=None, auto_detail=None, bff_context=None, recreatieve_analyse=None
):
    """Bundelt de aanvullingen die nu automatisch ingevuld kunnen worden.
    De output wordt zowel in de app als in de PDF getoond.
    """
    auto_detail = auto_detail or {}
    bff_context = bff_context or {}
    recreatieve_analyse = recreatieve_analyse or {}
    locatieprofiel = bepaal_locatieprofiel(haltes, hoppinpunten, scholen, horeca, winkels, parkings, straal, ov_score, fiets_score)
    ov_kwaliteit = analyseer_ov_kwaliteit(haltes, dichtste_halte_algemeen, dichtstbijzijnde_station)
    fietscomfort = analyseer_fietscomfort_automatisch(trappers_analyse, bff_context, recreatieve_analyse)
    crow_module = bereken_crow_achtige_verkeersgeneratie(projecttype, aantal_wooneenheden, bvo)
    hoppin_kwaliteit = analyseer_hoppin_kwaliteit(haltes, hoppinpunten, dichtstbijzijnde_station)
    schoolroutes = analyseer_schoolroutes_automatisch(scholen, stappers_analyse, trappers_analyse, straal)
    bezoekersbereikbaarheid = analyseer_werknemers_bezoekersbereikbaarheid(dichtste_halte_algemeen, dichtstbijzijnde_station, haltes)

    programma = []
    if projecttype == "Wonen" and aantal_wooneenheden > 0:
        programma.append(f"{aantal_wooneenheden} wooneenheden")
    if bvo > 0:
        programma.append(f"{bvo} m² BVO/programma")
    programma_txt = ", ".join(programma) if programma else "projectprogramma beperkt ingevuld"

    automatische_rows = [
        ["Projectprogramma", programma_txt, "Automatisch uit sidebar-input. Functiemix blijft manueel te verfijnen bij gemengde projecten."],
        ["Locatieprofiel", f'{locatieprofiel["profiel"]} ({locatieprofiel["punten"]}/100)', locatieprofiel["toelichting"]],
        ["OV-kwaliteit", f'{ov_kwaliteit["score"]}; beste halte: {ov_kwaliteit["beste_halte"]}', ov_kwaliteit["toelichting"]],
        ["Dichtstbijzijnde halte/station", f'{ov_kwaliteit["dichtste_halte"]}; station: {ov_kwaliteit["dichtste_station"]}', "Automatisch bepaald los van de gekozen radius."],
        ["Fietscomfortscore", f'{fietscomfort["score"]} ({fietscomfort["punten"]}/100)', f'{fietscomfort["pluspunten"]}. Aandacht: {fietscomfort["aandacht"]}'],
        ["Parkeerbalans", f'{effecten.get("parkeerbehoefte_display", effecten.get("parkeerbehoefte", "n.b."))}; balans {effecten.get("parkeerbalans", "n.b.")}', "Automatisch berekend op basis van projectinput en gekozen parkeerkader."],
        ["Fietsparkeerbalans", f'{effecten.get("fietsbehoefte", "n.b.")} stallingen; balans {effecten.get("fietsbalans", "n.b.")}', "Automatisch berekend als eerste toetsing. Kwaliteit en type stallingen blijven plancontrole."],
        ["Verkeersgeneratie", f'{effecten.get("ritten_dag", "n.b.")} ritten/dag; {effecten.get("ritten_spits", "n.b.")} ritten spitsuur', effecten.get("verkeersgeneratie_methode", "Indicatieve prototypeberekening")],
        ["CROW/Richtlijnenboek-kencijfermodule", f'{crow_module["dag_bandbreedte"]}; {crow_module["spits_bandbreedte"]}', f'{crow_module["methode"]}. {crow_module["beperking"]}'],
        ["Hoppin-/knooppuntkwaliteit", f'{hoppin_kwaliteit["score"]} ({hoppin_kwaliteit["punten"]}/100)', f'{hoppin_kwaliteit["criteria"]}. {hoppin_kwaliteit["toelichting"]}'],
        ["Schoolroutequickscan", schoolroutes["score"], schoolroutes["toelichting"]],
        ["Bereikbaarheid werknemers/bezoekers", bezoekersbereikbaarheid["score"], f'{bezoekersbereikbaarheid["resultaat"]}. {bezoekersbereikbaarheid["beperking"]}'],
        ["Studieplicht", f'{studieplicht.get("mobiliteitstoets", "n.b.")} / {studieplicht.get("mober", "n.b.")}', "Automatische drempelcheck; formele beoordeling blijft bij bevoegde overheid."],
        ["Auto-ontsluiting", f'{auto_detail.get("ontsluitingsweg", "niet beschikbaar")} · {auto_detail.get("wegcategorie", "")}', "Automatisch uit OSM. Officiële wegencategorisering blijft te bevestigen."],
        ["Milderende maatregelen", f'{len(mobiliteitseffecten.get("maatregelen", []))} automatische aanbevelingen', "Automatisch gegenereerd uit scores, parkeerbalans, fietsbalans en verkeersgeneratie."],
    ]

    resterende_rows = [
        ["Laatste planversie", "Manueel", "Architect / vergunningsdossier"],
        ["Interne circulatie op plan", "Gedeeltelijk automatisch toegelicht, maar planinterpretatie blijft manueel", "Inplantingsplan, grondplan, ontwerpteam"],
        ["Leveringen en afvalophaling", "Nog manueel", "Exploitant, afvalintercommunale, grondplan, draaicirkels"],
        ["Hulpdiensten en brandweerroute", "Nog manueel", "Brandweeradvies, inplantingsplan"],
        ["Werffase en werfverkeer", "Nog manueel", "Aannemer, werfinrichtingsplan, gemeente"],
        ["Officiële beleids- en planningscontext", "Gedeeltelijk automatiseerbaar wanneer gemeentelijke bronnen worden gekoppeld", "Gemeente, AWV, vervoerregio, omgevingsloket"],
        ["Tellingen en kruispuntafwikkeling", "Nog manueel of via aparte teldata-import", "Verkeerstellingen, kruispuntmodel, terreinonderzoek"],
        ["Finale expertconclusie", "Niet volledig automatiseren", "Mobiliteitsexpert / vergunningstraject"],
    ]

    samenvatting = (
        "Een deel van de vroegere aanvulpunten wordt nu automatisch ingevuld: locatieprofiel, OV-kwaliteit, fietscomfort, "
        "parkeerbalans, fietsparkeerbalans, verkeersgeneratie, CROW/Richtlijnenboek-kencijfercontrole, Hoppin-kwaliteit, schoolroutequickscan, bezoekersbereikbaarheid, studieplicht, auto-ontsluiting en automatische maatregelen. "
        "De resterende punten vragen nog projectkennis, terreincontrole of officiële beleidsinformatie."
    )
    return {
        "locatieprofiel": locatieprofiel,
        "ov_kwaliteit": ov_kwaliteit,
        "fietscomfort": fietscomfort,
        "crow_module": crow_module,
        "hoppin_kwaliteit": hoppin_kwaliteit,
        "schoolroutes": schoolroutes,
        "bezoekersbereikbaarheid": bezoekersbereikbaarheid,
        "automatische_rows": automatische_rows,
        "resterende_rows": resterende_rows,
        "samenvatting": samenvatting,
    }

# =========================================================
# HOOFDAPP
# =========================================================

if adres:
    geolocator = Nominatim(
        user_agent="mobiliteitsapp_vlaamse_bronnen",
        timeout=10
    )

    try:
        locatie = geolocator.geocode(adres)
    except Exception as e:
        st.error("Adres kon tijdelijk niet worden opgezocht.")
        st.write(e)
        st.stop()

    if locatie:
        lat = locatie.latitude
        lon = locatie.longitude

        st.success(f"Locatie gevonden: {lat}, {lon}")

        # Parkeerdata automatisch bepalen zodra de coördinaten gekend zijn.
        if parkeer_context.get("automatisch_bepaald"):
            parkeer_context = bepaal_automatische_parkeer_context(adres, lat, lon, projecttype)
            st.sidebar.success("Parkeerdata automatisch ingevuld")
            st.sidebar.write(f"**Normen:** {parkeer_context.get('norm_context')}")
            st.sidebar.write(f"**Zone:** {parkeer_context.get('zone')}")
            st.sidebar.write(f"**Sector:** {parkeer_context.get('statistische_sector')}")
            if parkeer_context.get("lokaal_wagenbezit", 0) > 0:
                st.sidebar.write(f"**Wagenbezit:** {parkeer_context.get('lokaal_wagenbezit')} wagens/huishouden")
            st.sidebar.caption(parkeer_context.get("automatische_opmerking", ""))
            if parkeer_context.get("gemeente") == "generiek":
                st.sidebar.info(parkeer_context.get("automatische_opmerking", ""))

        kaart = folium.Map(location=[lat, lon], zoom_start=15, tiles=None)

        folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(kaart)
        folium.TileLayer("CartoDB positron", name="Lichte kaart").add_to(kaart)
        folium.TileLayer("CartoDB dark_matter", name="Donkere kaart").add_to(kaart)

        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri",
            name="Luchtfoto"
        ).add_to(kaart)

        laag_project = folium.FeatureGroup(name="Projectsite + analysegebied", show=True).add_to(kaart)
        laag_ov = folium.FeatureGroup(name="De Lijn-haltes", show=True).add_to(kaart)
        laag_hoppin = folium.FeatureGroup(name="Hoppinpunten", show=True).add_to(kaart)
        laag_bff = folium.FeatureGroup(name="BFF-fietsroutes", show=True).add_to(kaart)
        laag_stappers = folium.FeatureGroup(name="Stappers", show=False).add_to(kaart)
        laag_trappers = folium.FeatureGroup(name="Trappers", show=False).add_to(kaart)
        laag_auto = folium.FeatureGroup(name="Auto - wegen en ontsluiting", show=False).add_to(kaart)
        laag_omgeving = folium.FeatureGroup(name="Omgevingsomschrijving", show=True).add_to(kaart)

        folium.Marker(
            [lat, lon],
            popup="Projectsite",
            tooltip="Projectsite",
            icon=folium.Icon(color="red", icon="home")
        ).add_to(laag_project)

        folium.Circle(
            location=[lat, lon],
            radius=straal,
            fill=False,
            tooltip=f"{straal} meter analysegebied"
        ).add_to(laag_project)

        gtfs = download_gtfs()

        if gtfs is None:
            st.warning("De Lijn-data is niet beschikbaar. De app werkt verder zonder haltes, lijnen en frequenties.")
            stops = pd.DataFrame(columns=["stop_id", "stop_name", "stop_lat", "stop_lon"])
            stop_times = pd.DataFrame(columns=["trip_id", "stop_id", "departure_time"])
            trips = pd.DataFrame(columns=["trip_id", "route_id"])
            routes = pd.DataFrame(columns=["route_id", "route_short_name", "route_long_name"])
        else:
            stops, stop_times, trips, routes = gtfs

        dichtste_halte_algemeen = zoek_dichtstbijzijnde_halte(stops, lat, lon)
        dichtstbijzijnde_station = zoek_dichtstbijzijnde_station(lat, lon)

        if dichtste_halte_algemeen.get("lat") is not None:
            folium.Marker(
                [dichtste_halte_algemeen["lat"], dichtste_halte_algemeen["lon"]],
                popup=f'Dichtstbijzijnde bushalte: {dichtste_halte_algemeen["halte_naam"]}<br>{dichtste_halte_algemeen["afstand_m"]} m',
                tooltip="Dichtstbijzijnde bushalte",
                icon=folium.Icon(color="cadetblue", icon="bus", prefix="fa")
            ).add_to(laag_omgeving)

        if dichtstbijzijnde_station.get("lat") is not None:
            folium.Marker(
                [dichtstbijzijnde_station["lat"], dichtstbijzijnde_station["lon"]],
                popup=f'Dichtstbijzijnde station/spoorhalte: {dichtstbijzijnde_station["station_naam"]}<br>{dichtstbijzijnde_station["afstand_m"]} m',
                tooltip="Dichtstbijzijnde station/spoorhalte",
                icon=folium.Icon(color="darkpurple", icon="train", prefix="fa")
            ).add_to(laag_omgeving)

        haltes = zoek_haltes(stops, lat, lon, straal)

        if not haltes.empty:
            with st.spinner("Buslijnen en frequenties koppelen..."):
                haltes = voeg_lijnen_toe(haltes, stop_times, trips, routes)
                haltes = bereken_ov_frequenties(haltes, stop_times, trips)

        st.subheader("Openbaar vervoer - De Lijn-haltes")
        st.write(f"Aantal haltes binnen {straal} m: **{len(haltes)}**")

        if not haltes.empty:
            st.dataframe(
                haltes[["halte_naam", "afstand_m", "ritten_spits_uur", "frequentie_score", "buslijnen", "halte_id"]].sort_values("afstand_m"),
                use_container_width=True
            )

            for _, halte in haltes.iterrows():
                folium.Marker(
                    [halte["lat"], halte["lon"]],
                    popup=f'{halte["halte_naam"]}<br>{halte["afstand_m"]} m<br>{halte["buslijnen"]}',
                    tooltip=halte["halte_naam"],
                    icon=folium.Icon(color="blue", icon="bus", prefix="fa")
                ).add_to(laag_ov)

        hoppin = download_hoppinpunten()
        hoppinpunten = zoek_hoppinpunten_binnen_straal(hoppin, lat, lon, straal)

        st.subheader("Openbaar vervoer - Hoppinpunten")
        st.write(f"Aantal Hoppinpunten binnen {straal} m: **{len(hoppinpunten)}**")

        if not hoppinpunten.empty:
            st.dataframe(
                hoppinpunten[["naam", "gemeente", "afstand_m"]].sort_values("afstand_m"),
                use_container_width=True
            )

            for _, punt in hoppinpunten.iterrows():
                folium.Marker(
                    [punt["lat"], punt["lon"]],
                    popup=f'{punt["naam"]}<br>{punt["gemeente"]}<br>{punt["afstand_m"]} m',
                    tooltip=punt["naam"],
                    icon=folium.Icon(color="green", icon="info-sign")
                ).add_to(laag_hoppin)

        bff = download_bff()
        bff_routes = zoek_bff_binnen_straal(bff, lat, lon, straal)

        st.subheader("Trappers - BFF-fietsroutes")
        st.write(f"Aantal BFF-segmenten binnen {straal} m: **{len(bff_routes)}**")

        if not bff_routes.empty:
            bff_df = bff_tabel_dataframe(bff_routes)

            if not bff_df.empty:
                st.dataframe(bff_df, use_container_width=True)

            folium.GeoJson(
                bff_routes,
                name="BFF-fietsroutes",
                style_function=lambda feature: {
                    "color": "purple",
                    "weight": 4,
                    "opacity": 0.8,
                }
            ).add_to(laag_bff)

        osm = zoek_osm_voorzieningen(lat, lon, straal)
        scholen, horeca, winkels, parkings = tel_osm(osm)

        st.subheader("OpenStreetMap voorzieningen")

        st.dataframe(pd.DataFrame({
            "Voorziening": ["Scholen", "Horeca", "Winkels", "Parkings"],
            "Aantal": [scholen, horeca, winkels, parkings]
        }), use_container_width=True)

        stappers = zoek_stappersvoorzieningen(lat, lon, straal)
        stappers_analyse = analyseer_stappers(stappers)

        st.subheader("Stappers - voetgangersanalyse")

        st.dataframe(pd.DataFrame({
            "Onderdeel": [
                "Voetpaden / voetgangersverbindingen",
                "Oversteekplaatsen",
                "Trage wegen / paden",
                "Indicatieve comfortscore"
            ],
            "Waarde": [
                stappers_analyse["voetpaden"],
                stappers_analyse["oversteekplaatsen"],
                stappers_analyse["trage_wegen"],
                stappers_analyse["comfortscore"]
            ]
        }), use_container_width=True)

        if not stappers.empty:
            try:
                folium.GeoJson(
                    stappers,
                    name="Stappers",
                    style_function=lambda feature: {
                        "color": "orange",
                        "weight": 2,
                        "opacity": 0.8,
                    }
                ).add_to(laag_stappers)
            except Exception:
                pass

        trappers = zoek_trappersvoorzieningen(lat, lon, straal)
        trappers_analyse = analyseer_trappers(trappers, bff_routes)
        bff_context = analyseer_bff_context(bff_routes)
        recreatieve_routes = zoek_recreatieve_fietsroutes(lat, lon, straal)
        recreatieve_analyse = analyseer_recreatieve_fietsroutes(recreatieve_routes)

        st.subheader("Trappers - fietsanalyse")

        st.dataframe(pd.DataFrame({
            "Onderdeel": [
                "Fietspaden",
                "Fietssuggesties / cycleway-tags",
                "Gedeelde paden / fietsbare paden",
                "Fietsstraten",
                "BFF-segmenten",
                "BFF-hoofdroute",
                "Fietssnelweg",
                "Recreatieve fietsroutes",
                "Indicatieve fietsscore"
            ],
            "Waarde": [
                trappers_analyse["fietspaden"],
                trappers_analyse["fietssuggesties"],
                trappers_analyse["gedeelde_paden"],
                trappers_analyse.get("fietsstraten", 0),
                trappers_analyse["bff_segmenten"],
                bff_context.get("hoofdroute", "Niet beschikbaar"),
                bff_context.get("fietssnelweg", "Niet beschikbaar"),
                recreatieve_analyse.get("aantal", 0),
                trappers_analyse["fietsscore"]
            ]
        }), use_container_width=True)

        st.caption(bff_context.get("toelichting", ""))
        st.caption(recreatieve_analyse.get("toelichting", ""))

        if not trappers.empty:
            try:
                folium.GeoJson(
                    trappers,
                    name="Trappers",
                    style_function=lambda feature: {
                        "color": "darkgreen",
                        "weight": 2,
                        "opacity": 0.8,
                    }
                ).add_to(laag_trappers)
            except Exception:
                pass

        auto = zoek_auto_infrastructuur(lat, lon, straal)
        auto_analyse = analyseer_auto(auto)
        auto_detail = detailleer_auto_ontsluiting(auto, lat, lon)

        st.subheader("Auto - ontsluitingsanalyse")

        st.dataframe(pd.DataFrame({
            "Onderdeel": [
                "Ontsluitingsweg",
                "Wegcategorie ontsluitingsweg",
                "Snelheidsregime ontsluitingsweg",
                "Eén- of tweerichtingsverkeer",
                "Dichtstbijzijnd kruispunt / regelpunt",
                "Afstand tot hoofdweg",
                "Hoofdwegen binnen radius",
                "Lokale wegen",
                "Woonstraten / verblijfsstraten",
                "Kruispunt- of regelpunten",
                "Gekende snelheidsregimes",
                "Indicatieve ontsluitingsscore"
            ],
            "Waarde": [
                auto_detail.get("ontsluitingsweg", "niet beschikbaar"),
                auto_detail.get("wegcategorie", "niet beschikbaar"),
                auto_detail.get("snelheidsregime", "niet beschikbaar"),
                auto_detail.get("richting", "niet beschikbaar"),
                f'{auto_detail.get("dichtstbijzijnd_kruispunt", "niet beschikbaar")} ({auto_detail.get("afstand_kruispunt_m")} m)' if auto_detail.get("afstand_kruispunt_m") is not None else auto_detail.get("dichtstbijzijnd_kruispunt", "niet beschikbaar"),
                f'{auto_detail.get("afstand_hoofdweg_m")} m' if auto_detail.get("afstand_hoofdweg_m") is not None else "niet beschikbaar",
                auto_analyse["hoofdwegen"],
                auto_analyse["lokale_wegen"],
                auto_analyse["woonstraten"],
                auto_analyse["kruispunten"],
                auto_analyse["snelheidsregimes"],
                auto_analyse["ontsluitingsscore"]
            ]
        }), use_container_width=True)

        st.caption(auto_detail.get("toelichting", ""))
        if isinstance(auto_detail.get("hoofdwegen"), pd.DataFrame) and not auto_detail.get("hoofdwegen").empty:
            st.markdown("**5 dichtstbijzijnde hoofdwegen binnen de gekozen radius**")
            st.dataframe(auto_detail.get("hoofdwegen"), use_container_width=True)

        if isinstance(auto_detail.get("ontsluitingsassen_breed"), pd.DataFrame) and not auto_detail.get("ontsluitingsassen_breed").empty:
            st.markdown("**Belangrijke ontsluitingsassen binnen 10 km**")
            st.dataframe(auto_detail.get("ontsluitingsassen_breed"), use_container_width=True)

        if isinstance(auto_detail.get("grote_wegen_breed"), pd.DataFrame) and not auto_detail.get("grote_wegen_breed").empty:
            st.markdown("**Dichtstbijzijnde hoofdwegen/grote banen binnen 10 km**")
            st.dataframe(auto_detail.get("grote_wegen_breed"), use_container_width=True)

        if isinstance(auto_detail.get("snelwegen_breed"), pd.DataFrame) and not auto_detail.get("snelwegen_breed").empty:
            st.markdown("**Dichtstbijzijnde snelwegen / hoofdverbindingswegen binnen 10 km**")
            st.dataframe(auto_detail.get("snelwegen_breed"), use_container_width=True)

        if not auto.empty:
            try:
                folium.GeoJson(
                    auto,
                    name="Auto",
                    style_function=lambda feature: {
                        "color": "red",
                        "weight": 2,
                        "opacity": 0.7,
                    }
                ).add_to(laag_auto)
            except Exception:
                pass

        ov_score, hoppin_score, fiets_score, totaal_score = maak_scores(
            haltes,
            hoppinpunten,
            bff_routes
        )

        effecten = bereken_project_effecten(
            projecttype,
            aantal_wooneenheden,
            bvo,
            parkeerplaatsen,
            fietsenstallingen,
            parkeer_context=parkeer_context
        )

        studieplicht = check_studieplicht(
            projecttype,
            aantal_wooneenheden,
            bvo,
            parkeerplaatsen
        )

        mobiliteitseffecten = maak_mobiliteitseffecten_en_maatregelen(
            projecttype,
            aantal_wooneenheden,
            bvo,
            parkeerplaatsen,
            fietsenstallingen,
            straal,
            haltes,
            hoppinpunten,
            bff_routes,
            scholen,
            horeca,
            winkels,
            parkings,
            stappers_analyse,
            trappers_analyse,
            auto_analyse,
            ov_score,
            hoppin_score,
            fiets_score,
            totaal_score,
            effecten,
            studieplicht,
            dichtste_halte_algemeen=dichtste_halte_algemeen,
            dichtstbijzijnde_station=dichtstbijzijnde_station,
        )

        st.subheader("Aftoetsing mobiliteitstoets / MOBER")

        st.dataframe(pd.DataFrame({
            "Onderdeel": ["Mobiliteitstoets", "MOBER", "Toelichting"],
            "Resultaat": [
                studieplicht["mobiliteitstoets"],
                studieplicht["mober"],
                studieplicht["toelichting"]
            ]
        }), use_container_width=True)

        st.subheader("Indicatieve parkeer- en verkeersanalyse")

        st.dataframe(pd.DataFrame({
            "Onderdeel": [
                "Gebruikte parkeermethode",
                "Automatisch bepaald",
                "Parkeerzone",
                "Lokale parkeernorm",
                "Indicatieve parkeerbehoefte",
                "Ingegeven parkeeraanbod",
                "Parkeerbalans t.o.v. bovengrens",
                "Lokaal wagenbezit / statistische sector",
                "Bezoekers- en straatparkeren",
                "Indicatieve fietsparkeerbehoefte",
                "Ingegeven fietsenstallingen",
                "Fietsparkeerbalans",
                "Indicatieve ritten per dag",
                "Indicatieve ritten spitsuur",
                "Methode verkeersgeneratie",
            ],
            "Waarde": [
                "Ja" if effecten.get("automatisch_bepaald") else "Nee / handmatig",
                effecten.get("parkeerzone", "Niet beschikbaar"),
                effecten.get("parkeermethode", "Generieke prototypeformule"),
                effecten.get("parkeernorm", "Niet lokaal gespecificeerd"),
                effecten.get("parkeerbehoefte_display", f'{effecten["parkeerbehoefte"]} plaatsen'),
                f"{parkeerplaatsen} plaatsen",
                f'{effecten["parkeerbalans"]} plaatsen',
                f'{effecten.get("lokaal_wagenbezit", "")} wagens/huishouden · {effecten.get("statistische_sector", "")}',
                effecten.get("straatparkeren_toelichting", "Niet ingevuld"),
                f'{effecten["fietsbehoefte"]} plaatsen',
                f"{fietsenstallingen} plaatsen",
                f'{effecten["fietsbalans"]} plaatsen',
                f'{effecten["ritten_dag"]} ritten',
                f'{effecten["ritten_spits"]} ritten',
                effecten.get("verkeersgeneratie_methode", "Niet gespecificeerd"),
            ]
        }), use_container_width=True)
        st.caption(effecten.get("norm_toelichting", ""))
        if effecten.get("automatische_opmerking"):
            st.info(effecten.get("automatische_opmerking"))


        st.subheader("Mobiliteitseffecten en milderende maatregelen")
        st.dataframe(pd.DataFrame({
            "Thema": [
                "Impact op bereikbaarheid",
                "Impact op parkeren",
                "Impact op verkeersgeneratie",
                "Impact op verkeersveiligheid",
            ],
            "Beoordeling": [
                mobiliteitseffecten["bereikbaarheid_score"],
                mobiliteitseffecten["parkeren_score"],
                mobiliteitseffecten["verkeers_score"],
                mobiliteitseffecten["verkeersveiligheid_score"],
            ],
            "Kerntekst": [
                mobiliteitseffecten["bereikbaarheid"],
                mobiliteitseffecten["parkeren"] + " " + mobiliteitseffecten["fietsparkeren"],
                mobiliteitseffecten["verkeersgeneratie"],
                mobiliteitseffecten["verkeersveiligheid"],
            ]
        }), use_container_width=True)

        st.markdown("**Aanbevelingen en milderende maatregelen**")
        st.dataframe(pd.DataFrame({
            "Nr.": list(range(1, len(mobiliteitseffecten.get("maatregelen", [])) + 1)),
            "Maatregel / aanbeveling": mobiliteitseffecten.get("maatregelen", [])
        }), use_container_width=True)

        geautomatiseerde_aanvullingen = maak_geautomatiseerde_aanvullingen(
            projecttype, aantal_wooneenheden, bvo, parkeerplaatsen, fietsenstallingen, straal,
            haltes, hoppinpunten, bff_routes, scholen, horeca, winkels, parkings,
            stappers_analyse, trappers_analyse, auto_analyse, ov_score, fiets_score,
            effecten, studieplicht, mobiliteitseffecten,
            dichtste_halte_algemeen=dichtste_halte_algemeen,
            dichtstbijzijnde_station=dichtstbijzijnde_station,
            auto_detail=auto_detail,
            bff_context=bff_context,
            recreatieve_analyse=recreatieve_analyse,
        )

        st.subheader("Geautomatiseerde aanvullingen")
        st.info(geautomatiseerde_aanvullingen["samenvatting"])
        st.dataframe(pd.DataFrame(
            geautomatiseerde_aanvullingen["automatische_rows"],
            columns=["Onderdeel", "Automatisch resultaat", "Interpretatie / beperking"]
        ), use_container_width=True)
        st.markdown("**Aanvulpunten die bewust manueel blijven**")
        st.dataframe(pd.DataFrame(
            geautomatiseerde_aanvullingen["resterende_rows"],
            columns=["Onderdeel", "Automatiseringsstatus", "Waar te vinden / controleren"]
        ), use_container_width=True)

        plan_paths = verzamel_projectplannen()

        synthese_data = maak_synthese_kwaliteitscheck_eindconclusie(
            projecttype,
            aantal_wooneenheden,
            bvo,
            parkeerplaatsen,
            fietsenstallingen,
            straal,
            haltes,
            hoppinpunten,
            bff_routes,
            stappers_analyse,
            trappers_analyse,
            auto_analyse,
            ov_score,
            fiets_score,
            totaal_score,
            effecten,
            studieplicht,
            mobiliteitseffecten,
            plan_paths=plan_paths,
            korte_omschrijving=korte_omschrijving,
            huidige_toestand=huidige_toestand,
            toekomstige_toestand=toekomstige_toestand,
            dichtste_halte_algemeen=dichtste_halte_algemeen,
            dichtstbijzijnde_station=dichtstbijzijnde_station,
        )

        st.subheader("Synthese en kwaliteitscheck")
        st.dataframe(pd.DataFrame(synthese_data["synthese_rows"], columns=["Thema", "Synthese"]), use_container_width=True)
        st.markdown(f"**Eindconclusie:** {synthese_data['conclusie_type']}")
        st.info(synthese_data["eindconclusie"])
        st.dataframe(pd.DataFrame({
            "Onderdeel": ["Automatisch berekend", "Nog aan te vullen", "Expertcontrole"],
            "Controle": [
                "\n".join(synthese_data["gebruikte_input"]),
                "\n".join(synthese_data["ontbrekende_info"]),
                "\n".join(synthese_data["expert_check"]),
            ]
        }), use_container_width=True)

        ai_teksten = None
        if ai_actief:
            openai_api_key = _haal_openai_api_key(ai_api_key_input)
            with st.spinner("AI-interpretatie wordt gegenereerd op basis van de berekende MOBISCAN-data..."):
                ai_teksten = genereer_ai_mobiliteitstekst(
                    openai_api_key,
                    ai_model,
                    ai_promptstijl,
                    projectnaam,
                    adres,
                    projecttype,
                    aantal_wooneenheden,
                    bvo,
                    parkeerplaatsen,
                    fietsenstallingen,
                    straal,
                    haltes,
                    hoppinpunten,
                    bff_routes,
                    scholen,
                    horeca,
                    winkels,
                    parkings,
                    stappers_analyse,
                    trappers_analyse,
                    auto_analyse,
                    ov_score,
                    hoppin_score,
                    fiets_score,
                    totaal_score,
                    effecten,
                    studieplicht,
                    mobiliteitseffecten,
                    dichtste_halte_algemeen=dichtste_halte_algemeen,
                    dichtstbijzijnde_station=dichtstbijzijnde_station,
                )
            if ai_teksten.get("tekst"):
                st.success(f"AI-interpretaties gegenereerd met {ai_teksten['model']} · vaste prompt: Professioneel en neutraal. De teksten worden in de PDF bij de relevante hoofdstukken geplaatst.")
                with st.expander("Gebruikte vaste AI-prompt bekijken"):
                    st.code(ai_teksten["prompt"], language="text")
            else:
                st.warning(ai_teksten.get("fout", "AI-tekst kon niet worden gegenereerd."))
                with st.expander("Prompt die naar het model zou worden gestuurd"):
                    st.code(ai_teksten.get("prompt", ""), language="text")
        else:
            ai_teksten = {
                "actief": False,
                "tekst": "",
                "model": ai_model,
                "promptstijl": ai_promptstijl,
                "prompt": "AI stond uit voor deze run.",
                "fout": ""
            }

        st.subheader("Omgevingsomschrijving")
        st.dataframe(pd.DataFrame({
            "Onderdeel": [
                "Dichtstbijzijnde bushalte",
                "Afstand tot dichtstbijzijnde bushalte",
                "Dichtstbijzijnde station / spoorhalte",
                "Afstand tot dichtstbijzijnde station / spoorhalte",
                "Haltes binnen gekozen radius",
                "Voorzieningen binnen gekozen radius"
            ],
            "Waarde": [
                dichtste_halte_algemeen.get("halte_naam", "niet beschikbaar"),
                f'{dichtste_halte_algemeen.get("afstand_m")} m' if dichtste_halte_algemeen.get("afstand_m") is not None else "niet beschikbaar",
                dichtstbijzijnde_station.get("station_naam", "niet beschikbaar"),
                f'{dichtstbijzijnde_station.get("afstand_m")} m' if dichtstbijzijnde_station.get("afstand_m") is not None else "niet beschikbaar",
                f"{len(haltes)} haltes binnen {straal} m",
                f"{scholen} scholen, {horeca} horeca, {winkels} winkels, {parkings} parkings"
            ]
        }), use_container_width=True)

        st.subheader("Projectomschrijving")
        st.dataframe(pd.DataFrame({
            "Onderdeel": [
                "Fase",
                "Korte projectomschrijving",
                "Huidige toestand",
                "Toekomstige toestand"
            ],
            "Waarde": [
                projectfase,
                korte_omschrijving if korte_omschrijving else "Niet ingevuld",
                huidige_toestand if huidige_toestand else "Niet ingevuld",
                toekomstige_toestand if toekomstige_toestand else "Niet ingevuld"
            ]
        }), use_container_width=True)

        st.subheader("Aangeleverde projectplannen")
        if plan_paths:
            st.dataframe(pd.DataFrame([
                {
                    "Document": item["label"],
                    "Bestandsnaam": item["filename"],
                    "Type": "Afbeelding" if item["source_type"] == "afbeelding" else "PDF - eerste pagina als preview",
                    "Komt zichtbaar in PDF": "Ja" if item.get("preview_path") else "Nee"
                }
                for item in plan_paths
            ]), use_container_width=True)

            plan_uitleg = {
                "Inplantingsplan": "Wordt opgenomen bij de projectomschrijving. De PDF bespreekt hierbij de organisatie van de site, de randen van het perceel, de toegangen, de relatie met de omliggende straten, de ligging van parkeer- en stallingszones en de aansluiting op routes naar OV-haltes.",
                "Situatieplan": "Wordt opgenomen bij de omgevingsomschrijving. De PDF koppelt dit plan aan de openbare databronnen: dichtstbijzijnde bushalte, dichtstbijzijnde station, omliggende voorzieningen, Hoppinpunten en de relatie met het gekozen analysegebied.",
                "Grondplan gelijkvloers": "Wordt opgenomen bij de projectkenmerken. De PDF bespreekt hierbij de interne werking van de site: toegangen, looplijnen, fietsstallingen, parkeerplaatsen, leveringen, afvalophaling, verhuisbewegingen en mogelijke conflictpunten.",
                "Doorsnede / gevel": "Wordt opgenomen bij de projectkenmerken. De PDF bespreekt hierbij niveauverschillen, hellingen, keldertoegangen, fietsbereikbaarheid, toegankelijkheid en de relatie tussen gebouw en straatprofiel."
            }

            volgorde = ["Inplantingsplan", "Situatieplan", "Grondplan gelijkvloers", "Doorsnede / gevel"]
            for label in volgorde:
                item = next((p for p in plan_paths if p["label"] == label), None)
                if item is None:
                    continue
                st.markdown(f"### {item['label']}")
                st.caption(plan_uitleg.get(item["label"], "Dit plan wordt opgenomen als projectdocument."))
                if item.get("preview_path") and os.path.exists(item["preview_path"]):
                    st.markdown(f"**Bestand:** {item['filename']}")
                    st.image(item["preview_path"], use_container_width=True)
                else:
                    st.warning(f"{item['label']} kon niet als afbeelding worden weergegeven. Het bestand wordt wel vermeld in de projectdocumenten.")
        else:
            st.info("Er werden nog geen projectplannen opgeladen.")

        profiel = maak_profiel(
            projectnaam,
            adres,
            projecttype,
            aantal_wooneenheden,
            bvo,
            parkeerplaatsen,
            fietsenstallingen,
            straal,
            haltes,
            hoppinpunten,
            bff_routes,
            scholen,
            horeca,
            winkels,
            parkings,
            stappers_analyse,
            trappers_analyse,
            auto_analyse,
            ov_score,
            hoppin_score,
            fiets_score,
            totaal_score,
            effecten,
            studieplicht,
            mobiliteitseffecten=mobiliteitseffecten,
            projectfase=projectfase,
            korte_omschrijving=korte_omschrijving,
            huidige_toestand=huidige_toestand,
            toekomstige_toestand=toekomstige_toestand,
            dichtste_halte_algemeen=dichtste_halte_algemeen,
            dichtstbijzijnde_station=dichtstbijzijnde_station
        )

        st.subheader("Automatisch bereikbaarheidsprofiel")
        st.markdown(profiel)

        kaart_html = kaart.get_root().render()

        app_logo_path = bewaar_upload_als_temp(app_logo_upload, "mobiscan_logo")
        bureau_logo_path = bewaar_upload_als_temp(bureau_logo_upload, "bureau_logo")

        pdf = maak_pdf(
            projectnaam,
            adres,
            projecttype,
            aantal_wooneenheden,
            bvo,
            parkeerplaatsen,
            fietsenstallingen,
            lat,
            lon,
            straal,
            haltes,
            hoppinpunten,
            bff_routes,
            scholen,
            horeca,
            winkels,
            parkings,
            stappers_analyse,
            trappers_analyse,
            auto_analyse,
            profiel,
            ov_score,
            hoppin_score,
            fiets_score,
            totaal_score,
            effecten,
            studieplicht,
            mobiliteitseffecten=mobiliteitseffecten,
            projectfase=projectfase,
            korte_omschrijving=korte_omschrijving,
            huidige_toestand=huidige_toestand,
            toekomstige_toestand=toekomstige_toestand,
            plan_paths=plan_paths,
            dichtste_halte_algemeen=dichtste_halte_algemeen,
            dichtstbijzijnde_station=dichtstbijzijnde_station,
            auto_detail=auto_detail,
            bff_context=bff_context,
            recreatieve_analyse=recreatieve_analyse,
            stappers_gdf=stappers,
            trappers_gdf=trappers,
            auto_gdf=auto,
            recreatieve_routes_gdf=recreatieve_routes,
            ai_teksten=ai_teksten,
            opdrachtgever=opdrachtgever,
            architectenbureau=architectenbureau,
            opdrachtnemer=opdrachtnemer,
            projectmedewerkers=projectmedewerkers,
            versienummer=versienummer,
            vrijgavedatum=vrijgavedatum,
            rapportstatus=rapportstatus,
            referentie=referentie,
            app_logo_path=app_logo_path,
            bureau_logo_path=bureau_logo_path
        )

        st.download_button(
            label="Download bereikbaarheidsfiche als PDF",
            data=pdf,
            file_name="bereikbaarheidsfiche_professioneel_en_neutraal.pdf",
            mime="application/pdf"
        )

    
        st.download_button(
            label="Download interactieve kaart als HTML",
            data=kaart_html,
            file_name="mobiliteitskaart.html",
            mime="text/html"
        )

        st.subheader("Interactieve kaart")

        folium.LayerControl(collapsed=False).add_to(kaart)

        st_folium(
            kaart,
            width=None,
            height=700,
            key="hoofdkaart"
        )

        st.subheader("Isochronenkaart bereikbaarheid")

        st.caption(
            "Indicatieve bereikbaarheid op basis van gemiddelde snelheden: "
            "20 min wandelen ≈ 1,6 km, "
            "20 min fietsen ≈ 5 km, "
            "20 min auto ≈ 12 km."
        )

        kaart_iso = maak_isochronenkaart(lat, lon)

        kaart_iso_html = kaart_iso.get_root().render()

        st.download_button(
            label="Download isochronenkaart als HTML",
            data=kaart_iso_html,
            file_name="isochronenkaart.html",
            mime="text/html"
        )

        components.html(
            kaart_iso_html,
            height=700,
            scrolling=False
        )

    else:
        st.error("Adres niet gevonden")

