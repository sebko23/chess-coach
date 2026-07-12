import { describe, expect, test } from "vitest";
import { Provider } from "jotai";
import { createElement, type ComponentType } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MantineProvider, createTheme } from "@mantine/core";
import CoachPanel from "./CoachPanel";

// Sprint-1 acceptance: the component accepts a `mode` prop and, when set to
// `"rail"`, does NOT render the page-level `<Title order={1}>CHESS COACH</Title>`
// header that the `"full"` mode (default) renders at the top of `/coach`.
//
// We use `react-dom/server.renderToStaticMarkup` because the project does not
// include @testing-library/react and sprint-1 forbids adding dependencies.
// `useEffect` does not run in SSR, which is exactly what we want: we are only
// inspecting the initial render output to verify the prop is accepted and the
// rail layout is in effect.
//
// The component reads several Jotai atoms and uses Mantine components, so we
// wrap it in a Jotai Provider AND a MantineProvider. Mantine 8 throws if its
// provider is missing in the tree (`useMantineTheme` requires it).

const theme = createTheme({});

function renderWithProvider(node: ReturnType<typeof createElement>): string {
  return renderToStaticMarkup(
    createElement(Provider, null, createElement(MantineProvider, { theme }, node)),
  );
}

describe("CoachPanel mode prop (sprint-1 right-rail)", () => {
  test("rail mode omits the page-level h1 header and shows the smaller h4 rail header", () => {
    const html = renderWithProvider(
      createElement(CoachPanel as ComponentType<{ mode?: "full" | "rail" }>, { mode: "rail" }),
    );

    // The full layout's page-level header is `<Title order={1}>CHESS COACH</Title>`
    // which renders as `<h1>...CHESS COACH</h1>`. In rail mode it must be absent.
    // We assert on the structural element (no <h1>) rather than the literal
    // substring "CHESS COACH" because the latter appears in the
    // `ConnectionStatus` "Backend not found" alert's help text in BOTH modes
    // ("Start the CHESS COACH backend:"). The negative assertion must target
    // the h1 element specifically.
    expect(html).not.toMatch(/<h1[^>]*>[\s\S]*?CHESS COACH[\s\S]*?<\/h1>/);

    // The rail header is `<Title order={4}>Coach</Title>` which renders as
    // `<h4 ... data-order="4">...Coach</h4>`. The full layout also contains
    // the word "Coach" in nested card titles, so this is a necessary-but-
    // not-sufficient check; the negative h1 assertion above is authoritative.
    expect(html).toMatch(/<h4[^>]*data-order="4"[^>]*>[\s\S]*?Coach[\s\S]*?<\/h4>/);
  });

  test("default mode (no prop) preserves the full layout with the h1 page-level header", () => {
    const html = renderWithProvider(createElement(CoachPanel, {}));

    // No `mode` prop → defaults to `"full"` per the prop signature, so the
    // page-level h1 header must be present.
    expect(html).toMatch(/<h1[^>]*>[\s\S]*?CHESS COACH[\s\S]*?<\/h1>/);
  });

  test("explicit full mode preserves the full layout with the h1 page-level header", () => {
    const html = renderWithProvider(
      createElement(CoachPanel as ComponentType<{ mode?: "full" | "rail" }>, { mode: "full" }),
    );

    expect(html).toMatch(/<h1[^>]*>[\s\S]*?CHESS COACH[\s\S]*?<\/h1>/);
  });
});
