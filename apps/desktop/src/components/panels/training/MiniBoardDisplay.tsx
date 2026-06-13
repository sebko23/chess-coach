import { Chessground } from "@/chessground/Chessground";
import { Box } from "@mantine/core";

interface MiniBoardDisplayProps {
  fen: string;
  size?: number;
  orientation?: "white" | "black";
}

export function MiniBoardDisplay({
  fen,
  size = 180,
  orientation = "white",
}: MiniBoardDisplayProps) {
  return (
    <Box style={{ width: size, height: size, flexShrink: 0 }}>
      <Chessground
        fen={fen}
        orientation={orientation}
        viewOnly={true}
        coordinates={false}
        animation={{ enabled: false }}
        drawable={{ enabled: false, visible: false }}
        movable={{ free: false, color: undefined }}
        draggable={{ enabled: false }}
        selectable={{ enabled: false }}
      />
    </Box>
  );
}
