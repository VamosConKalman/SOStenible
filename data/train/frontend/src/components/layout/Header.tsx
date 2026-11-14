import { useState } from "react";
import { Link } from "react-router-dom";

export const LEVELS = [
  { id: "entendre", n: "01", label: "Entén" },
  { id: "juga", n: "02", label: "Juga" },
  { id: "analitza", n: "03", label: "Analitza" },
  { id: "comunitat", n: "04", label: "Comunitat" },
];

const base = import.meta.env.BASE_URL;

/** Capçalera: marca UPC + UPC Sostenible i accés als quatre nivells. */
export default function Header() {
  const [upcOk, setUpcOk] = useState(true);
  return (
    <header className="masthead">
      <div className="masthead-inner">
        <Link to="/" className="brand" aria-label="Inici">
          {upcOk ? (
            <img src={`${base}brand/logo-upc.svg`} alt="Universitat Politècnica de Catalunya"
              className="brand-upc" onError={() => setUpcOk(false)} />
          ) : (
            <span className="brand-upc-text">UPC</span>
          )}
          <img src={`${base}brand/upc-sostenible.png`} alt="UPC Sostenible" className="brand-sos" />
          <span className="brand-title">Energia<br />Campus Nord</span>
        </Link>
        <nav className="levels-nav" aria-label="Nivells">
          {LEVELS.map((l) => (
            <a key={l.id} href={`#${l.id}`}><span>{l.n}</span>{l.label}</a>
          ))}
          <Link to="/projecte" className="nav-plain">El repte</Link>
        </nav>
      </div>
    </header>
  );
}

/** Capçalera de nivell: número gran, títol i pregunta guia. */
export function LevelHeader({ n, title, question }: { n: string; title: string; question: string }) {
  return (
    <div className="level-head">
      <span className="level-n" aria-hidden>{n}</span>
      <div>
        <p className="level-kicker">Nivell {Number(n)}</p>
        <h2 className="level-title">{title}</h2>
        <p className="level-q">{question}</p>
      </div>
    </div>
  );
}
