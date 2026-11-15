// Rolling horizon i escenaris (versió simplificada).
// A cada hora l'agent fa un pla per a les properes hores amb la seva previsió,
// n'aplica només la primera hora i torna a planificar. Aquí es mostren:
//  1) diverses versions del dia (Montecarlo) i la puntuació de l'agent a cada una;
//  2) els plans successius de l'agent per a l'estat de la bateria.
import { useEffect, useMemo, useState } from "react";
import { Loader2, Pause, Play } from "lucide-react";
import { C, fmt } from "../../theme";
import { useAgents, useDays, useRollingHorizon, type Mode } from "../../api/hooks";
import type { RollingHorizonResult, ScenarioParams } from "../../api/types";
import { LineChart, type Pt, type Series } from "./charts";
import { DEFAULT_SCENARIO } from "./ScenarioControls";

const hourLbl = (x: number) => (x < 24 ? `${String(x).padStart(2, "0")}:00` : `+1d ${String(x - 24).padStart(2, "0")}h`);
const kwh = (v: number) => `${fmt.int(v)} kWh`;

/** Nivells d'incertesa: errors de previsió de consum, sol, preu i CO₂. */
const UNCERTAINTY: { id: string; label: string; desc: string; p: Partial<ScenarioParams> }[] = [
  { id: "low", label: "Baixa", desc: "Errors petits: consum ±5 %, sol ±10 %.", p: { demand_noise: 0.05, solar_noise: 0.1, persistence: 0.7 } },
  { id: "mid", label: "Mitjana", desc: "Consum ±10 %, sol ±20 %, preu ±10 %.", p: { demand_noise: 0.1, solar_noise: 0.2, price_noise: 0.1, persistence: 0.8 } },
  { id: "high", label: "Alta", desc: "Consum ±15 %, sol ±30 %, preu ±20 % i CO₂ ±10 %.", p: { demand_noise: 0.15, solar_noise: 0.3, price_noise: 0.2, co2_noise: 0.1, persistence: 0.8 } },
];
const N_SAMPLES = 12;

function mean(a: number[]) { return a.length ? a.reduce((s, v) => s + v, 0) / a.length : 0; }

/** Punts de cada versió del dia: punt = agent, marca verda = el millor possible en aquella versió. */
function ScoreStrip({ r, active, onPick }: { r: RollingHorizonResult; active: number; onPick: (seed: number) => void }) {
  const all = r.ensemble.flatMap((e) => [e.score, e.oracle]);
  const lo = Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo) * 0.08 || 1;
  const x = (v: number) => 30 + ((v - (lo - pad)) / (hi - lo + 2 * pad)) * 700;
  const ticks = [...Array(6).keys()].map((i) => lo - pad + (i * (hi - lo + 2 * pad)) / 5);
  return (
    <svg viewBox="0 0 760 92" role="img" aria-label="Puntuació de l'agent a cada versió del dia" style={{ width: "100%", height: "auto" }}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={10} y2={68} stroke={C.grid} />
          <text x={x(t)} y={86} textAnchor="middle" className="rh-axis">{fmt.dec(t, 1)} pts</text>
        </g>
      ))}
      {r.ensemble.map((e, i) => {
        const y = 18 + (i % 6) * 9;
        const on = e.seed === active;
        return (
          <g key={e.seed} style={{ cursor: "pointer" }} onClick={() => onPick(e.seed)}>
            <title>{`Versió ${i + 1}: agent ${fmt.dec(e.score, 2)} punts · màxim possible ${fmt.dec(e.oracle, 2)}`}</title>
            <line x1={x(e.score)} x2={x(e.oracle)} y1={y} y2={y} stroke={on ? C.charge : C.grid} strokeWidth={on ? 2 : 1} />
            <rect x={x(e.oracle) - 1.5} y={y - 4} width={3} height={8} fill={C.green} />
            <circle cx={x(e.score)} cy={y} r={on ? 6 : 4.5} fill={on ? C.charge : C.upc} stroke="#fff" strokeWidth={2} />
          </g>
        );
      })}
    </svg>
  );
}

