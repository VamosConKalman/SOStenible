// Dashboard de Rolling Horizon + generador d'escenaris.
// A cada hora t l'agent (el de 22,94 en mode difícil) resol un LP de H hores amb
// la seva previsió; només n'aplica la primera hora i a t+1 torna a planificar.
// Aquí es veuen totes aquestes plans ("ventall"), el camí executat, la referència
// amb informació perfecta i un conjunt d'escenaris pertorbats (Monte Carlo).
import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Loader2, Pause, Play, RotateCcw } from "lucide-react";
import { C, fmt } from "../../theme";
import { useDays, useRollingHorizon, type Mode } from "../../api/hooks";
import type { RhStep, RollingHorizonResult, ScenarioParams } from "../../api/types";
import { Bars, Heatmap, LineChart, type Pt, type Series } from "./charts";
import ScenarioControls, { DEFAULT_SCENARIO, PRESETS } from "./ScenarioControls";

type Var = "soc" | "power" | "net";

const VARS: { key: Var; label: string; unit: string }[] = [
  { key: "soc", label: "Estat de càrrega planificat", unit: "kWh" },
  { key: "power", label: "Potència planificada", unit: "kW" },
  { key: "net", label: "Càrrega neta prevista", unit: "kW" },
];

const hourLbl = (x: number) => (x < 24 ? `${String(x).padStart(2, "0")}:00` : `+1d ${String(x - 24).padStart(2, "0")}h`);
const kw = (v: number) => `${fmt.int(v)} kW`;
const kwh = (v: number) => `${fmt.int(v)} kWh`;

function planPts(st: RhStep, v: Var): Pt[] {
  if (v === "soc") return (st.soc ?? []).map((y, k) => [st.t + k, y]);
  if (v === "power") return (st.c ?? []).map((c, k) => [st.t + k, c === null || st.d?.[k] == null ? null : c - (st.d[k] as number)]);
  return (st.netRaw ?? []).map((y, k) => [st.t + k, y]);
}

function mean(a: number[]) { return a.length ? a.reduce((s, v) => s + v, 0) / a.length : 0; }
function quantile(a: number[], q: number) {
  if (!a.length) return 0;
  const s = [...a].sort((x, y) => x - y);
  const i = (s.length - 1) * q, lo = Math.floor(i), hi = Math.ceil(i);
  return s[lo] + (s[hi] - s[lo]) * (i - lo);
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "good" | "bad" | "upc" }) {
  return (
    <div className={`rh-kpi ${tone ?? ""}`}>
      <span className="rh-kpi-label">{label}</span>
      <span className="rh-kpi-value">{value}</span>
      {sub && <span className="rh-kpi-sub">{sub}</span>}
    </div>
  );
}

