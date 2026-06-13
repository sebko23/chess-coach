import { useState, useCallback } from "react";
import {
  Container,
  Title,
  TextInput,
  NumberInput,
  Select,
  Switch,
  Button,
  Paper,
  Text,
  Table,
  Badge,
  Group,
  Stack,
  Alert,
  Loader,
  Progress,
} from "@mantine/core";
import { useAtomValue } from "jotai";
import {
  backendBaseUrlAtom,
  backendTokenAtom,
} from "@/state/atoms/coach";

interface ImportResult {
  username: string;
  games_fetched: number;
  imported_count: number;
  errors: string[];
}

export default function LichessSyncPage() {
  const baseUrl = useAtomValue(backendBaseUrlAtom);
  const token = useAtomValue(backendTokenAtom);

  const [username, setUsername] = useState("");
  const [maxGames, setMaxGames] = useState(50);
  const [perfType, setPerfType] = useState<string | null>(null);
  const [rated, setRated] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  const handleImport = useCallback(async () => {
    if (!baseUrl || !username.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);
    setProgress(20);

    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      setProgress(40);
      const body: Record<string, unknown> = {
        username: username.trim(),
        max_games: maxGames,
      };
      if (perfType) body.perf_type = perfType;
      if (rated !== null) body.rated = rated;

      const res = await fetch(`${baseUrl}/v1/import/lichess`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });

      setProgress(80);

      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`HTTP ${res.status}: ${detail}`);
      }

      const data: ImportResult = await res.json();
      setResult(data);
      setProgress(100);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setLoading(false);
    }
  }, [baseUrl, token, username, maxGames, perfType, rated]);

  return (
    <Container size="md" py="md">
      <Title order={2} mb="lg">
        Lichess Import
      </Title>

      <Paper shadow="xs" p="md" mb="lg">
        <Stack gap="md">
          <TextInput
            label="Lichess Username"
            placeholder="e.g. hikaru, magnuscarlsen"
            value={username}
            onChange={(e) => setUsername(e.currentTarget.value)}
            required
          />

          <Group grow>
            <NumberInput
              label="Max Games"
              value={maxGames}
              onChange={(v) => setMaxGames(Number(v) || 50)}
              min={1}
              max={500}
            />
            <Select
              label="Time Control"
              placeholder="All"
              data={[
                { value: "rapid", label: "Rapid" },
                { value: "blitz", label: "Blitz" },
                { value: "classical", label: "Classical" },
                { value: "bullet", label: "Bullet" },
                { value: "correspondence", label: "Correspondence" },
              ]}
              value={perfType}
              onChange={setPerfType}
              clearable
            />
            <Switch
              label="Rated only"
              checked={rated === true}
              onChange={(e) => setRated(e.currentTarget.checked ? true : null)}
              mt="lg"
            />
          </Group>

          <Button
            onClick={handleImport}
            disabled={!username.trim() || loading}
            fullWidth
          >
            {loading ? <Loader size="sm" color="white" /> : "Import from Lichess"}
          </Button>

          {loading && <Progress value={progress} animated striped />}
        </Stack>
      </Paper>

      {error && (
        <Alert color="red" title="Import Error" mb="md">
          {error}
        </Alert>
      )}

      {result && (
        <Paper shadow="xs" p="md">
          <Title order={4} mb="sm">
            Import Results for {result.username}
          </Title>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Metric</Table.Th>
                <Table.Th>Value</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              <Table.Tr>
                <Table.Td>Games Fetched</Table.Td>
                <Table.Td>
                  <Badge color="blue">{result.games_fetched}</Badge>
                </Table.Td>
              </Table.Tr>
              <Table.Tr>
                <Table.Td>Imported</Table.Td>
                <Table.Td>
                  <Badge color={result.imported_count > 0 ? "green" : "yellow"}>
                    {result.imported_count}
                  </Badge>
                </Table.Td>
              </Table.Tr>
            </Table.Tbody>
          </Table>
          {result.errors.length > 0 && (
            <Alert color="yellow" title="Warnings" mt="md">
              <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
                {result.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </Alert>
          )}
        </Paper>
      )}
    </Container>
  );
}
