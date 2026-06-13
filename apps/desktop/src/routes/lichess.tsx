import { createFileRoute } from "@tanstack/react-router";
import LichessSyncPage from "@/components/panels/lichess/LichessSyncPage";
export const Route = createFileRoute("/lichess")({ component: LichessSyncPage });
