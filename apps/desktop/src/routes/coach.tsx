import { createFileRoute } from "@tanstack/react-router";
import CoachPanel from "@/components/panels/coach/CoachPanel";

export const Route = createFileRoute("/coach")({
  component: CoachPanel,
});
