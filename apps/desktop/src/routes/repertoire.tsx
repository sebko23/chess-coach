import { createFileRoute } from "@tanstack/react-router";
import RepertoirePage from "@/components/panels/repertoire/RepertoirePage";

export const Route = createFileRoute("/repertoire")({ component: RepertoirePage });