/** Franja de punts: cada escenari és un punt (agent) i una marca (informació perfecta). */
function ScoreStrip({ r, active, onPick }: { r: RollingHorizonResult; active: number; onPick: (seed: number) => void }) {
  const all = r.ensemble.flatMap((e) => [e.score, e.oracle]).concat([r.baseline.score, r.baseline.oracle]);
  const lo = Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo) * 0.08 || 1;
  const x = (v: number) => 30 + ((v - (lo - pad)) / (hi - lo + 2 * pad)) * 700;
  const ticks = [...Array(6).keys()].map((i) => lo - pad + (i * (hi - lo + 2 * pad)) / 5);
  return (
    <svg viewBox="0 0 760 96" role="img" aria-label="Puntuació de cada escenari" style={{ width: "100%", height: "auto" }}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={14} y2={70} stroke={C.grid} />
          <text x={x(t)} y={88} textAnchor="middle" className="rh-axis">{fmt.dec(t, 1)}</text>
        </g>
      ))}
      <line x1={x(r.baseline.score)} x2={x(r.baseline.score)} y1={8} y2={76} stroke={C.ink2} strokeDasharray="4 3" strokeWidth={1.5} />
      <text x={x(r.baseline.score) + 4} y={12} className="rh-axis">dia real {fmt.dec(r.baseline.score, 2)}</text>
      {r.ensemble.map((e, i) => {
        const y = 26 + (i % 5) * 9;
        const on = e.seed === active;
        return (
          <g key={e.seed} style={{ cursor: "pointer" }} onClick={() => onPick(e.seed)}>
            <title>{`Escenari llavor ${e.seed}: agent ${fmt.dec(e.score, 2)} · informació perfecta ${fmt.dec(e.oracle, 2)}`}</title>
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
  const [mode, setMode] = useState<Mode>("dificil");
  const { days, loading: daysLoading } = useDays(mode);
  const [date, setDate] = useState(initialDate ?? "");
  const [scenario, setScenario] = useState<ScenarioParams>(DEFAULT_SCENARIO);
  const [preset, setPreset] = useState<string | null>("real");
  const [nSamples, setNSamples] = useState(8);
  const [activeSeed, setActiveSeed] = useState<number | null>(null);
  const [step, setStep] = useState(12);
  const [hoverPlan, setHoverPlan] = useState<string | null>(null);
  const [v, setV] = useState<Var>("soc");
  const [playing, setPlaying] = useState(false);
  const [showFan, setShowFan] = useState(true);

  useEffect(() => {
    if (!date && days.length) setDate(days.find((d) => d.date === initialDate)?.date ?? days[Math.floor(days.length / 2)].date);
  }, [days, date, initialDate]);

  const req = useMemo(() => (date ? { date, mode, scenario, nSamples, activeSeed: activeSeed ?? undefined } : null),
    [date, mode, scenario, nSamples, activeSeed]);
  const { result: r, loading, error, ms } = useRollingHorizon(req);

  useEffect(() => {
    if (!playing) return;
    const id = setTimeout(() => setStep((s) => (s + 1) % 24), 900);
    return () => clearTimeout(id);
  }, [playing, step]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT" || (e.target as HTMLElement)?.tagName === "SELECT") return;
      if (e.key === "ArrowRight") setStep((s) => Math.min(23, s + 1));
      if (e.key === "ArrowLeft") setStep((s) => Math.max(0, s - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const setS = (p: Partial<ScenarioParams>) => { setScenario((s) => ({ ...s, ...p })); setPreset(null); setActiveSeed(null); };
  const pickPreset = (id: string) => {
    const pr = PRESETS.find((p) => p.id === id);
    if (!pr) return;
    setScenario({ ...DEFAULT_SCENARIO, seed: scenario.seed, ...pr.p });
    setPreset(id);
    setActiveSeed(null);
  };

  const cap = r?.battery.capacityKwh ?? (mode === "dificil" ? 6000 : 2000);
  const pmax = r?.battery.powerKw ?? (mode === "dificil" ? 1500 : 500);
  const st = r?.steps[Math.min(step, (r?.steps.length ?? 1) - 1)];
  const maxX = useMemo(() => (r ? Math.max(24, ...r.steps.map((s) => s.t + s.H)) : 47), [r]);
  const isReal = preset === "real";
  const actSeed = r?.activeSeed ?? scenario.seed;

  // --- ventall de plans (rolling horizon) ---
  const fanSeries: Series[] = useMemo(() => {
    if (!r) return [];
    const out: Series[] = [];
    if (showFan) {
      for (const s of r.steps) {
        const id = `plan-${s.t}`;
        const on = s.t === step, hov = hoverPlan === id;
        if (on) continue;
        out.push({ id, label: `Pla de les ${hourLbl(s.t)}`, pts: planPts(s, v), color: hov ? C.charge : C.upc,
          width: hov ? 2.5 : 1.2, opacity: hov ? 0.95 : 0.22, onClick: () => { setStep(s.t); setPlaying(false); } });
      }
    }
    if (v === "soc") {
      if (!isReal) out.push({ id: "base", label: "Executat al dia real (línia base)", pts: r.baseline.socPath.map((y, x) => [x, y]),
        color: C.muted, width: 2, dash: "6 4", legend: true, tooltip: true, fmt: kwh });
      out.push({ id: "oracle", label: "Informació perfecta", pts: r.active.oracleSoc.map((y, x) => [x, y]),
        color: C.green, width: 2, dash: "2 3", legend: true, tooltip: true, fmt: kwh });
      out.push({ id: "exec", label: "Executat (escenari actiu)", pts: r.active.socPath.map((y, x) => [x, y]),
        color: C.ink, width: 3, legend: true, tooltip: true, fmt: kwh });
    } else if (v === "power") {
      out.push({ id: "oracle", label: "Informació perfecta", pts: r.active.oraclePower.map((y, x) => [x, y]),
        color: C.green, width: 2, dash: "2 3", legend: true, tooltip: true, fmt: kw });
      out.push({ id: "exec", label: "Aplicat", pts: r.active.applied.map((y, x) => [x, y]), color: C.ink, width: 3, legend: true, tooltip: true, fmt: kw });
    } else {
      if (!isReal) out.push({ id: "realnet", label: "Càrrega neta del dia real", pts: r.real.net.map((y, x) => [x, y]),
        color: C.muted, width: 2, dash: "6 4", legend: true, tooltip: true, fmt: kw });
      out.push({ id: "net", label: "Càrrega neta de l'escenari", pts: r.day.net.map((y, x) => [x, y]), color: C.ink, width: 3, legend: true, tooltip: true, fmt: kw });
    }
    const sel = r.steps.find((s) => s.t === step);
    if (sel) out.push({ id: "sel", label: `Pla de les ${hourLbl(step)}`, pts: planPts(sel, v), color: C.charge, width: 3.2,
      legend: true, tooltip: true, fmt: v === "soc" ? kwh : kw });
    return out;
  }, [r, v, step, hoverPlan, isReal, showFan]);

  // --- escenaris (estats executats de cada mostra) ---
  const ensSeries: Series[] = useMemo(() => {
    if (!r) return [];
    const out: Series[] = r.ensemble.filter((e) => e.seed !== actSeed).map((e) => ({
      id: `ens-${e.seed}`, label: `Escenari ${e.seed} · ${fmt.dec(e.score, 2)} pts`, pts: e.socPath.map((y, x) => [x, y] as Pt),
      color: hoverPlan === `ens-${e.seed}` ? C.charge : C.upc, width: hoverPlan === `ens-${e.seed}` ? 2.5 : 1.3,
      opacity: hoverPlan === `ens-${e.seed}` ? 1 : 0.35, onClick: () => setActiveSeed(e.seed),
    }));
    out.push({ id: "base", label: "Dia real", pts: r.baseline.socPath.map((y, x) => [x, y]), color: C.muted, width: 2, dash: "6 4", legend: true, tooltip: true, fmt: kwh });
    out.push({ id: "act", label: `Escenari actiu (llavor ${actSeed})`, pts: r.active.socPath.map((y, x) => [x, y]), color: C.charge, width: 3, legend: true, tooltip: true, fmt: kwh });
    return out;
  }, [r, hoverPlan, actSeed]);

  const ens = r?.ensemble ?? [];
  const ensScores = ens.map((e) => e.score);
  const capture = r && r.active.oracle > 0 ? (100 * r.active.score) / r.active.oracle : 0;

  // --- inspector del pas seleccionat ---
  const inspector = useMemo(() => {
    if (!r || !st || !st.H) return null;
    const H = st.H, t = st.t;
    const realNet = r.day.net, realW = r.day.w;
    const netS: Series[] = [
      { id: "raw", label: "Previsió (sense marge)", pts: (st.netRaw ?? []).map((y, k) => [t + k, y]), color: C.charge, width: 2.5, legend: true, tooltip: true, fmt: kw },
      { id: "lp", label: "El que fa servir l'LP (amb marge z)", pts: (st.net ?? []).map((y, k) => [t + k, y]), color: C.charge, width: 1.5, dash: "5 4", legend: true, tooltip: true, fmt: kw },
      { id: "real", label: "Real", pts: realNet.slice(t).map((y, k) => [t + k, y] as Pt), color: C.ink, width: 2.5, legend: true, tooltip: true, fmt: kw },
    ];
    const wS: Series[] = [
      { id: "wf", label: "Pes previst", pts: (st.w ?? []).map((y, k) => [t + k, y]), color: C.charge, width: 2.5, legend: true, tooltip: true, fmt: (x) => fmt.dec(x, 3) },
      { id: "wr", label: "Pes real", pts: realW.slice(t).map((y, k) => [t + k, y] as Pt), color: C.ink, width: 2.5, legend: true, tooltip: true, fmt: (x) => fmt.dec(x, 3) },
    ];
    const plan = (st.c ?? []).map((c, k) => (c === null || st.d?.[k] == null ? null : c - (st.d[k] as number)));
    let err = 0, n = 0;
    (st.netRaw ?? []).forEach((y, k) => { if (y !== null && t + k < 24) { err += Math.abs(y - realNet[t + k]); n++; } });
    return { H, netS, wS, plan, mae: n ? err / n : null };
  }, [r, st]);

  const heat = r ? (row: number, col: number) => {
    const s = r.steps[row];
    if (!s || !s.c || !s.d) return null;
    const k = col - row;
    if (k < 0 || k >= s.H) return null;
    const c = s.c[k], d = s.d[k];
    return c === null || d === null ? null : c - d;
  } : () => null;

  const appliedNow = r && st ? r.active.applied[st.t] : 0;
  const ptsNow = r && st ? r.active.ptsPerHour[st.t] : 0;
  const ptsCum = r && st ? r.active.ptsPerHour.slice(0, st.t + 1).reduce((a, b) => a + b, 0) : 0;
  const orNow = r && st ? r.active.oraclePower[st.t] : 0;

  return (
    <div className="rh">
      <header className="rh-head">
        <div>
          <h2>Rolling horizon i generador d'escenaris</h2>
          <p className="fine">
            Cada hora l'agent resol un problema lineal per a les properes {mode === "dificil" ? "24" : "≤24"} hores amb la seva previsió,
            n'aplica només la primera decisió i torna a planificar quan arriba la mesura nova. Pertorba el dia i mira com reacciona.
          </p>
        </div>
        <div className="rh-head-ctl">
          <div className="rh-seg" role="group" aria-label="Mode">
            {(["dificil", "estandar"] as Mode[]).map((m) => (
              <button key={m} className={mode === m ? "on" : ""} onClick={() => { setMode(m); setActiveSeed(null); }}>
                {m === "dificil" ? "Difícil · 6 MWh · 22,94" : "Estàndard · 2 MWh · 6,43"}
              </button>
            ))}
          </div>
          <select value={date} onChange={(e) => { setDate(e.target.value); setActiveSeed(null); }} aria-label="Dia" disabled={daysLoading}>
            {days.map((d) => <option key={d.date} value={d.date}>{d.date} · {d.label}{d.weekday >= 5 ? " (cap de setmana)" : ""}</option>)}
          </select>
          <span className={`rh-status ${loading ? "busy" : ""}`} aria-live="polite">
            {loading ? <><Loader2 size={14} className="spin" /> Recalculant…</> : ms !== null ? `Recalculat en ${ms} ms` : ""}
          </span>
        </div>
      </header>

      <ScenarioControls s={scenario} set={setS} nSamples={nSamples} setNSamples={(n) => { setNSamples(n); }} pmax={pmax}
        preset={preset} setPreset={pickPreset} />
      {preset && <p className="fine rh-preset-desc">{PRESETS.find((p) => p.id === preset)?.desc}</p>}

      {error && <p className="rh-error">No s'ha pogut calcular: {error}. Comprova que el backend és en marxa (uvicorn a :8000).</p>}
      {!r && !error && <p className="muted">Calculant el primer escenari…</p>}

      {r && (
        <div className={`rh-body ${loading ? "stale" : ""}`}>
          <section className="rh-kpis">
            <Kpi label="Agent · escenari actiu" value={`${fmt.dec(r.active.score, 2)} pts`} tone="upc"
              sub={`CO₂ −${fmt.dec(r.active.dCO2, 1)} % · cost −${fmt.dec(r.active.dCost, 1)} %${r.active.infracciones ? ` · ${r.active.infracciones} infr.` : ""}`} />
            <Kpi label="Línia base · dia real" value={`${fmt.dec(r.baseline.score, 2)} pts`}
              sub={`Δ escenari ${r.active.score - r.baseline.score >= 0 ? "+" : "−"}${fmt.dec(Math.abs(r.active.score - r.baseline.score), 2)}`} />
            <Kpi label="Informació perfecta" value={`${fmt.dec(r.active.oracle, 2)} pts`} tone="good"
              sub={`l'agent n'aconsegueix el ${fmt.int(capture)} %`} />
            <Kpi label="Pèrdua per no saber el futur" value={`${fmt.dec(r.active.oracle - r.active.score, 2)} pts`} tone="bad"
              sub="informació perfecta − agent" />
            {ens.length > 1 && (
              <Kpi label={`Monte Carlo · ${ens.length} escenaris`} value={`${fmt.dec(mean(ensScores), 2)} pts`}
                sub={`P10 ${fmt.dec(quantile(ensScores, 0.1), 2)} · P90 ${fmt.dec(quantile(ensScores, 0.9), 2)}`} />
            )}
          </section>

          {ens.length > 1 && (
            <section className="card rh-card">
              <div className="rh-card-head">
                <h3>Escenaris generats: estat de la bateria executat</h3>
                <p className="fine">Cada línia és un escenari amb una llavor diferent. Fes-hi clic (o al punt de sota) per fer-lo actiu i veure'n el solver pas a pas.</p>
              </div>
              <LineChart series={ensSeries} xMin={0} xMax={24} yMin={0} yMax={cap} xFmt={hourLbl} yFmt={kwh}
                xTicks={[0, 3, 6, 9, 12, 15, 18, 21, 24]} onHoverSeries={setHoverPlan} vline={step}
                ariaLabel="Estat de càrrega executat a cada escenari" height={220} />
              <p className="label" style={{ marginTop: 10 }}>Punts per escenari · <span style={{ color: C.upc }}>●</span> agent · <span style={{ color: C.green }}>▮</span> informació perfecta</p>
              <ScoreStrip r={r} active={actSeed} onPick={(s) => setActiveSeed(s)} />
            </section>
          )}

          <section className="card rh-card">
            <div className="rh-card-head">
              <h3>El ventall del rolling horizon</h3>
              <div className="rh-seg small" role="group" aria-label="Variable">
                {VARS.map((x) => <button key={x.key} className={v === x.key ? "on" : ""} onClick={() => setV(x.key)}>{x.label}</button>)}
              </div>
              <label className="rh-check"><input type="checkbox" checked={showFan} onChange={(e) => setShowFan(e.target.checked)} /> Mostra els 24 plans</label>
            </div>
            <p className="fine">Cada línia blava és el pla que el solver va fer a una hora; la negra és el que realment va passar. Clica una línia per inspeccionar aquell pas.</p>
            <LineChart series={fanSeries} xMin={0} xMax={maxX} xFmt={hourLbl} yFmt={v === "soc" ? kwh : kw}
              xTicks={[0, 6, 12, 18, 24, 30, 36, 42].filter((x) => x <= maxX)}
              yMin={v === "soc" ? 0 : undefined} yMax={v === "soc" ? cap : undefined} hline={v === "soc" ? null : 0}
              bands={[{ x0: 24, x1: maxX, fill: "rgba(20,20,20,0.04)", label: "Més enllà del dia (només previsió)" },
                ...(st ? [{ x0: st.t, x1: Math.min(maxX, st.t + Math.min(st.seenPrices, 24)), fill: "rgba(138,92,194,0.08)" }] : [])]}
              vline={step} onHoverSeries={setHoverPlan} onClickX={(x) => { if (x < 24) { setStep(x); setPlaying(false); } }}
              ariaLabel="Plans successius del solver" height={300} />
          </section>

          <section className="card rh-card">
            <div className="rh-card-head">
              <h3>Mapa de replanificació</h3>
              <p className="fine">Fila = hora en què decideix el solver; columna = hora per a la qual planifica. Lila = carregar, verd = descarregar. La diagonal marcada és el que s'aplica de veritat.</p>
            </div>
            <Heatmap rows={r.steps.length} cols={maxX} value={heat} vmax={pmax} selectedRow={step} dayEnd={24}
              onSelectRow={(t) => { setStep(t); setPlaying(false); }} rowFmt={(t) => hourLbl(t)} colFmt={(c) => (c < 24 ? `${c}h` : `+${c - 24}`)}
              cellTip={(t, c, val) => (<><b>Pla de les {hourLbl(t)} → {hourLbl(c)}</b><span>{val >= 0 ? "Carregar" : "Descarregar"} {kw(Math.abs(val))}</span></>)}
              ariaLabel="Mapa de calor de les decisions planificades" />
          </section>

          {st && (
            <section className="card rh-card rh-inspector">
              <div className="rh-card-head">
                <h3>Solver pas a pas · {hourLbl(st.t)}</h3>
                <div className="rh-stepper">
                  <button className="btn-line" onClick={() => setStep(Math.max(0, step - 1))} aria-label="Hora anterior"><ChevronLeft size={16} /></button>
                  <button className="btn-line" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Atura" : "Reprodueix"}>
                    {playing ? <Pause size={16} /> : <Play size={16} />}
                  </button>
                  <button className="btn-line" onClick={() => setStep(Math.min(23, step + 1))} aria-label="Hora següent"><ChevronRight size={16} /></button>
                  <input type="range" min={0} max={23} value={step} onChange={(e) => { setStep(+e.target.value); setPlaying(false); }} aria-label="Hora" />
                </div>
              </div>

              <ol className="rh-pipeline">
                <li><b>1 · Observa</b> SOC {kwh(st.soc0)} ({fmt.int((100 * st.soc0) / cap)} %).
                  {st.meas ? ` Última mesura: consum ${kw(st.meas[0])}, solar ${kw(st.meas[1])}.` : " Encara no té mesura."}
                  {` Veu ${st.seenPrices} h de preu i CO₂ reals.`}
                  {st.meas && st.meas[0] === 0 && st.meas[1] === 0 && <em> Mesura 0/0: tall de dades detectat.</em>}</li>
                <li><b>2 · Preveu</b> {st.H} h de càrrega neta{inspector?.mae !== null && inspector?.mae !== undefined ? ` (error mitjà d'aquest pla: ${kw(inspector.mae)})` : ""}
                  {st.H > st.seenPrices ? ` i ${st.H - st.seenPrices} h de preu/CO₂.` : "."}</li>
                <li><b>3 · Optimitza</b> un LP de {st.H} h: minimitza Σ w·importació amb w = 0,7·CO₂ + 0,3·κ·preu.</li>
                <li><b>4 · Aplica</b> només la primera hora: demana <b>{st.P >= 0 ? `carregar ${kw(st.P)}` : `descarregar ${kw(-st.P)}`}</b>
                  {Math.abs(appliedNow - st.P) > 1 ? `, la bateria n'accepta ${kw(Math.abs(appliedNow))}` : ""}.
                  {" "}Informació perfecta: {orNow >= 0 ? `carregar ${kw(orNow)}` : `descarregar ${kw(-orNow)}`}.</li>
                <li><b>5 · Avalua</b> aquesta hora suma <b>{fmt.pts(ptsNow)}</b> pts (acumulat {fmt.pts(ptsCum)} de {fmt.dec(r.active.score, 2)}).</li>
              </ol>

              {inspector && (
                <div className="rh-grid2">
                  <div>
                    <p className="label">Càrrega neta: previsió vs real (kW)</p>
                    <LineChart series={inspector.netS} xMin={st.t} xMax={st.t + st.H - 1} xFmt={hourLbl} yFmt={kw} hline={0}
                      bands={[{ x0: 24, x1: st.t + st.H, fill: "rgba(20,20,20,0.04)" }]} ariaLabel="Previsió de càrrega neta" height={200} />
                  </div>
                  <div>
                    <p className="label">Pes de cada kWh importat (×1000)</p>
                    <LineChart series={inspector.wS} xMin={st.t} xMax={st.t + st.H - 1} xFmt={hourLbl} yFmt={(x) => fmt.dec(x, 2)}
                      bands={[{ x0: st.t, x1: st.t + Math.min(st.seenPrices, st.H) - 1, fill: "rgba(138,92,194,0.10)", label: "conegut" }]}
                      ariaLabel="Pes previst i real" height={200} />
                  </div>
                  <div>
                    <p className="label">Pla de la bateria (kW, + carregar / − descarregar)</p>
                    <Bars values={inspector.plan} labels={inspector.plan.map((_, k) => hourLbl(st.t + k))} color={C.charge} negColor={C.battery}
                      fmt={kw} ariaLabel="Potència planificada" selected={0} height={170} />
                  </div>
                  <div>
                    <p className="label">Estat de càrrega planificat (kWh)</p>
                    <LineChart series={[{ id: "s", label: "SOC planificat", pts: (st.soc ?? []).map((y, k) => [st.t + k, y]), color: C.charge, width: 2.5, tooltip: true, fmt: kwh, legend: true },
                      { id: "e", label: "SOC executat", pts: r.active.socPath.slice(st.t).map((y, k) => [st.t + k, y] as Pt), color: C.ink, width: 2, tooltip: true, fmt: kwh, legend: true }]}
                      xMin={st.t} xMax={st.t + st.H} yMin={0} yMax={cap} xFmt={hourLbl} yFmt={kwh} ariaLabel="SOC planificat" height={170} />
                  </div>
                </div>
              )}
            </section>
          )}

          <div className="rh-grid2">
            <section className="card rh-card">
              <h3>Punts guanyats cada hora</h3>
              <p className="fine">Clica una barra per anar a aquella hora.</p>
              <Bars values={r.active.ptsPerHour} labels={r.day.hours} color={C.upc} negColor={C.bad} fmt={(x) => fmt.dec(x, 2)}
                ariaLabel="Punts per hora" selected={step} onSelect={(i) => { setStep(i); setPlaying(false); }} />
            </section>
            <section className="card rh-card">
              <h3>Error de la previsió segons l'antelació</h3>
              <p className="fine">Error absolut mitjà de la càrrega neta prevista a k hores vista (escenari actiu).</p>
              <Bars values={r.leadError.map((e) => e.mae)} labels={r.leadError.map((e) => `+${e.k}h`)} color={C.muted}
                fmt={kw} ariaLabel="Error per antelació" />
            </section>
          </div>

          <p className="fine rh-foot">
            <RotateCcw size={12} /> Les pertorbacions només afecten el dia triat; les 48 h anteriors (memòria de l'agent) són les reals, així que cada canvi és una sorpresa per al solver.
            La referència d'informació perfecta resol un sol LP amb el dia sencer ja conegut.
          </p>
        </div>
      )}
    </div>
  );
}
