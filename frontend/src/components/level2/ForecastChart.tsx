import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Leaf, Lightbulb, TriangleAlert } from "lucide-react";
import { AXIS, C, fmt, tercile } from "../../theme";
import type { DayData } from "../../types";

const CO2_C = "#3E8E2A";
const PRICE_C = "#E07B00";
const BAT_C = "#2A86D1";

/** Etiqueta en forma de "pastilla" per marcar valors clau sobre una línia. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const badge = (text: string, bg: string, dy = -16) => (props: any) => {
  const { viewBox } = props;
  if (!viewBox) return null;
  const w = 8 + text.length * 6.6;
  return (
    <g transform={`translate(${viewBox.x} ${viewBox.y + dy})`}>
      <rect x={-w / 2} y={-10} width={w} height={20} rx={6} fill={bg} />
      <text x={0} y={4} textAnchor="middle" fontSize={11.5} fontWeight={700} fill="#fff">{text}</text>
    </g>
  );
};

/** Trams consecutius d'hores en un mateix terç (per pintar les zones). */
function runs(hours: number[], cls: (h: number) => string, want: string) {
  const out: [number, number][] = [];
  let s: number | null = null;
  hours.forEach((h, i) => {
    const on = cls(h) === want;
    if (on && s === null) s = h;
    if ((!on || i === hours.length - 1) && s !== null) { out.push([s, on ? h : hours[i - 1]]); s = null; }
  });
  return out;
}

