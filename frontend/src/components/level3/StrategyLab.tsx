import { useMemo } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, C, fmt } from "../../theme";
import type { DayData } from "../../types";
import {
  type Action, type Battery, diagnose, heuristicActions, hourWeights, optimalRun, runActions,
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

  const w = useMemo(() => hourWeights(day), [day]);
  const why = played ? diagnose(day, bat, runs.user) : [];
  const max = Math.max(...STRATS.map((s) => runs[s.k].score), 0.1);
  const chart = day.hours.map((h, i) => ({
    hour: h,
    user: (100 * runs.user.soc[i]) / bat.cap,
    heur: (100 * runs.heur.soc[i]) / bat.cap,
    opt: (100 * runs.opt.soc[i]) / bat.cap,
  }));
  const wMax = Math.max(...w);

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

      <div className="lab-grid">
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

        <section className="why">
          <p className="label">Per què?</p>
          {why.length ? (
            <ol>{why.map((t, i) => <li key={i}>{t}</li>)}</ol>
          ) : (
            <p className="muted">{played ? "Bona partida: no hem detectat errors clars respecte a l'estratègia òptima." : "Quan juguis, aquí t'explicarem on has guanyat i on has perdut punts."}</p>
          )}
        </section>
      </div>

      <div className="block-sub">
        <p className="label">Què ha fet cada estratègia, hora a hora</p>
        <div className="matrix" role="table" aria-label="Decisions per hora de cada estratègia">
          <div className="mx-row mx-value" role="row">
            <span className="mx-lab" role="rowheader">Valor de l'hora</span>
            {w.map((v, h) => (
              <span key={h} className="mx-cell" role="cell" title={`${day.hours[h]} · ${fmt.gCo2(day.co2[h])}/kWh · ${fmt.cKwh(day.price[h])}/kWh`}>
                <span className="mx-v" style={{ height: `${(100 * v) / wMax}%` }} />
              </span>
            ))}
          </div>
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
          <li><i style={{ background: C.ink }} />Valor de l'hora: com de cara i bruta és l'electricitat (més alt = millor per descarregar)</li>
        </ul>
      </div>

      <div className="block-sub">
        <p className="label">Nivell de la bateria</p>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chart} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={C.grid} vertical={false} />
            <XAxis dataKey="hour" tick={AXIS} interval={2} tickLine={false} axisLine={{ stroke: C.ink }} />
            <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} allowDataOverflow unit=" %" width={50} tick={AXIS} tickLine={false} axisLine={false} />
            <Tooltip formatter={(v, n) => [`${fmt.int(Number(v))} %`, STRATS.find((s) => s.k === n)?.name ?? n]} />
            {STRATS.map((s) => (
              <Line key={s.k} type="stepAfter" dataKey={s.k} stroke={s.color} strokeWidth={s.k === "user" ? 3 : 2}
                strokeDasharray={s.k === "heur" ? "5 4" : undefined} dot={false} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
        <ul className="legend">
          {STRATS.map((s) => <li key={s.k}><i style={{ background: s.color }} />{s.name}</li>)}
        </ul>
      </div>

      <div className="principles">
        <div><b>1 · Posa preu a cada hora.</b><p>L'algorisme combina el CO₂ (70 %) i el preu (30 %) en un sol "valor" per kWh.</p></div>
        <div><b>2 · Busca diferències grans.</b><p>Només mou energia d'una hora barata a una de cara si la diferència supera el 10 % que es perd a la bateria.</p></div>
        <div><b>3 · Respecta els límits.</b><p>{fmt.int(bat.cap)} kWh, {fmt.int(bat.pmax)} kW, sense abocar a la xarxa i acabant el dia com l'ha començat.</p></div>
        <div><b>4 · El repte real: predir.</b><p>Aquí l'algorisme coneix el futur. A la realitat ha de decidir amb previsions de consum, sol, preu i CO₂ que poden fallar.</p></div>
      </div>
    </div>
  );
}
