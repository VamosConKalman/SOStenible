// Generador d'escenaris: presets + controls (sliders) que modifiquen el dia
// abans d'enviar-lo al backend (/api/rolling-horizon).
import type { ScenarioParams } from "../../api/types";

export const DEFAULT_SCENARIO: ScenarioParams = {
  demand_scale: 1, demand_noise: 0,
  solar_scale: 1, solar_noise: 0,
  price_scale: 1, price_noise: 0,
  co2_scale: 1, co2_noise: 0,
  persistence: 0.7,
  cloud_start: 12, cloud_hours: 0, cloud_depth: 0.8,
  shock_start: 18, shock_hours: 0, shock_kw: 400,
  cut_start: 10, cut_hours: 0,
  seed: 0,
};

export const PRESETS: { id: string; label: string; desc: string; p: Partial<ScenarioParams> }[] = [
  { id: "real", label: "Dia real", desc: "Les dades tal com van passar: és la línia base de l'agent (22,94).", p: {} },
  { id: "noise", label: "Previsió imperfecta", desc: "Consum ±10 % i solar ±20 % amb errors que duren hores.", p: { demand_noise: 0.1, solar_noise: 0.2, persistence: 0.8 } },
  { id: "cloud", label: "Núvol a migdia", desc: "De 11 a 15 h la solar cau un 85 %: l'agent no ho sap fins que ho mesura.", p: { cloud_start: 11, cloud_hours: 4, cloud_depth: 0.85 } },
  { id: "shock", label: "Pic al vespre", desc: "600 kW extres de 18 a 21 h (un esdeveniment no previst).", p: { shock_start: 18, shock_hours: 3, shock_kw: 600 } },
  { id: "cut", label: "Tall de dades", desc: "De 10 a 13 h el comptador envia 0: l'agent ha de detectar el tall.", p: { cut_start: 10, cut_hours: 3 } },
  { id: "market", label: "Mercat volàtil", desc: "Preu ±25 % i CO₂ ±15 %, canviant ràpid.", p: { price_noise: 0.25, co2_noise: 0.15, persistence: 0.4 } },
  { id: "heat", label: "Onada de calor", desc: "+25 % de consum (climatització) i calitja: −10 % de solar.", p: { demand_scale: 1.25, solar_scale: 0.9 } },
  { id: "storm", label: "Tempesta perfecta", desc: "Tot alhora: soroll, núvol, pic de demanda i mercat volàtil.", p: { demand_noise: 0.12, solar_noise: 0.25, price_noise: 0.2, co2_noise: 0.1, cloud_start: 12, cloud_hours: 3, cloud_depth: 0.7, shock_start: 19, shock_hours: 2, shock_kw: 500 } },
];

function Slider({ label, value, min, max, step, fmt, onChange, hint }: {
  label: string; value: number; min: number; max: number; step: number;
  fmt: (v: number) => string; onChange: (v: number) => void; hint?: string;
}) {
  return (
    <label className="rh-slider" title={hint}>
      <span className="rh-slider-top"><span>{label}</span><b>{fmt(value)}</b></span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} />
    </label>
  );
}

const pct = (v: number) => `${Math.round(v * 100)} %`;
const mult = (v: number) => `×${v.toFixed(2)}`;
const hh = (v: number) => `${String(v).padStart(2, "0")}:00`;

