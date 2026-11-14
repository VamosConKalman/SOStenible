import { Link } from "react-router-dom";

function Sidebar() {
  return (
    <aside className="sidebar">

      <div className="sidebar-header">
        <div className="sidebar-logo">
          ⚡
        </div>

        <div>
          <div className="sidebar-title">
            UPC Sustainable
          </div>

          <div className="sidebar-subtitle">
            Battery Optimization Challenge
          </div>
        </div>
      </div>

      <nav className="sidebar-nav">

        <Link className="sidebar-link" to="/">
          Decision Center
        </Link>

        <Link className="sidebar-link" to="/battery">
          Battery Analytics
        </Link>

        <Link className="sidebar-link" to="/about">
          Challenge Overview
        </Link>

      </nav>

    </aside>
  );
}

export default Sidebar;
