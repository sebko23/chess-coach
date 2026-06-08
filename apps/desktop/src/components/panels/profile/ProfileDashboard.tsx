import { useAtomValue } from "jotai";
import { backendBaseUrlAtom, backendTokenAtom } from "@/state/atoms/coach";
import {
  Container, Title, Text, SimpleGrid, Card, RingProgress, Progress,
  Badge, Stack, Group, Paper, Loader, Alert, Divider, Space,
} from "@mantine/core";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid,
} from "recharts";

interface MetricsResponse {
  blunder_rate: number | null;
  conversion_ability: number | null;
  opening_comfort: number | null;
  game_count: number;
  computed_at: string | null;
}

interface HistoryPoint {
  date: string;
  blunder_rate: number;
  conversion_ability: number;
  opening_comfort: number;
}

interface HistoryResponse {
  history: HistoryPoint[];
}

const BLUNDER_COLORS: Record<string, string> = {
  blunder: "red",
  mistake: "orange",
  inaccuracy: "yellow",
};

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "N/A";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", {
      year: "numeric", month: "short", day: "numeric",
    });
  } catch {
    return dateStr;
  }
}

function trendEmoji(current: number | null, previous: number | null, higherIsBetter: boolean): { emoji: string; color: string; text: string } {
  if (current === null || previous === null) return { emoji: "â†’", color: "gray", text: "No trend data" };
  const diff = current - previous;
  const improving = higherIsBetter ? diff > 0 : diff < 0;
  const threshold = 0.03;
  if (Math.abs(diff) < threshold) return { emoji: "â†’", color: "gray", text: "Stable" };
  if (improving) return { emoji: "â†‘", color: "green", text: `Improved by ${Math.abs(diff).toFixed(2)}` };
  return { emoji: "â†“", color: "red", text: `Declined by ${Math.abs(diff).toFixed(2)}` };
}

