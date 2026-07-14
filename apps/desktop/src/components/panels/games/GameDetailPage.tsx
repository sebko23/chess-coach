"use no memo";

import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Group,
  Loader,
  NumberInput,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import {
  IconAlertCircle,
  IconArrowLeft,
  IconChevronDown,
  IconChevronUp,
  IconDownload,
  IconRefresh,
} from "@tabler/icons-react";
import { useNavigate, useParams } from "@tanstack/react-router";
import { useAtomValue } from "jotai";
import {
  backendBaseUrlAtom,
  backendTokenAtom,
} from "@/state/atoms/coach";
import EvalGraph from "@/components/panels/coach/EvalGraph";
import type { FC } from "react";

interface EvalPoint {
  ply: number;
  score_cp: number | null;
  score_mate: number | null;
  move_san: string | null;
  classification: string | null;
}

interface Blunder {
  fen: string;
  ply: number;
  move_san: string;
  classification: string;
  score_cp: number | null;
  score_mate: number | null;
}

interface BlunderEnvelope {
  blunders: Blunder[];
}

const CLASSIFICATION_COLORS: Record<string, string> = {
  blunder: "red",
  mistake: "orange",
  inaccuracy: "yellow",
  good: "green",
  excellent: "teal",
  best: "blue",
};

