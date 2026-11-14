import { BrowserRouter, Routes, Route } from "react-router-dom";
import Header from "./components/layout/Header";
import Home from "./pages/Home";
import About from "./pages/About";
import "@fontsource/montserrat/800.css";
import "@fontsource/montserrat/900.css";
import "./App.css";

export default function App() {
  return (
    <BrowserRouter>
      <Header />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/projecte" element={<About />} />
      </Routes>
    </BrowserRouter>
  );
}
