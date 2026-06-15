import { createFileRoute } from "@tanstack/react-router";
import PracticePanel from "@/components/panels/practice/PracticePanel";

export const Route = createFileRoute("/practice")({
  component: PracticePanel,
});
