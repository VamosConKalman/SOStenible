// Secció 4 · Solver: com decideix l'agent quan no coneix el futur (rolling horizon + escenaris).
import RollingHorizonDashboard from "./rolling/RollingHorizonDashboard";

export default function SimulationPage({ initialDate }: { initialDate?: string }) {
  return (
    <div className="sim-wrap">
      <RollingHorizonDashboard initialDate={initialDate} />
    </div>
  );
}
