import { useMemo } from "react";
import { C, fmt } from "../../theme";
import type { DayData } from "../../types";
import {
  type Action, type Battery, heuristicActions, optimalRun, runActions,
} from "../../lib/energy";

interface Props { day: DayData; bat: Battery; actions: Action[] }

const STRATS = [
  { k: "user", name: "La teva estratègia", color: C.charge },
  { k: "heur", name: "Estratègia heurística", color: C.muted },
  { k: "opt", name: "Estratègia òptima", color: C.upc },
] as const;

export default function StrategyLab({ day, bat, actions }: Props) {
  const played = actions.length;
  const full: Action[] = [...actions, ...Array(24 - played).fill("wait")];

  const runs = useMemo(() => ({
    user: runActions(day, bat, full),
    heur: runActions(day, bat, heuristicActions(day)),
    opt: optimalRun(day, bat),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [day, bat, actions]);

  const max = Math.max(...STRATS.map((s) => runs[s.k].score), 0.1);

  const actOf = (k: "user" | "heur" | "opt", h: number) => {
    const r = runs[k];
    return r.c[h] > 5 ? "c" : r.d[h] > 5 ? "d" : "";
  };

  return (
    <div className="lab">
      {played < 24 && (
        <p className="notice">
          {played === 0
            ? "Encara no has jugat. Ara mateix \"la teva estratègia\" és no fer res. Juga al nivell 2 i torna aquí."
            : `Has decidit ${played} de 24 hores. Les hores que falten compten com a "esperar".`}
        </p>
      )}

      <div className="card">
        <section>
          <p className="label">Puntuació oficial del repte · 0,7 × ΔCO₂ % + 0,3 × Δcost %</p>
          <ul className="scores">
            {STRATS.map((s) => {
              const r = runs[s.k];
              return (
                <li key={s.k} className={s.k === "user" ? "me" : ""}>
                  <span className="sc-name">{s.name}</span>
                  <span className="sc-bar"><span style={{ width: `${Math.max(0, (100 * r.score) / max)}%`, background: s.color }} /></span>
                  <span className="sc-val">{fmt.dec(r.score, 1)}<small> punts</small></span>
                  <span className="sc-sub">{fmt.int(r.co2SavedKg)} kg CO₂ · {fmt.eur(r.costSavedEur)}</span>
                </li>
              );
            })}
          </ul>
          <p className="fine">
            Heurística: carrega en el terç d'hores més netes i barates i descarrega en el terç pitjor. Òptima: un model
            d'optimització lineal que coneix tot el dia per endavant. És el sostre: ningú pot fer-ho millor amb aquestes dades.
            Totes han d'acabar el dia amb la bateria com l'han començada: si no, l'energia que falta es compta a l'hora més cara.
          </p>
        </section>

      </div>

      <div className="card">
        <p className="label">Què ha fet cada estratègia, hora a hora</p>
        <div className="matrix" role="table" aria-label="Decisions per hora de cada estratègia">
          {STRATS.map((s) => (
            <div className="mx-row" role="row" key={s.k}>
              <span className="mx-lab" role="rowheader">{s.name.replace("Estratègia ", "")}</span>
              {day.hours.map((hh, h) => {
                const a = actOf(s.k, h);
                return <span key={hh} role="cell" className={`mx-cell act-${a || "w"}`}>{a === "c" ? "▲" : a === "d" ? "▼" : ""}</span>;
              })}
            </div>
          ))}
          <div className="mx-row mx-hours"><span className="mx-lab" />
            {day.hours.map((hh, h) => <span key={hh} className="mx-cell">{h % 3 === 0 ? hh.slice(0, 2) : ""}</span>)}
          </div>
        </div>
        <ul className="legend">
          <li><i style={{ background: C.charge }} />▲ Carrega</li>
          <li><i style={{ background: C.battery }} />▼ Descarrega</li>
        </ul>
      </div>

    </div>
  );
}