export default function RollingHorizonDashboard({ initialDate }: { initialDate?: string }) {
  const { agents, defaultMode } = useAgents();
  const [mode, setMode] = useState<Mode>("dificil");
  useEffect(() => { if (agents.some((agent) => agent.id === defaultMode)) setMode(defaultMode); }, [agents, defaultMode]);
  const { days, loading: daysLoading } = useDays(mode);
  const [date, setDate] = useState(initialDate ?? "");
  const [unc, setUnc] = useState("mid");
  const [activeSeed, setActiveSeed] = useState<number | null>(null);
  const [step, setStep] = useState(12);
  const [hoverPlan, setHoverPlan] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!date && days.length) setDate(days.find((d) => d.date === initialDate)?.date ?? days[Math.floor(days.length / 2)].date);
  }, [days, date, initialDate]);

  const scenario = useMemo<ScenarioParams>(() => ({ ...DEFAULT_SCENARIO, ...UNCERTAINTY.find((u) => u.id === unc)!.p }), [unc]);
  const req = useMemo(() => (date ? { date, mode, scenario, nSamples: N_SAMPLES, activeSeed: activeSeed ?? undefined } : null),
    [date, mode, scenario, activeSeed]);
  const { result: r, loading, error } = useRollingHorizon(req);

  useEffect(() => {
    if (!playing) return;
    const id = setTimeout(() => setStep((s) => (s + 1) % 24), 900);
    return () => clearTimeout(id);
  }, [playing, step]);

  const cap = r?.battery.capacityKwh ?? (mode === "dificil" ? 6000 : 2000);
  const maxX = useMemo(() => (r ? Math.max(24, ...r.steps.map((s) => s.t + s.H)) : 47), [r]);
  const actSeed = r?.activeSeed ?? scenario.seed;

  // Versions del dia: estat de la bateria executat a cadascuna
  const ensSeries: Series[] = useMemo(() => {
    if (!r) return [];
    const out: Series[] = r.ensemble.filter((e) => e.seed !== actSeed).map((e) => ({
      id: `ens-${e.seed}`, label: `Versió · ${fmt.dec(e.score, 2)} pts`, pts: e.socPath.map((y, x) => [x, y] as Pt),
      color: hoverPlan === `ens-${e.seed}` ? C.charge : C.upc, width: hoverPlan === `ens-${e.seed}` ? 2.5 : 1.3,
      opacity: hoverPlan === `ens-${e.seed}` ? 1 : 0.35, onClick: () => setActiveSeed(e.seed),
    }));
    out.push({ id: "act", label: "Versió seleccionada", pts: r.active.socPath.map((y, x) => [x, y]), color: C.charge, width: 3, legend: true, tooltip: true, fmt: kwh });
    return out;
  }, [r, hoverPlan, actSeed]);

  // Plans successius (només estat de la bateria)
  const fanSeries: Series[] = useMemo(() => {
    if (!r) return [];
    const out: Series[] = r.steps.filter((s) => s.t !== step).map((s) => ({
      id: `plan-${s.t}`, label: `Pla de les ${hourLbl(s.t)}`, pts: (s.soc ?? []).map((y, k) => [s.t + k, y] as Pt),
      color: hoverPlan === `plan-${s.t}` ? C.charge : C.upc, width: hoverPlan === `plan-${s.t}` ? 2.5 : 1.2,
      opacity: hoverPlan === `plan-${s.t}` ? 0.95 : 0.2, onClick: () => { setStep(s.t); setPlaying(false); },
    }));
    out.push({ id: "exec", label: "El que passa de veritat", pts: r.active.socPath.map((y, x) => [x, y]), color: C.ink, width: 3, legend: true, tooltip: true, fmt: kwh });
    const sel = r.steps.find((s) => s.t === step);
    if (sel) out.push({ id: "sel", label: `Pla fet a les ${hourLbl(step)}`, pts: (sel.soc ?? []).map((y, k) => [sel.t + k, y]), color: C.charge, width: 3.2, legend: true, tooltip: true, fmt: kwh });
    return out;
  }, [r, step, hoverPlan]);

  const scores = r?.ensemble.map((e) => e.score) ?? [];
  const oracles = r?.ensemble.map((e) => e.oracle) ?? [];
  const capture = mean(oracles) > 0 ? (100 * mean(scores)) / mean(oracles) : 0;
  const uncDesc = UNCERTAINTY.find((u) => u.id === unc)!.desc;

  return (
    <div className="rh rh-simple">
      <header className="rh-head">
        <div>
          <h2>Com decideix l'agent quan no coneix el futur</h2>
          <p className="lead">
            Cada hora l'agent fa un pla per a les properes hores amb la seva previsió, aplica només la primera decisió i,
            quan arriba la dada real, torna a planificar. És el que s'anomena <em>rolling horizon</em>.
          </p>
        </div>
        <div className="rh-head-ctl">
          <select value={mode} onChange={(e) => { setMode(e.target.value as Mode); setActiveSeed(null); }} aria-label="Agent">
            {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.label} · bateria {fmt.int(agent.capacity_kwh / 1000)} MWh</option>)}
          </select>
          <select value={date} onChange={(e) => { setDate(e.target.value); setActiveSeed(null); }} aria-label="Dia" disabled={daysLoading}>
            {days.map((d) => <option key={d.date} value={d.date}>{d.date} · {d.label}</option>)}
          </select>
          {loading && <span className="rh-status busy" aria-live="polite"><Loader2 size={14} className="spin" /> Calculant…</span>}
        </div>
      </header>

      {error && <p className="rh-error">No s'ha pogut calcular: {error}. Comprova que el backend és en marxa (uvicorn al port 8000).</p>}
      {!r && !error && <p className="muted">Calculant…</p>}

      {r && (
        <div className={`rh-body ${loading ? "stale" : ""}`}>
          <section className="card rh-card">
            <div className="rh-card-head">
              <div>
                <h3>1 · El mateix dia, {N_SAMPLES} versions possibles</h3>
                <p className="fine">
                  La previsió mai és perfecta. Hem generat {N_SAMPLES} versions del dia amb errors diferents (Montecarlo) i
                  l'agent les ha gestionat totes. Cada línia és com evoluciona la bateria en una versió.
                </p>
              </div>
              <div className="rh-seg small" role="group" aria-label="Incertesa de la previsió">
                <span className="rh-seg-label">Incertesa</span>
                {UNCERTAINTY.map((u) => (
                  <button key={u.id} className={unc === u.id ? "on" : ""} title={u.desc} onClick={() => { setUnc(u.id); setActiveSeed(null); }}>{u.label}</button>
                ))}
              </div>
            </div>
            <LineChart series={ensSeries} xMin={0} xMax={24} yMin={0} yMax={cap} xFmt={hourLbl} yFmt={kwh}
              xTicks={[0, 3, 6, 9, 12, 15, 18, 21, 24]} onHoverSeries={setHoverPlan}
              ariaLabel="Estat de la bateria a cada versió del dia" height={220} />
            <div className="rh-summary">
              <p><b>{fmt.dec(mean(scores), 1)} punts</b> de mitjana · l'agent aconsegueix el <b>{fmt.int(capture)} %</b> del que faria qui conegués el futur.</p>
              <p className="fine">{uncDesc} Cada punt blau és una versió (fes-hi clic per seleccionar-la); la marca verda és el màxim possible en aquella versió.</p>
            </div>
            <ScoreStrip r={r} active={actSeed} onPick={(s) => setActiveSeed(s)} />
          </section>

          <section className="card rh-card">
            <div className="rh-card-head">
              <div>
                <h3>2 · Un pla nou cada hora</h3>
                <p className="fine">
                  Les línies blaves són els plans que l'agent fa a cada hora per a la bateria; la negra és el que passa de veritat.
                  Mou l'hora per veure el pla que tenia en aquell moment (en lila).
                </p>
              </div>
              <div className="rh-stepper">
                <button className="btn-line" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Atura" : "Reprodueix"}>
                  {playing ? <Pause size={16} /> : <Play size={16} />}
                </button>
                <input type="range" min={0} max={23} value={step} onChange={(e) => { setStep(+e.target.value); setPlaying(false); }} aria-label="Hora" />
                <b>{hourLbl(step)}</b>
              </div>
            </div>
            <LineChart series={fanSeries} xMin={0} xMax={maxX} xFmt={hourLbl} yFmt={kwh}
              xTicks={[0, 6, 12, 18, 24, 30, 36, 42].filter((x) => x <= maxX)} yMin={0} yMax={cap}
              bands={[{ x0: 24, x1: maxX, fill: "rgba(20,20,20,0.04)", label: "Demà (només previsió)" }]}
              vline={step} onHoverSeries={setHoverPlan} onClickX={(x) => { if (x < 24) { setStep(x); setPlaying(false); } }}
              ariaLabel="Plans successius de l'agent per a l'estat de la bateria" height={280} />
          </section>
        </div>
      )}
    </div>
  );
}
