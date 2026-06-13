import { createFileRoute } from "@tanstack/react-router";
import TrainingQueuePage from "@/components/panels/training/TrainingQueuePage";

export const Route = createFileRoute("/training")({ component: TrainingQueuePage });
