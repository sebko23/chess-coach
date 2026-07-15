import { useAtomValue } from "jotai";
import { backendBaseUrlAtom, backendTokenAtom } from "@/state/atoms/coach";
import {
  Container, Title, Text, SimpleGrid, Card, Badge, Stack, Group,
  Paper, Loader, Alert, Divider, Modal, ScrollArea, Code, Progress,
  Anchor, Box,
} from "@mantine/core";
import { useCallback, useEffect, useMemo, useState } from "react";

/**
 * ProfileDashboard — Phase 4 finish sprint (BBF-62)
 *
 * The dashboard reads from the unified /v1/profile/{player}/analysis
 * response shape (BBF-61): `metrics: [{id, value, sample_size, d,
 * ci_low, ci_high, passes_b4_gate}]`.
 *
 * §B4 contract (docs/13_review_response/response-to-review.md):
 *  - Each metric tile carries a permanent "experimental" badge
 *  - The non-clinical disclaimer banner is rendered alongside
 *    the "Playing Style Patterns" header
 *  - Each tile has an "Explain" drill-down that opens a modal
 *    with the /v1/profile/{player}/explain/{metric} response
 *    (methodology + raw inputs + intermediate values)
 *  - Below-threshold metrics (passes_b4_gate = false) are NOT
 *    surfaced as coaching insights — they're rendered as
 *    "Insufficient evidence" with a footnote.
 */

interface UnifiedMetric {
  id: string;
  value: number | null;
  sample_size: number;
  d: number | null;
  ci_low: number | null;
  ci_high: number | null;
  passes_b4_gate: boolean;
}

interface AnalysisResponse {
  player_name: string;
  total_games: number;
  // Legacy flat fields kept for backward compat with
  // the pre-BBF-61 dashboard. Not used in this rewrite.
  tactical_tendency: number;
  risk_appetite: number;
  tilt_index: number;
  time_pressure_blunders: number;
  opening_breadth: number;
  // New unified shape (BBF-61 onward).
  metrics: UnifiedMetric[];
}

interface ExplainResponse {
  player_name: string;
  metric_id: string;
  effect: {
    point_estimate: number | null;
    d: number | null;
    ci_low: number | null;
    ci_high: number | null;
    sample_size: number;
    null_value: number;
  };
  passes_b4_gate: boolean;
  methodology: string;
  raw_inputs: Record<string, unknown>;
  intermediate_values: Record<string, unknown>;
  caveats: string[];
}

// The 7 BBF-54..59 metric IDs, in display order.
// Order matches the phase-plan-v2.md Phase 4 exit criteria.
const METRIC_DISPLAY_ORDER: string[] = [
  "tactical_vs_positional_bias",
  "time_pressure_quality",
  "opening_comfort",
  "conversion_ability",
  "blunder_rate_vs_rating",
  "decision_fatigue",
  "sequence_based_tilt",
];

// Friendly display labels for the 7 metrics. Keys must
// match the METRIC_DISPLAY_ORDER ids.
const METRIC_DISPLAY_LABELS: Record<string, string> = {
  tactical_vs_positional_bias: "Tactical vs Positional Bias",
  time_pressure_quality: "Time Pressure Quality",
  opening_comfort: "Opening Comfort",
  conversion_ability: "Conversion Ability",
  blunder_rate_vs_rating: "Blunder Rate vs Rating",
  decision_fatigue: "Decision Fatigue",
  sequence_based_tilt: "Sequence-Based Tilt",
};

