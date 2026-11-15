import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Cpu, Lightbulb, MonitorOff, ThermometerSun } from "lucide-react";
import { AXIS, C, fmt } from "../../theme";
import type { DayData } from "../../types";
import { describeDay } from "../../lib/days";

const LECTIVE_DAYS = 180; // supòsit divulgatiu: dies lectius en un curs

/** Nivell 4: què passa si la comunitat universitària també canvia hàbits. */
export default function CommunityPanel({ day, days }: { day: DayData; days: DayData[] }) {
  const dirtiest = day.co2.indexOf(Math.max(...day.co2.slice(14)));
  const [start, setStart] = useState(Math.max(14, dirtiest - 1));
  const [len, setLen] = useState(3);
  const [pct, setPct] = useState(5);

  const hrs = [...Array(len).keys()].map((k) => start + k).filter((h) => h < 24);
  const r = useMemo(() => {
    const kwh = hrs.reduce((a, h) => a + (pct / 100) * day.demand[h], 0);
    const co2 = hrs.reduce((a, h) => a + (pct / 100) * day.demand[h] * day.co2[h], 0);
    const eur = hrs.reduce((a, h) => a + (pct / 100) * day.demand[h] * day.price[h], 0);
    return { kwh, co2, eur };
  }, [hrs, pct, day]);

  const bat = day.totals;
  const extraCo2 = (100 * r.co2) / Math.max(1, bat.co2SavedKg);
  const extraEur = (100 * r.eur) / Math.max(1, bat.costSavedEur);


  return (
    <div className="community">
      <div className="card comm-grid">
        <section className="comm-sim">
          <p className="label">Escenari real · {describeDay(day).title.toLowerCase()}</p>
          <p className="comm-q">I si la comunitat reduís el consum un <b>{pct} %</b> de les <b>{day.hours[start]}</b> a les <b>{day.hours[Math.min(23, start + len - 1)].slice(0, 2)}:59</b>?</p>

          <label className="slider"><span>Reducció</span>
            <input type="range" min={1} max={20} value={pct} onChange={(e) => setPct(+e.target.value)} /><output>{pct} %</output></label>
          <label className="slider"><span>A partir de</span>
            <input type="range" min={0} max={23} value={start} onChange={(e) => setStart(+e.target.value)} /><output>{day.hours[start]}</output></label>
          <label className="slider"><span>Durant</span>
            <input type="range" min={1} max={8} value={len} onChange={(e) => setLen(+e.target.value)} /><output>{len} h</output></label>

          <div className="comm-out">
            <div><span className="big">+{fmt.int(extraCo2)} %</span><span>més CO₂ evitat que amb la bateria sola ({fmt.int(r.co2)} kg addicionals)</span></div>
            <div><span className="big">+{fmt.int(extraEur)} %</span><span>més estalvi econòmic ({fmt.eur(r.eur)} addicionals)</span></div>
          </div>
          <p className="fine">
            {fmt.int(r.kwh)} kWh menys en aquest dia. Al costat, què podria passar al llarg de tot un curs.
          </p>
        </section>

        <MonteCarlo days={days} start={start} len={len} pct={pct} />
      </div>

      <div className="card eco">
        <h3 className="eco-title">Ecoconsells</h3>
        <div className="actions">
        <div><MonitorOff size={22} aria-hidden /><b>Apaga en marxar</b><p>Ordinadors, pantalles i equips de laboratori que queden encesos de nit alimenten el consum de fons.</p></div>
        <div><ThermometerSun size={22} aria-hidden /><b>Climatització a les hores punta</b><p>Un grau menys de fred o de calor al vespre redueix el consum quan l'electricitat és menys sostenible.</p></div>
        <div><Cpu size={22} aria-hidden /><b>Càlculs pesats a les hores vall</b><p>Simulacions, entrenaments de models i còpies de seguretat es poden programar al migdia.</p></div>
        <div><Lightbulb size={22} aria-hidden /><b>Llum natural</b><p>Les aules buides amb els llums encesos són energia que ni el sol ni la bateria poden compensar.</p></div>
        </div>
      </div>
    </div>
  );
}

const N_SIM = 1000;

/** Generador pseudoaleatori amb llavor (resultats estables per a uns mateixos controls). */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const gauss = (r: () => number) => Math.sqrt(-2 * Math.log(r() || 1e-9)) * Math.cos(2 * Math.PI * r());

