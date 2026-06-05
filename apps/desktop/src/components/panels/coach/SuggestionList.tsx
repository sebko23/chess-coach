import { Badge, Box, Divider, Group, Stack, Text } from "@mantine/core";

export interface EvalPoint {
  ply: number;
  move_san: string;
  score_cp_white: number;
  best_move: string;
  is_mate: boolean;
}

interface SuggestionListProps {
  points: EvalPoint[];
  currentPly: number;
  onPlyClick?: (ply: number) => void;
  pvMoves?: string[];
  scoreDisplay?: string;
  depthReached?: number;
}

function cpLabel(cp: number, isMate: boolean): string {
  if (isMate) return cp > 0 ? "Mate" : "-Mate";
  const val = Math.abs(cp / 100).toFixed(1);
  return cp >= 0 ? `+${val}` : `-${val}`;
}

function cpColor(cp: number, isMate: boolean): string {
  if (isMate) return cp > 0 ? "teal" : "red";
  if (cp >= 50) return "teal";
  if (cp >= -50) return "yellow";
  return "red";
}

function classifyDelta(prev: number | null, curr: number): string | null {
  if (prev === null) return null;
  const delta = curr - prev;
  if (delta <= -150) return "Blunder";
  if (delta <= -75) return "Mistake";
  if (delta <= -25) return "Inaccuracy";
  return null;
}

export function SuggestionList({
  points,
  currentPly,
  onPlyClick,
  pvMoves,
  scoreDisplay,
  depthReached,
}: SuggestionListProps) {
  const hasPv = pvMoves && pvMoves.length > 0;
  const hasPoints = points && points.length > 0;

  if (!hasPv && !hasPoints) return null;

  const window = hasPoints
    ? points.filter((p) => p.ply >= currentPly - 2 && p.ply <= currentPly + 2)
    : [];

  return (
    <Stack gap={8}>
      {hasPv && (
        <Box>
          <Group gap={6} mb={6} align="center">
            <Text size="xs" fw={500} c="dimmed">Engine line</Text>
            {depthReached && (
              <Badge size="xs" variant="outline" color="gray">
                depth {depthReached}
              </Badge>
            )}
            {scoreDisplay && (
              <Badge size="xs" variant="light" color="teal">
                {scoreDisplay}
              </Badge>
            )}
          </Group>
          <Box
            style={{
              background: "var(--mantine-color-default-hover)",
              borderRadius: 6,
              padding: "6px 10px",
            }}
          >
            <Text size="sm" ff="monospace" style={{ lineHeight: 1.8, wordBreak: "break-word" }}>
              {pvMoves.slice(0, 8).join(" ")}
              {pvMoves.length > 8 && (
                <Text span size="xs" c="dimmed"> +{pvMoves.length - 8} more</Text>
              )}
            </Text>
          </Box>
        </Box>
      )}

      {hasPv && hasPoints && window.length > 0 && (
        <Divider label="game plies" labelPosition="left" />
      )}

      {window.length > 0 && (
        <Stack gap={4}>
          {window.map((point, i) => {
            const prev = i > 0 ? window[i - 1].score_cp_white : null;
            const delta = classifyDelta(prev, point.score_cp_white);
            const isCurrent = point.ply === currentPly;
            return (
              <Box
                key={point.ply}
                onClick={() => onPlyClick?.(point.ply)}
                style={{
                  padding: "6px 10px",
                  borderRadius: 6,
                  background: isCurrent ? "var(--mantine-color-blue-light)" : "transparent",
                  border: isCurrent
                    ? "1px solid var(--mantine-color-blue-light-hover)"
                    : "1px solid transparent",
                  cursor: onPlyClick ? "pointer" : "default",
                  transition: "background 150ms ease",
                }}
              >
                <Group justify="space-between" wrap="nowrap" gap={8}>
                  <Group gap={6} wrap="nowrap">
                    <Text size="xs" c="dimmed" w={24} ta="right">
                      {Math.ceil(point.ply / 2)}{point.ply % 2 === 1 ? "." : "..."}
                    </Text>
                    <Text size="sm" fw={isCurrent ? 600 : 400}>
                      {point.move_san}
                    </Text>
                    {delta && (
                      <Badge
                        size="xs"
                        color={delta === "Blunder" ? "red" : delta === "Mistake" ? "orange" : "yellow"}
                        variant="light"
                      >
                        {delta}
                      </Badge>
                    )}
                  </Group>
                  <Group gap={6} wrap="nowrap">
                    <Text size="xs" c="dimmed" ff="monospace">{point.best_move}</Text>
                    <Badge size="sm" color={cpColor(point.score_cp_white, point.is_mate)} variant="light">
                      {cpLabel(point.score_cp_white, point.is_mate)}
                    </Badge>
                  </Group>
                </Group>
              </Box>
            );
          })}
        </Stack>
      )}
    </Stack>
  );
}