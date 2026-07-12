import { describe, expect, test } from "vitest";
import { Provider, createStore } from "jotai";
import { createElement, type ComponentType } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MantineProvider, createTheme } from "@mantine/core";
import ProfileDashboard from "./ProfileDashboard";
import { backendDescriptorAtom } from "@/state/atoms/coach";

// Sprint-2 acceptance: the new Tilt Over Time card renders the empty-state
// alert when no history data is present. The card must not crash, must not
// render an empty LineChart, and must show the explicit "no tilt history
// data yet" message — which is the user-facing signal that the backend
// endpoint is missing.
//
// Same SSR pattern as CoachPanel.test.tsx (sprint-1): no @testing-library
// dependency added. Wrap in Jotai Provider AND MantineProvider; Mantine 8
// throws if its provider is missing.
//
// ProfileDashboard has an early return (`if (!baseUrl) return <Alert />`)
// that hides the entire dashboard if `backendBaseUrlAtom` is null. We
// pre-create a Jotai store with the atoms set to stub values, then pass
// that store to the Provider, so the component renders the dashboard body
// (including the new Tilt card) instead of the "Backend not connected"
// alert. The stub URL is never called — the data-fetching useEffects run,
// hit the unreachable URL, and fail; setHistory([]) is the initial state,
// which is what the tests assert against.

const theme = createTheme({});

const STUB_BASE_URL = "http://127.0.0.1:0";
const STUB_TOKEN = "test-token";

function makeStore() {
  const store = createStore();
  // Set the writable primitive `backendDescriptorAtom`. The derived atoms
  // (`backendBaseUrlAtom`, `backendTokenAtom`) are computed from this and
  // will resolve to the stub values when the component reads them.
  store.set(backendDescriptorAtom, {
    backend_version: "0.1.0",
    host: "127.0.0.1",
    port: 0,
    protocol_version: "1.0.0",
    session_token: STUB_TOKEN,
  });
  return store;
}

function renderWithProvider(node: ReturnType<typeof createElement>): string {
  return renderToStaticMarkup(
    createElement(
      Provider,
      { store: makeStore() },
      createElement(MantineProvider, { theme }, node),
    ),
  );
}

describe("ProfileDashboard Tilt Over Time card (sprint-2)", () => {
  test("renders the empty-state alert when no history data is present", () => {
    const html = renderWithProvider(createElement(ProfileDashboard as ComponentType));

    // The empty-state alert has the title "No tilt history data yet".
    // We assert on the title text (not a generic substring) so that a
    // future change to the explanatory body text doesn't break the test.
    expect(html).toContain("No tilt history data yet");
  });

  test("renders the card header regardless of data state", () => {
    const html = renderWithProvider(createElement(ProfileDashboard as ComponentType));

    // The card title is "Tilt Over Time" — verifies the card itself is in
    // the DOM, not just the empty-state alert.
    expect(html).toContain("Tilt Over Time");
  });

  test("renders the page-level Profile header (sanity check on the test render)", () => {
    const html = renderWithProvider(createElement(ProfileDashboard as ComponentType));

    // The page-level <Title order={2}>Profile</Title> header must be
    // present, confirming the component rendered the dashboard layout
    // (not just a fragment or the empty state in isolation).
    expect(html).toMatch(/<h2[^>]*>[\s\S]*?Profile[\s\S]*?<\/h2>/);
  });
});
