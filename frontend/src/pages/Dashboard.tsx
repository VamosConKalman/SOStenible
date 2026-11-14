function Dashboard() {
  return (
    <div className="page">

      <div className="hero">

        <h1>Decision Center</h1>

        <p className="hero-subtitle">
          High-level insights on battery performance,
          emissions and energy costs.
        </p>

      </div>

      <div className="kpis">

        <div className="card">
          <h3>CO₂ Avoided</h3>
          <h2>238 kg</h2>
        </div>

        <div className="card">
          <h3>Economic Savings</h3>
          <h2>145 €</h2>
        </div>

        <div className="card">
          <h3>Battery Cycles</h3>
          <h2>16</h2>
        </div>

        <div className="card">
          <h3>Current SOC</h3>
          <h2>76 %</h2>
        </div>

      </div>

      <div className="chart-container">

        <h2>Battery Decision Timeline</h2>

        <p>
          This visualization will show when the battery charges,
          discharges or remains idle throughout time.
        </p>

      </div>

      <div className="chart-container">

        <h2>Cost and Emissions Analysis</h2>

        <p>
          Understanding the relationship between grid emissions,
          electricity prices and battery decisions.
        </p>

      </div>

    </div>
  );
}

export default Dashboard;