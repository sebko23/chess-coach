import { useContext, useEffect } from "react";
import { useSetAtom } from "jotai";
import { boardFenAtom } from "@/state/atoms/coach";
import { TreeStateContext } from "../common/TreeStateContext";
import { INITIAL_FEN } from "chessops/fen";

/**
 * Real-time bridge that subscribes to the Zustand tree store via
 * TreeStateContext and pushes every position change into boardFenAtom.
 *
 * Mounted inside BoardAnalysis (wrapped with TreeStateProvider).
 * Does NOT mount outside board context — the app-root bridge handles
 * the case when no board tab is open.
 */
export default function BoardFenBridge() {
  const store = useContext(TreeStateContext);
  const setFen = useSetAtom(boardFenAtom);

  useEffect(() => {
    if (!store) return;

    const unsub = store.subscribe((state) => {
      try {
        const path: number[] = state.position ?? [];
        const root = state.root;
        if (!root) return;

        let node = root;
        for (const idx of path) {
          node = node?.children?.[idx];
          if (!node) break;
        }
        const fen = node?.fen ?? root.fen ?? INITIAL_FEN;
        setFen(fen);
        localStorage.setItem("chess_coach_last_fen", fen);
      } catch {
        // transient; leave current FEN
      }
    });

    // Read initial position immediately
    const state = store.getState();
    if (state?.root?.fen) setFen(state.root.fen);

    return () => {
      unsub();
      // Do NOT set null on unmount — the app-root bridge will fill the gap
    };
  }, [store, setFen]);

  return null;
}
