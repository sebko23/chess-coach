/**
 * Jotai atoms for CHESS COACH backend connection state.
 *
 * Reads ``backend.json`` written by the Python gateway at startup.
 * Falls back gracefully when no backend is running.
 */
import { atom } from "jotai";
import { readTextFile, exists } from "@tauri-apps/plugin-fs";
import {
  resolve,
  homeDir,
} from "@tauri-apps/api/path";

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

/**
 * Resolved path to the backend descriptor file.
 * The gateway writes this to ``~/.local/share/chess-coach/runtime/backend.json``.
 */
export const backendDescriptorPathAtom = atom<string>(async () => {
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

    const fileExists = await exists(path);
    if (!fileExists) {
      setAtom(null);
      return;
    }

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
export const narrationErrorAtom = atom<string | null>(null);