// Brief insight copy rendered under each metric. The insight
// is shown ONLY when passes_b4_gate is true (per §B4 rule 3).
// Below-threshold metrics render "Insufficient evidence".
function insightCopy(
  metricId: string,
  value: number | null,
  passesGate: boolean,
): { text: string; tone: "good" | "neutral" | "warn" | "bad" } {
  if (value === null) {
    return { text: "No data", tone: "neutral" };
  }
  if (!passesGate) {
    return {
      text: `Insufficient evidence — sample size is too small or effect size below the §B4 threshold.`,
      tone: "neutral",
    };
  }
  switch (metricId) {
    case "tactical_vs_positional_bias":
      if (value > 0.6) return { text: "Strong tactical vision — converts opportunities well.", tone: "good" };
      if (value > 0.4) return { text: "Average tactical conversion — more puzzle practice recommended.", tone: "neutral" };
      return { text: "Tactical blindness — daily puzzle training recommended.", tone: "warn" };
    case "time_pressure_quality":
      if (value < 0.05) return { text: "Good time management — blunders don't increase in deep play.", tone: "good" };
      if (value < 0.15) return { text: "Mild time pressure effect — moderate late-game blunders.", tone: "neutral" };
      return { text: "Struggles under time pressure — practice fast games.", tone: "warn" };
    case "opening_comfort":
      if (value >= 2) return { text: "Broad opening repertoire — consider specialising.", tone: "good" };
      if (value >= 1) return { text: "Balanced opening repertoire.", tone: "neutral" };
      return { text: "Narrow repertoire — try new openings to broaden your range.", tone: "warn" };
    case "conversion_ability":
      if (value > 0.6) return { text: "Strong conversion — capitalizes on advantages effectively.", tone: "good" };
      if (value > 0.4) return { text: "Average conversion — winning positions need more precision.", tone: "neutral" };
      return { text: "Weak conversion — closing out games is a priority area.", tone: "warn" };
    case "blunder_rate_vs_rating":
      if (value < 0.1) return { text: "Low blunder rate — better than the rating-expected level.", tone: "good" };
      if (value < 0.2) return { text: "Moderate blunder rate — tactical errors are a key weakness.", tone: "neutral" };
      return { text: "High blunder rate — tactical errors are a priority area.", tone: "bad" };
    case "decision_fatigue":
      if (value < 0.05) return { text: "Decision quality is stable across the session.", tone: "good" };
      if (value < 0.15) return { text: "Mild decision fatigue — consider taking breaks.", tone: "neutral" };
      return { text: "Decision fatigue is significant — short sessions help.", tone: "warn" };
    case "sequence_based_tilt":
      if (value < 0.05) return { text: "Resilient — performs well after loss streaks.", tone: "good" };
      if (value < 0.15) return { text: "Moderate tilt — monitor after losses.", tone: "neutral" };
      return { text: "High tilt risk — take breaks after losses.", tone: "warn" };
    default:
      return { text: "", tone: "neutral" };
  }
}

function toneColor(tone: "good" | "neutral" | "warn" | "bad"): string {
  switch (tone) {
    case "good": return "teal";
    case "neutral": return "gray";
    case "warn": return "yellow";
    case "bad": return "red";
  }
}

function formatValue(metricId: string, value: number | null): string {
  if (value === null) return "N/A";
  switch (metricId) {
    case "opening_comfort":
      // Distinct count -> show as integer or "limited"
      return Number.isFinite(value) && Number.isInteger(value)
        ? String(value)
        : value.toFixed(2);
    default:
      return value.toFixed(3);
  }
}

