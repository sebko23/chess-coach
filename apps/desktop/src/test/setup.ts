// Vitest setup file — runs before each test file in this project.
//
// Polyfill window.matchMedia, which jsdom doesn't implement by default.
// Mantine's color-scheme provider calls
//   window.matchMedia("(prefers-color-scheme: dark)")?.matches
// during its initial render to determine whether to apply dark mode.
// Without this polyfill, every test that renders a Mantine component
// throws "TypeError: window.matchMedia is not a function".
//
// The polyfill returns false for the dark-preference match, matching
// the default Mantine "light" color scheme. Tests that need to assert
// dark-mode rendering can override this by setting the global state
// before rendering.
//
// FU-16 (2026-08-10): added because @testing-library/react's render()
// runs effects synchronously, which Mantine's color-scheme provider
// relies on window.matchMedia for. The prior renderToStaticMarkup
// test harness avoided this because SSR doesn't run effects.

if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
    Object.defineProperty(window, "matchMedia", {
        writable: true,
        configurable: true,
        value: (query: string) => ({
            matches: false,
            media: query,
            onchange: null,
            addEventListener: () => {},
            removeEventListener: () => {},
            addListener: () => {},
            removeListener: () => {},
            dispatchEvent: () => false,
        }),
    });
}
