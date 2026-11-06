import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Basemap, Inst, Routes } from "../types";
import { IDLE_COLOR, routeColor } from "../format";

const BASEMAPS: Record<Basemap, string> = {
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
};
const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

interface Props {
  inst: Inst | null;
  routes: Routes | null;
  highlight: number | null; // camion survolé dans le tableau
  basemap: Basemap;
}

function ensureLayers(map: maplibregl.Map) {
  if (map.getSource("clients")) return;
  map.addSource("clients", { type: "geojson", data: EMPTY });
  map.addSource("routes", { type: "geojson", data: EMPTY });
  map.addLayer({
    id: "routes-casing", type: "line", source: "routes",
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": "#ffffff", "line-width": 6.5, "line-opacity": 0.75 },
  });
  map.addLayer({
    id: "routes", type: "line", source: "routes",
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": ["get", "color"], "line-width": 3.5 },
  });
  map.addLayer({
    id: "clients", type: "circle", source: "clients",
    paint: {
      "circle-radius": ["get", "r"], "circle-color": ["get", "color"],
      "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5,
    },
  });
}

function draw(map: maplibregl.Map, marker: maplibregl.Marker, inst: Inst | null, routes: Routes | null) {
  const clientsSrc = map.getSource("clients") as maplibregl.GeoJSONSource | undefined;
  const routesSrc = map.getSource("routes") as maplibregl.GeoJSONSource | undefined;
  if (!inst || !clientsSrc || !routesSrc) return;

  const owner = new Map<number, [number, number]>();
  (routes ?? []).forEach((r, ri) => r.forEach((c, k) => owner.set(c, [ri, k + 1])));
  const q = inst.demand.slice(1);
  const qmin = Math.min(...q);
  const span = Math.max(...q) - qmin || 1;
  const pt = (i: number): [number, number] => [inst.lon[i], inst.lat[i]];

  const clients: GeoJSON.Feature[] = [];
  for (let i = 1; i < inst.n; i++) {
    const [ri, step] = owner.get(i) ?? [-1, 0];
    clients.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: pt(i) },
      properties: {
        id: i, demand: inst.demand[i], route: ri, step,
        color: ri >= 0 ? routeColor(ri) : IDLE_COLOR,
        r: 5 + (7 * (inst.demand[i] - qmin)) / span,
      },
    });
  }
  const lines: GeoJSON.Feature[] = (routes ?? []).map((r, ri) => ({
    type: "Feature",
    geometry: { type: "LineString", coordinates: [0, ...r, 0].map(pt) },
    properties: { route: ri, color: routeColor(ri) },
  }));

  clientsSrc.setData({ type: "FeatureCollection", features: clients });
  routesSrc.setData({ type: "FeatureCollection", features: lines });
  marker.setLngLat(pt(0)).addTo(map);
}

function applyHighlight(map: maplibregl.Map, route: number | null) {
  if (!map.getLayer("routes")) return; // fond de carte en cours de changement : couches absentes
  const pick = (on: number, off: number) =>
    route === null ? on : ["case", ["==", ["get", "route"], route], on, off];
  map.setPaintProperty("routes", "line-opacity", pick(1, 0.12));
  map.setPaintProperty("routes-casing", "line-opacity", pick(0.75, 0.05));
  map.setPaintProperty("clients", "circle-opacity", pick(1, 0.25));
  map.setPaintProperty("clients", "circle-stroke-opacity", pick(1, 0.25));
}

export default function MapView({ inst, routes, highlight, basemap }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const style = useRef<Basemap>(basemap);
  // dernières valeurs, lues par les gestionnaires d'événements de la carte (créés une seule fois)
  const latest = useRef({ inst, routes, highlight });
  latest.current = { inst, routes, highlight };

  // création de la carte (une fois)
  useEffect(() => {
    if (!box.current) return;
    const map = new maplibregl.Map({
      container: box.current,
      style: BASEMAPS[style.current],
      center: [2.4, 46.6],
      zoom: 4.8,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const pin = document.createElement("div");
    pin.className = "depot-pin";
    pin.textContent = "Dépôt";
    const marker = new maplibregl.Marker({ element: pin, anchor: "bottom" });
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });

    const sync = () => {  // au chargement initial et après chaque changement de fond de carte
      ensureLayers(map);
      draw(map, marker, latest.current.inst, latest.current.routes);
      applyHighlight(map, latest.current.highlight);
    };
    map.on("load", sync);
    map.on("style.load", sync);

    // écouteurs liés à une couche : à poser une seule fois (ils survivent au rechargement du style)
    map.on("mousemove", "clients", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      map.getCanvas().style.cursor = "pointer";
      const p = f.properties as { id: number; demand: number; route: number; step: number };
      const rows = [`<b>Client ${p.id}</b>`, `demande ${p.demand}`];
      if (p.route >= 0) rows.push(`camion ${p.route + 1}, étape ${p.step}`);
      popup.setLngLat((f.geometry as GeoJSON.Point).coordinates as [number, number])
        .setHTML(rows.join("<br>")).addTo(map);
    });
    map.on("mouseleave", "clients", () => {
      map.getCanvas().style.cursor = "";
      popup.remove();
    });

    mapRef.current = map;
    markerRef.current = marker;
    return () => {
      marker.remove();
      map.remove();
      mapRef.current = markerRef.current = null;
    };
  }, []);

  // nouvelles données (instance ou tournées)
  useEffect(() => {
    const map = mapRef.current, marker = markerRef.current;
    if (map && marker) draw(map, marker, inst, routes);
  }, [inst, routes]);

  // recadrage quand l'instance ou son placement change (pas à chaque amélioration du solveur)
  const placementKey = inst ? `${inst.id}|${inst.zone}|${inst.span}` : "";
  useEffect(() => {
    const map = mapRef.current;
    const cur = latest.current.inst;
    if (!map || !cur) return;
    const b = new maplibregl.LngLatBounds();
    cur.lon.forEach((x, i) => b.extend([x, cur.lat[i]]));
    map.fitBounds(b, { padding: 70, duration: 500, maxZoom: 14 });
  }, [placementKey]);

  // fond de carte : rechargement complet du style (diff:false), sinon MapLibre retire nos couches
  // sans relancer "style.load"
  useEffect(() => {
    const map = mapRef.current;
    if (!map || style.current === basemap) return;
    style.current = basemap;
    map.setStyle(BASEMAPS[basemap], { diff: false });
  }, [basemap]);

  useEffect(() => {
    if (mapRef.current) applyHighlight(mapRef.current, highlight);
  }, [highlight]);

  return <div ref={box} className="map" />;
}
