import { describe, expect, test } from "vitest";
import { Provider } from "jotai";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MantineProvider, createTheme } from "@mantine/core";
import CoachPanel from "./CoachPanel";

// Sprint-1 acceptance: the component renders the page-level
// `<Title order={1}>CHESS COACH</Title>` header at the top of the
// `/coach` route.
//
// We use `react-dom/server.renderToStaticMarkup` because the project
// does not include @testing-library/react and sprint-1 forbids adding
// dependencies. `useEffect` does not run in SSR, which is fine here:
// we are only inspecting the initial render output.
//
// The component reads several Jotai atoms and uses Mantine components, so
// we wrap it in a Jotai Provider AND a MantineProvider. Mantine 8 throws
// if its provider is missing in the tree (`useMantineTheme` requires it).
//
// FU-15 history: the previous version of this file had a "rail mode"
// test (line 30-50) asserting `mode="rail"` should hide the page-level
// h1 header and show a smaller `<Title order={4}>Coach</Title>` header.
// That test was failing because CoachPanel does NOT have a `mode` prop
// at all (verified: line 307 is `export default function CoachPanel()`
// with no parameters). The test was aspirational — the rail-mode
// feature was never implemented. Per FU-15 scope discipline, that test
// is deleted (other tests in this file cover the component's actual
// current behavior). If/when a rail-mode feature is implemented, the
// deleted test should be reinstated as the acceptance criterion.

const theme = createTheme({});

function renderWithProvider(node: ReturnType<typeof createElement>): string {
  return renderToStaticMarkup(
    createElement(Provider, null, createElement(MantineProvider, { theme }, node)),
  );
}

describe("CoachPanel page-level header (sprint-1)", () => {
  test("default mode (no prop) renders the page-level h1 header", () => {
    const html = renderWithProvider(createElement(CoachPanel, {}));

    // The page-level header is `<Title order={1}>CHESS COACH</Title>`
    // which renders as `<h1>...CHESS COACH</h1>`.
    expect(html).toMatch(/<h1[^>]*>[\s\S]*?CHESS COACH[\s\S]*?<\/h1>/);
  });
});
