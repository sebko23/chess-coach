/**
 * Jotai atoms for CHESS COACH backend connection state.
 *
 * Reads ``backend.json`` written by the Python gateway at startup.
 * Falls back gracefully when no backend is running.
 */
import { atom } from "jotai";
import {
  resolve,
  homeDir,
} from "@tauri-apps/api/path";
import { readTextFile } from "@tauri-apps/plugin-fs";

/** Shape of backend.json */
export interface BackendDescriptor {
  backend_version: string;
  host: string;
  port: number;
  protocol_version: string;
  session_token: string;
  started_at?: string;
}

/** Shape of the narration API response */
export interface NarrationResult {
  fen: string;
  narration: string;
  depth_reached: number;
  best_move: string;
  score_display: string;
  pv_moves: string[];
}

/** One blunder/mistake/inaccuracy record from the backend. */
export interface BlunderItem {
  ply: number;
  move_san: string;
  best_move: string;
  score_cp_white: number;
  cp_delta: number;
  classification: string;
}

/** Shape of the blunder-by-fen API response. */
export interface BlunderByFenResult {
  game_id: string;
  fen: string;
  current_ply: number;
  blunders: BlunderItem[];
  position_classification: BlunderItem | null;
}

/** Mantine Badge color per classification. */
export const BLUNDER_COLORS: Record<string, string> = {
  blunder: "red",
  mistake: "orange",
  inaccuracy: "yellow",
};

/**
 * Resolved path to the backend descriptor file.
 * The gateway writes this to ``~/.local/share/chess-coach/runtime/backend.json``.
 */
export const backendDescriptorPathAtom = atom(async () => {
  const home = await homeDir();
  return await resolve(home, ".local", "share", "chess-coach", "runtime", "backend.json");
});

/**
 * Parsed BackendDescriptor, or null when the backend is not reachable.
 */
export const backendDescriptorAtom = atom<BackendDescriptor | null>(null);

/**
 * Re-read the backend descriptor file and update the atom.
 *
 * Idempotent — safe to call at any time.  Never throws.
 * Returns true if the descriptor changed compared to the atom's current value.
 */
export async function loadDescriptor(
  setAtom: (value: BackendDescriptor | null) => void,
): Promise<void> {
  try {
    const home = await homeDir();
    const path = await resolve(home, ".local", "share", "chess-coach", "runtime", "backend.json");
    const raw = await readTextFile(path);
    const descriptor: BackendDescriptor = JSON.parse(raw);
    setAtom(descriptor);
  } catch {
    setAtom(null);
  }
}

// ── onMount: read once at startup ──
backendDescriptorAtom.onMount = (setAtom) => {
  loadDescriptor(setAtom);
};

/**
 * Full base URL for the backend API, e.g. ``http://127.0.0.1:41781``.
 */
/**
 * Resolve a descriptor host to a routable address.
 *
 * ``0.0.0.0`` is a bind wildcard (listen on all interfaces), not a
 * destination that can be connected to.  Normalize it to ``127.0.0.1``
 * for same-machine Docker port-proxy connections.
 *
 * This is defensive-programming guard; the gateway should already
 * announce ``127.0.0.1`` in the descriptor.  The normalization here
 * catches any future config drift or descriptors written by older
 * gateway versions.
 */
function resolveHost(host: string): string {
  return host === "0.0.0.0" ? "127.0.0.1" : host;
}

export const backendBaseUrlAtom = atom<string | null>((get) => {
  const d = get(backendDescriptorAtom);
  if (!d) return null;
  return `http://${resolveHost(d.host)}:${d.port}`;
});

/** Bearer token extracted from the descriptor. */
export const backendTokenAtom = atom<string | null>((get) => {
  return get(backendDescriptorAtom)?.session_token ?? null;
});

/** Whether the backend connection has been attempted. */
export const backendCheckedAtom = atom<boolean>(false);

