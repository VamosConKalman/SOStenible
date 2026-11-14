function BatteryMonitor() {
  return (
    <div className="page">

      <div className="hero">

        <h1>Battery Analytics</h1>

        <p className="hero-subtitle">
          Detailed monitoring of battery behaviour and operation.
        </p>

      </div>

      <div className="card">

        <h2>Current State of Charge</h2>

        <h1>76%</h1>

        <p>
          Battery currently charging.
        </p>

      </div>

      <div className="chart-container">

        <h2>Operational Status</h2>

        <p>
          Future visualizations will display charging,
          discharging and idle periods over time.
        </p>

      </div>

    </div>
  );
}

export default BatteryMonitor;