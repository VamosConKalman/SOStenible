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
import { type Action, batteryOf, runActions } from "./lib/energy";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { fmt } from "./theme";
import { findDay } from "./lib/days";
import "@fontsource/montserrat/600.css";
import "@fontsource/montserrat/700.css";
import "@fontsource/montserrat/800.css";
import "./App.css";

const LAST = 5;

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
  const socNow = actions.length ? (100 * runActions(day, bat, actions).soc[actions.length - 1]) / bat.cap : (100 * bat.soc0) / bat.cap;

  return (
    <div className="shell">
      <Sidebar active={active} setActive={setActive} month={month} dayOfMonth={dom} setDate={setDate} day={day} exact={picked.exact} hideDate={active === 4} />

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
              question={actions.length < 24
                ? `Són les ${day.hours[actions.length]} i la bateria és al ${fmt.int(socNow)} %. Què faries tu, hora a hora?`
                : "Has gestionat el campus durant tot el dia: mira el resultat final."} />
            <DecisionGame key={day.id} day={day} bat={bat} actions={actions} setActions={setActions} onAnalyse={() => setActive(3)} />
          </section>
        )}

        {active === 3 && (
          <section className="section">
            <SectionHeader n={3} title="Pensa com un expert" question="Com de bona ha estat la teva estratègia comparada amb una regla simple i amb el model?" />
            <StrategyLab day={day} bat={bat} actions={actions} />
            <AnnualBanner data={data} />
          </section>
        )}

        {active === 4 && (
          <section className="section sim-section">
            <SimulationPage />
          </section>
        )}

        {active === 5 && (
          <section className="section">
            <SectionHeader n={5} title="Què faria la comunitat universitària de la UPC?" question="Amb la tecnologia sola no n'hi ha prou: la transició energètica també depèn de com fem servir l'energia les persones." />
            <CommunityPanel key={day.id} day={day} days={data.days} />
          </section>
        )}

        <nav className="pager" aria-label="Navegació entre seccions">
          {active > 1 ? <button className="btn-soft btn-arrow" onClick={() => setActive(active - 1)} aria-label="Secció anterior"><ArrowLeft size={20} /></button> : <span />}
          {active < LAST ? <button className="btn-solid btn-arrow" onClick={() => setActive(active + 1)} aria-label="Secció següent"><ArrowRight size={20} /></button> : <span />}
        </nav>

        <Methodology data={data} />
      </main>
    </div>
  );
}