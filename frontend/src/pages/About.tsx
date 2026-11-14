import { Link } from "react-router-dom";

export default function About() {
  return (
    <main className="wrap narrow">
      <section className="level">
        <p className="kicker dark">El repte</p>
        <h1 className="page-title">Datathon UPC Sostenible 2026</h1>
        <p>
          El Campus Nord té una planta fotovoltaica i una bateria de 2 MWh. El repte demana decidir, hora a hora,
          quan carregar-la, quan descarregar-la i quan deixar-la en repòs per reduir les emissions de CO₂ (70 %)
          i el cost de l'electricitat (30 %), sense saber amb certesa què passarà l'endemà.
        </p>
        <p>Aquest web té un doble objectiu: optimitzar una bateria real i fer visible la transició energètica de la universitat a tota la comunitat.</p>
        <ol className="about-levels">
          <li><b>Entén</b> el sistema energètic del campus.</li>
          <li><b>Juga</b> a prendre decisions com la persona responsable de la bateria.</li>
          <li><b>Analitza</b> com les dades i els algorismes redueixen emissions i costos.</li>
          <li><b>Comunitat:</b> la tecnologia sola no n'hi ha prou.</li>
        </ol>
        <p><Link to="/">← Torna al panell</Link></p>
      </section>
    </main>
  );
}
