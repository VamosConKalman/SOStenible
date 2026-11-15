import { useMemo } from "react";
import { C, fmt, tercile } from "../../theme";
import type { DayData } from "../../types";
import {
  type Action, type Battery, type RunResult, heuristicActions, optimalRun, runActions,
} from "../../lib/energy";

interface Props { day: DayData; bat: Battery; actions: Action[] }
type Key = "user" | "heur" | "opt";

const STRATS: { k: Key; name: string; color: string; desc: string }[] = [
  { k: "user", name: "La teva estratègia", color: C.charge, desc: "Les decisions que has pres al joc, hora a hora." },
  { k: "heur", name: "Estratègia heurística", color: "#7A7A75", desc: "Carrega en el terç d'hores més netes i barates i descarrega en el terç pitjor." },
  { k: "opt", name: "Estratègia òptima", color: C.upc, desc: "Un model d'optimització lineal que coneix tot el dia per endavant. És el sostre: ningú pot fer-ho millor amb aquestes dades." },
];

/** Fons de cada hora segons la intensitat de carboni de la xarxa. */
const ZONE = ["#DCEFD0", "#F7E7C2", "#F6D3CF"];
const ZONE_TXT = ["Xarxa baixa en carboni", "De transició", "Xarxa alta en carboni"];

function ScoreCard({ s, r, best, lo }: { s: (typeof STRATS)[number]; r: RunResult; best: number; lo: number }) {
  const span = best - lo || 1;
  const zeroX = (100 * (0 - lo)) / span;
  const valX = (100 * (r.score - lo)) / span;
  const pct = s.k !== "opt" && best > 0 ? (100 * r.score) / best : null;
  return (
    <article className={`score-card ${s.k}`}>
      <p className="sc-title" style={{ color: s.color }}>{s.name}</p>
      <p className="sc-desc">{s.desc}</p>
      <div className="sc-big">
        <span className={r.score < 0 ? "neg" : ""}>{fmt.dec(r.score, 1)}</span><small>punts</small>
        {pct !== null && <em>{fmt.int(pct)} % del model</em>}
        {s.k === "opt" && <em>màxim possible</em>}
      </div>
      <div className="sc-scale" role="img" aria-label={`${fmt.dec(r.score, 1)} punts sobre ${fmt.dec(best, 1)} possibles`}>
        <span className="sc-fill" style={{ left: `${Math.min(zeroX, valX)}%`, width: `${Math.abs(valX - zeroX)}%`, background: r.score < 0 ? C.bad : s.color }} />
        <span className="sc-zero" style={{ left: `${zeroX}%` }} />
      </div>
      <dl className="sc-facts">
        <div><dt>CO₂</dt><dd>{r.co2SavedKg >= 0 ? `${fmt.int(r.co2SavedKg)} kg evitats` : `${fmt.int(-r.co2SavedKg)} kg de més`}</dd></div>
        <div><dt>Factura</dt><dd>{r.costSavedEur >= 0 ? `${fmt.eur(r.costSavedEur)} estalviats` : `${fmt.eur(-r.costSavedEur)} de més`}</dd></div>
      </dl>
    </article>
  );
}

/** Pistes de potència: barres amunt (carrega) i avall (descarrega) sobre el CO₂ de cada hora. */
function PowerTracks({ day, runs, pmax }: { day: DayData; runs: Record<Key, RunResult>; pmax: number }) {
  const W = 960, lab = 170, cw = (W - lab) / 24, rh = 64, gap = 16, H = STRATS.length * (rh + gap) + 20;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="tracks" role="img" aria-label="Potència de càrrega i descàrrega de cada estratègia, hora a hora, sobre la intensitat de carboni de la xarxa">
      {STRATS.map((s, r) => {
        const y0 = r * (rh + gap), mid = y0 + rh / 2, run = runs[s.k];
        return (
          <g key={s.k}>
            <text x={0} y={mid - 3} className="tr-name" fill={s.color}>{s.name.replace("Estratègia ", "")}</text>
            <text x={0} y={mid + 14} className="tr-sub">{fmt.dec(run.score, 1)} punts</text>
            {day.co2.map((v, h) => {
              const t = tercile(day.co2, v);
              return <rect key={h} x={lab + h * cw} y={y0} width={cw - 1} height={rh} fill={ZONE[t === "good" ? 0 : t === "warn" ? 1 : 2]} />;
            })}
            <line x1={lab} x2={W} y1={mid} y2={mid} stroke="#C3C2B7" />
            {day.hours.map((hh, h) => {
              const p = run.c[h] - run.d[h];
              if (Math.abs(p) < 5) return null;
              const bh = (Math.abs(p) / pmax) * (rh / 2 - 3);
              return (
                <rect key={hh} x={lab + h * cw + 2.5} y={p > 0 ? mid - bh : mid} width={cw - 6} height={bh} rx={2.5} fill={p > 0 ? C.charge : C.battery}>
                  <title>{`${hh} · ${p > 0 ? "carrega" : "descarrega"} ${fmt.int(Math.abs(p))} kW · ${fmt.gCo2(day.co2[h])} CO₂/kWh`}</title>
                </rect>
              );
            })}
          </g>
        );
      })}
      {[0, 3, 6, 9, 12, 15, 18, 21].map((h) => (
        <text key={h} x={lab + h * cw + cw / 2} y={H - 4} textAnchor="middle" className="tr-sub">{String(h).padStart(2, "0")}</text>
      ))}
    </svg>
  );
}

export default function StrategyLab({ day, bat, actions }: Props) {
  const played = actions.length;
  const full: Action[] = [...actions, ...Array(24 - played).fill("wait")];

  const runs = useMemo<Record<Key, RunResult>>(() => ({
    user: runActions(day, bat, full),
    heur: runActions(day, bat, heuristicActions(day)),
    opt: optimalRun(day, bat),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [day, bat, actions]);

  const best = Math.max(runs.opt.score, 0.1);
  const lo = Math.min(0, runs.user.score, runs.heur.score);

  return (
    <div className="lab">
      {played < 24 && (
        <p className="notice">
          {played === 0
            ? "Encara no has jugat. Ara mateix \"la teva estratègia\" és no fer res. Juga a la secció 2 i torna aquí."
            : `Has decidit ${played} de 24 hores. Les hores que falten compten com a "esperar".`}
        </p>
      )}

      <div className="card">
        <p className="label">Puntuació oficial del repte · 0,7 × ΔCO₂ % + 0,3 × Δcost %</p>
        <div className="score-cards">
          {STRATS.map((s) => <ScoreCard key={s.k} s={s} r={runs[s.k]} best={best} lo={lo} />)}
        </div>
        <p className="fine sc-rule">
          0 punts vol dir el mateix que no tenir bateria. Totes les estratègies han d'acabar el dia amb la bateria com l'han
          començada: si no, l'energia que falta es compta a l'hora més cara.
        </p>
      </div>

      <div className="card">
        <p className="label">Què ha fet cada estratègia, hora a hora</p>
        <ul className="legend">
          <li><i style={{ background: C.charge }} />Carrega</li>
          <li><i style={{ background: C.battery }} />Descarrega</li>
          {ZONE.map((z, i) => <li key={z}><i style={{ background: z, border: "1px solid #e4e2da" }} />{ZONE_TXT[i]}</li>)}
        </ul>
        <PowerTracks day={day} runs={runs} pmax={bat.pmax} />
        <p className="fine">Barra cap amunt = carrega; cap avall = descarrega. L'alçada indica la potència (fins a {fmt.int(bat.pmax)} kW).</p>
      </div>
    </div>
  );
}
