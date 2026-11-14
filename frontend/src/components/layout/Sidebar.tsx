import { useState } from "react";
import { CalendarDays } from "lucide-react";
import { MONTHS, daysInMonth, describeDay, longDate } from "../../lib/days";
import type { DayData } from "../../types";

export const SECTIONS = [
  { n: 1, label: "Entén", text: "Entén el sistema energètic del campus." },
  { n: 2, label: "Juga", text: "Pren decisions com la persona responsable de la bateria." },
  { n: 3, label: "Analitza", text: "Descobreix com les dades i els algorismes redueixen emissions i costos." },
  { n: 4, label: "Comunitat", text: "Amb la tecnologia sola no n'hi ha prou." },
];

const base = import.meta.env.BASE_URL;

interface Props {
  active: number;
  setActive: (n: number) => void;
  month: number;
  dayOfMonth: number;
  setDate: (m: number, d: number) => void;
  day: DayData;
  exact: boolean;
}

/** Barra lateral: marca, tria del dia (dia i mes) i pestanyes de les seccions 1–4. */
export default function Sidebar({ active, setActive, month, dayOfMonth, setDate, day, exact }: Props) {
  const [upcOk, setUpcOk] = useState(true);
  const desc = describeDay(day);
  const maxD = daysInMonth(month);

  return (
    <aside className="sidebar">
      <div className="side-brand">
        {upcOk ? (
          <img src={`${base}brand/logo-upc.svg`} alt="Universitat Politècnica de Catalunya" className="brand-upc" onError={() => setUpcOk(false)} />
        ) : (
          <span className="brand-upc-text">UPC</span>
        )}
        <img src={`${base}brand/upc-sostenible.png`} alt="UPC Sostenible" className="brand-sos" />
      </div>
      <p className="side-title">Energia al Campus Nord</p>

      <div className="side-date">
        <label className="label" htmlFor="sel-day"><CalendarDays size={14} aria-hidden /> Tria un dia</label>
        <div className="date-inputs">
          <select id="sel-day" value={dayOfMonth} onChange={(e) => setDate(month, +e.target.value)} aria-label="Dia">
            {[...Array(maxD).keys()].map((i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}
          </select>
          <select value={month} onChange={(e) => setDate(+e.target.value, Math.min(dayOfMonth, daysInMonth(+e.target.value)))} aria-label="Mes">
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        </div>
        <div className="day-card">
          <strong>{desc.title}</strong>
          <p>{desc.text}</p>
          <p className="fine">
            {exact ? `Dades del ${longDate(day.date)}.` : `No tenim dades completes d'aquest dia; mostrem el més proper: ${longDate(day.date)}.`}
          </p>
        </div>
      </div>

      <nav className="side-tabs" aria-label="Seccions">
        {SECTIONS.map((s) => (
          <button key={s.n} className={active === s.n ? "on" : ""} aria-current={active === s.n ? "page" : undefined}
            onClick={() => setActive(s.n)}>
            <span className="tab-n">{s.n}</span>
            <span className="tab-txt"><b>{s.label}</b><small>{s.text}</small></span>
          </button>
        ))}
      </nav>
    </aside>
  );
}

/** Capçalera de secció: número, títol i pregunta guia. */
export function SectionHeader({ n, title, question, help }: { n: number; title: string; question: string; help?: string }) {
  return (
    <header className="section-head">
      <span className="section-n" aria-hidden>{n}</span>
      <div>
        <h2>{title}{help && <HelpTip text={help} />}</h2>
        <p>{question}</p>
      </div>
    </header>
  );
}

/** Botó "?" que mostra l'explicació en passar-hi el ratolí (o en enfocar-lo amb el teclat). */
export function HelpTip({ text }: { text: string }) {
  return (
    <span className="help">
      <button type="button" className="help-btn" aria-label="Com es juga" aria-describedby="help-pop">?</button>
      <span className="help-pop" id="help-pop" role="tooltip"><b>Com es juga</b>{text}</span>
    </span>
  );
}
