import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend
} from "recharts";

import { energyData } from "../data/mockData";

export default function BatteryTimeline() {
  return (
    <ResponsiveContainer
      width="100%"
      height={400}
    >
      <ComposedChart data={energyData}>
        <XAxis dataKey="hour" />

        <YAxis yAxisId="left" />

        <YAxis
          yAxisId="right"
          orientation="right"
        />

        <Tooltip />
        <Legend />

        <Bar
          yAxisId="left"
          dataKey="soc"
          fill="#00b894"
          name="SOC (%)"
        />

        <Line
          yAxisId="right"
          dataKey="co2"
          stroke="#e74c3c"
          name="CO₂"
        />

        <Line
          yAxisId="right"
          dataKey="cost"
          stroke="#3498db"
          name="Cost"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}