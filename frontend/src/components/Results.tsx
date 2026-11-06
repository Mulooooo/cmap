import type { Inst, Solution } from "../types";
import { fmt, routeColor } from "../format";
import Chart from "./Chart";
import { Stat } from "./Stat";

interface Props {
  inst: Inst;
  solution: Solution;
  onHover(route: number | null): void;
}

export default function Results({ inst, solution: sol, onHover }: Props) {
  return (
    <section id="results">
      <div className={"verdict " + (sol.valid ? "ok" : "bad")}>
        {sol.valid ? `Solution valide (${sol.solver})` : "Solution invalide : " + sol.errors.join(" ; ")}
      </div>
      <div className="stats">
        <Stat label="Coût total" value={fmt(sol.cost)} />
        <Stat label="≈ km" value={fmt(Math.round(sol.cost * inst.km_per_unit))} />
        <Stat label="Camions utilisés" value={sol.routes.length} />
        {sol.gap !== null && <Stat label="Gap vs meilleure connue" value={`${fmt(sol.gap)} %`} />}
        <Stat label="Temps de calcul" value={`${fmt(sol.elapsed)} s`} />
      </div>

      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Camion</th><th>Itinéraire</th><th className="num">Clients</th><th>Charge</th>
              <th className="num">Distance</th><th className="num">≈ km</th>
            </tr>
          </thead>
          <tbody>
            {sol.routes.map((r, i) => {
              const s = sol.per_route[i];
              return (
                <tr key={i} onMouseEnter={() => onHover(i)} onMouseLeave={() => onHover(null)}>
                  <td><span className="dot" style={{ background: routeColor(i) }} />{i + 1}</td>
                  <td className="path">{["D", ...r, "D"].join(" → ")}</td>
                  <td className="num">{s.n}</td>
                  <td>
                    <div className="load">
                      <i><em style={{ width: `${Math.min(100, (100 * s.load) / inst.capacity)}%` }} /></i>
                      <span>{s.load}/{inst.capacity}</span>
                    </div>
                  </td>
                  <td className="num">{fmt(s.dist)}</td>
                  <td className="num">{fmt(Math.round(s.dist * inst.km_per_unit))}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {sol.history.length >= 2 && (
        <>
          <h3>Convergence</h3>
          <Chart points={sol.history.map((h) => [h[0], h[2]])} bks={inst.bks} />
        </>
      )}
    </section>
  );
}
