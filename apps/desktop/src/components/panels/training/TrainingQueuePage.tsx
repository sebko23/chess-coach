import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { backendBaseUrlAtom, backendTokenAtom } from "@/state/atoms/coach";
import { activeTabAtom, tabsAtom } from "@/state/atoms";
import { createTab } from "@/utils/tabs";
import {
  Container, Title, Text, Card, Badge, Stack, Group, SimpleGrid,
  ScrollArea, Paper, Loader, Alert, Divider, Progress, Button,
  Center, Space, Tooltip,
} from "@mantine/core";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { IconBolt, IconChessKnight } from "@tabler/icons-react";
import { MiniBoardDisplay } from "./MiniBoardDisplay";

interface CardData {
  id: string;
  player_name: string;
  card_type: string;
  reference_id: string;
  fen: string;
  move_san: string;
  game_id: string;
  white: string;
  black: string;
  stability: number;
  difficulty: number;
  retrievability: number;
  reviews: number;
  lapses: number;
  last_review: string | null;
  due: string;
  created_at: string;
  updated_at: string;
}

interface QueueResponse {
  due_count: number;
  cards: CardData[];
}

interface ReviewResponse {
  interval_days: number;
  new_due: string;
  new_stability: number;
  new_difficulty: number;
  new_retrievability: number;
  reviews: number;
  lapses: number;
}

const BLUNDER_COLORS: Record<string, string> = {
  blunder: "red",
  mistake: "orange",
  inaccuracy: "yellow",
  good: "green",
  excellent: "teal",
  best: "blue",
};

