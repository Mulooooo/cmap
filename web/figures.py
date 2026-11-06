"""Carte folium, courbe de convergence (SVG) et mise en forme des nombres."""

from dataclasses import dataclass, field

import folium
from folium.plugins import PolyLineTextPath

from web.geo import MapFrame

# Palette qualitative : assez de couleurs distinctes pour ~20 camions.
PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#17becf",
    "#bcbd22", "#7f7f7f", "#393b79", "#e6550d", "#31a354", "#756bb1", "#843c39", "#d6616b",
    "#637939", "#8ca252", "#3182bd", "#fd8d3c",
]
IDLE_COLOR = "#4a6fa5"
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/{service}/MapServer/tile/{{z}}/{{y}}/{{x}}"


def route_color(i: int) -> str:
    return PALETTE[i % len(PALETTE)]


def fr(x: float) -> str:
    """Nombre à la française : 1 234,5 (espace fine insécable, virgule décimale)."""
    s = f"{x:,.2f}".rstrip("0").rstrip(".")
    return s.replace(",", " ").replace(".", ",")


@dataclass
class MapLayer:
    """Une solution à tracer sur la carte. Les couches s'affichent/masquent depuis la carte."""

    name: str
    routes: list[list[int]]
    stats: list[dict] = field(default_factory=list)  # une entrée {load, distance, ...} par tournée (info-bulle)
    dashed: bool = False  # tirets : pour distinguer une solution de référence de la solution calculée
    show: bool = True


def build_map(frame: MapFrame, demand: list[int], capacity: int, layers: list[MapLayer]) -> str:
    """Page HTML complète d'une carte folium (à mettre dans un iframe `srcdoc`).

    Sans couche, on ne montre que les clients et le dépôt. Les clients sont colorés selon la
    première couche affichée par défaut.
    """
    m = folium.Map(
        location=[frame.center_lat, frame.center_lon], zoom_start=6, tiles=None,
        width="100%", height="100%", control_scale=True, zoom_control=True,
    )
    # Fonds de carte sans clé d'API. Pas de CartoDB (folium l'exige désormais) ni d'OpenStreetMap :
    # ses serveurs refusent (403) les pages ouvertes sans Referer.
    folium.TileLayer(
        ESRI.format(service="World_Street_Map"), name="Rues (Esri)", show=True,
        attr="Tiles © Esri — Source: Esri, DeLorme, NAVTEQ, USGS, HERE, OpenStreetMap contributors",
        max_zoom=19,
    ).add_to(m)
    folium.TileLayer(
        ESRI.format(service="Canvas/World_Light_Gray_Base"), name="Gris clair (Esri)", show=False,
        attr="Tiles © Esri — Esri, DeLorme, NAVTEQ", max_zoom=16,
    ).add_to(m)
    folium.TileLayer(
        ESRI.format(service="World_Imagery"), name="Satellite (Esri)", show=False,
        attr="Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics", max_zoom=18,
    ).add_to(m)

    def pt(i):
        return float(frame.lat[i]), float(frame.lon[i])

    for layer in layers:
        group = folium.FeatureGroup(name=layer.name, show=layer.show)
        for ri, r in enumerate(layer.routes):
            st = layer.stats[ri] if ri < len(layer.stats) else None
            info = f" · charge {st['load']}/{capacity} · distance {fr(st['distance'])}" if st else ""
            line = folium.PolyLine(
                [pt(c) for c in (0, *r, 0)], color=route_color(ri),
                weight=3 if layer.dashed else 4, opacity=0.75 if layer.dashed else 0.9,
                dash_array="8 7" if layer.dashed else None,
                tooltip=f"{layer.name} · camion {ri + 1}{info}",
            )
            line.add_to(group)
            # flèches le long du trajet : elles donnent le sens de parcours
            PolyLineTextPath(
                line, "      ►      ", repeat=True, offset=7,
                attributes={"fill": route_color(ri), "font-size": "14"},
            ).add_to(group)
        group.add_to(m)

    primary = next((l for l in layers if l.show), layers[0] if layers else None)
    owners = [
        (l.name, {c: (ri, k) for ri, r in enumerate(l.routes) for k, c in enumerate(r, 1)})
        for l in layers
    ]
    primary_owner = dict(owners).get(primary.name, {}) if primary else {}

    qmax = max(demand[1:]) or 1
    clients = folium.FeatureGroup(name="Clients", show=True)
    for i in range(1, len(demand)):
        tip = f"Client {i} · demande {demand[i]}"
        for name, owner in owners:
            if i in owner:
                tip += f"<br>{name} : camion {owner[i][0] + 1}, étape {owner[i][1]}"
        ri = primary_owner.get(i, (-1, 0))[0]
        folium.CircleMarker(
            pt(i), radius=5 + 7 * demand[i] / qmax,
            color="#ffffff", weight=1.5, fill=True,
            fill_color=route_color(ri) if ri >= 0 else IDLE_COLOR, fill_opacity=0.95,
            tooltip=tip,
        ).add_to(clients)
    clients.add_to(m)

    folium.Marker(
        pt(0), tooltip="Dépôt",
        icon=folium.DivIcon(
            icon_size=(60, 26), icon_anchor=(30, 13),
            html='<div style="background:#111;color:#fff;font:600 12px sans-serif;text-align:center;'
                 'line-height:22px;border:2px solid #fff;border-radius:13px;'
                 'box-shadow:0 1px 6px rgba(0,0,0,.4)">Dépôt</div>',
        ),
    ).add_to(m)

    m.fit_bounds([[float(frame.lat.min()), float(frame.lon.min())],
                  [float(frame.lat.max()), float(frame.lon.max())]], padding=(40, 40))
    folium.LayerControl(collapsed=True, position="topright").add_to(m)
    return m.get_root().render()