/**
 * Montecarlo: 1.000 cursos simulats. A cada curs:
 *  · el grau de seguiment real de la comunitat és incert: es multiplica la reducció triada per un factor
 *    aleatori (mitjana 1, desviació 0,4, mai negatiu);
 *  · es trien a l'atzar 180 dies lectius reals de les dades (cada un amb el seu consum i CO₂ hora a hora);
 *  · cada hora hi ha una petita variació addicional (±20 %).
 * Resultat: tones de CO₂ evitades en un curs.
 */
function MonteCarlo({ days, start, len, pct }: { days: DayData[]; start: number; len: number; pct: number }) {
  const sim = useMemo(() => {
    const pool = days.filter((d) => d.weekday < 5 && d.activityIdx >= 0.85 && d.date.slice(5, 7) !== "08");
    const r = rng(start * 7919 + len * 104729 + pct * 1299709);
    const hrs = [...Array(len).keys()].map((k) => start + k).filter((h) => h < 24);
    const out: number[] = [];
    for (let s = 0; s < N_SIM; s++) {
      const adherence = Math.max(0, 1 + 0.4 * gauss(r));
      let kg = 0;
      for (let k = 0; k < LECTIVE_DAYS; k++) {
        const d = pool[Math.floor(r() * pool.length)];
        for (const h of hrs) {
          const red = (pct / 100) * adherence * Math.max(0, 1 + 0.2 * gauss(r));
          kg += red * d.demand[h] * d.co2[h];
        }
      }
      out.push(kg / 1000);
    }
    out.sort((a, b) => a - b);
    const q = (p: number) => out[Math.min(N_SIM - 1, Math.floor(p * N_SIM))];
    const mean = out.reduce((a, b) => a + b, 0) / N_SIM;
    const lo = out[0], hi = out[N_SIM - 1];
    const nb = 28, w = (hi - lo) / nb || 1;
    const bins = [...Array(nb).keys()].map((i) => ({ x: lo + (i + 0.5) * w, n: 0 }));
    out.forEach((v) => { bins[Math.min(nb - 1, Math.floor((v - lo) / w))].n++; });
    return { mean, p5: q(0.05), p50: q(0.5), p95: q(0.95), bins, w };
  }, [days, start, len, pct]);

  const t = (v: number) => fmt.dec(v, 1);
  return (
    <section className="comm-mc">
      <p className="label">Simulació de Montecarlo · {fmt.int(N_SIM)} cursos possibles</p>
      <ResponsiveContainer width="100%" height={230}>
        <BarChart data={sim.bins} margin={{ top: 18, right: 8, bottom: 0, left: 0 }} barCategoryGap={1}>
          <CartesianGrid stroke={C.grid} vertical={false} />
          <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v) => `${t(v)} t`}
            tick={AXIS} tickLine={false} axisLine={{ stroke: C.grid }} tickCount={6} padding={{ left: 8, right: 8 }} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={40} />
          <Tooltip cursor={{ fill: "rgba(0,0,0,.04)" }}
            formatter={(v) => [`${v} simulacions`, ""]}
            labelFormatter={(x) => `≈ ${t(Number(x))} t de CO₂`} />
          <ReferenceArea x1={sim.p5} x2={sim.p95} fill={C.green} fillOpacity={0.08} />
          <ReferenceLine x={sim.mean} stroke={C.ink} strokeDasharray="4 3"
            label={{ value: `mitjana ${t(sim.mean)} t`, position: "top", fill: C.ink, fontSize: 12, fontWeight: 700 }} />
          <Bar dataKey="n" isAnimationActive={false} radius={[3, 3, 0, 0]}>
            {sim.bins.map((b) => <Cell key={b.x} fill={b.x >= sim.p5 && b.x <= sim.p95 ? C.green : "#C9D9BE"} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="note">
        En el <b>90 % de les simulacions</b> la comunitat evitaria entre <b>{t(sim.p5)} i {t(sim.p95)} t de CO₂</b> en un curs
        (franja verda), amb una mitjana de {t(sim.mean)} t. Cada simulació tria a l'atzar {LECTIVE_DAYS} dies lectius reals i un
        grau de seguiment diferent de la comunitat: per això el resultat no és un número únic, sinó una distribució.
      </p>
    </section>
  );
}
