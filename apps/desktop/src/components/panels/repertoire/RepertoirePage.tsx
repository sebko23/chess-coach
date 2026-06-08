import { useAtomValue } from "jotai";
import { backendBaseUrlAtom, backendTokenAtom } from "@/state/atoms/coach";
import {
  Container, Title, Text, Card, Badge, Stack, Group, SegmentedControl,
  ScrollArea, Paper, Loader, Alert, Divider, SimpleGrid,
} from "@mantine/core";
import { useCallback, useEffect, useMemo, useState } from "react";

/* ---------- Backend response types ---------- */

interface OpeningNode {
  fen: string;
  move_san: string | null;
  move_uci: string | null;
  ply: number;
  times_played: number;
  children_count: number;
}

interface TreeResponse {
  player_name: string;
  color: string;
  node_count: number;
  nodes: OpeningNode[];
}

interface GapResponse {
  fen: string;
  ply: number;
  move_san: string | null;
  times_reached: number;
  suggested_alternatives: string[];
}

interface NoveltyResponse {
  fen: string;
  ply: number;
  move_san: string | null;
  game_id: string;
  total_times_played: number;
}

/* ---------- TreeNode that builds hierarchy from flat list ---------- */

interface FlatNode extends OpeningNode {
  children: FlatNode[];
  indent: number;
}

function buildTree(nodes: OpeningNode[]): FlatNode[] {
  if (!nodes || nodes.length === 0) return [];
  const nodeMap = new Map<string, FlatNode>();
  for (const n of nodes) {
    nodeMap.set(n.fen, { ...n, children: [], indent: n.ply });
  }
  // Group by ply depth — first moves are the root level
  const byPly: Map<number, FlatNode[]> = new Map();
  for (const n of nodeMap.values()) {
    const arr = byPly.get(n.ply) || [];
    arr.push(n);
    byPly.set(n.ply, arr);
  }
  // Return the first ply nodes (root level)
  const minPly = Math.min(...byPly.keys());
  return byPly.get(minPly) || [];
}

/* ---------- Component ---------- */


interface RecommendationItem {
  fen: string;
  ply: number;
  priority: "normal" | "important" | "critical";
  best_move_uci: string | null;
  best_move_san: string | null;
  score_cp: number | null;
  depth_reached: number;
  alternatives_san: string[];
}

interface RecommendationResponse {
  player_name: string;
  color: string;
  total_gaps: number;
  recommendations: RecommendationItem[];
}

