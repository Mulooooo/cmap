"""Interface graphique : charger une instance VRPLIB, la voir sur une carte de
France, lancer un solveur et suivre le calcul en direct.

Lancer :  streamlit run interface/app.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from interface import solvers  # noqa: E402
from interface.figures import (  # noqa: E402
    convergence_figure, instance_map, routes_table, solution_map,
)
from interface.geo import PRESETS, place_on_map  # noqa: E402
from interface.instance import load_instance, load_instance_from_bytes  # noqa: E402

MAP_STYLES = {
    "Clair": "carto-positron",
    "OpenStreetMap": "open-street-map",
    "Sombre": "carto-darkmatter",
}

st.set_page_config(page_title="CMAP - Tournées de livraison", page_icon="🚚", layout="wide")


# ----------------------------------------------------------------- chargement
def sidebar_instance():
    """Choix de l'instance. Renvoie (Instance | None)."""
    st.sidebar.header("1. Instance")
    source = st.sidebar.radio(
        "Source", ["Instances du dépôt", "Téléverser un .vrp", "Chemin local"],
        label_visibility="collapsed",
    )
    try:
        if source == "Instances du dépôt":
            files = sorted((ROOT / "instances").glob("*.vrp"))
            if not files:
                st.sidebar.info("Aucun fichier dans instances/")
                return None
            choice = st.sidebar.selectbox("Fichier", files, format_func=lambda p: p.name)
            return load_instance(choice)
        if source == "Téléverser un .vrp":
            up = st.sidebar.file_uploader("Fichier .vrp", type=["vrp"])
            return load_instance_from_bytes(up.getvalue(), up.name) if up else None
        path = st.sidebar.text_input("Chemin du fichier .vrp")
        return load_instance(Path(path).expanduser()) if path.strip() else None
    except Exception as exc:  # fichier illisible : on l'explique, on ne plante pas
        st.sidebar.error(f"Impossible de lire l'instance : {exc}")
        return None


def sidebar_map():
    st.sidebar.header("2. Carte")
    preset = st.sidebar.selectbox("Zone", list(PRESETS))
    lat, lon, span = PRESETS[preset]
    span = st.sidebar.slider("Étendue de l'instance (km)", 20, 1200, int(span), step=10)
    style = MAP_STYLES[st.sidebar.selectbox("Fond de carte", list(MAP_STYLES))]
    return lat, lon, float(span), style


def sidebar_solver():
    st.sidebar.header("3. Calcul")
    if not solvers.SOLVERS:
        st.sidebar.warning("Aucun solveur enregistré")
        return None, 0.0, 0
    name = st.sidebar.selectbox("Solveur", list(solvers.SOLVERS))
    limit = st.sidebar.slider("Temps limite (s)", 1, 120, 10)
    seed = st.sidebar.number_input("Graine aléatoire", 0, 10_000, 0)
    return name, float(limit), int(seed)


# -------------------------------------------------------------------- affichage
def show_metrics(inst, frame):
    cols = st.columns(5)
    cols[0].metric("Clients", inst.n - 1)
    cols[1].metric("Capacité", inst.capacity)
    cols[2].metric("Demande totale", int(inst.demand.sum()))
    cols[3].metric("Camions (min.)", inst.min_vehicles,
                   help="⌈demande totale / capacité⌉. "
                        + (f"Le fichier annonce {inst.n_vehicles} camions." if inst.n_vehicles else ""))
    cols[4].metric("Meilleure connue", f"{inst.bks:g}" if inst.bks else "n/a")
    st.caption(
        f"Échelle : 1 unité de distance = {frame.km_per_unit:.1f} km. "
        "Les points de l'instance sont posés sur la carte par homothétie (ils ne correspondent "
        "pas à de vraies villes) et les trajets sont tracés à vol d'oiseau."
    )


def show_solution(inst, frame, sol):
    errors = solvers.check_solution(inst, sol.routes)
    cols = st.columns(5)
    cols[0].metric("Coût total", f"{sol.cost:g}")
    cols[1].metric("≈ km", f"{sol.cost * frame.km_per_unit:,.0f}".replace(",", " "))
    cols[2].metric("Camions utilisés", len(sol.routes))
    if inst.bks:
        gap = 100 * (sol.cost - inst.bks) / inst.bks
        cols[3].metric("Gap vs meilleure connue", f"{gap:.2f} %")
    cols[4].metric("Temps de calcul", f"{sol.elapsed:.1f} s")
    if errors:
        st.error("Solution invalide : " + " ; ".join(errors))
    else:
        st.success(f"Solution valide ({sol.solver})")
    st.dataframe(routes_table(inst, sol.routes, frame), hide_index=True, width="stretch")
    st.plotly_chart(convergence_figure(sol.history, inst.bks), width="stretch")


# ------------------------------------------------------------------------ page
st.title("🚚 Tournées de livraison")

inst = sidebar_instance()
lat, lon, span, style = sidebar_map()
solver_name, time_limit, seed = sidebar_solver()

if inst is None:
    st.info("Choisis une instance dans le panneau de gauche pour l'afficher sur la carte.")
    st.stop()

frame = place_on_map(inst.coords, lat, lon, span)
st.subheader(f"{inst.name}  ·  {inst.n - 1} clients")
show_metrics(inst, frame)

# Une nouvelle instance invalide l'ancienne solution.
if st.session_state.get("solution_for") != inst.name:
    st.session_state.pop("solution", None)

run = st.sidebar.button("▶ Calculer", type="primary", disabled=solver_name is None,
                        width="stretch")

map_slot = st.empty()
result_slot = st.container()

if run:
    live = {"t": 0.0, "n": 0}
    status = st.empty()

    def on_progress(it, cost, routes):
        # on limite le rafraîchissement : redessiner la carte coûte plus cher qu'un coup de solveur
        now = time.perf_counter()
        if now - live["t"] < 0.4:
            return
        live["t"], live["n"] = now, live["n"] + 1
        status.info(f"Calcul en cours... itération {it}, meilleur coût {cost:g}")
        map_slot.plotly_chart(solution_map(inst, frame, routes, style), width="stretch",
                              key=f"map_live_{live['n']}")  # clé unique : Streamlit refuse les doublons

    sol = solvers.SOLVERS[solver_name](inst, time_limit, seed, on_progress)
    status.empty()
    st.session_state.solution = sol
    st.session_state.solution_for = inst.name

sol = st.session_state.get("solution")
if sol is not None:
    map_slot.plotly_chart(solution_map(inst, frame, sol.routes, style), width="stretch",
                          key="map_final")
    with result_slot:
        show_solution(inst, frame, sol)
else:
    map_slot.plotly_chart(instance_map(inst, frame, style), width="stretch")
