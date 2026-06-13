// SPDX-License-Identifier: GPL-3.0-only
// CHESS COACH addition — typed API client wrapper.

import createClient from "openapi-fetch";
import type { paths } from "./api";

export function coachClient(baseUrl: string, token: string | null) {
  return createClient<paths>({
    baseUrl,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

export type CoachClient = ReturnType<typeof coachClient>;
