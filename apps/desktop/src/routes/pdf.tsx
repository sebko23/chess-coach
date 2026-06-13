import { createFileRoute } from "@tanstack/react-router";
import PdfIngestPage from "@/components/panels/pdf/PdfIngestPage";

export const Route = createFileRoute("/pdf")({ component: PdfIngestPage });
