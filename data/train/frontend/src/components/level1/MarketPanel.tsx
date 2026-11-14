import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, C, fmt, tercile } from "../../theme";
import type { DashboardData, DayData } from "../../types";

const MONTHS = ["gen", "feb", "mar", "abr", "mai", "jun", "jul", "ago", "set", "oct", "nov", "des"];
const STATE = { good: C.good, warn: C.warn, bad: C.bad };

/** Columnes horàries acolorides per terços: verd (barat/net), groc, vermell (car/brut). */
function HourBars({ values, format, unit }: { values: number[]; format: (v: number) => string; unit: string }) {
  const rows = values.map((v, h) => ({ hour: `${String(h).padStart(2, "0")}:00`, v }));
  return (
    <ResponsiveContainer width="100%" height={210}>
      <BarChart data={rows} margin={{ top: 6, right: 4, bottom: 0, left: 0 }} barCategoryGap={2}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="hour" tick={AXIS} interval={3} tickLine={false} axisLine={{ stroke: C.ink }} />
        <YAxis tick={AXIS} tickFormatter={format} width={56} tickLine={false} axisLine={false} />
        <Tooltip cursor={{ fill: "rgba(0,0,0,.05)" }} formatter={(v) => [`${format(Number(v))} ${unit}`, ""]} />
        <Bar dataKey="v" isAnimationActive={false} radius={[2, 2, 0, 0]}>
          {rows.map((r) => <Cell key={r.hour} fill={STATE[tercile(values, r.v)]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function MarketPanel({ data, day }: { data: DashboardData; day: DayData }) {
  const pMin = day.price.indexOf(Math.min(...day.price)), pMax = day.price.indexOf(Math.max(...day.price));
  const cMin = day.co2.indexOf(Math.min(...day.co2)), cMax = day.co2.indexOf(Math.max(...day.co2));
  const flat = data.co2Heatmap.values.flat().filter((v): v is number => v !== null);
  const lo = Math.min(...flat), hi = Math.max(...flat);
  const cell = (v: number | null) => v === null ? "#EEEDE7" : `hsl(204 100% ${95 - ((v - lo) / (hi - lo)) * 65}%)`;

  return (
    <div className="block">
      <h3>Per què importa <em>quan</em> fem servir l'electricitat?</h3>
      <p className="lead">Un kWh no costa ni contamina igual a totes les hores. En verd, les hores bones del dia; en vermell, les dolentes.</p>
      <ul className="legend">
        <li><i style={{ background: C.good }} />Barat / net</li>
        <li><i style={{ background: C.warn }} />Intermedi</li>
        <li><i style={{ background: C.bad }} />Car / brut</li>
      </ul>

      <div className="cols-2">
        <div>
          <p className="label">Preu de l'electricitat (PVPC), €/kWh</p>
          <HourBars values={day.price} unit="€/kWh" format={(v) => fmt.dec(v, 2)} />
          <p className="note">Més barata a les <b>{day.hours[pMin]}</b> ({fmt.cKwh(day.price[pMin])}/kWh), més cara a les <b>{day.hours[pMax]}</b> ({fmt.cKwh(day.price[pMax])}/kWh). Al vespre s'apaga el sol i tot el país encén llums i cuines: la demanda puja i el preu també.</p>
        </div>
        <div>
          <p className="label">Intensitat de carboni de la xarxa, g CO₂/kWh</p>
          <HourBars values={day.co2} unit="kg CO₂/kWh" format={(v) => String(Math.round(v * 1000))} />
          <p className="note">Més neta a les <b>{day.hours[cMin]}</b> ({fmt.gCo2(day.co2[cMin])}), més bruta a les <b>{day.hours[cMax]}</b> ({fmt.gCo2(day.co2[cMax])}). Quan es fa fosc, les centrals de gas cobreixen el pic i cada kWh porta més CO₂. Avui la generació amb emissions ha anat del {fmt.int(Math.min(...day.pctFossil))} % al {fmt.int(Math.max(...day.pctFossil))} %.</p>
        </div>
      </div>

      <p className="label" style={{ marginTop: 28 }}>Tot l'any: intensitat de carboni mitjana per mes i hora (més fosc = més CO₂)</p>
      <div className="heat" role="img" aria-label="Mapa de calor de la intensitat de carboni per mes i hora">
        <div className="heat-row heat-head"><span />{[...Array(24).keys()].map((h) => <span key={h}>{h % 3 === 0 ? h : ""}</span>)}</div>
        {data.co2Heatmap.months.map((m, r) => (
          <div className="heat-row" key={m}>
            <span className="heat-lab">{MONTHS[m - 1]}</span>
            {data.co2Heatmap.values[r].map((v, h) => (
              <span key={h} className="heat-cell" style={{ background: cell(v) }}
                title={`${MONTHS[m - 1]} ${h}:00 · ${v === null ? "sense dades" : fmt.gCo2(v) + " CO₂/kWh"}`} />
            ))}
          </div>
        ))}
        <div className="heat-scale"><span>{fmt.gCo2(lo)}</span><span className="heat-ramp" /><span>{fmt.gCo2(hi)}/kWh</span></div>
      </div>
      <p className="note">La franja clara del migdia, sobretot a la primavera, és la solar de tota la península. És la finestra que la bateria aprofita per carregar.</p>
    </div>
  );
}
