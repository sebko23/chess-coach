import { Box, Text, Tooltip } from "@mantine/core";

interface EvalBarProps {
  scoreCpWhite: number;
  isMate?: boolean;
  height?: number;
}

function cpToPercent(cp: number): number {
  const clamped = Math.max(-400, Math.min(400, cp));
  return 50 + (clamped / 400) * 50;
}

function formatScore(cp: number, isMate: boolean): string {
  if (isMate) return cp > 0 ? "M" : "-M";
  const pawns = Math.abs(cp / 100).toFixed(1);
  return cp >= 0 ? `+${pawns}` : `-${pawns}`;
}

export function EvalBar({ scoreCpWhite, isMate = false, height = 320 }: EvalBarProps) {
  const whitePct = isMate
    ? scoreCpWhite > 0 ? 100 : 0
    : cpToPercent(scoreCpWhite);
  const blackPct = 100 - whitePct;
  const label = formatScore(scoreCpWhite, isMate);
  const labelOnTop = scoreCpWhite < 0;

  return (
    <Tooltip label={`${label} (centipawns: ${scoreCpWhite})`} position="right">
      <Box
        style={{
          width: 24,
          height,
          borderRadius: 4,
          overflow: "hidden",
          border: "1px solid var(--mantine-color-default-border)",
          display: "flex",
          flexDirection: "column",
          cursor: "default",
          flexShrink: 0,
        }}
      >
        <Box
          style={{
            height: `${blackPct}%`,
            background: "#1a1a1a",
            transition: "height 400ms ease",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "center",
            paddingTop: 2,
          }}
        >
          {labelOnTop && (
            <Text size="9px" fw={700} c="gray.3" style={{ lineHeight: 1 }}>
              {label}
            </Text>
          )}
        </Box>
        <Box
          style={{
            height: `${whitePct}%`,
            background: "#f0f0f0",
            transition: "height 400ms ease",
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "center",
            paddingBottom: 2,
          }}
        >
          {!labelOnTop && (
            <Text size="9px" fw={700} c="dark.7" style={{ lineHeight: 1 }}>
              {label}
            </Text>
          )}
        </Box>
      </Box>
    </Tooltip>
  );
}
