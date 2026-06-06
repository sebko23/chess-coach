"use no memo";

import {
  Alert,
  Badge,
  Box,
  Button,
  Group,
  Loader,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { IconAlertCircle, IconDatabase, IconUpload } from "@tabler/icons-react";
import { useNavigate } from "@tanstack/react-router";
import { useAtomValue, useAtom, useSetAtom } from "jotai";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  backendBaseUrlAtom,
  backendTokenAtom,
} from "@/state/atoms/coach";
import { activeTabAtom, tabsAtom } from "@/state/atoms";
import { createTab } from "@/utils/tabs";
import type { FC } from "react";

interface GameSummary {
  game_id: string;
  white: string | null;
  black: string | null;
  result: string | null;
  date: string | null;
  event: string | null;
  import_status: string;
  position_count: number;
  created_at: string;
}

interface GamesListResponse {
  games: GameSummary[];
  total: number;
  limit: number;
  offset: number;
}

const GamesPage: FC = () => {
  const baseUrl = useAtomValue(backendBaseUrlAtom);
  const token = useAtomValue(backendTokenAtom);
  const [, setTabs] = useAtom(tabsAtom);
  const setActiveTab = useSetAtom(activeTabAtom);
  const navigate = useNavigate();
  const [games, setGames] = useState<GameSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importSuccess, setImportSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchGames = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${baseUrl}/v1/games?limit=50&offset=0`, { headers });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      const data: GamesListResponse = await res.json();
      setGames(data.games);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [baseUrl, token]);

  const handleOpenGame = async (g: GameSummary) => {
    if (!baseUrl || !token) return;
    try {
      const resp = await fetch(`${baseUrl}/v1/games/${g.game_id}/pgn`, {
        headers: { "Authorization": `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const pgn: string = data.pgn;

      await createTab({
        tab: {
          name: `${g.white ?? "?"} - ${g.black ?? "?"}`,
          type: "analysis",
        },
        setTabs,
        setActiveTab,
        pgn,
      });

      navigate({ to: "/games/$gameId", params: { gameId: g.game_id } });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to open game");
    }
  };

  const handleImport = async (file: File | null) => {
    if (!file || !baseUrl || !token) return;

    setImporting(true);
    setImportError(null);
    setImportSuccess(null);

    try {
      const pgn = await file.text();

      const resp = await fetch(`${baseUrl}/v1/import/pgn-database`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          pgn,
          depth: 8,
          max_games: 500,
        }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err?.detail ?? err?.error?.message ?? `HTTP ${resp.status}`);
      }

      const result = await resp.json();
      const count = result?.imported_count ?? result?.games_imported ?? 0;
      setImportSuccess(`Imported ${count} game${count !== 1 ? "s" : ""}`);

      await fetchGames();

    } catch (e) {
      setImportError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  useEffect(() => {
    fetchGames();
  }, [fetchGames]);

  // --- Loading state ---
  if (loading) {
    return (
      <Stack align="center" p="xl">
        <Loader />
        <Text c="dimmed" size="sm">Loading imported games…</Text>
      </Stack>
    );
  }

  // --- Error state ---
  if (error) {
    return (
      <Box p="md">
        <Alert icon={<IconAlertCircle size={16} />} title="Failed to load games" color="red">
          <Text size="sm">{error}</Text>
        </Alert>
      </Box>
    );
  }

  // --- Empty state ---
  if (games.length === 0) {
    return (
      <Stack align="center" p="xl" gap="xs">
        <IconDatabase size={48} opacity={0.3} />
        <Text size="lg" fw={500} c="dimmed">No games imported yet</Text>
        <Text size="sm" c="dimmed" mb="sm">Import a PGN to see your games here.</Text>
        <input
          type="file"
          accept=".pgn"
          hidden
          ref={fileInputRef}
          onChange={(e) => handleImport(e.target.files?.[0] ?? null)}
        />
        <Button
          leftSection={<IconUpload size={16} />}
          onClick={() => fileInputRef.current?.click()}
          loading={importing}
        >
          Import PGN
        </Button>
        {importSuccess && <Text size="sm" c="green" mt="xs">{importSuccess}</Text>}
        {importError && <Text size="sm" c="red" mt="xs">{importError}</Text>}
      </Stack>
    );
  }

  // --- Populated state ---
  return (
    <Box p="md">
      <Group justify="apart" mb="md">
        <Box>
          <Title order={3}>Imported Games</Title>
          <Text size="sm" c="dimmed">{total} game{total !== 1 ? "s" : ""} total</Text>
        </Box>
        <input
          type="file"
          accept=".pgn"
          hidden
          ref={fileInputRef}
          onChange={(e) => handleImport(e.target.files?.[0] ?? null)}
        />
        <Button
          leftSection={<IconUpload size={16} />}
          onClick={() => fileInputRef.current?.click()}
          loading={importing}
          size="sm"
        >
          Import PGN
        </Button>
      </Group>
      {importSuccess && (
        <Alert icon={<IconAlertCircle size={16} />} color="green" mb="md" withCloseButton onClose={() => setImportSuccess(null)}>
          <Text size="sm">{importSuccess}</Text>
        </Alert>
      )}
      {importError && (
        <Alert icon={<IconAlertCircle size={16} />} color="red" mb="md" withCloseButton onClose={() => setImportError(null)}>
          <Text size="sm">{importError}</Text>
        </Alert>
      )}

      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>White</Table.Th>
            <Table.Th>Black</Table.Th>
            <Table.Th>Result</Table.Th>
            <Table.Th>Date</Table.Th>
            <Table.Th>Positions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {games.map((g) => (
            <Table.Tr
              key={g.game_id}
              style={{ cursor: "pointer" }}
              onClick={() => handleOpenGame(g)}
            >
              <Table.Td>{g.white ?? "—"}</Table.Td>
              <Table.Td>{g.black ?? "—"}</Table.Td>
              <Table.Td>
                <Badge color={
                  g.result === "1-0" ? "green" :
                  g.result === "0-1" ? "red" :
                  g.result === "½-½" ? "yellow" : "gray"
                } variant="light">
                  {g.result ?? "—"}
                </Badge>
              </Table.Td>
              <Table.Td>{g.date ?? "—"}</Table.Td>
              <Table.Td>{g.position_count}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Box>
  );
};

export default GamesPage;
