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
import { useCallback, useEffect, useRef, useState } from "react";
import {
  backendBaseUrlAtom,
  backendTokenAtom,
  backendDescriptorAtom,
  narrationResultAtom,
  narrationLoadingAtom,
  narrationErrorAtom,
  boardFenAtom,
  blunderResultAtom,
  blunderLoadingAtom,
  BLUNDER_COLORS,
  DEFAULT_FEN,
  loadDescriptor,
} from "@/state/atoms/coach";
import type { NarrationResult, BlunderByFenResult } from "@/state/atoms/coach";
import EvalGraph from "./EvalGraph";
import { EvalBar } from "./EvalBar";
import { currentGameIdAtom } from "@/state/atoms";
import { SuggestionList, type EvalPoint } from "./SuggestionList";

/**
 * Default FEN â€” used as fallback when no board tab is open.
 * The live board position is read from ``boardFenAtom`` instead.
 */
const FALLBACK_FEN = DEFAULT_FEN;

/**
 * Analysis depth for Stockfish evaluation.
 *
 * Temporary: depth 10 provides ~1-2s engine response for quick feedback
 * during Phase 1 testing.  Phase 2 will replace this with a dual-mode
 * pipeline: quick eval at depth 10 (no LLM) + full narration at depth 14+.
 */
const ANALYSIS_DEPTH = 10;


/**
 * Derive the game phase from the current ply number.
 * Matches the backend's `game_phase` enum in services/chess_coach/gateway/routes/narration.py:
 *   "opening"   -> ply <= 20 (first 10 full moves)
 *   "middlegame" -> ply <= 60 (moves 11..30)
 *   "endgame"    -> ply > 60
 */
function deriveGamePhase(
  ply: number,
): "opening" | "middlegame" | "endgame" {
  if (ply <= 20) return "opening";
  if (ply <= 60) return "middlegame";
  return "endgame";
}

/**
 * Fetch a grounded narration from the backend for the given position.
 *
 * The backend's /v1/narration/explain endpoint accepts only the position
 * context (fen + move_san + eval_cp + game_phase) — it does NOT take engine
 * config (depth/engine_id/multipv). Those fields are silently ignored by
 * the Pydantic model and result in a generic fallback narration. See
 * services/chess_coach/gateway/routes/narration.py for the contract.
 */