const GameDetailPage: FC = () => {
  const { gameId } = useParams({ from: "/games/$gameId" });
  const baseUrl = useAtomValue(backendBaseUrlAtom);
  const token = useAtomValue(backendTokenAtom);
  const navigate = useNavigate();

  const [pgn, setPgn] = useState<string | null>(null);
  const [evalPoints, setEvalPoints] = useState<EvalPoint[]>([]);
  const [blunders, setBlunders] = useState<Blunder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPgn, setShowPgn] = useState(false);
  const [computeDepth, setComputeDepth] = useState<number>(6);
  const [computing, setComputing] = useState(false);
  const [computeResult, setComputeResult] = useState<string | null>(null);
  const [computeError, setComputeError] = useState<string | null>(null);

  const fetchDetail = useCallback(async () => {
    if (!baseUrl || !token || !gameId) return;
    setLoading(true);
    setError(null);
    try {
      const headers = { Authorization: `Bearer ${token}` };

      // Fetch PGN
      const pgnResp = await fetch(`${baseUrl}/v1/games/${gameId}/pgn`, { headers });
      if (!pgnResp.ok) throw new Error(`PGN: HTTP ${pgnResp.status}`);
      const pgnData = await pgnResp.json();
      setPgn(pgnData.pgn ?? "");

      // Fetch eval graph
      const evalResp = await fetch(`${baseUrl}/v1/games/${gameId}/eval-graph`, { headers });
      if (evalResp.ok) {
        const evalData: EvalPoint[] = await evalResp.json();
        setEvalPoints(evalData);
      }

      // Fetch blunders (use first position FEN)
      const firstPosResp = await fetch(`${baseUrl}/v1/games/${gameId}/eval-graph?limit=1`, { headers });
      if (firstPosResp.ok) {
        const firstPos: EvalPoint[] = await firstPosResp.json();
        if (firstPos.length > 0 && firstPos[0].move_san) {
          const blunderResp = await fetch(
            `${baseUrl}/v1/blunders/by-fen?fen=${encodeURIComponent(firstPos[0].move_san)}`,
            { headers }
          );
          if (blunderResp.ok) {
            const blunderData: BlunderEnvelope = await blunderResp.json();
            setBlunders(blunderData.blunders ?? []);
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load game details");
    } finally {
      setLoading(false);
    }
  }, [baseUrl, token, gameId]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  // BBF-24: explicit pre-compute button. The eval-graph route is already
  // lazy — it computes missing analyses on first call and caches them.
  // This button triggers a fresh GET with a chosen depth, so the user
  // gets progress feedback (loading banner) and can pre-warm the cache
  // at a non-default depth (e.g. depth 12) before a deep study session.
  // No new backend endpoint is needed; the GET /v1/games/{id}/eval-graph
  // route is the implementation.
  const handleCompute = useCallback(async () => {
    if (!baseUrl || !token || !gameId) return;
    setComputing(true);
    setComputeResult(null);
    setComputeError(null);
    const t0 = Date.now();
    try {
      const headers = { 'Authorization': 'Bearer ' + token };
      const resp = await fetch(
        `${baseUrl}/v1/games/${gameId}/eval-graph?depth=${computeDepth}`,
        { headers },
      );
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data: EvalPoint[] = await resp.json();
      const n = data.length;
      const withScore = data.filter((p) => p.score_cp != null).length;
      const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
      setComputeResult(
        `Computed ${withScore}/${n} plies at depth ${computeDepth} in ${elapsed}s`,
      );
      // Refresh the displayed eval-graph with the new data.
      setEvalPoints(data);
    } catch (e) {
      setComputeError(
        e instanceof Error ? e.message : "Compute failed",
      );
    } finally {
      setComputing(false);
    }
  }, [baseUrl, token, gameId, computeDepth]);

  if (loading) {
    return (
      <Stack align="center" p="xl">
        <Loader />
        <Text c="dimmed" size="sm">Loading game details…</Text>
      </Stack>
    );
  }

  if (error) {
    return (
      <Box p="md">
        <Alert icon={<IconAlertCircle size={16} />} title="Failed to load game" color="red">
          <Text size="sm">{error}</Text>
        </Alert>
        <Button
          variant="subtle"
          leftSection={<IconArrowLeft size={16} />}
          onClick={() => navigate({ to: "/games" })}
          mt="md"
        >
          Back to Games
        </Button>
      </Box>
    );
  }

  return (
    <Box p="md">
      <Group justify="apart" mb="md">
        <Group>
          <Button
            variant="subtle"
            leftSection={<IconArrowLeft size={16} />}
            onClick={() => navigate({ to: "/games" })}
          >
            Back
          </Button>
          <Title order={3}>Game Detail</Title>
        </Group>
        <Group>
          <NumberInput
            aria-label="Compute depth"
            value={computeDepth}
            onChange={(v) =>
              setComputeDepth(typeof v === "number" ? v : 6)
            }
            min={1}
            max={30}
            step={1}
            w={90}
            disabled={computing}
          />
          <Button
            leftSection={<IconRefresh size={16} />}
            onClick={handleCompute}
            loading={computing}
            size="sm"
            variant="light"
          >
            Compute full analysis
          </Button>
          <Badge size="lg">ID: {gameId?.substring(0, 8)}…</Badge>
        </Group>
      </Group>

      {computeResult && (
        <Alert
          icon={<IconRefresh size={16} />}
          color="blue"
          mb="md"
          withCloseButton
          onClose={() => setComputeResult(null)}
        >
          <Text size="sm">{computeResult}</Text>
        </Alert>
      )}
      {computeError && (
        <Alert
          icon={<IconAlertCircle size={16} />}
          color="red"
          mb="md"
          withCloseButton
          onClose={() => setComputeError(null)}
        >
          <Text size="sm">{computeError}</Text>
        </Alert>
      )}

      {/* Eval Graph */}
      <Card withBorder mb="md">
        <Card.Section p="md">
          <Title order={5} mb="xs">Evaluation Graph</Title>
          {evalPoints.length > 0 ? (
            <EvalGraph />
          ) : (
            <Text c="dimmed" size="sm">No evaluation data available.</Text>
          )}
        </Card.Section>
      </Card>

      {/* Blunders */}
      {blunders.length > 0 && (
        <Card withBorder mb="md">
          <Card.Section p="md">
            <Title order={5} mb="xs">Blunders & Mistakes ({blunders.length})</Title>
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Ply</Table.Th>
                  <Table.Th>Move</Table.Th>
                  <Table.Th>Classification</Table.Th>
                  <Table.Th>Score</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {blunders.map((b, i) => (
                  <Table.Tr key={i}>
                    <Table.Td>{b.ply}</Table.Td>
                    <Table.Td><Text ff="monospace">{b.move_san}</Text></Table.Td>
                    <Table.Td>
                      <Badge
                        color={CLASSIFICATION_COLORS[b.classification] ?? "gray"}
                        variant="light"
                      >
                        {b.classification}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      {b.score_cp != null
                        ? `${(b.score_cp / 100).toFixed(2)}`
                        : b.score_mate != null
                        ? `#${b.score_mate}`
                        : "—"}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Card.Section>
        </Card>
      )}

      {/* PGN */}
      <Card withBorder>
        <Card.Section p="md">
          <Group justify="apart" mb="xs">
            <Title order={5}>PGN</Title>
            <Group>
              <Button
                variant="subtle"
                size="xs"
                rightSection={showPgn ? <IconChevronUp size={14} /> : <IconChevronDown size={14} />}
                onClick={() => setShowPgn(!showPgn)}
              >
                {showPgn ? "Hide" : "Show"}
              </Button>
              {pgn && (
                <Button
                  variant="subtle"
                  size="xs"
                  leftSection={<IconDownload size={14} />}
                  onClick={() => {
                    const blob = new Blob([pgn], { type: "text/plain" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `game-${gameId?.substring(0, 8)}.pgn`;
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                >
                  Download
                </Button>
              )}
            </Group>
          </Group>
          {showPgn && pgn && (
            <Box
              component="pre"
              style={{
                maxHeight: 300,
                overflow: "auto",
                fontSize: 12,
                background: "var(--mantine-color-gray-0)",
                padding: 8,
                borderRadius: 4,
              }}
            >
              {pgn}
            </Box>
          )}
        </Card.Section>
      </Card>
    </Box>
  );
};

export default GameDetailPage;