export default function ProfileDashboard() {
  const baseUrl = useAtomValue(backendBaseUrlAtom);
  const token = useAtomValue(backendTokenAtom);

  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Drill-down modal state
  const [explainModal, setExplainModal] = useState<{
    metricId: string;
    data: ExplainResponse | null;
    loading: boolean;
  } | null>(null);

  const headers = useMemo(
    () => (token
      ? ({ Authorization: `Bearer ${token}` } as HeadersInit)
      : ({} as HeadersInit)),
    [token],
  );

  /**
   * Fetch the unified analysis response (BBF-61 onward).
   *
   * POST /v1/profile/{player}/analysis returns both the
   * legacy flat fields AND the new metrics:[{id, value,
   * sample_size, d, passes_b4_gate}] array. This dashboard
   * reads from the metrics array; the flat fields are
   * ignored.
   */
  const fetchAnalysis = useCallback(async () => {
    if (!baseUrl) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(
        `${baseUrl}/v1/profile/default/analysis`,
        { method: "POST", headers },
      );
      if (!resp.ok) throw new Error(`Analysis: ${resp.status}`);
      const data = (await resp.json()) as AnalysisResponse;
      setAnalysis(data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [baseUrl, headers]);

  useEffect(() => { fetchAnalysis(); }, [fetchAnalysis]);

  /**
   * Fetch the /explain/{metric} response for the drill-down
   * modal. The response includes methodology text + raw
   * inputs + intermediate values per §B4 rule 4.
   */
  const openExplain = useCallback(async (metricId: string) => {
    if (!baseUrl || !token) return;
    setExplainModal({ metricId, data: null, loading: true });
    try {
      const resp = await fetch(
        `${baseUrl}/v1/profile/default/explain/${metricId}`,
        { headers },
      );
      if (!resp.ok) throw new Error(`Explain: ${resp.status}`);
      const data = (await resp.json()) as ExplainResponse;
      setExplainModal({ metricId, data, loading: false });
    } catch (e: unknown) {
      // Surface as a minimal modal with the error string;
      // the user can close it and try again.
      const msg = e instanceof Error ? e.message : String(e);
      setExplainModal({
        metricId,
        data: {
          player_name: "",
          metric_id: metricId,
          effect: { point_estimate: null, d: null, ci_low: null, ci_high: null, sample_size: 0, null_value: 0 },
          passes_b4_gate: false,
          methodology: "Failed to load methodology.",
          raw_inputs: { error: msg },
          intermediate_values: {},
          caveats: [msg],
        },
        loading: false,
      });
    }
  }, [baseUrl, token, headers]);

  // Build a metric_id -> UnifiedMetric lookup so the render
  // can iterate over METRIC_DISPLAY_ORDER (not over the
  // server's order).
  const metricsById = useMemo(() => {
    const out = new Map<string, UnifiedMetric>();
    if (analysis) {
      for (const m of analysis.metrics) {
        out.set(m.id, m);
      }
    }
    return out;
  }, [analysis]);

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

  if (error || !analysis) {
    return (
      <Container py="xl">
        <Alert color="red" title="Failed to load profile">
          <Text>{error || "No data"}</Text>
        </Alert>
      </Container>
    );
  }

  return (
    <Container size="lg" py="md">
      {/* Header + non-clinical disclaimer (BBF-62 §B4) */}
      <Title order={2} mb="xs">
        Playing Style Patterns
        <Badge ml="sm" color="orange" variant="light" size="sm">
          experimental
        </Badge>
      </Title>
      <Text c="dimmed" size="sm" mb="md">
        Based on {analysis.total_games} {analysis.total_games === 1 ? "game" : "games"}
        {" \u00b7 "}
        player: {analysis.player_name}
      </Text>

      {/* Non-clinical disclaimer (BBF-62 §B4) */}
      <Alert
        color="yellow"
        title="Non-clinical disclaimer"
        mb="md"
        icon={<Box>{"\u26A0"}</Box>}
      >
        <Text size="xs">
          These metrics are experimental. They are not a clinical
          assessment of cognitive function, mental health, or any
          other condition. They are statistical summaries of chess
          game data, intended for chess coaching only. Consult a
          qualified chess coach for interpretation.
        </Text>
      </Alert>

      {/* The 7 metric tiles (BBF-62 unified-shape render). */}
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md" mb="xl">
        {METRIC_DISPLAY_ORDER.map((metricId) => {
          const metric = metricsById.get(metricId);
          if (!metric) {
            // Server didn't return this metric (e.g. metric
            // was removed or renamed). Render an empty tile.
            return (
              <Card withBorder shadow="sm" p="md" radius="md" key={metricId}>
                <Stack align="center" gap="xs">
                  <Group gap="xs">
                    <Text fw={600} size="sm">
                      {METRIC_DISPLAY_LABELS[metricId] ?? metricId}
                    </Text>
                    <Badge color="orange" variant="light" size="xs">experimental</Badge>
                  </Group>
                  <Text c="dimmed" size="xs">No data</Text>
                </Stack>
              </Card>
            );
          }
          const insight = insightCopy(metricId, metric.value, metric.passes_b4_gate);
          const displayValue = formatValue(metricId, metric.value);
          // Confidence interval width as a % of the CI midpoint
          const ciWidth = (metric.ci_low !== null && metric.ci_high !== null)
            ? Math.abs(metric.ci_high - metric.ci_low)
            : 0;
          const showCi = metric.ci_low !== null && metric.ci_high !== null
            && ciWidth > 0;
          return (
            <Card withBorder shadow="sm" p="md" radius="md" key={metricId}>
              <Stack align="stretch" gap="xs">
                <Group justify="space-between" align="center">
                  <Text fw={600} size="sm">
                    {METRIC_DISPLAY_LABELS[metricId] ?? metricId}
                  </Text>
                  <Badge color="orange" variant="light" size="xs">
                    experimental
                  </Badge>
                </Group>
                {/* Large numeric display */}
                <Text ta="center" size="xl" fw={700}>
                  {displayValue}
                </Text>
                {/* Insight copy */}
                <Text size="xs" c="dimmed" ta="center" style={{ minHeight: 32 }}>
                  {insight.text}
                </Text>
                {/* CI / d / sample_size metadata */}
                <Group justify="space-between" gap="xs">
                  <Text size="xs" c="dimmed">
                    n = {metric.sample_size}
                  </Text>
                  <Text size="xs" c="dimmed">
                    d = {metric.d !== null ? metric.d.toFixed(2) : "N/A"}
                  </Text>
                  <Badge
                    color={metric.passes_b4_gate ? "teal" : "gray"}
                    variant="light"
                    size="xs"
                  >
                    {metric.passes_b4_gate ? "B4: passes" : "B4: not surfaced"}
                  </Badge>
                </Group>
                {/* CI progress bar (visualizes the CI range) */}
                {showCi && metric.value !== null && (
                  <Box>
                    <Progress
                      value={((metric.value! - metric.ci_low!) /
                        ciWidth) * 100}
                      color={toneColor(insight.tone)}
                      size="xs"
                    />
                    <Text size="xs" c="dimmed" ta="center" mt={4}>
                      95% CI [{metric.ci_low!.toFixed(2)}, {metric.ci_high!.toFixed(2)}]
                    </Text>
                  </Box>
                )}
                {/* Explain drill-down button */}
                <Anchor
                  size="xs"
                  onClick={() => openExplain(metricId)}
                  style={{ cursor: "pointer", textAlign: "center" }}
                >
                  How is this calculated? (Explain)
                </Anchor>
              </Stack>
            </Card>
          );
        })}
      </SimpleGrid>

      <Divider label="End of Profile" labelPosition="left" mb="md" />

      {/* Drill-down modal: loads /v1/profile/default/explain/{metric_id} */}
      <Modal
        opened={explainModal !== null}
        onClose={() => setExplainModal(null)}
        title={
          explainModal
            ? `Explain: ${METRIC_DISPLAY_LABELS[explainModal.metricId] ?? explainModal.metricId}`
            : "Explain"
        }
        size="xl"
        scrollAreaComponent={ScrollArea.Autosize}
      >
        {explainModal?.loading && (
          <Stack align="center" py="xl">
            <Loader size="md" />
            <Text size="sm">Loading methodology...</Text>
          </Stack>
        )}
        {explainModal?.data && (
          <Stack gap="md">
            <Group>
              <Badge
                color={explainModal.data.passes_b4_gate ? "teal" : "gray"}
                variant="light"
              >
                {explainModal.data.passes_b4_gate
                  ? "B4 gate: passes"
                  : "B4 gate: not surfaced"}
              </Badge>
              <Badge color="orange" variant="light">experimental</Badge>
              <Text size="xs" c="dimmed">
                n = {explainModal.data.effect.sample_size}
              </Text>
            </Group>
            <Box>
              <Text size="sm" fw={600} mb="xs">Methodology</Text>
              <Paper withBorder p="sm" radius="sm">
                <Code block style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
                  {explainModal.data.methodology}
                </Code>
              </Paper>
            </Box>
            <Box>
              <Text size="sm" fw={600} mb="xs">Raw inputs</Text>
              <Code block style={{ fontSize: 11 }}>
                {JSON.stringify(explainModal.data.raw_inputs, null, 2)}
              </Code>
            </Box>
            <Box>
              <Text size="sm" fw={600} mb="xs">Intermediate values</Text>
              <Code block style={{ fontSize: 11 }}>
                {JSON.stringify(explainModal.data.intermediate_values, null, 2)}
              </Code>
            </Box>
            {explainModal.data.caveats.length > 0 && (
              <Box>
                <Text size="sm" fw={600} mb="xs">Caveats</Text>
                <Stack gap="xs">
                  {explainModal.data.caveats.map((c, i) => (
                    <Alert key={i} color="yellow" variant="light">
                      <Text size="xs">{c}</Text>
                    </Alert>
                  ))}
                </Stack>
              </Box>
            )}
          </Stack>
        )}
      </Modal>
    </Container>
  );
}
