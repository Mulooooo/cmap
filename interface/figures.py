"""Figures Plotly : carte de l'instance, tournées, courbe de convergence."""

import numpy as np
import plotly.graph_objects as go

from interface.geo import MapFrame, zoom_for
from interface.instance import Instance
from interface.solvers import Routes, route_cost, route_load

# Palette qualitative (Plotly D3 + Set1) : assez de couleurs distinctes pour ~20 camions.
PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#7f7f7f",
    "#393b79", "#e6550d", "#31a354", "#756bb1", "#843c39",
    "#d6616b", "#637939", "#8ca252", "#3182bd", "#fd8d3c",
]
DEPOT_COLOR = "#111111"
IDLE_COLOR = "#4a6fa5"


def route_color(i: int) -> str:
    return PALETTE[i % len(PALETTE)]


def _base_layout(frame: MapFrame, style: str, height: int) -> dict:
    return dict(
        map=dict(
            style=style,
            center=dict(lat=frame.center_lat, lon=frame.center_lon),
            zoom=zoom_for(frame.span_km, frame.center_lat, height),
        ),
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="left", x=0.01,
                    bgcolor="rgba(255,255,255,0.8)"),
        uirevision="map",  # garde zoom/déplacement de l'utilisateur pendant le calcul
    )


def _marker_sizes(inst: Instance) -> np.ndarray:
    """Taille de point proportionnelle à la demande (entre 8 et 22 px)."""
    q = inst.demand[1:].astype(float)
    span = (q.max() - q.min()) or 1.0
    return 8 + 14 * (q - q.min()) / span


def _depot_trace(frame: MapFrame) -> go.Scattermap:
    return go.Scattermap(
        lat=[frame.lat[0]], lon=[frame.lon[0]], mode="markers+text",
        marker=dict(size=22, color=DEPOT_COLOR), text=["Dépôt"], textposition="top right",
        textfont=dict(size=13, color=DEPOT_COLOR), name="Dépôt", hoverinfo="text",
        hovertext="Dépôt",
    )


def instance_map(inst: Instance, frame: MapFrame, style: str, height: int = 650) -> go.Figure:
    """Carte de l'instance seule : dépôt + clients (taille = demande)."""
    fig = go.Figure()
    fig.add_trace(go.Scattermap(
        lat=frame.lat[1:], lon=frame.lon[1:], mode="markers",
        marker=dict(size=_marker_sizes(inst), color=IDLE_COLOR, opacity=0.9),
        name="Clients",
        hovertext=[f"Client {i}<br>demande {inst.demand[i]}" for i in range(1, inst.n)],
        hoverinfo="text",
    ))
    fig.add_trace(_depot_trace(frame))
    fig.update_layout(**_base_layout(frame, style, height))
    return fig


def solution_map(
    inst: Instance, frame: MapFrame, routes: Routes, style: str, height: int = 650
) -> go.Figure:
    """Carte avec une couleur par camion. Les segments sont à vol d'oiseau, pas routiers."""
    fig = go.Figure()
    for i, r in enumerate(routes):
        path = [0, *r, 0]
        color = route_color(i)
        load = route_load(inst, r)
        fig.add_trace(go.Scattermap(
            lat=frame.lat[path], lon=frame.lon[path], mode="lines",
            line=dict(width=3, color=color), name=f"Camion {i + 1}",
            legendgroup=f"r{i}", hoverinfo="skip",
        ))
        fig.add_trace(go.Scattermap(
            lat=frame.lat[r], lon=frame.lon[r], mode="markers",
            marker=dict(size=_marker_sizes(inst)[np.array(r) - 1], color=color),
            legendgroup=f"r{i}", showlegend=False, hoverinfo="text",
            hovertext=[
                f"Client {c}<br>camion {i + 1}, étape {k}<br>demande {inst.demand[c]}"
                f"<br>charge {load}/{inst.capacity}"
                for k, c in enumerate(r, 1)
            ],
        ))
    fig.add_trace(_depot_trace(frame))
    fig.update_layout(**_base_layout(frame, style, height))
    return fig


def convergence_figure(history, bks: float | None = None) -> go.Figure:
    """Meilleur coût en fonction du temps de calcul."""
    fig = go.Figure()
    if history:
        t, _, cost = zip(*history)
        fig.add_trace(go.Scatter(x=t, y=cost, mode="lines", line=dict(shape="hv", width=2),
                                 name="Meilleur coût"))
    if bks:
        fig.add_hline(y=bks, line=dict(dash="dash", color="#2ca02c"),
                      annotation_text=f"Meilleure connue : {bks:g}", annotation_position="top right")
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis_title="Temps de calcul (s)", yaxis_title="Coût total",
                      showlegend=False)
    return fig


def routes_table(inst: Instance, routes: Routes, frame: MapFrame):
    """Une ligne par camion : ordre de visite, charge, distance."""
    import pandas as pd

    rows = []
    for i, r in enumerate(routes, 1):
        cost = route_cost(inst, r)
        rows.append({
            "Camion": i,
            "Itinéraire": " → ".join(["D", *map(str, r), "D"]),
            "Clients": len(r),
            "Charge": f"{route_load(inst, r)}/{inst.capacity}",
            "Distance": cost,
            "≈ km": round(cost * frame.km_per_unit),
        })
    return pd.DataFrame(rows)
