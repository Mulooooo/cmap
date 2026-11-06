import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api";
import { fmt } from "./format";
import type { Config, Inst, Routes, Solution } from "./types";
import MapView from "./components/MapView";
import Results from "./components/Results";
import Sidebar, { type Controls } from "./components/Sidebar";
import { Stat } from "./components/Stat";

const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [controls, setControls] = useState<Controls>({
    library: "", zone: "", span: 700, basemap: prefersDark ? "dark" : "light",
    solver: "", limit: 10, seed: 0,
  });
  const [inst, setInst] = useState<Inst | null>(null);
  const [routes, setRoutes] = useState<Routes | null>(null);
  const [solution, setSolution] = useState<Solution | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<number | null>(null);
  const stopRef = useRef<(() => void) | null>(null);

  const fail = useCallback((e: unknown) => setToast(e instanceof Error ? e.message : String(e)), []);

  const stop = useCallback(() => {
    stopRef.current?.();
    stopRef.current = null;
    setRunning(false);
    setStatus(null);
  }, []);

  /** Nouvelle instance : on abandonne le calcul et la solution précédents. */
  const adopt = useCallback((i: Inst) => {
    stop();
    setInst(i);
    setRoutes(null);
    setSolution(null);
    setHighlight(null);
  }, [stop]);

  // démarrage : configuration du serveur, puis première instance du dépôt
  useEffect(() => {
    api.getConfig().then((cfg) => {
      setConfig(cfg);
      const zone = Object.keys(cfg.zones)[0];
      const span = cfg.zones[zone].span;
      const library = cfg.library[0] ?? "";
      setControls((c) => ({ ...c, library, zone, span, solver: cfg.solvers[0] ?? "" }));
      if (library) api.loadLibrary(library, zone, span).then(adopt).catch(fail);
    }).catch((e) => fail(new Error("Impossible de joindre le serveur : " + (e as Error).message)));
    return () => stopRef.current?.();
  }, [adopt, fail]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 7000);
    return () => clearTimeout(t);
  }, [toast]);

  // zone / étendue modifiées : on replace les mêmes points ailleurs (un peu de délai pendant le glissement)
  useEffect(() => {
    if (!inst || (inst.zone === controls.zone && inst.span === controls.span)) return;
    const t = setTimeout(() => {
      api.replaceInstance(inst.id, controls.zone, controls.span).then(setInst).catch(fail);
    }, 150);
    return () => clearTimeout(t);
  }, [inst, controls.zone, controls.span, fail]);

  const change = (patch: Partial<Controls>) => {
    if (patch.zone && config) patch = { ...patch, span: config.zones[patch.zone].span };
    setControls((c) => ({ ...c, ...patch }));
  };

  const loadFile = useCallback((file: File) => {
    api.uploadInstance(file, controls.zone, controls.span).then(adopt).catch(fail);
  }, [controls.zone, controls.span, adopt, fail]);

  // un .vrp lâché n'importe où sur la page ne doit pas être ouvert par le navigateur
  const loadFileRef = useRef(loadFile);
  loadFileRef.current = loadFile;
  useEffect(() => {
    const over = (e: DragEvent) => e.preventDefault();
    const drop = (e: DragEvent) => {
      e.preventDefault();
      const f = e.dataTransfer?.files[0];
      if (f) loadFileRef.current(f);
    };
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, []);

  const run = () => {
    if (running) return stop();
    if (!inst) return;
    stop();
    setRunning(true);
    setSolution(null);
    setStatus("Démarrage du calcul…");
    const finish = () => { stopRef.current = null; setRunning(false); setStatus(null); };
    stopRef.current = api.solve(
      { instance: inst.id, solver: controls.solver, timeLimit: controls.limit, seed: controls.seed },
      {
        onProgress: (p) => {
          setRoutes(p.routes);
          setStatus(`Calcul en cours… ${fmt(p.elapsed)} s · meilleur coût ${fmt(p.cost)}`);
        },
        onDone: (s) => { finish(); setRoutes(s.routes); setSolution(s); },
        onError: (m) => { finish(); setToast(m); },
      },
    );
  };

  if (!config) {
    return <div className="app"><main><p className="note">Connexion au serveur…</p>{toast && <div className="toast">{toast}</div>}</main></div>;
  }

  return (
    <div className="app">
      <Sidebar
        config={config}
        controls={controls}
        running={running}
        canRun={inst !== null}
        onChange={change}
        onLibrary={(name) => {
          change({ library: name });
          api.loadLibrary(name, controls.zone, controls.span).then(adopt).catch(fail);
        }}
        onFile={loadFile}
        onRun={run}
      />
      <main>
        <header className="top">
          <h2>{inst ? `${inst.name} · ${inst.n - 1} clients` : "Choisis une instance"}</h2>
          {inst && (
            <div className="stats">
              <Stat label="Capacité" value={inst.capacity} />
              <Stat label="Demande totale" value={inst.total_demand} />
              <Stat label="Camions (min.)" value={inst.min_vehicles} />
              <Stat label="Meilleure connue" value={inst.bks ? fmt(inst.bks) : "n/a"} />
            </div>
          )}
        </header>

        <div id="mapWrap">
          <MapView inst={inst} routes={routes} highlight={highlight} basemap={controls.basemap} />
          {status && <div className="status">{status}</div>}
          {toast && <div className="toast" role="alert">{toast}</div>}
        </div>
        {inst && (
          <p className="note">
            Les points de l'instance sont posés sur la carte par homothétie (ils ne correspondent pas à de
            vraies villes) et les trajets sont tracés à vol d'oiseau.{" "}
            Échelle : 1 unité de distance = {fmt(inst.km_per_unit)} km.
          </p>
        )}

        {inst && solution && !running && <Results inst={inst} solution={solution} onHover={setHighlight} />}
      </main>
    </div>
  );
}