export default function ProfileDashboard() {
  const baseUrl = useAtomValue(backendBaseUrlAtom);
  const token = useAtomValue(backendTokenAtom);

  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const headers = useMemo(() => (token ? { Authorization: `Bearer ${token}` } as HeadersInit : {} as HeadersInit), [token]);

  const fetchData = useCallback(async () => {
    if (!baseUrl) return;
    setLoading(true);
    setError(null);
    try {
      const profileRes = await fetch(`${baseUrl}/v1/profile/default`, { headers });
      if (!profileRes.ok) throw new Error(`Profile: ${profileRes.status}`);
      const profileData = await profileRes.json();
      // Backend returns { player_id, metrics: [...] }
      const metricsData = profileData.metrics || [];
      // Map metrics array to flat object
      const mapped = {
        game_count: 0,
        computed_at: null,
        blunder_rate: null,
        conversion_ability: null,
        opening_comfort: null,
      };
      for (const m of metricsData) {
        if (m.metric_id === "blunder_rate") mapped.blunder_rate = m.value;
        if (m.metric_id === "conversion_ability") mapped.conversion_ability = m.value;
        if (m.metric_id === "opening_comfort") mapped.opening_comfort = m.value;
      }
      setMetrics(mapped);
      setHistory([]);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [baseUrl, headers]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const blunderRate = metrics?.blunder_rate ?? null;
  const conversionAbility = metrics?.conversion_ability ?? null;
  const openingComfort = metrics?.opening_comfort ?? null;
  const gameCount = metrics?.game_count ?? 0;
  const computedAt = metrics?.computed_at ?? null;

  // Blunder rate: lower is better (0 = perfect, ~0.5 = terrible)
  const blunderPct = blunderRate !== null ? Math.round((1 - Math.min(blunderRate, 0.5) / 0.5) * 100) : 0;
  const blunderTrend = trendEmoji(blunderRate, history.length >= 2 ? history[history.length - 2].blunder_rate : null, false);

  // Conversion ability: higher is better (>0.5 = good)
  const convPct = conversionAbility !== null ? Math.round(Math.min(conversionAbility, 1) * 100) : 0;
  const convTrend = trendEmoji(conversionAbility, history.length >= 2 ? history[history.length - 2].conversion_ability : null, true);

  // Opening comfort: higher values (>0.75) indicate strong familiar positions
  const openingPct = openingComfort !== null ? Math.round(Math.min(openingComfort, 1) * 100) : 0;
  const openingTrend = trendEmoji(openingComfort, history.length >= 2 ? history[history.length - 2].opening_comfort : null, true);

  // Key insight paragraph
  const insight = useMemo(() => {
    const parts: string[] = [];
    if (blunderRate !== null) {
      if (blunderRate < 0.1) parts.push("Low blunder rate â€” excellent tactical accuracy.");
      else if (blunderRate < 0.2) parts.push("Moderate blunder rate â€” tactical consistency is average.");
      else parts.push("High blunder rate â€” tactical errors are a key weakness.");
    }
    if (conversionAbility !== null) {
      if (conversionAbility > 0.6) parts.push("Strong conversion â€” you capitalize on advantages effectively.");
      else if (conversionAbility > 0.4) parts.push("Average conversion â€” winning positions need more precision.");
      else parts.push("Weak conversion â€” closing out games is a priority area.");
    }
    if (openingComfort !== null) {
      if (openingComfort > 0.8) parts.push("High opening comfort â€” you excel in familiar structures.");
      else if (openingComfort > 0.6) parts.push("Moderate opening comfort â€” expanding the repertoire may help.");
      else parts.push("Low opening comfort â€” position unfamiliarity is costing points.");
    }
    if (parts.length === 0) return "Import more games to generate profile insights.";
    return parts.join(" ");
  }, [blunderRate, conversionAbility, openingComfort]);

  if (!baseUrl) {
    return (
      <Container py="xl">
        <Alert color="yellow" title="Backend not connected">
          <Text>Waiting for backend connection.</Text>
        </Alert>
      </Container>
    );
  }

  if (loading) {
    return (
      <Container py="xl" style={{ textAlign: "center" }}>
        <Loader size="lg" />
        <Text mt="md">Loading profile metrics...</Text>
      </Container>
    );
  }

  if (error) {
    return (
      <Container py="xl">
        <Alert color="red" title="Failed to load profile">
          <Text>{error}</Text>
        </Alert>
      </Container>
    );
  }

  const chartData = history.map((h) => ({
    date: h.date ? h.date.slice(0, 10) : "",
    blunder: h.blunder_rate,
    conversion: h.conversion_ability,
    opening: h.opening_comfort,
  }));

  return (
    <Container size="lg" py="md">
      <Title order={2}>Profile</Title>
      <Text c="dimmed" size="sm" mb="lg">
        Based on {gameCount > 0 ? `${gameCount} analysed games` : "0 games"}
        {computedAt ? ` Â· Updated ${formatDate(computedAt)}` : ""}
      </Text>

      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md" mb="xl">
        {/* Blunder Rate */}
        <Card withBorder shadow="sm" p="lg" radius="md">
          <Stack align="center" gap="xs">
            <RingProgress
              size={120}
              thickness={14}
              roundCaps
              sections={[
                { value: blunderPct, color: blunderPct > 70 ? "green" : blunderPct > 40 ? "yellow" : "red", tooltip: `${blunderPct}% clean` },
              ]}
              label={
                <Text ta="center" size="sm" fw={700}>
                  {blunderRate !== null ? blunderRate.toFixed(2) : "N/A"}
                </Text>
              }
            />
            <Text fw={600} size="sm">Blunder Rate</Text>
            <Text size="xs" c="dimmed">Lower is better</Text>
            <Group gap={4}>
              <Text size="sm" c={blunderTrend.color}>{blunderTrend.emoji}</Text>
              <Text size="xs" c={blunderTrend.color}>{blunderTrend.text}</Text>
            </Group>
            <Progress
              value={blunderPct}
              color={blunderPct > 70 ? "green" : blunderPct > 40 ? "yellow" : "red"}
              size="sm"
              w="100%"
            />
          </Stack>
        </Card>

        {/* Conversion Ability */}
        <Card withBorder shadow="sm" p="lg" radius="md">
          <Stack align="center" gap="xs">
            <RingProgress
              size={120}
              thickness={14}
              roundCaps
              sections={[
                { value: convPct, color: convPct > 60 ? "green" : convPct > 40 ? "yellow" : "red", tooltip: `${convPct}%` },
              ]}
              label={
                <Text ta="center" size="sm" fw={700}>
                  {conversionAbility !== null ? conversionAbility.toFixed(2) : "N/A"}
                </Text>
              }
            />
            <Text fw={600} size="sm">Conversion Ability</Text>
            <Text size="xs" c="dimmed">Higher is better</Text>
            <Group gap={4}>
              <Text size="sm" c={convTrend.color}>{convTrend.emoji}</Text>
              <Text size="xs" c={convTrend.color}>{convTrend.text}</Text>
            </Group>
            <Progress
              value={convPct}
              color={convPct > 60 ? "green" : convPct > 40 ? "yellow" : "red"}
              size="sm"
              w="100%"
            />
          </Stack>
        </Card>

        {/* Opening Comfort */}
        <Card withBorder shadow="sm" p="lg" radius="md">
          <Stack align="center" gap="xs">
            <RingProgress
              size={120}
              thickness={14}
              roundCaps
              sections={[
                { value: openingPct, color: openingPct > 75 ? "green" : openingPct > 50 ? "yellow" : "red", tooltip: `${openingPct}%` },
              ]}
              label={
                <Text ta="center" size="sm" fw={700}>
                  {openingComfort !== null ? openingComfort.toFixed(2) : "N/A"}
                </Text>
              }
            />
            <Text fw={600} size="sm">Opening Comfort</Text>
            <Text size="xs" c="dimmed">Familiar positions</Text>
            <Group gap={4}>
              <Text size="sm" c={openingTrend.color}>{openingTrend.emoji}</Text>
              <Text size="xs" c={openingTrend.color}>{openingTrend.text}</Text>
            </Group>
            <Progress
              value={openingPct}
              color={openingPct > 75 ? "green" : openingPct > 50 ? "yellow" : "red"}
              size="sm"
              w="100%"
            />
          </Stack>
        </Card>
      </SimpleGrid>

      {/* Key Insight */}
      <Paper withBorder p="md" radius="md" mb="xl">
        <Title order={5} mb="xs">Key Insight</Title>
        <Text size="sm" style={{ lineHeight: 1.7 }}>{insight}</Text>
      </Paper>

      {/* Trend Charts */}
      {chartData.length >= 4 && (
        <>
          <Divider label="Trend History" labelPosition="left" mb="md" />
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
            <Card withBorder shadow="sm" p="sm">
              <Text size="xs" fw={600} mb="xs">Blunder Rate</Text>
              <ResponsiveContainer width="100%" height={100}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="date" hide />
                  <YAxis hide domain={[0, "dataMax + 0.1"]} />
                  <Tooltip
                    contentStyle={{ fontSize: 11 }}
                    formatter={(value: any) => value?.toFixed?.(3) ?? ""}
                  />
                  <Line
                    type="monotone" dataKey="blunder" stroke="#e03131"
                    strokeWidth={2} dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Card>

            <Card withBorder shadow="sm" p="sm">
              <Text size="xs" fw={600} mb="xs">Conversion Ability</Text>
              <ResponsiveContainer width="100%" height={100}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="date" hide />
                  <YAxis hide domain={[0, 1]} />
                  <Tooltip
                    contentStyle={{ fontSize: 11 }}
                    formatter={(value: any) => value?.toFixed?.(3) ?? ""}
                  />
                  <Line
                    type="monotone" dataKey="conversion" stroke="#2f9e44"
                    strokeWidth={2} dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Card>

            <Card withBorder shadow="sm" p="sm">
              <Text size="xs" fw={600} mb="xs">Opening Comfort</Text>
              <ResponsiveContainer width="100%" height={100}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="date" hide />
                  <YAxis hide domain={[0, 1]} />
                  <Tooltip
                    contentStyle={{ fontSize: 11 }}
                    formatter={(value: any) => value?.toFixed?.(3) ?? ""}
                  />
                  <Line
                    type="monotone" dataKey="opening" stroke="#1971c2"
                    strokeWidth={2} dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          </SimpleGrid>
        </>
      )}
    </Container>
  );
}
