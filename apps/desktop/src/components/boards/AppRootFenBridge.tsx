import { useEffect } from "react";
import { useSetAtom } from "jotai";
import { boardFenAtom } from "@/state/atoms/coach";
import { INITIAL_FEN } from "chessops/fen";

const STORAGE_KEY = "chess_coach_last_fen";

/**
 * App-root bridge that reads FEN from localStorage on mount
 * and polls every 500ms to stay in sync with BoardFenBridge.
 *
 * BoardFenBridge (inside BoardAnalysis) writes the live position
 * to localStorage on every tree store change. This bridge re-reads
 * it even after route changes, keeping boardFenAtom up to date.
 *
 * Falls back to INITIAL_FEN if no FEN has been stored yet.
 */
export default function AppRootFenBridge() {
  const setFen = useSetAtom(boardFenAtom);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) setFen(stored);

    const interval = setInterval(() => {
      const latest = localStorage.getItem(STORAGE_KEY);
      if (latest) setFen(latest);
    }, 500);

    return () => clearInterval(interval);
  }, [setFen]);

  return null;
}