def convergence_svg(points: list[tuple[float, float]], bks: float | None) -> str:
    """Courbe en escalier du meilleur coût selon le temps (SVG inline, sans script)."""
    if len(points) < 2:
        return ""
    W, H, L, R, T, B = 760, 260, 56, 16, 14, 36
    xmax = max(p[0] for p in points) or 1.0
    costs = [p[1] for p in points]
    ymin = min(costs + ([bks] if bks else []))
    ymax = max(costs)
    pad = (ymax - ymin) * 0.08 or 1.0
    ymin, ymax = ymin - pad, ymax + pad

    def X(x):
        return L + x / xmax * (W - L - R)

    def Y(y):
        return T + (1 - (y - ymin) / (ymax - ymin)) * (H - T - B)

    d = f"M{X(points[0][0]):.1f},{Y(points[0][1]):.1f}"
    for t, c in points[1:]:
        d += f" H{X(t):.1f} V{Y(c):.1f}"

    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Meilleur coût en fonction du temps de calcul">']
    for i in range(5):
        y = ymin + i / 4 * (ymax - ymin)
        x = i / 4 * xmax
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(y):.1f}" y2="{Y(y):.1f}" '
                     f'stroke="currentColor" stroke-opacity=".12"/>')
        parts.append(f'<text x="{L - 8}" y="{Y(y) + 4:.1f}" text-anchor="end">{fr(round(y))}</text>')
        parts.append(f'<text x="{X(x):.1f}" y="{H - 14}" text-anchor="middle">{fr(round(x, 1))} s</text>')
    if bks:
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(bks):.1f}" y2="{Y(bks):.1f}" '
                     f'stroke="#2ca02c" stroke-dasharray="5 4"/>')
        parts.append(f'<text x="{W - R}" y="{Y(bks) - 5:.1f}" text-anchor="end" fill="#2ca02c">'
                     f'Meilleure connue : {fr(bks)}</text>')
    parts.append(f'<path d="{d}" fill="none" stroke="#2563eb" stroke-width="2"/></svg>')
    return "".join(parts)
