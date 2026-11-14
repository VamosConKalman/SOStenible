function About() {
  return (
    <div className="page">

      <div className="hero">

        <h1>
          UPC Sustainable Battery Optimization Challenge
        </h1>

        <p className="hero-subtitle">
          Transforming energy data into actionable decisions.
        </p>

      </div>

      <div className="info-card">

        <h2>Challenge Overview</h2>

        <p>
          This project has been developed as part of the UPC Sustainable
          Datathon, a collaborative event where multidisciplinary teams
          work on real sustainability challenges through data analysis,
          visualization and optimization.
        </p>

        <p>
          Participants are asked to design and evaluate battery operating
          strategies capable of improving sustainability outcomes in a
          university campus environment.
        </p>

      </div>

      <div className="info-card">

        <h2>Objective</h2>

        <p>
          The challenge focuses on determining when a battery should charge,
          discharge or remain idle in order to achieve the best possible
          environmental and economic performance.
        </p>

        <p>
          Optimization follows a weighted objective:
        </p>

        <ul>
          <li>70% Reduction of CO₂ emissions</li>
          <li>30% Reduction of electricity costs</li>
        </ul>

      </div>

      <div className="info-card">

        <h2>Data Sources</h2>

        <p>
          The optimization model combines different datasets representing
          energy behaviour and external conditions.
        </p>

        <ul>
          <li>Campus electricity demand</li>
          <li>Photovoltaic generation</li>
          <li>Electricity market prices</li>
          <li>Grid carbon intensity indicators</li>
          <li>Battery operating constraints</li>
        </ul>

      </div>

      <div className="info-card">

        <h2>Purpose of this Platform</h2>

        <p>
          This web platform converts raw energy data into visual information
          designed to support decision making.
        </p>

        <p>
          Rather than displaying only numerical values, the platform
          highlights operational patterns, emissions impacts and economic
          trade-offs associated with battery operation.
        </p>

      </div>

    </div>
  );
}

export default About;