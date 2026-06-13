import { createFileRoute } from "@tanstack/react-router";
import GamesPage from "@/components/panels/games/GamesPage";

export const Route = createFileRoute("/games")({
  component: GamesPage,
});
