import { useRef, useState } from "react";
import type { Basemap, Config } from "../types";

export interface Controls {
  library: string;
  zone: string;
  span: number;
  basemap: Basemap;
  solver: string;
  limit: number;
  seed: number;
}

interface Props {
  config: Config;
  controls: Controls;
  running: boolean;
  canRun: boolean;
  onChange(patch: Partial<Controls>): void;
  onLibrary(name: string): void;
  onFile(file: File): void;
  onRun(): void;
}

export default function Sidebar({ config, controls: c, running, canRun, onChange, onLibrary, onFile, onRun }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  return (
    <aside className="side">
      <h1>
        CMAP <small>Tournées de livraison</small>
      </h1>

      <section>
        <h2><span className="step">1</span> Instance</h2>
        <label>
          Instances du dépôt
          <select value={c.library} onChange={(e) => onLibrary(e.target.value)}>
            {config.library.map((n) => <option key={n}>{n}</option>)}
          </select>
        </label>
        <div
          className={"drop" + (over ? " over" : "")}
          tabIndex={0}
          role="button"
          aria-label="Choisir un fichier .vrp"
          onClick={() => fileInput.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && fileInput.current?.click()}
          onDragEnter={(e) => { e.preventDefault(); setOver(true); }}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation(); // sinon le dépôt est traité deux fois (zone + fenêtre)
            setOver(false);
            const f = e.dataTransfer.files[0];
            if (f) onFile(f);
          }}
        >
          Glisse un fichier <b>.vrp</b> ici<br /><span>ou clique pour en choisir un</span>
          <input
            ref={fileInput} type="file" accept=".vrp" hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onFile(f);
              e.target.value = "";
            }}
          />
        </div>
      </section>

      <section>
        <h2><span className="step">2</span> Carte</h2>
        <label>
          Zone
          <select value={c.zone} onChange={(e) => onChange({ zone: e.target.value })}>
            {Object.keys(config.zones).map((z) => <option key={z}>{z}</option>)}
          </select>
        </label>
        <label>
          Étendue de l'instance <span className="val">{c.span} km</span>
          <input type="range" min={20} max={1200} step={10} value={c.span}
                 onChange={(e) => onChange({ span: Number(e.target.value) })} />
        </label>
        <label>
          Fond de carte
          <select value={c.basemap} onChange={(e) => onChange({ basemap: e.target.value as Basemap })}>
            <option value="light">Clair</option>
            <option value="dark">Sombre</option>
          </select>
        </label>
      </section>

      <section>
        <h2><span className="step">3</span> Calcul</h2>
        <label>
          Solveur
          <select value={c.solver} onChange={(e) => onChange({ solver: e.target.value })}>
            {config.solvers.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <label>
          Temps limite <span className="val">{c.limit} s</span>
          <input type="range" min={1} max={120} step={1} value={c.limit}
                 onChange={(e) => onChange({ limit: Number(e.target.value) })} />
        </label>
        <label>
          Graine aléatoire
          <input type="number" min={0} max={100000} value={c.seed}
                 onChange={(e) => onChange({ seed: Math.max(0, Number(e.target.value) || 0) })} />
        </label>
        <button className={"primary" + (running ? " stop" : "")} disabled={!canRun && !running} onClick={onRun}>
          {running ? "■ Arrêter" : "▶ Calculer"}
        </button>
      </section>
    </aside>
  );
}
