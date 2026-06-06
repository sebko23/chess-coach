import { createFileRoute } from "@tanstack/react-router";
import GameDetailPage from "@/components/panels/games/GameDetailPage";

export const Route = createFileRoute("/games/$gameId")({
  component: GameDetailPage,
});