/**
 * Atom that triggers a backend connection check on first read.
 * Derived atoms depend on ``backendDescriptorAtom``; reading any of
 * them will cause the descriptor to be loaded.
 */
export const ensureBackendCheckedAtom = atom<boolean>((get) => {
  const checked = get(backendCheckedAtom);
  return checked;
});

/** The result of the last narration request, or null. */
export const narrationResultAtom = atom<NarrationResult | null>(null);

/** True while a narration request is in flight. */
export const narrationLoadingAtom = atom<boolean>(false);

/** Error message from last failed narration request, or null. */


/** The last blunder-by-fen result, or null. */
export const blunderResultAtom = atom<BlunderByFenResult | null>(null);

/** True while a blunder fetch is in flight. */
export const blunderLoadingAtom = atom<boolean>(false);

export const narrationErrorAtom = atom<string | null>(null);

// ── Live board FEN (bridged from en-croissant's zustand TreeStore) ──

/**
 * Default FEN — starting position, used when no tab is active.
 */
export const DEFAULT_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

/**
 * Current board FEN from en-croissant's active analysis/play tab.
 *
 * The coach panel lives on route ``/coach``, which is **outside** the
 * ``TreeStateContext`` (React context) that wraps board components.
 * We cannot call ``useStore()`` directly.  Instead we bridge the gap
 * by polling sessionStorage, where the zustand TreeStore persists its
 * full state per tab under the active tab's UUID.
 *
 * ``storage`` events do **not** fire in same-window contexts (Tauri
 * webview is a single window), so polling is genuinely necessary.
 * At 200 ms the read is cheap — sessionStorage is synchronous
 * in-memory and the CPU cost is negligible.
 *
 * See ``apps/desktop/src/state/store/tree.ts`` for the persist config.
 * Schema of the stored value:
 *   ``{"state": {"root": {fen, children: []}, "position": number[]}}``
 *
 * ``position`` is a depth-first child-index path through
 * ``root.children`` — e.g. ``[0, 2, 1]`` means root → child[0] →
 * child[2] → child[1].  Every ``TreeNode`` carries its own ``fen``,
 * so the leaf node at the end of the path gives the cursor's current
 * board state.
 */
export const boardFenAtom = atom<string | null>(null);

boardFenAtom.onMount = (set) => {
  // Re-read backend descriptor every 30s to auto-recover from gateway restarts
  const descriptorInterval = setInterval(() => {
    loadDescriptor(set as Parameters<typeof loadDescriptor>[0]);
  }, 30_000);

  const interval = setInterval(() => {
    try {
      // Read the "tabs" array — en-croissant does NOT persist an activeTab
      // atom to sessionStorage.  Instead it stores an array of tab objects
      // (each with name, value, type) under the "tabs" key.
      const tabsRaw = sessionStorage.getItem("tabs");
      if (!tabsRaw) { set(null); return; }

      const tabs = JSON.parse(tabsRaw);
      if (!Array.isArray(tabs) || tabs.length === 0) { set(null); return; }

      const activeTabId = sessionStorage.getItem("activeTab");
      const activeTab = tabs.find((t: {value: string; type: string}) => t.value === activeTabId)
        ?? tabs.find((t: {value: string; type: string}) => t.type === "analysis")
        ?? null;
      if (!activeTab?.value) { set(null); return; }

      const raw = sessionStorage.getItem(activeTab.value);
      if (!raw) { set(null); return; }

      const parsed = JSON.parse(raw);
      const treeState = parsed?.state;
      if (!treeState) return;

      // Traverse position path through root.children to find leaf FEN.
      const path: number[] = treeState.position ?? [];
      let node = treeState.root;
      for (const idx of path) {
        node = node?.children?.[idx];
        if (!node) break;
      }
      const fen = node?.fen ?? treeState.root?.fen ?? DEFAULT_FEN;
      set(fen);
    } catch {
      // sessionStorage parse errors are transient; leave current value.
    }
  }, 200);
  return () => { clearInterval(interval); clearInterval(descriptorInterval); };
};

