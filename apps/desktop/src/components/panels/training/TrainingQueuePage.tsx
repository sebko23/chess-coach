import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { backendBaseUrlAtom, backendTokenAtom } from "@/state/atoms/coach";
import { activePlayerAtom } from "@/state/atoms/playerAtom";
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
  eco: string | null;
  opening: string | null;
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

interface DayPlanCard {
  id: string;
  card_type: "position" | "opening_gap" | "concept";
  reference_id: string;
  priority_score: number;
  difficulty: number;
  stability: number;
  reviews: number;
  is_new: boolean;
  due: string;
}

interface DayPlan {
  day: number;
  date: string;
  estimated_minutes: number;
  new_cards: number;
  review_cards: number;
  card_type_breakdown: Record<string, number>;
  cards: DayPlanCard[];
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
  classification,
}: {
  classification: string | null;
}) {

  return (
    <Badge
      size="sm"
      variant="filled"
      color={BLUNDER_COLORS[classification ?? ""] ?? "gray"}
    >
      {classification ? classification.charAt(0).toUpperCase() + classification.slice(1) : "—"}
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
            {card.eco && card.opening && (
              <Badge
                size="sm"
                variant="outline"
                color="cyan"
                title={`${card.eco}: ${card.opening}`}
              >
                {card.eco}
              </Badge>
            )}
            
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
  const [classifications, setClassifications] = useState<Record<string, string | null>>({});
  const [dueCount, setDueCount] = useState(0);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [reviewedCount, setReviewedCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [rating, setRating] = useState<number | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [schedule, setSchedule] = useState<DayPlan[] | null>(null);
  const [scheduleExpanded, setScheduleExpanded] = useState(false);
const [expandedDay, setExpandedDay] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playerName] = useAtom(activePlayerAtom);

  const headers = useMemo(() => (token ? { Authorization: `Bearer ${token}` } as HeadersInit : {} as HeadersInit), [token]);
const priorityColor = (score: number): string => {
  if (score >= 0.7) return "var(--mantine-color-red-1)";
  if (score >= 0.4) return "var(--mantine-color-yellow-1)";
  return "var(--mantine-color-teal-1)";
};

const priorityBorder = (score: number): string => {
  if (score >= 0.7) return "var(--mantine-color-red-4)";
  if (score >= 0.4) return "var(--mantine-color-yellow-4)";
  return "var(--mantine-color-teal-4)";
};

const cardTypeLabel = (type: "position" | "opening_gap" | "concept"): string => {
  if (type === "opening_gap") return "Opening";
  if (type === "concept") return "Concept";
  return "Position";
};

const today = new Date().toISOString().slice(0, 10);


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
      // Batch fetch blunder classifications
      const fens = (data.cards ?? []).map((c: { fen: string }) => c.fen).filter(Boolean);
      if (fens.length > 0) {
        fetch(`${baseUrl}/v1/blunders/batch-by-fen`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ fens }),
        })
          .then(r => r.json())
          .then(batchData => setClassifications(batchData.results ?? {}))
          .catch(() => {});
      }
      setDueCount(data.due_count || 0);
      setCurrentIndex(0);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [baseUrl, headers]);

  useEffect(() => { fetchQueue(); }, [fetchQueue]);

  const fetchSchedule = useCallback(async () => {
    if (!baseUrl || !token) return;
    try {
      const res = await fetch(
        `${baseUrl}/v1/training/schedule/default?days=7&daily_minutes=30`,
        { headers: { Authorization: `Bearer ${token}` } as HeadersInit }
      );
      if (res.ok) {
        const data = await res.json();
        setSchedule(data.schedule ?? null);
      }
    } catch { /* silent */ }
  }, [baseUrl, token]);

  useEffect(() => { fetchSchedule(); }, [fetchSchedule]);


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

        {schedule && (
          <Card withBorder shadow="sm" p="md" mb="md">
            <Group justify="space-between" mb={scheduleExpanded ? "sm" : 0}>
              <Group gap="xs">
                <Text fw={600} size="sm">7-Day Study Plan</Text>
                <Badge size="sm" variant="light" color="blue">
                  {schedule.reduce((s, d) => s + d.new_cards + d.review_cards, 0)} cards
                </Badge>
              </Group>
              <Button size="xs" variant="subtle"
                onClick={() => setScheduleExpanded(e => !e)}>
                {scheduleExpanded ? "Hide" : "Show"}
              </Button>
            </Group>
            {scheduleExpanded && (
              <>
                {schedule.length === 0 ? (
                  <Text size="sm" c="dimmed" ta="center" mt="sm">
                    No schedule loaded — click Refresh to generate your 7-day plan.
                  </Text>
                ) : (
                  <SimpleGrid cols={7} spacing="xs" mt="xs">
                    {schedule.map((day) => {
                      const isToday = day.date === today;
                      const avgPriority = day.cards.length > 0
                        ? day.cards.reduce((s, c) => s + c.priority_score, 0) / day.cards.length
                        : 0;
                      const isExpanded = expandedDay === day.day;
                      return (
                        <Stack key={day.day} gap={2} align="center"
                          style={{
                            background: priorityColor(avgPriority),
                            border: `${isToday ? "2px" : "1px"} solid ${isToday ? "var(--mantine-color-blue-5)" : priorityBorder(avgPriority)}`,
                            borderRadius: 6,
                            padding: "6px 4px",
                            cursor: "pointer",
                            transition: "opacity 0.15s",
                          }}
                          onClick={() => setExpandedDay(isExpanded ? null : day.day)}
                        >
                          <Text size="xs" fw={isToday ? 800 : 600}
                            c={isToday ? "blue" : undefined}>
                            {isToday ? "Today" : day.date.slice(5)}
                          </Text>
                          <Badge size="xs" color="blue" variant="filled">
                            {day.new_cards + day.review_cards}
                          </Badge>
                          <Text size="xs" c="dimmed">{day.estimated_minutes}m</Text>
                          {day.new_cards > 0 && (
                            <Badge size="xs" color="teal" variant="light">
                              {day.new_cards} new
                            </Badge>
                          )}
                          <Text size="xs" c="dimmed">{isExpanded ? "▲" : "▼"}</Text>
                        </Stack>
                      );
                    })}
                  </SimpleGrid>
                )}

                {expandedDay !== null && (() => {
                  const day = schedule.find(d => d.day === expandedDay);
                  if (!day) return null;
                  return (
                    <Stack gap="xs" mt="sm">
                      <Text size="xs" fw={600} c="dimmed">
                        {day.date} — {day.cards.length} cards · {day.estimated_minutes} min
                      </Text>
                      {day.cards.map((card) => (
                        <Group key={card.id} justify="space-between"
                          style={{
                            background: priorityColor(card.priority_score),
                            border: `1px solid ${priorityBorder(card.priority_score)}`,
                            borderRadius: 4,
                            padding: "4px 8px",
                          }}
                        >
                          <Group gap="xs">
                            <Badge size="xs" variant="light"
                              color={card.card_type === "opening_gap" ? "violet" : card.card_type === "concept" ? "orange" : "blue"}>
                              {cardTypeLabel(card.card_type)}
                            </Badge>
                            <Text size="xs" c="dimmed" style={{ fontFamily: "monospace" }}>
                              {card.reference_id.split(":").slice(0, 2).join(":")}
                            </Text>
                            {card.is_new && (
                              <Badge size="xs" color="teal" variant="dot">new</Badge>
                            )}
                          </Group>
                          <Group gap="xs">
                            <Text size="xs" c="dimmed">
                              d:{Math.round(card.difficulty)} · p:{card.priority_score.toFixed(2)}
                            </Text>
                          </Group>
                        </Group>
                      ))}
                    </Stack>
                  );
                })()}
              </>
            )}
          </Card>
        )}

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
