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
        <Badge size="lg">ID: {gameId?.substring(0, 8)}…</Badge>
      </Group>

      {/* Eval Graph */}
      <Card withBorder mb="md">
        <Card.Section p="md">
          <Title order={5} mb="xs">Evaluation Graph</Title>
          {evalPoints.length > 0 ? (
            <EvalGraph data={{ points: evalPoints }} />
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
