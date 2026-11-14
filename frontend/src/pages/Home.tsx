import { useMemo, useState } from "react";
import { useDashboardData } from "../hooks/useDashboardData";
import { LevelHeader, LEVELS } from "../components/layout/Header";
import Methodology, { AnnualBanner } from "../components/layout/Methodology";
import DidYouKnow, { buildFacts } from "../components/DidYouKnow";
import KpiStrip from "../components/level1/KpiStrip";
import ControlRoom from "../components/level1/ControlRoom";
import EnergyWall from "../components/level1/EnergyWall";
import MarketPanel from "../components/level1/MarketPanel";
import DecisionGame from "../components/level2/DecisionGame";
import StrategyLab from "../components/level3/StrategyLab";
import CommunityPanel from "../components/level4/CommunityPanel";
import { type Action, batteryOf } from "../lib/energy";

const DATE_FMT = new Intl.DateTimeFormat("ca-ES", { weekday: "long", day: "numeric", month: "long" });

const LEVEL_TEXT = [
  "Entén el sistema energètic del campus.",
  "Pren decisions com la persona responsable de la bateria.",
  "Descobreix com les dades i els algorismes redueixen emissions i costos.",
  "La tecnologia sola no n'hi ha prou: la comunitat també forma part de la solució.",
];

export default function Home() {
  const { data, error } = useDashboardData();
  const [dayIdx, setDayIdx] = useState(0);
  const [hour, setHour] = useState(9);
  const [actions, setActions] = useState<Action[]>([]);

  const day = data?.days[dayIdx];
  const bat = useMemo(() => (data ? batteryOf(data) : null), [data]);
  const facts = useMemo(() => (data && day ? buildFacts(data, day) : null), [data, day]);

  if (error) return <div className="state">No s'han pogut carregar les dades ({error}). Executa <code>python frontend/scripts/build_dashboard_data.py</code>.</div>;
  if (!data || !day || !bat || !facts) return <div className="state">Carregant l'energia del campus…</div>;

  const pickDay = (i: number) => { setDayIdx(i); setActions([]); };

  return (
    <>
      <section className="hero">
        <div className="wrap hero-grid">
          <div>
            <p className="kicker">UPC Sostenible · Campus Nord</p>
            <h1>L'energia del campus, <span>hora a hora</span></h1>
            <p className="hero-lead">
              El Campus Nord té plaques solars i una bateria de {data.battery.capacityKwh / 1000} MWh: la Pila Gigant.
              Aquí pots entendre d'on ve l'electricitat que fem servir, provar de gestionar-la tu mateix i descobrir
              què hi podem fer com a comunitat.
            </p>
          </div>
          <ol className="hero-levels">
            {LEVELS.map((l, i) => (
              <li key={l.id}><a href={`#${l.id}`}><span>{l.n}</span><b>{l.label}</b><small>{LEVEL_TEXT[i]}</small></a></li>
            ))}
          </ol>
        </div>

        <div className="daybar">
          <div className="wrap daybar-inner">
            <span className="label">Tria un dia real</span>
            <div className="days" role="tablist">
              {data.days.map((d, i) => (
                <button key={d.id} role="tab" aria-selected={i === dayIdx} className={i === dayIdx ? "on" : ""} onClick={() => pickDay(i)}>
                  <b>{d.label}</b><small>{DATE_FMT.format(new Date(d.date))}</small>
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      <main className="wrap">
        <section id="entendre" className="level">
          <LevelHeader n="01" title="Entén què està passant" question="D'on surt l'electricitat del campus, què fan les plaques i la bateria, i quan és més neta i més barata?" />
          <p className="day-desc">{day.description}</p>
          <KpiStrip data={data} day={day} />
          <ControlRoom day={day} capacityKwh={data.battery.capacityKwh} hour={hour} setHour={setHour} />
          <DidYouKnow facts={[...facts.system, ...facts.battery]} />
          <EnergyWall day={day} hour={hour} />
          <MarketPanel data={data} day={day} />
          <DidYouKnow facts={facts.market} />
        </section>

        <section id="juga" className="level">
          <LevelHeader n="02" title="Juga a ser el gestor energètic" question="Són les 00:00 i la bateria és a mig carregar. Què faries tu, hora a hora?" />
          <DecisionGame day={day} bat={bat} actions={actions} setActions={setActions} />
        </section>

        <section id="analitza" className="level">
          <LevelHeader n="03" title="Pensa com un científic de dades" question="Com de bona ha estat la teva estratègia comparada amb una regla simple i amb l'òptim? I per què?" />
          <StrategyLab day={day} bat={bat} actions={actions} />
        </section>

        <section id="comunitat" className="level">
          <LevelHeader n="04" title="Què faria la comunitat universitària?" question="Tenim una bateria. Però la transició energètica també depèn de com fem servir l'energia les persones." />
          <CommunityPanel key={day.id} day={day} />
          <DidYouKnow facts={facts.people} tone="green" />
        </section>

        <AnnualBanner data={data} />
      </main>

      <Methodology data={data} />
    </>
  );
}
