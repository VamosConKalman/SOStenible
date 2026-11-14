interface Props {
  title: string;
  value: string;
  color: string;
}

export default function KPICard({
  title,
  value,
  color,
}: Props) {
  return (
    <div className="card">
      <h3>{title}</h3>

      <h2 style={{ color }}>
        {value}
      </h2>
    </div>
  );
}