export default function RepertoirePage() {
  const baseUrl = useAtomValue(backendBaseUrlAtom);
  const token = useAtomValue(backendTokenAtom);

  const [color, setColor] = useState<string>("white");
  const [treeData, setTreeData] = useState<TreeResponse | null>(null);
  const [gaps, setGaps] = useState<GapResponse[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [recsLoading, setRecsLoading] = useState(false);
  const [novelties, setNovelties] = useState<NoveltyResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const headers = useMemo(() => (token ? { Authorization: `Bearer ${token}` } as HeadersInit : {} as HeadersInit), [token]);

  const fetchData = useCallback(async () => {
    if (!baseUrl) return;
    setLoading(true);
    setError(null);
    try {
      const [treeRes, gapsRes, noveltiesRes] = await Promise.all([
        fetch(`${baseUrl}/v1/repertoire/default/tree?color=${color}`, { headers }),
        fetch(`${baseUrl}/v1/repertoire/default/gaps?color=${color}`, { headers }),
        fetch(`${baseUrl}/v1/repertoire/default/novelties?color=${color}`, { headers }),
      ]);
      if (!treeRes.ok) throw new Error(`Tree: ${treeRes.status}`);
      if (!gapsRes.ok) throw new Error(`Gaps: ${gapsRes.status}`);
      if (!noveltiesRes.ok) throw new Error(`Novelties: ${noveltiesRes.status}`);

      const t: TreeResponse = await treeRes.json();
      setTreeData(t);
      const g: GapResponse[] = await gapsRes.json();
      setGaps(g || []);
      const n: NoveltyResponse[] = await noveltiesRes.json();
      setNovelties(n || []);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [baseUrl, headers, color]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const fetchRecommendations = useCallback(async () => {
    if (!baseUrl || !token) return;
    setRecsLoading(true);
    try {
      const resp = await fetch(
        `${baseUrl}/v1/repertoire/default/recommendations?limit=5&color=${color}`,
        { method: "POST", headers }
      );
      if (resp.ok) {
        const data: RecommendationResponse = await resp.json();
        setRecommendations(data.recommendations);
      }
    } catch {
      setRecommendations([]);
    } finally {
      setRecsLoading(false);
    }
  }, [baseUrl, token, color, headers]);

  useEffect(() => { fetchRecommendations(); }, [fetchRecommendations]);


  const treeNodes = useMemo(() => treeData ? buildTree(treeData.nodes) : [], [treeData]);

  if (!baseUrl) {
    return (
      <Container py="xl">
        <Alert color="yellow" title="Backend not connected">
          <Text>Waiting for backend connection.</Text>
        </Alert>
      </Container>
    );
  }

  if (loading) {
    return (
      <Container py="xl" style={{ textAlign: "center" }}>
        <Loader size="lg" />
        <Text mt="md">Loading repertoire...</Text>
      </Container>
    );
  }

  if (error) {
    return (
      <Container py="xl">
        <Alert color="red" title="Failed to load repertoire">
          <Text>{error}</Text>
        </Alert>
      </Container>
    );
  }

  return (
    <Container size="xl" py="md" style={{ height: "calc(100vh - 60px)", display: "flex", flexDirection: "column" }}>
      <Group justify="space-between" mb="md">
        <Title order={3}>Repertoire</Title>
        <SegmentedControl
          value={color}
          onChange={setColor}
          data={[
            { value: "white", label: "White" },
            { value: "black", label: "Black" },
          ]}
        />
      </Group>

      <div style={{ display: "flex", flex: 1, gap: 16, overflow: "hidden" }}>
        {/* Left panel: Opening Tree nodes */}
        <div style={{ width: 320, flexShrink: 0 }}>
          <Card withBorder shadow="sm" p="sm" h="100%" style={{ display: "flex", flexDirection: "column" }}>
            <Group justify="space-between" mb="xs">
              <Text fw={600} size="sm">Opening Tree</Text>
              {treeData && <Badge size="sm" variant="light">{treeData.node_count} nodes</Badge>}
            </Group>
            {(!treeData || treeData.nodes.length === 0) ? (
              <Text size="sm" c="dimmed" ta="center" py="xl">
                No games found for {color}.
              </Text>
            ) : (
              <ScrollArea style={{ flex: 1 }}>
                <Stack gap={4}>
                  {treeData.nodes.map((node, i) => (
                    <Group key={`${node.fen}-${i}`} gap={4} wrap="nowrap" style={{ paddingLeft: Math.min(node.ply * 12, 120) }}>
                      <Badge size="xs" variant="outline" color="gray" style={{ minWidth: 20 }}>
                        {node.ply}
                      </Badge>
                      <Text size="sm" ff="monospace" fw={500}>
                        {node.move_san || "..."}
                      </Text>
                      <Badge size="xs" variant="light" color="blue">
                        ×{node.times_played}
                      </Badge>
                      {node.children_count > 0 && (
                        <Badge size="xs" variant="dot" color="green">
                          {node.children_count} var
                        </Badge>
                      )}
                    </Group>
                  ))}
                </Stack>
              </ScrollArea>
            )}
          </Card>
        </div>

        {/* Right panel: Gaps + Novelties */}
        <div style={{ flex: 1, overflow: "hidden" }}>
          <ScrollArea style={{ height: "100%" }}>
            <Stack gap="md">
              {/* Preparation Gaps */}
              <Card withBorder shadow="sm" p="md">
                <Title order={5} mb="sm">Preparation Gaps <Badge size="sm" ml="xs">{gaps.length}</Badge></Title>
                {gaps.length === 0 ? (
                  <Text size="sm" c="dimmed">No preparation gaps detected.</Text>
                ) : (
                  <Stack gap="sm">
                    {gaps.map((gap, i) => (
                      <Paper key={i} withBorder p="sm" radius="sm">
                        <Group gap="xs" mb={4}>
                          <Badge size="sm" variant="outline" color="gray">{gap.ply}.</Badge>
                          <Text size="sm" ff="monospace" fw={500}>{gap.move_san || "?"}</Text>
                          <Badge size="sm" variant="light" color="orange">×{gap.times_reached} reached</Badge>
                        </Group>
                        {gap.suggested_alternatives.length > 0 && (
                          <Text size="xs" c="dimmed">
                            Suggested: {gap.suggested_alternatives.join(", ")}
                          </Text>
                        )}
                      </Paper>
                    ))}
                  </Stack>
                )}
              </Card>

              <Divider />

              {/* Opponent Novelties */}
              <Card withBorder shadow="sm" p="md">
                <Title order={5} mb="sm">Opponent Novelties <Badge size="sm" ml="xs">{novelties.length}</Badge></Title>
                {novelties.length === 0 ? (
                  <Text size="sm" c="dimmed">No opponent novelties detected.</Text>
                ) : (
                  <Stack gap="sm">
                    {novelties.map((nov, i) => (
                      <Paper key={i} withBorder p="sm" radius="sm">
                        <Group gap="xs" mb={4}>
                          <Badge size="sm" variant="outline" color="gray">{nov.ply}.</Badge>
                          <Text size="sm" ff="monospace" fw={700}>{nov.move_san || "?"}</Text>
                          <Badge size="sm" variant="light" color="violet">×{nov.total_times_played}</Badge>
                        </Group>
                      </Paper>
                    ))}
                  </Stack>
                )}
              </Card>

              <Card withBorder shadow="sm" p="md">
                <Group justify="space-between" mb="sm">
                  <Title order={5}>
                    Engine Recommendations
                    <Badge ml="xs" color="violet">{recommendations.length}</Badge>
                  </Title>
                  {recsLoading && <Loader size="xs" />}
                </Group>
                {recommendations.length === 0 && !recsLoading && (
                  <Text size="sm" c="dimmed">No recommendations available.</Text>
                )}
                <Stack gap="xs">
                  {recommendations.map((rec, i) => (
                    <Group key={i} justify="space-between" wrap="nowrap" p="xs"
                      style={{ background: "var(--mantine-color-default-hover)", borderRadius: 6 }}>
                      <Group gap="xs" wrap="nowrap">
                        <Badge size="xs" color={rec.priority === "critical" ? "red" : rec.priority === "important" ? "orange" : "blue"} variant="filled">
                          {rec.priority}
                        </Badge>
                        <Text size="xs" c="dimmed">ply {rec.ply}</Text>
                        <Text size="sm" fw={600} ff="monospace">{rec.best_move_san ?? rec.best_move_uci ?? "?"}</Text>
                        {rec.score_cp !== null && (
                          <Badge size="xs" variant="light" color={rec.score_cp >= 0 ? "teal" : "red"}>
                            {rec.score_cp >= 0 ? "+" : ""}{(rec.score_cp / 100).toFixed(2)}
                          </Badge>
                        )}
                        {rec.alternatives_san.length > 0 && (
                          <Text size="xs" c="dimmed">alt: {rec.alternatives_san.join(", ")}</Text>
                        )}
                      </Group>
                      <Badge size="xs" variant="outline" color="gray">depth {rec.depth_reached}</Badge>
                    </Group>
                  ))}
                </Stack>
              </Card>

            </Stack>
          </ScrollArea>
        </div>
      </div>
    </Container>
  );
}
