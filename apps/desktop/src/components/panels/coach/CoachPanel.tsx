"use no memo";

import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Group,
  Loader,
  Stack,
  Text,
  Title,
  useMantineTheme,
} from "@mantine/core";
import {
  IconArrowRight,
  IconBrain,
  IconExternalLink,
  IconPlugConnected,
  IconPlugConnectedX,
  IconRefresh,
} from "@tabler/icons-react";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { useCallback, useEffect, useRef } from "react";
import {
  backendBaseUrlAtom,
  backendTokenAtom,
  backendDescriptorAtom,
  narrationResultAtom,
  narrationLoadingAtom,
  narrationErrorAtom,
  loadDescriptor,
} from "@/state/atoms/coach";
import type { NarrationResult } from "@/state/atoms/coach";

/** Default FEN — the starting position. */
const DEFAULT_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

/**
 * Fetch a grounded narration from the backend for the given position.
 */
async function fetchNarration(
  baseUrl: string,
  token: string,
  fen: string,
  depth: number,
  engineId: string,
  multipv: number,
): Promise<NarrationResult> {
  const resp = await fetch(`${baseUrl}/v1/narration/explain`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
    },
    body: JSON.stringify({
      fen,
      depth,
      engine_id: engineId,
      multipv,
    }),
  });

  if (!resp.ok) {
    const errBody = await resp.text();
    throw new Error(`Backend returned ${resp.status}: ${errBody}`);
  }

  const envelope = await resp.json();
  // Protocol envelope: { data: { fen, narration, ... } }
  return envelope.data as NarrationResult;
}

function ConnectionStatus() {
  const descriptor = useAtomValue(backendDescriptorAtom);
  const baseUrl = useAtomValue(backendBaseUrlAtom);

  if (!descriptor) {
    return (
      <Alert
        color="yellow"
        icon={<IconPlugConnectedX size={16} />}
        title="Backend not found"
      >
        Start the CHESS COACH backend:{" "}
        <Text component="code" size="sm">
          chess-coach-gateway
        </Text>
      </Alert>
    );
  }

  return (
    <Alert
      color="green"
      icon={<IconPlugConnected size={16} />}
      title={`Connected to backend`}
    >
      <Text size="sm">
        v{descriptor.backend_version} on {baseUrl} — protocol{" "}
        {descriptor.protocol_version}
      </Text>
    </Alert>
  );
}

/**
 * Single-line PV display: score badge + first few moves.
 */
function PVLine({
  score,
  moves,
  isBest = false,
}: {
  score: string;
  moves: string[];
  isBest?: boolean;
}) {
  const theme = useMantineTheme();
  return (
    <Group gap="xs" wrap="nowrap">
      <Badge
        size="lg"
        variant={isBest ? "filled" : "light"}
        color={isBest ? theme.primaryColor : "gray"}
      >
        {score}
      </Badge>
      <Text component="span" ff="monospace" size="sm">
        {moves.slice(0, 8).join(" ")}
      </Text>
    </Group>
  );
}

