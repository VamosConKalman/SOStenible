// Nivell 5 · Repte del dia: el mateix funcionament que els nivells 1 i 2
// (campus en directe + joc de decisions), però amb un dia ja designat.
// No es pot triar el dia: tothom juga el mateix i els resultats són comparables.
import { useMemo, useRef, useState } from "react";
import { CalendarCheck, Lock } from "lucide-react";
import { fmt } from "../../theme";
import type { DashboardData, DayData } from "../../types";
import type { Action, Battery } from "../../lib/energy";
import { describeDay, longDate } from "../../lib/days";
import CampusLive from "../level1/CampusLive";
import DecisionGame from "../level2/DecisionGame";
import StrategyLab from "../level3/StrategyLab";

/** Dia designat del repte: dijous lectiu de primavera, assolellat i amb molta activitat. */
export const FIXED_DATE = "2026-04-16";

/** El dia designat si és a les dades; si no, el dia lectiu amb més estalvi possible. */
export function fixedDay(days: DayData[]): DayData {
  const exact = days.find((d) => d.date === FIXED_DATE);
  if (exact) return exact;
  const gain = (d: DayData) => 0.7 * d.totals.co2SavedKg / Math.max(1, d.totals.co2BaseKg) + 0.3 * d.totals.costSavedEur / Math.max(1, d.totals.costBaseEur);
  return [...days].filter((d) => d.weekday < 5).sort((a, b) => gain(b) - gain(a))[0] ?? days[0];
}

export default function FixedDayChallenge({ data, bat, onOpenSolver }: {
  data: DashboardData;
  bat: Battery;
  onOpenSolver: (date: string) => void;
}) {
  const day = useMemo(() => fixedDay(data.days), [data.days]);
  const [hour, setHour] = useState(12);
  const [actions, setActions] = useState<Action[]>([]);
  const [showLab, setShowLab] = useState(false);
  const labRef = useRef<HTMLDivElement>(null);
  const desc = describeDay(day);
  const t = day.totals;

  return (
    <div className="fixed-day">
      <div className="card fixed-day-card">
        <span className="fixed-day-icon" aria-hidden><CalendarCheck size={28} /></span>
        <div>
          <p className="kicker"><Lock size={12} aria-hidden /> Dia designat · no es pot canviar</p>
          <h3>{longDate(day.date)}</h3>
          <p><b>{desc.title}.</b> {desc.text}</p>
          <p className="fine">
            Consum {fmt.int(t.demandKwh)} kWh · solar {fmt.int(t.solarKwh)} kWh ({fmt.dec(t.solarShare, 1)} %) ·
            la millor estratègia possible estalvia {fmt.int(t.co2SavedKg)} kg de CO₂ i {fmt.eur(t.costSavedEur)}.
          </p>
        </div>
        <button className="btn-solid" onClick={() => onOpenSolver(day.date)}>Mira com ho planifica el solver →</button>
      </div>

      <h3 className="fixed-day-sub">1 · Mira el dia en directe</h3>
      <CampusLive day={day} hour={hour} setHour={setHour} />

      <h3 className="fixed-day-sub">2 · Ara decideix tu, hora a hora</h3>
      <DecisionGame key={day.id} day={day} bat={bat} actions={actions} setActions={setActions}
        onAnalyse={() => { setShowLab(true); setTimeout(() => labRef.current?.scrollIntoView({ behavior: "smooth" }), 50); }} />

      {showLab && (
        <div ref={labRef}>
          <h3 className="fixed-day-sub">3 · Compara la teva estratègia</h3>
          <StrategyLab day={day} bat={bat} actions={actions} />
        </div>
      )}
    </div>
  );
}
