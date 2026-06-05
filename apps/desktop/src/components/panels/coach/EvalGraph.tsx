"use no memo";

import { Box, Card, Text, Title } from "@mantine/core";
import { useAtomValue } from "jotai";
import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceDot,
  ResponsiveContainer,
} from "recharts";
import {
  backendBaseUrlAtom,
  backendTokenAtom,
  blunderResultAtom,
  BLUNDER_COLORS,
} from "@/state/atoms/coach";

interface EvalPoint {
  ply: number;
  move_san: string | null;
  score_cp_white: number;
  best_move: string | null;
  is_mate: boolean;
}

interface EvalGraphData {
  game_id: string;
  points: EvalPoint[];
}

/** Custom tooltip showing move details on hover. */
function EvalTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: EvalPoint }>;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <Card withBorder p="xs" style={{ fontSize: 12 }}>
      <Text size="xs" fw={700}>
        Ply {d.ply}: {d.move_san ?? "starting"}
      </Text>
      <Text size="xs" c={d.score_cp_white >= 0 ? "green" : "red"}>
        {d.score_cp_white >= 0 ? "+" : ""}
        {d.is_mate ? (d.score_cp_white > 0 ? "M" : "-M") : d.display_score}cp
      </Text>
      {d.best_move && (
        <Text size="xs" c="dimmed">
          Best: {d.best_move}
        </Text>
      )}
    </Card>
  );
}

export default function EvalGraph() {
  const baseUrl = useAtomValue(backendBaseUrlAtom);
  const token = useAtomValue(backendTokenAtom);
  const blunderResult = useAtomValue(blunderResultAtom);
  const [data, setData] = useState<EvalGraphData | null>(null);

  const gameId = blunderResult?.game_id ?? null;

  useEffect(() => {
    if (!baseUrl || !token || !gameId) {
      setData(null);
      return;
    }
    let cancelled = false;
    const fetchGraph = async () => {
      try {
        const resp = await fetch(
          `${baseUrl}/v1/games/${gameId}/eval-graph`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!cancelled && resp.ok) {
          setData(await resp.json());
        }
      } catch {
        if (!cancelled) setData(null);
      }
    };
    fetchGraph();
    return () => { cancelled = true; };
  }, [baseUrl, token, gameId]);

  if (!data || !data?.points || data.points.length < 2) return null;

  // Find blunder positions from blunderResult for overlay markers
  const blunderPlies = new Map<number, string>();
  if (blunderResult?.blunders) {
    for (const b of blunderResult.blunders) {
      blunderPlies.set(b.ply, b.classification);
    }
  }

  // Clamp extreme values for readable Y-axis (cap at +-3000)
  const chartData = data.points.map((p) => ({
    ...p,
    display_score: Math.max(-1000, Math.min(1000, p.score_cp_white)),
  }));

  // Build blunder markers
  const blunderDots = data.points
    .filter((p) => blunderPlies.has(p.ply))
    .map((p) => (
      <ReferenceDot
        key={p.ply}
        x={p.ply}
        y={Math.max(-1000, Math.min(1000, p.score_cp_white))}
        r={5}
        fill={BLUNDER_COLORS[blunderPlies.get(p.ply)!] ?? "gray"}
        stroke="white"
        strokeWidth={2}
      />
    ));

  return (
    <Card withBorder>
      <Title order={4} mb="sm">
        Evaluation Curve
      </Title>
      <Box style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis
              dataKey="ply"
              label={{ value: "Ply", position: "insideBottomRight", offset: -5 }}
              tick={{ fontSize: 11 }}
            />
            <YAxis
              domain={[(dataMin: number) => Math.min(dataMin, -100), (dataMax: number) => Math.max(dataMax, 100)]}
              tick={{ fontSize: 11 }}
              label={{ value: "cp (White)", angle: -90, position: "insideLeft" }}
            />
            <Tooltip content={<EvalTooltip />} />
            <Line
              type="monotone"
              dataKey="display_score"
              stroke="#228be6"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
            {blunderDots}
          </LineChart>
        </ResponsiveContainer>
      </Box>
    </Card>
  );
}