function NarrationResultView({ result }: { result: NarrationResult }) {
  return (
    <Stack gap="md">
      <Card withBorder>
        <Group justify="space-between" mb="sm">
          <Title order={3}>
            <IconBrain size={24} style={{ verticalAlign: "middle", marginRight: 8 }} />
            Coach Analysis
          </Title>
          <Badge variant="outline">depth {result.depth_reached}</Badge>
        </Group>

        <Text size="md" style={{ lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
          {result.narration}
        </Text>
      </Card>

      <Card withBorder>
        <Title order={4} mb="sm">
          <IconArrowRight size={18} style={{ verticalAlign: "middle", marginRight: 6 }} />
          Best Line
        </Title>
        <PVLine
          score={result.score_display}
          moves={result.pv_moves}
          isBest
        />
      </Card>

      {result.fen && (
        <Group gap="xs" justify="flex-end">
          <Text size="xs" c="dimmed" ff="monospace">
            {result.fen}
          </Text>
        </Group>
      )}
    </Stack>
  );
}

/**
 * Main CHESS COACH panel rendered at ``/coach``.
 */
export default function CoachPanel() {
  const baseUrl = useAtomValue(backendBaseUrlAtom);
  const token = useAtomValue(backendTokenAtom);
  const [result, setResult] = useAtom(narrationResultAtom);
  const [loading, setLoading] = useAtom(narrationLoadingAtom);
  const [error, setError] = useAtom(narrationErrorAtom);
  const setDescriptor = useSetAtom(backendDescriptorAtom);

  // Track whether an analysis has been attempted, so we don't auto-fetch
  // when the user hasn't explicitly requested one (avoids mount-triggered fetch
  // in Phase 2 when the FEN is wired to the board).
  const hasRun = useRef(false);

  /** Re-read the backend descriptor and re-trigger analysis. */
  const handleRetry = useCallback(async () => {
    // The user may have started the backend since the error appeared.
    // Re-read the descriptor; the derived atoms (baseUrl, token) will
    // update, and the useEffect below will fire the analysis if needed.
    await loadDescriptor(setDescriptor);
    // Clear the error so the UI shows a fresh state.
    setError(null);
    setResult(null);
    // Allow the useEffect to re-trigger (ref is reset by the dep change).
    hasRun.current = false;
  }, [setDescriptor, setError, setResult]);

  // Analyse the starting position on mount, or when connection appears
  useEffect(() => {
    if (!baseUrl || !token) {
      // Backend not available — don't attempt yet.
      return;
    }

    if (hasRun.current) {
      // Already ran the analysis for this connection.
      return;
    }

    let cancelled = false;

    const run = async () => {
      setLoading(true);
      setError(null);
      setResult(null);

      const attemptFetch = async () => {
        return fetchNarration(
          baseUrl,
          token,
          DEFAULT_FEN,
          18,    // depth
          "stockfish",
          1,     // multipv
        );
      };

      try {
        // First attempt
        const narration = await attemptFetch();
        if (!cancelled) {
          setResult(narration);
          hasRun.current = true;
        }
      } catch (firstErr) {
        // Connection failure — likely stale descriptor.  Re-read once and retry.
        await loadDescriptor(setDescriptor);

        // Wait one microtask tick for derived atoms to settle.
        await new Promise((r) => setTimeout(r, 0));

        // If the re-read gave us a new connection, retry the fetch.
        // (We use the atom values directly — they may have updated.)
        try {
          const narration = await attemptFetch();
          if (!cancelled) {
            setResult(narration);
            hasRun.current = true;
            return;
          }
        } catch (_secondErr) {
          // Still failing — show error with retry button.
        }

        if (!cancelled) {
          setError(
            firstErr instanceof Error
              ? firstErr.message
              : String(firstErr),
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    run();
    return () => { cancelled = true; };
  }, [baseUrl, token, setResult, setLoading, setError, setDescriptor]);

  return (
    <Container size="md" py="xl">
      <Stack gap="lg">
        <Group justify="space-between">
          <Title order={1}>
            <IconBrain size={32} style={{ verticalAlign: "middle", marginRight: 10 }} />
            CHESS COACH
          </Title>
          {error && (
            <Button
              variant="light"
              leftSection={<IconRefresh size={16} />}
              onClick={handleRetry}
            >
              Retry
            </Button>
          )}
        </Group>

        <ConnectionStatus />

        {loading && (
          <Box py="xl" style={{ textAlign: "center" }}>
            <Loader size="lg" />
            <Text mt="md" c="dimmed">
              Analysing position…
            </Text>
          </Box>
        )}

        {error && !loading && (
          <Alert
            color="red"
            title="Analysis error"
            icon={<IconRefresh size={16} />}
          >
            <Stack gap="sm">
              <Text>{error}</Text>
              <Text size="sm" c="dimmed">
                The backend may have restarted on a different port. Click Retry
                to re-discover the backend and try again.
              </Text>
            </Stack>
          </Alert>
        )}

        {result && !loading && <NarrationResultView result={result} />}

        {!baseUrl && !loading && !error && (
          <Card withBorder py="xl">
            <Stack align="center" gap="md">
              <IconBrain size={48} opacity={0.3} />
              <Text c="dimmed" ta="center" maw={400}>
                Start the CHESS COACH backend to see coaching analysis for
                any chess position. The grounded narration pipeline uses
                Stockfish evaluation with fact-checking to prevent
                hallucinations.
              </Text>
            </Stack>
          </Card>
        )}
      </Stack>
    </Container>
  );
}
