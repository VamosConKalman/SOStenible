import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

/** Píndoles "Sabies que…?" (textos fixats per l'equip). */
export const FACTS = [
  "Sabies que al Campus Nord hi ha més de 500 plaques solars generant electricitat neta per al consum propi de la universitat?",
  "Sabies que l'energia solar d'aquestes plaques evita cada any l'emissió de desenes de tones de CO₂ a l'atmosfera?",
  "Sabies que el Campus Nord funciona com un laboratori viu on s'assagen pèrgoles solars que donen ombra i generen energia alhora?",
  "Sabies que alguns refugis solars del campus també filtren l'aire i refresquen l'ambient dels espais exteriors?",
  "Sabies que la xarxa d'autoconsum solar de la UPC supera els 680 kWp de potència entre tots els seus campus?",
];

export default function DidYouKnow() {
  const [i, setI] = useState(0);
  const n = FACTS.length;
  return (
    <aside className="dyk" aria-live="polite">
      <div className="dyk-tag">Sabies que…?</div>
      <p className="dyk-body">{FACTS[i].replace(/^Sabies que /, "").replace(/^./, (c) => c.toUpperCase()).replace(/\?$/, ".")}</p>
      <div className="dyk-nav">
        <button aria-label="Anterior" onClick={() => setI((i + n - 1) % n)}><ChevronLeft size={18} /></button>
        <span>{i + 1}/{n}</span>
        <button aria-label="Següent" onClick={() => setI((i + 1) % n)}><ChevronRight size={18} /></button>
      </div>
    </aside>
  );
}