async function fetchNarration(
  baseUrl: string,
  token: string,
  fen: string,
  moveSan: string | null,
  evalCp: number | null,
  gamePhase: "opening" | "middlegame" | "endgame" | null,
): Promise<NarrationResult> {
  const resp = await fetch(`${baseUrl}/v1/narration/explain`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
    },
    body: JSON.stringify({
      fen,
      move_san: moveSan,
      eval_cp: evalCp,
      game_phase: gamePhase,
    }),
  });

  if (!resp.ok) {
    const errBody = await resp.text();
    throw new Error(`Backend returned ${resp.status}: ${errBody}`);
  }

  // Narration endpoint returns NarrationResponse directly (no {data:{...}} envelope).
  return (await resp.json()) as NarrationResult;
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
        v{descriptor.backend_version} on {baseUrl} â€” protocol{" "}
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
  moves: string[] | undefined;
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
        {(moves ?? []).slice(0, 8).join(" ")}
      </Text>
    </Group>
  );
}
/** Strip citation tags from narration text for clean display. */
function renderNarration(text: string | undefined): string {
  if (!text) return "";
  return text
    .replace(/<move>([^<]+)<\/move>/g, '$1')
    .replace(/<eval>([^<]+)<\/eval>/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1');
}

function parseScoreDisplay(s: string): { cp: number; isMate: boolean } {
  if (!s) return { cp: 0, isMate: false };
  const mate = s.match(/mate in (-?\d+)/i) ?? s.match(/[Mm](-?\d+)/);
  if (mate) return { cp: parseInt(mate[1]) > 0 ? 400 : -400, isMate: true };
  const num = parseFloat(s.replace("+", ""));
  return { cp: isNaN(num) ? 0 : Math.round(num * 100), isMate: false };
}

function NarrationResultView({ result, evalPoints, currentPly, onPlyClick }: { result: NarrationResult; evalPoints: EvalPoint[]; currentPly: number; onPlyClick: (ply: number) => void }) {
  const blunderResult = useAtomValue(blunderResultAtom);
  return (
    <Stack gap="md">
      <Card withBorder>
        <Group justify="space-between" mb="sm">
          <Title order={3}>
            <IconBrain size={24} style={{ verticalAlign: "middle", marginRight: 8 }} />
            Coach Analysis
          </Title>
          <Badge variant="outline">depth {result.depth_reached}</Badge>
          {blunderResult?.position_classification && (
            <Badge
              size="lg"
              color={BLUNDER_COLORS[blunderResult.position_classification.classification ?? ""] || "gray"}
              variant="filled"
            >
              {blunderResult.position_classification.classification}
            </Badge>
          )}
        </Group>

        <Text size="md" style={{ lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
          {renderNarration(result.narration)}
        </Text>
      </Card>

      {result.pv_moves && result.pv_moves.length > 0 && (
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
      )}


      {blunderResult && blunderResult?.blunders?.length > 0 && (
        <Card withBorder>
          <Title order={4} mb="sm">
            Game Blunders
          </Title>
          <Box style={{ maxHeight: 300, overflowY: "auto" }}>
            {blunderResult.blunders.map((b) => (
              <Group key={b.ply} gap="xs" mb="xs" wrap="nowrap">
                <Badge
                  size="sm"
                  color={BLUNDER_COLORS[b.classification] || "gray"}
                >
                  {b.classification}
                </Badge>
                <Text size="sm" ff="monospace">
                  {b.move_san}
                </Text>
                <Text size="xs" c="dimmed">
                  ({b.cp_delta >= 0 ? "+" : ""}{b.cp_delta}cp)
                </Text>
                <Text size="xs" fw={700}>
                  â†’ {b.best_move}
                </Text>
              </Group>
            ))}
          </Box>
        </Card>
      )}

      {(() => {
        const score = parseScoreDisplay(result?.score_display ?? "");
        return (
          <Group gap="md" align="flex-start" wrap="nowrap">
            <EvalBar scoreCpWhite={score.cp} isMate={score.isMate} height={320} />
            <Box style={{ flex: 1 }}>
              <SuggestionList
                points={evalPoints}
                currentPly={currentPly}
                onPlyClick={(ply) => onPlyClick(ply)}
                pvMoves={result.pv_moves}
                scoreDisplay={result.score_display}
                depthReached={result.depth_reached}
              />
            </Box>
          </Group>
        );
      })()}
      <EvalGraph />

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
  const [evalPoints, setEvalPoints] = useState<EvalPoint[]>([]);
  const [currentPly, setCurrentPly] = useState(0);
  const gameId = useAtomValue(currentGameIdAtom);
  const [result, setResult] = useAtom(narrationResultAtom);
  const [loading, setLoading] = useAtom(narrationLoadingAtom);
  const [error, setError] = useAtom(narrationErrorAtom);
  const [blunderResult, setBlunderResult] = useAtom(blunderResultAtom);
  const [blunderLoading, setBlunderLoading] = useAtom(blunderLoadingAtom);
  const setDescriptor = useSetAtom(backendDescriptorAtom);
  const liveFen = useAtomValue(boardFenAtom);  // null = no board tab yet
  // Game ID from first training card or current board game
  const [evalGraphGameId, setEvalGraphGameId] = useState<string | null>(null);

  // Debounce the live FEN so analysis only triggers after a pause.
  // Without this, fast move browsing fires 10+ sequential analysis requests.
  const [debouncedFen, setDebouncedFen] = useState<string | null>(null);
  const lastAnalyzedFen = useRef<string | null>(null);

  useEffect(() => {
    // Skip analysis until the sessionStorage bridge has read the live FEN.
    // Otherwise we analyze the starting position before the board is ready.
    if (liveFen === null) return;
    const timer = setTimeout(() => setDebouncedFen(liveFen), 800);
    return () => clearTimeout(timer);
  }, [liveFen]);

  /** Re-read the backend descriptor and re-trigger analysis. */
  const handleRetry = useCallback(async () => {
    // Re-read the descriptor; the derived atoms (baseUrl, token) will
    // update, and the useEffect below will fire the analysis if needed.
    await loadDescriptor(setDescriptor);
    // Clear the error so the UI shows a fresh state.
    setError(null);
    setResult(null);
    // Reset the analyzed-FEN cache so the next debounce fires analysis.
    lastAnalyzedFen.current = null;
  }, [setDescriptor, setError, setResult]);


  // Watch for tab switches by polling sessionStorage.
  // When the active tab changes, reset the analyzed-FEN cache so the
  // next FEN variation triggers re-analysis regardless of identical FEN.
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  useEffect(() => {
    const interval = setInterval(() => {
      const id = sessionStorage.getItem("activeTab");
      setActiveTabId(prev => {
        if (prev !== id) {
          // Tab switched â€” reset cache so next FEN triggers re-analysis
          lastAnalyzedFen.current = null;
        }
        return id;
      });
    }, 200);
    return () => clearInterval(interval);
  }, []);


  // Fetch blunder-by-fen result when FEN stabilises.
  useEffect(() => {
    if (!baseUrl || !token || !debouncedFen) return;

    let cancelled = false;
    const fetchBlunders = async () => {
      setBlunderLoading(true);
      try {
        const resp = await fetch(
          `${baseUrl}/v1/blunders/by-fen?fen=${encodeURIComponent(debouncedFen)}`,
          { headers: { Authorization: `Bearer ${token}` } as HeadersInit },
        );
        if (!cancelled) {
          if (resp.ok) {
            setBlunderResult(await resp.json() as BlunderByFenResult);
          } else {
            setBlunderResult(null);
          }
        }
      } catch {
        if (!cancelled) setBlunderResult(null);
      } finally {
        if (!cancelled) setBlunderLoading(false);
      }
    };
    fetchBlunders();
    return () => { cancelled = true; };
  }, [baseUrl, token, debouncedFen]);
  
  // Fetch eval-graph points when we have a game ID
  useEffect(() => {
    if (!baseUrl || !token || !gameId) return;
    let cancelled = false;
    const fetchEval = async () => {
      try {
        const resp = await fetch(
          `${baseUrl}/v1/games/${gameId}/eval-graph?limit=100`,
          { headers: { Authorization: `Bearer ${token}` } as HeadersInit },
        );
        if (!cancelled && resp.ok) {
          const data = await resp.json();
          setEvalPoints(data.points || []);
          // Set current ply from the game data if available
          if (data.points && data.points.length > 0) {
            setCurrentPly(data.points[data.points.length - 1]?.ply ?? 0);
          }
        }
      } catch {
        if (!cancelled) setEvalPoints([]);
      }
    };
    fetchEval();
    return () => { cancelled = true; };
  }, [baseUrl, token, gameId]);
  // Analyse the current board position when the FEN changes.
  // debouncedFen in deps ensures re-analysis on position change.
  useEffect(() => {
    if (!baseUrl || !token) {
      // Backend not available â€” don't attempt yet.
      return;
    }

    // Skip if we already analyzed this exact FEN.
    if (lastAnalyzedFen.current === debouncedFen) return;
    lastAnalyzedFen.current = debouncedFen;

    let cancelled = false;

    const run = async () => {
      setLoading(true);
      setError(null);
      setResult(null);

      const attemptFetch = async () => {
        // Build grounded context from currently loaded eval-graph points.
        // evalPoints / currentPly are in scope from the parent component;
        // either may be absent if the eval fetch is still in flight, in
        // which case we send nulls and the backend falls back to a generic
        // narration for the FEN alone.
        const pointAtPly = evalPoints.find((p) => p.ply === currentPly);
        const moveSan = pointAtPly?.move_san ?? null;
        const evalCp = pointAtPly ? pointAtPly.score_cp_white : null;
        const gamePhase = currentPly > 0 ? deriveGamePhase(currentPly) : null;
        return fetchNarration(
          baseUrl,
          token,
          debouncedFen!,
          moveSan,
          evalCp,
          gamePhase,
        );
      };
      try {
        // First attempt
        const narration = await attemptFetch();
        if (!cancelled) {
          setResult(narration);

        }
      } catch (firstErr) {
        // Connection failure â€” likely stale descriptor.  Re-read once and retry.
        await loadDescriptor(setDescriptor);

        // Wait one microtask tick for derived atoms to settle.
        await new Promise((r) => setTimeout(r, 0));

        // If the re-read gave us a new connection, retry the fetch.
        // (We use the atom values directly â€” they may have updated.)
        try {
          const narration = await attemptFetch();
          if (!cancelled) {
            setResult(narration);
  
            return;
          }
        } catch (_secondErr) {
          // Still failing â€” show error with retry button.
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
  }, [baseUrl, token, debouncedFen, setDescriptor]);

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
              Analysing positionâ€¦
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

        {result && !loading && <NarrationResultView result={result} evalPoints={evalPoints} currentPly={currentPly} onPlyClick={setCurrentPly} />}

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
