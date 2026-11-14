import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend
} from "recharts";

import { energyData } from "../data/mockData";

export default function EnergyBalanceChart() {
  return (
    <ResponsiveContainer
      width="100%"
      height={350}
    >
      <AreaChart data={energyData}>
        <XAxis dataKey="hour" />
        <YAxis />

        <Tooltip />
        <Legend />

        <Area
          dataKey="load"
          stackId="1"
          stroke="#34495e"
          fill="#34495e"
        />

        <Area
          dataKey="solar"
          stackId="1"
          stroke="#f1c40f"
          fill="#f1c40f"
        />

        <Area
          dataKey="battery"
          stackId="1"
          stroke="#2ecc71"
          fill="#2ecc71"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}