import { BrowserRouter, Routes, Route } from "react-router-dom";

import Dashboard from "./pages/Dashboard";
import BatteryMonitor from "./pages/BatteryMonitor";
import About from "./pages/About";

import Sidebar from "./components/Sidebar";

import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <div className="layout">
        <Sidebar />

        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/battery" element={<BatteryMonitor />} />
            <Route path="/about" element={<About />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;