import { createFileRoute } from "@tanstack/react-router";
import ProfileDashboard from "@/components/panels/profile/ProfileDashboard";

export const Route = createFileRoute("/profile")({ component: ProfileDashboard });