function BlunderBadge({
  baseUrl,
  token,
  fen,
}: {
  baseUrl: string | null;
  token: string | null;
  fen: string | undefined;
}) {
  const [classification, setClassification] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!baseUrl || !token || !fen) {
      setClassification(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const encoded = encodeURIComponent(fen);
    fetch(`${baseUrl}/v1/blunders/by-fen?fen=${encoded}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : { blunders: [] })
      .then((data: { blunders?: { classification: string }[] }) => {
        if (cancelled) return;
        const blunders = data.blunders ?? [];
        if (blunders.length > 0 && blunders[0].classification) {
          setClassification(blunders[0].classification);
        } else {
          setClassification(null);
        }
      })
      .catch(() => { if (!cancelled) setClassification(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [baseUrl, token, fen]);

  if (!classification) return null;
  return (
    <Badge
      size="sm"
      variant="filled"
      color={BLUNDER_COLORS[classification] ?? "gray"}
    >
      {loading ? "…" : classification}
    </Badge>
  );
}

const RATING_LABELS = [
  { value: 1, label: "Again", color: "red", description: "Completely forgot" },
  { value: 2, label: "Hard", color: "orange", description: "Recalled with effort" },
  { value: 3, label: "Good", color: "green", description: "Recalled correctly" },
  { value: 4, label: "Easy", color: "blue", description: "Instant recall" },
];

function CardReview({
  card,
  onRate,
  rating,
}: {
  card: CardData;
  onRate: (r: number) => void;
  rating: number | null;
}) {
  const [showAnswer, setShowAnswer] = useState(false);
  const [, setTabs] = useAtom(tabsAtom);
  const setActiveTab = useSetAtom(activeTabAtom);
  const navigate = useNavigate();

  useEffect(() => {
    setShowAnswer(false);
  }, [card.id]);

  const handleOpenInBoard = async () => {
    const fen = card.fen;
    if (!fen) return;
    const boardPart = fen.split(" ")[0];
    const validFenChars = /^[1-8rnbqkpRNBQKP/]+$/;
    if (!validFenChars.test(boardPart)) {
      console.warn("Skipping invalid FEN:", fen);
      return;
    }
    const pgn = [
      '[Event "Training"]',
      '[SetUp "1"]',
      `[FEN "${fen}"]`,
      '',
      '*'
    ].join('\n');
    await createTab({
      tab: { name: "Training position", type: "analysis" },
      setTabs,
      setActiveTab,
      pgn,
    });
    navigate({ to: "/" });
  };

  return (
    <Card withBorder shadow="sm" p="lg" radius="md">
      <Stack gap="md">
        <Group justify="space-between">
          <Group gap="xs">
            <Badge
              size="lg"
              variant="light"
              color={card.card_type === "position" ? "blue" : card.card_type === "opening_gap" ? "violet" : "teal"}
            >
              {card.card_type.replace(/_/g, " ")}
            </Badge>
            <BlunderBadge baseUrl={baseUrl} token={token} fen={card.fen} />
          </Group>
          <Badge size="sm" variant="outline" color="gray">
            Reviews: {card.reviews}
          </Badge>
        </Group>

        {card.fen && (
          <MiniBoardDisplay
            fen={card.fen}
            size={180}
            orientation="white"
          />
        )}

        <SimpleGrid cols={3} spacing="xs">
          <Paper withBorder p="xs" ta="center">
            <Text size="xs" c="dimmed">Stability</Text>
            <Text fw={700} size="sm">{card.stability.toFixed(1)}d</Text>
          </Paper>
          <Paper withBorder p="xs" ta="center">
            <Text size="xs" c="dimmed">Difficulty</Text>
            <Text fw={700} size="sm">{card.difficulty.toFixed(1)}</Text>
          </Paper>
          <Paper withBorder p="xs" ta="center">
            <Text size="xs" c="dimmed">Retrievability</Text>
            <Text fw={700} size="sm">{(card.retrievability * 100).toFixed(0)}%</Text>
          </Paper>
        </SimpleGrid>

        {card.last_review && (
          <Text size="xs" c="dimmed">
            Last reviewed: {new Date(card.last_review).toLocaleDateString()}
          </Text>
        )}

        {!showAnswer ? (
          <Button
            variant="light"
            color="blue"
            fullWidth
            onClick={() => setShowAnswer(true)}
          >
            Show Answer
          </Button>
        ) : (
          <>
            <Divider label="Rating" labelPosition="center" />
            <SimpleGrid cols={4} spacing="sm">
              {RATING_LABELS.map((r) => (
                <Button
                  key={r.value}
                  variant={rating === r.value ? "filled" : "outline"}
                  color={r.color}
                  disabled={rating !== null}
                  onClick={() => onRate(r.value)}
                  size="sm"
                  style={{ height: 60 }}
                >
                  <Stack gap={2} align="center">
                    <Text size="sm" fw={700}>{r.label}</Text>
                    <Text size="xs" c="dimmed">{r.description}</Text>
                  </Stack>
                </Button>
              ))}
            </SimpleGrid>
            {card.fen && (
              <Button
                variant="light"
                color="teal"
                size="xs"
                leftSection={<IconChessKnight size={14} />}
                onClick={handleOpenInBoard}
                mt="xs"
                fullWidth
              >
                Open in board
              </Button>
            )}
          </>
        )}
      </Stack>
    </Card>
  );
}

export default function TrainingQueuePage() {
  const baseUrl = useAtomValue(backendBaseUrlAtom);
  const token = useAtomValue(backendTokenAtom);

  const [cards, setCards] = useState<CardData[]>([]);
  const [dueCount, setDueCount] = useState(0);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [reviewedCount, setReviewedCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [rating, setRating] = useState<number | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const headers = useMemo(() => (token ? { Authorization: `Bearer ${token}` } : {}), [token]);

  const fetchQueue = useCallback(async () => {
    if (!baseUrl) return;
    setLoading(true);
    setError(null);
    setRating(null);
    try {
      const res = await fetch(`${baseUrl}/v1/training/queue/default?limit=50`, { headers });
      if (!res.ok) throw new Error(`Queue: ${res.status}`);
      const data: QueueResponse = await res.json();
      setCards(data.cards || []);
      setDueCount(data.due_count || 0);
      setCurrentIndex(0);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [baseUrl, headers]);

  useEffect(() => { fetchQueue(); }, [fetchQueue]);

  const handleRate = async (r: number) => {
    if (!baseUrl || rating !== null || currentIndex >= cards.length) return;
    setRating(r);
    const card = cards[currentIndex];
    try {
      const res = await fetch(`${baseUrl}/v1/training/review/${card.id}`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ rating: r }),
      });
      if (!res.ok) throw new Error(`Review: ${res.status}`);
      setReviewedCount(prev => prev + 1);
      // Advance after short delay
      setTimeout(() => {
        if (currentIndex >= cards.length - 1) {
          // Last card — reload queue
          fetchQueue();
        } else {
          setCurrentIndex(prev => prev + 1);
          setRating(null);
        }
      }, 400);
    } catch (e: any) {
      setError(e.message || String(e));
      setRating(null);
    }
  };

  const handleSeedCards = async () => {
    if (!baseUrl) return;
    setSeeding(true);
    try {
      const res = await fetch(`${baseUrl}/v1/training/seed-from-blunders`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(`Seed: \${res.status}`);
      const data = await res.json();
      alert(`Created \${data.cards_created} training cards from blunders!`);
      fetchQueue();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setSeeding(false);
    }
  };

  const currentCard = currentIndex < cards.length ? cards[currentIndex] : null;

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
        <Text mt="md">Loading training queue...</Text>
      </Container>
    );
  }

  if (error) {
    return (
      <Container py="xl">
        <Alert color="red" title="Failed to load queue">
          <Text>{error}</Text>
        </Alert>
      </Container>
    );
  }

  return (
    <Container size="md" py="md">
      <Group justify="space-between" mb="md">
        <Title order={3}>Training Queue</Title>
        <Badge size="lg" variant="light" color={reviewedCount > 0 ? "green" : "gray"}>
          {reviewedCount} reviewed this session
        </Badge>
      </Group>

      <SimpleGrid cols={4} spacing="sm" mb="md">
        <Paper withBorder p="sm" ta="center">
          <Text size="xs" c="dimmed">Due Now</Text>
          <Text fw={700} size="lg">{dueCount}</Text>
        </Paper>
        <Paper withBorder p="sm" ta="center">
          <Text size="xs" c="dimmed">In Queue</Text>
          <Text fw={700} size="lg">{cards.length}</Text>
        </Paper>
        <Paper withBorder p="sm" ta="center">
          <Text size="xs" c="dimmed">Progress</Text>
          <Text fw={700} size="lg">{currentIndex + 1}/{cards.length}</Text>
        </Paper>
        <Paper withBorder p="sm" ta="center">
          <Text size="xs" c="dimmed">Reviewed</Text>
          <Text fw={700} size="lg">{reviewedCount}</Text>
        </Paper>
      </SimpleGrid>

      {cards.length > 0 && (
        <Progress
          value={((currentIndex + 1) / cards.length) * 100}
          size="sm"
          mb="md"
          color="blue"
        />
      )}

      <Divider mb="md" />

      {!currentCard ? (
        <Paper withBorder p="xl" ta="center" radius="md">
          <Text size="lg" fw={700} c="green">✓</Text>
          <Text size="lg" fw={600} mt="sm">All caught up!</Text>
          <Text size="sm" c="dimmed" mt="xs">
            {dueCount > 0
              ? `${dueCount} card(s) are due but not in the current queue.`
              : "No cards due for review."
            }
          </Text>
          <Button variant="light" color="blue" mt="md" onClick={fetchQueue}>
            Check Again
          </Button>
          {dueCount === 0 && (
            <Button
              variant="light"
              color="violet"
              leftSection={<IconBolt size={16} />}
              onClick={handleSeedCards}
              loading={seeding}
              mt="md"
            >
              Generate training cards from blunders
            </Button>
          )}
        </Paper>
      ) : (
        <CardReview card={currentCard} onRate={handleRate} rating={rating} />
      )}
    </Container>
  );
}