/** Previsió de la resta del dia: CO₂, preu i bateria en tres panells alineats per hora. */
export default function ForecastChart({ day, h, socPct }: { day: DayData; h: number; socPct: number }) {
  const hours = [...Array(24 - h).keys()].map((k) => h + k);
  const rows = hours.map((k) => ({ hour: k, co2: Math.round(day.co2[k] * 1000), price: +(day.price[k] * 100).toFixed(1), bat: socPct }));
  const cls = (k: number) => tercile(day.co2, day.co2[k]);
  const good = runs(hours, cls, "good"), bad = runs(hours, cls, "bad");
  const longest = (r: [number, number][]) => r.reduce<[number, number] | null>((b, x) => (!b || x[1] - x[0] > b[1] - b[0] ? x : b), null);
  const gL = longest(good), bL = longest(bad);

  const nowCo2 = rows[0].co2, nowPrice = rows[0].price;
  const maxCo2 = rows.reduce((b, r) => (r.co2 > b.co2 ? r : b), rows[0]);
  const maxPrice = rows.reduce((b, r) => (r.price > b.price ? r : b), rows[0]);
  const hh = (k: number) => `${String(k).padStart(2, "0")}h`;
  const xMax = Math.max(h + 1, 23);

  const rise = Math.round((100 * (maxCo2.co2 - nowCo2)) / Math.max(1, nowCo2));
  let insight: { icon: typeof Lightbulb; text: string };
  if (rise >= 25) insight = { icon: Lightbulb, text: `Les emissions augmentaran un ${rise} % més tard (de ${nowCo2} g a ${maxCo2.co2} g a les ${hh(maxCo2.hour)}). Emmagatzemar energia ara pot ser una bona estratègia.` };
  else if (maxCo2.hour === h || nowCo2 >= maxCo2.co2 * 0.9) insight = { icon: TriangleAlert, text: `Ara és de les hores amb més emissions que queden (${nowCo2} g/kWh). Si la bateria té energia, és bon moment per fer-la servir.` };
  else insight = { icon: Lightbulb, text: `Les properes hores no canvien gaire (de ${nowCo2} g a ${maxCo2.co2} g com a màxim). Moure energia ara potser no compensa el 10 % de pèrdues.` };
  const Icon = insight.icon;

  const zones = (yTop: boolean) => [
    ...good.map(([a, b]) => <ReferenceArea key={`g${a}`} x1={a - 0.5} x2={b + 0.5} fill={CO2_C} fillOpacity={0.08} ifOverflow="hidden"
      label={yTop && gL && gL[0] === a ? { value: "Bones condicions per carregar", position: "insideTop", fill: CO2_C, fontSize: 11.5, fontWeight: 700 } : undefined} />),
    ...bad.map(([a, b]) => <ReferenceArea key={`b${a}`} x1={a - 0.5} x2={b + 0.5} fill={C.bad} fillOpacity={0.09} ifOverflow="hidden"
      label={yTop && bL && bL[0] === a ? { value: "Emissions altes", position: "insideTop", fill: C.bad, fontSize: 11.5, fontWeight: 700 } : undefined} />),
  ];
  const xProps = { dataKey: "hour", type: "number" as const, domain: [h - 0.5, xMax + 0.5], ticks: hours, tickFormatter: hh, tick: AXIS, tickLine: false, axisLine: { stroke: C.grid } };
  const margin = { top: 22, right: 18, bottom: 0, left: 4 };

  return (
    <div className="forecast2">
      <div className="fc-head">
        <p className="label">Previsió de les properes hores</p>
        <ul className="legend">
          <li><i style={{ background: CO2_C }} />CO₂ (g/kWh)</li>
          <li><i style={{ background: PRICE_C }} />Preu (c€/kWh)</li>
          <li><i style={{ background: BAT_C }} />Bateria si esperes (%)</li>
        </ul>
      </div>

      <p className="fc-panel"><Leaf size={13} aria-hidden /> CO₂ de la xarxa</p>
      <ResponsiveContainer width="100%" height={150}>
        <LineChart data={rows} margin={margin} syncId="fc">
          {zones(true)}
          <CartesianGrid stroke={C.grid} vertical={false} />
          <XAxis {...xProps} hide />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} domain={[0, (max: number) => Math.ceil(max * 1.25)]} />
          <Tooltip formatter={(v) => [`${v} g CO₂/kWh`, "CO₂"]} labelFormatter={(k) => `${hh(Number(k))}`} />
          <Line dataKey="co2" stroke={CO2_C} strokeWidth={2.5} dot={{ r: 3, fill: CO2_C }} isAnimationActive={false} />
          <ReferenceDot x={h} y={nowCo2} r={5} fill={CO2_C} stroke="#fff" strokeWidth={2} label={badge(`${nowCo2} g`, CO2_C)} />
          {maxCo2.hour !== h && <ReferenceDot x={maxCo2.hour} y={maxCo2.co2} r={5} fill={C.bad} stroke="#fff" strokeWidth={2} label={badge(`${maxCo2.co2} g`, C.bad)} />}
        </LineChart>
      </ResponsiveContainer>

      <p className="fc-panel">Preu de l'electricitat</p>
      <ResponsiveContainer width="100%" height={110}>
        <LineChart data={rows} margin={margin} syncId="fc">
          {zones(false)}
          <CartesianGrid stroke={C.grid} vertical={false} />
          <XAxis {...xProps} hide />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} domain={[0, (max: number) => Math.ceil(max * 1.3)]} />
          <Tooltip formatter={(v) => [`${fmt.dec(Number(v), 1)} c€/kWh`, "Preu"]} labelFormatter={(k) => `${hh(Number(k))}`} />
          <Line dataKey="price" stroke={PRICE_C} strokeWidth={2.5} dot={{ r: 3, fill: PRICE_C }} isAnimationActive={false} />
          <ReferenceDot x={h} y={nowPrice} r={5} fill={PRICE_C} stroke="#fff" strokeWidth={2} label={badge(`${fmt.dec(nowPrice, 1)} c€`, "#1f2a30")} />
          {maxPrice.hour !== h && <ReferenceDot x={maxPrice.hour} y={maxPrice.price} r={5} fill={PRICE_C} stroke="#fff" strokeWidth={2} label={badge(`${fmt.dec(maxPrice.price, 1)} c€`, PRICE_C)} />}
        </LineChart>
      </ResponsiveContainer>

      <p className="fc-panel">Bateria</p>
      <ResponsiveContainer width="100%" height={74}>
        <LineChart data={rows} margin={{ ...margin, top: 20 }} syncId="fc">
          <CartesianGrid stroke={C.grid} vertical={false} />
          <XAxis {...xProps} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} domain={[0, 100]} ticks={[0, 50, 100]} />
          <Tooltip formatter={(v) => [`${fmt.int(Number(v))} %`, "Bateria si esperes"]} labelFormatter={(k) => `${hh(Number(k))}`} />
          <Line dataKey="bat" stroke={BAT_C} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
          <ReferenceDot x={h} y={socPct} r={5} fill={BAT_C} stroke="#fff" strokeWidth={2} label={badge(`${fmt.int(socPct)} %`, BAT_C, socPct > 70 ? 14 : -14)} />
        </LineChart>
      </ResponsiveContainer>

      <p className="fc-insight"><Icon size={18} aria-hidden /><span>{insight.text}</span></p>
      <p className="fine">Al repte real l'agent només té previsions, amb error. Aquí la previsió és perfecta.</p>
    </div>
  );
}
