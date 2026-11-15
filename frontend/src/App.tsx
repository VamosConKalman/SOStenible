import { useEffect, useMemo, useState } from "react";
import { useDashboardData } from "./hooks/useDashboardData";
import Sidebar, { SectionHeader } from "./components/layout/Sidebar";
import Methodology, { AnnualBanner } from "./components/layout/Methodology";
import DidYouKnow from "./components/DidYouKnow";
import KpiStrip from "./components/level1/KpiStrip";
import CampusLive from "./components/level1/CampusLive";
import DecisionGame, { HOW_TO } from "./components/level2/DecisionGame";
import StrategyLab from "./components/level3/StrategyLab";
import CommunityPanel from "./components/level4/CommunityPanel";
import SimulationPage from "./components/SimulationPage";
import FixedDayChallenge from "./components/level5/FixedDayChallenge";
import { type Action, batteryOf } from "./lib/energy";
import { findDay } from "./lib/days";
import "@fontsource/montserrat/600.css";
import "@fontsource/montserrat/700.css";
import "@fontsource/montserrat/800.css";
import "./App.css";

const LAST = 6;

const fromHash = () => {
  const n = Number(window.location.hash.replace("#", ""));
  return n >= 1 && n <= LAST ? n : 1;
};

export default function App() {
  const { data, error } = useDashboardData();
  const today = new Date();
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [dom, setDom] = useState(today.getDate());
  const [active, setActiveState] = useState(fromHash);
  const [hour, setHour] = useState(12);
  const [actions, setActions] = useState<Action[]>([]);
  const [solverDate, setSolverDate] = useState<string | undefined>(undefined);

  useEffect(() => {
    const onHash = () => setActiveState(fromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const setActive = (n: number) => {
    window.history.replaceState(null, "", `#${n}`);
    setActiveState(n);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const picked = useMemo(() => (data ? findDay(data.days, month, dom) : null), [data, month, dom]);
  const day = picked?.day;
  const bat = useMemo(() => (data ? batteryOf(data) : null), [data]);

  if (error) return <div className="state">No s'han pogut carregar les dades ({error}). Executa <code>python frontend/scripts/build_dashboard_data.py</code>.</div>;
  if (!data || !day || !bat || !picked) return <div className="state">Carregant l'energia del campus...</div>;

  const setDate = (m: number, d: number) => { setMonth(m); setDom(d); setActions([]); };

  return (
    <div className="shell">
      <Sidebar active={active} setActive={setActive} month={month} dayOfMonth={dom} setDate={setDate} day={day} exact={picked.exact} hideDate={active >= 5} />

      <main className="content">
        {active === 1 && (
          <section className="section s1">
            <div className="intro">
              <span className="section-n" aria-hidden>1</span>
              <div>
                <h1>L'energia del campus, hora a hora</h1>
                <p className="intro-lead">
                  El Campus Nord té plaques solars i una bateria de {data.battery.capacityKwh / 1000} MWh que emmagatzema
                  l'energia generada. Aquí pots entendre d'on ve l'electricitat que fem servir, provar de gestionar-la tu
                  mateix i descobrir què hi podem fer com a comunitat.
                </p>
              </div>
            </div>
            <KpiStrip data={data} day={day} />
            <CampusLive day={day} hour={hour} setHour={setHour} />
            <DidYouKnow />
          </section>
        )}

        {active === 2 && (
          <section className="section">
            <SectionHeader n={2} title="Juga a ser el gestor energètic" help={HOW_TO}
              question="Són les 00:00 i la bateria és a mig carregar. Què faries tu, hora a hora?" />
            <DecisionGame key={day.id} day={day} bat={bat} actions={actions} setActions={setActions} onAnalyse={() => setActive(3)} />
          </section>
        )}

        {active === 3 && (
          <section className="section">
            <SectionHeader n={3} title="Pensa com un científic de dades" question="Com de bona ha estat la teva estratègia comparada amb una regla simple i amb el model?" />
            <StrategyLab day={day} bat={bat} actions={actions} />
            <AnnualBanner data={data} />
          </section>
        )}

        {active === 4 && (
          <section className="section">
            <SectionHeader n={4} title="Què faria la comunitat universitària de la UPC?" question="Amb la tecnologia sola no n'hi ha prou: la transició energètica també depèn de com fem servir l'energia les persones." />
            <CommunityPanel key={day.id} day={day} days={data.days} />
          </section>
        )}

        {active === 5 && (
          <section className="section">
            <SectionHeader n={5} title="Repte del dia" help={HOW_TO}
              question="Un dia ja triat, igual per a tothom: entén-lo, juga'l i compara't amb el model." />
            <FixedDayChallenge data={data} bat={bat} onOpenSolver={(d) => { setSolverDate(d); setActive(6); }} />
          </section>
        )}

        {active === 6 && (
          <section className="section sim-section">
            <SimulationPage key={solverDate ?? "auto"} initialDate={solverDate} />
          </section>
        )}

        <nav className="pager" aria-label="Navegació entre seccions">
          {active > 1 ? <button className="btn-soft" onClick={() => setActive(active - 1)}>← {active - 1}</button> : <span />}
          {active < LAST ? <button className="btn-solid" onClick={() => setActive(active + 1)}>Següent: {active + 1} →</button> : (
            <button className="btn-solid" onClick={() => setActive(1)}>Tornar a l'inici →</button>
          )}
        </nav>

        <Methodology data={data} />
      </main>
    </div>
  );
}