export default function ScenarioControls({ s, set, nSamples, setNSamples, pmax, preset, setPreset }: {
  s: ScenarioParams;
  set: (p: Partial<ScenarioParams>) => void;
  nSamples: number;
  setNSamples: (n: number) => void;
  pmax: number;
  preset: string | null;
  setPreset: (id: string) => void;
}) {
  return (
    <div className="rh-controls">
      <div className="rh-presets" role="group" aria-label="Escenaris predefinits">
        {PRESETS.map((p) => (
          <button key={p.id} className={`rh-preset ${preset === p.id ? "on" : ""}`} title={p.desc} onClick={() => setPreset(p.id)}>
            {p.label}
          </button>
        ))}
      </div>

      <div className="rh-groups">
        <fieldset>
          <legend>Demanda</legend>
          <Slider label="Escala" value={s.demand_scale} min={0.5} max={1.6} step={0.05} fmt={mult} onChange={(v) => set({ demand_scale: v })} />
          <Slider label="Soroll σ" value={s.demand_noise} min={0} max={0.4} step={0.01} fmt={pct} onChange={(v) => set({ demand_noise: v })}
            hint="Error relatiu AR(1) que l'agent no pot preveure" />
          <Slider label="Pic: hora" value={s.shock_start} min={0} max={23} step={1} fmt={hh} onChange={(v) => set({ shock_start: v })} />
          <Slider label="Pic: durada" value={s.shock_hours} min={0} max={8} step={1} fmt={(v) => `${v} h`} onChange={(v) => set({ shock_hours: v })} />
          <Slider label="Pic: potència" value={s.shock_kw} min={-Math.round(pmax / 2)} max={Math.round(pmax)} step={50} fmt={(v) => `${v} kW`} onChange={(v) => set({ shock_kw: v })} />
        </fieldset>

        <fieldset>
          <legend>Generació solar</legend>
          <Slider label="Escala" value={s.solar_scale} min={0} max={1.5} step={0.05} fmt={mult} onChange={(v) => set({ solar_scale: v })} />
          <Slider label="Soroll σ" value={s.solar_noise} min={0} max={0.5} step={0.01} fmt={pct} onChange={(v) => set({ solar_noise: v })} />
          <Slider label="Núvol: hora" value={s.cloud_start} min={0} max={23} step={1} fmt={hh} onChange={(v) => set({ cloud_start: v })} />
          <Slider label="Núvol: durada" value={s.cloud_hours} min={0} max={10} step={1} fmt={(v) => `${v} h`} onChange={(v) => set({ cloud_hours: v })} />
          <Slider label="Núvol: profunditat" value={s.cloud_depth} min={0} max={1} step={0.05} fmt={pct} onChange={(v) => set({ cloud_depth: v })} />
        </fieldset>

        <fieldset>
          <legend>Mercat</legend>
          <Slider label="Preu: escala" value={s.price_scale} min={0.5} max={2} step={0.05} fmt={mult} onChange={(v) => set({ price_scale: v })} />
          <Slider label="Preu: soroll σ" value={s.price_noise} min={0} max={0.5} step={0.01} fmt={pct} onChange={(v) => set({ price_noise: v })} />
          <Slider label="CO₂: escala" value={s.co2_scale} min={0.5} max={2} step={0.05} fmt={mult} onChange={(v) => set({ co2_scale: v })} />
          <Slider label="CO₂: soroll σ" value={s.co2_noise} min={0} max={0.5} step={0.01} fmt={pct} onChange={(v) => set({ co2_noise: v })} />
        </fieldset>

        <fieldset>
          <legend>Dades i aleatorietat</legend>
          <Slider label="Tall: hora" value={s.cut_start} min={0} max={23} step={1} fmt={hh} onChange={(v) => set({ cut_start: v })} />
          <Slider label="Tall: durada" value={s.cut_hours} min={0} max={6} step={1} fmt={(v) => `${v} h`} onChange={(v) => set({ cut_hours: v })} />
          <Slider label="Persistència φ" value={s.persistence} min={0} max={0.95} step={0.05} fmt={(v) => v.toFixed(2)} onChange={(v) => set({ persistence: v })}
            hint="0 = soroll blanc; 0,95 = errors que es mantenen durant hores" />
          <Slider label="Llavor" value={s.seed} min={0} max={200} step={1} fmt={(v) => String(v)} onChange={(v) => set({ seed: v })} />
          <Slider label="Escenaris (Monte Carlo)" value={nSamples} min={1} max={30} step={1} fmt={(v) => String(v)} onChange={setNSamples} />
        </fieldset>
      </div>
    </div>
  );
}
