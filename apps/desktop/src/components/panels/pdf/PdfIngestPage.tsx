import { useState, useRef, useCallback } from "react";
import {
  Container,
  Title,
  Text,
  Paper,
  Group,
  Stack,
  Badge,
  Button,
  Progress,
  Card,
  SimpleGrid,
  ThemeIcon,
  Alert,
  useMantineTheme,
} from "@mantine/core";
import {
  IconUpload,
  IconFiles,
  IconCheck,
  IconX,
  IconAlertCircle,
  IconInfoCircle,
  IconSearch,
} from "@tabler/icons-react";
import { useNavigate } from "@tanstack/react-router";
import { backendBaseUrlAtom, backendTokenAtom } from "@/state/atoms/coach";
import { useAtomValue } from "jotai";

interface DiagramSummary {
  page_number: number;
  diagram_index: number;
  fen: string;
  valid: boolean;
  confidence: number;
  issues: string[];
  game_id: string | null;
  job_id: string | null;
}

interface PdfIngestResponse {
  ingest_id: string;
  filename: string;
  page_count: number;
  diagrams_detected: number;
  diagrams_valid: number;
  diagrams: DiagramSummary[];
  errors: string[];
  completed_at: string;
}

type UploadState =
  | { status: "idle" }
  | { status: "uploading"; progress: number }
  | { status: "success"; result: PdfIngestResponse }
  | { status: "error"; message: string };

export default function PdfIngestPage() {
  const theme = useMantineTheme();
  const navigate = useNavigate();
  const backendBaseUrl = useAtomValue(backendBaseUrlAtom);
  const backendToken = useAtomValue(backendTokenAtom);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadState, setUploadState] = useState<UploadState>({ status: "idle" });
  const [dragOver, setDragOver] = useState(false);

  const uploadPdf = useCallback(async (file: File) => {
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setUploadState({ status: "error", message: "Only PDF files are supported." });
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setUploadState({ status: "error", message: "PDF exceeds 50 MB limit." });
      return;
    }

    setUploadState({ status: "uploading", progress: 0 });

    try {
      // Simulate progress for large files
      const progressInterval = setInterval(() => {
        setUploadState((prev) => {
          if (prev.status !== "uploading") return prev;
          const next = Math.min(prev.progress + 8, 90);
          return { status: "uploading", progress: next };
        });
      }, 200);

      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`${backendBaseUrl}/v1/import/pdf`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${backendToken}`,
        },
        body: formData,
      });

      clearInterval(progressInterval);

      if (!response.ok) {
        const body = await response.text();
        throw new Error(body ? body.substring(0, 200) : `HTTP ${response.status}`);
      }

      const result: PdfIngestResponse = await response.json();
      setUploadState({ status: "success", result });
    } catch (err: any) {
      setUploadState({
        status: "error",
        message: err.message || "Upload failed",
      });
    }
  }, [backendBaseUrl, backendToken]);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file) uploadPdf(file);
    },
    [uploadPdf]
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) uploadPdf(file);
    },
    [uploadPdf]
  );

  const formatConfidence = (v: number) => `${(v * 100).toFixed(0)}%`;

  return (
    <Container size="lg" py="md">
      <Title order={2}>PDF Ingest</Title>
      <Text c="dimmed" size="sm" mb="md">
        Upload a PDF with chess diagrams to automatically detect, OCR, and import positions into your game database.
      </Text>

      {/* Drag-and-drop zone */}
      <Paper
        p="xl"
        withBorder
        style={{
          borderStyle: dragOver ? "solid" : "dashed",
          borderColor: dragOver ? theme.colors.blue[6] : theme.colors.gray[5],
          backgroundColor: dragOver ? theme.colors.blue[0] : undefined,
          cursor: "pointer",
          transition: "all 0.15s",
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          style={{ display: "none" }}
          onChange={handleFileSelect}
        />
        <Stack align="center" gap="xs">
          <ThemeIcon size={48} variant="light" color="blue" radius="xl">
            <IconFiles size={24} />
          </ThemeIcon>
          <Text fw={500}>
            {dragOver ? "Drop your PDF here" : "Drop a PDF here or click to browse"}
          </Text>
          <Text size="xs" c="dimmed">
            Max 50 MB, PDF format only
          </Text>
        </Stack>
      </Paper>

      {/* Progress bar */}
      {uploadState.status === "uploading" && (
        <Paper withBorder p="md" mt="md">
          <Group mb="xs">
            <IconUpload size={16} />
            <Text size="sm" fw={500}>Uploading and processing...</Text>
          </Group>
          <Progress value={uploadState.progress} animated striped color="blue" />
          <Text size="xs" c="dimmed" mt={4}>
            {uploadState.progress}% — rasterizing, detecting boards, OCR, importing
          </Text>
        </Paper>
      )}

      {/* Error alert */}
      {uploadState.status === "error" && (
        <Alert
          icon={<IconAlertCircle size={16} />}
          title="Upload failed"
          color="red"
          mt="md"
          withCloseButton
          onClose={() => setUploadState({ status: "idle" })}
        >
          {uploadState.message}
        </Alert>
      )}

      {/* Success results */}
      {uploadState.status === "success" && (
        <>
          {/* Summary card */}
          <Paper withBorder p="md" mt="md">
            <Group justify="space-between" mb="xs">
              <Group>
                <ThemeIcon size={32} variant="light" color="green" radius="xl">
                  <IconCheck size={18} />
                </ThemeIcon>
                <div>
                  <Text fw={500}>{uploadState.result.filename}</Text>
                  <Text size="xs" c="dimmed">
                    Ingest ID: {uploadState.result.ingest_id}
                  </Text>
                </div>
              </Group>
              <Text size="xs" c="dimmed">
                {uploadState.result.completed_at}
              </Text>
            </Group>
            <SimpleGrid cols={3} spacing="md" mt="md">
              <Paper p="sm" withBorder>
                <Text size="xs" c="dimmed">Pages</Text>
                <Text fw={700} size="xl">{uploadState.result.page_count}</Text>
              </Paper>
              <Paper p="sm" withBorder>
                <Text size="xs" c="dimmed">Diagrams Detected</Text>
                <Text fw={700} size="xl">{uploadState.result.diagrams_detected}</Text>
              </Paper>
              <Paper p="sm" withBorder>
                <Text size="xs" c="dimmed">Valid Positions</Text>
                <Text fw={700} size="xl" c={uploadState.result.diagrams_valid > 0 ? "green" : "orange"}>
                  {uploadState.result.diagrams_valid} / {uploadState.result.diagrams_detected}
                </Text>
              </Paper>
            </SimpleGrid>
            {uploadState.result.errors.length > 0 && (
              <Alert icon={<IconInfoCircle size={16} />} title="Warnings" color="yellow" mt="sm" p="xs">
                <Text size="xs">{uploadState.result.errors.join("; ")}</Text>
              </Alert>
            )}
          </Paper>

          {/* Diagram results grid */}
          <Title order={4} mt="lg" mb="sm">Detected Diagrams</Title>
          <Stack gap="sm">
            {uploadState.result.diagrams.map((d, i) => (
              <Card key={i} withBorder padding="sm">
                <Group justify="space-between" align="flex-start">
                  <Stack gap={4} style={{ flex: 1 }}>
                    <Group gap="xs">
                      <Badge size="sm" variant="light" color="gray">
                        Page {d.page_number} · #{d.diagram_index}
                      </Badge>
                      <Badge
                        size="sm"
                        variant="light"
                        color={d.valid ? "green" : "red"}
                      >
                        {d.valid ? "Valid" : "Invalid"}
                      </Badge>
                      <Badge
                        size="sm"
                        variant="light"
                        color={
                          d.confidence >= 0.8
                            ? "green"
                            : d.confidence >= 0.5
                            ? "yellow"
                            : "red"
                        }
                      >
                        {formatConfidence(d.confidence)}
                      </Badge>
                    </Group>
                    <Text size="xs" ff="monospace" c="dimmed">
                      {d.fen}
                    </Text>
                    {d.issues.length > 0 && (
                      <Text size="xs" c="red.6">
                        {d.issues.join("; ")}
                      </Text>
                    )}
                  </Stack>
                  {d.valid && d.game_id && (
                    <Button
                      variant="light"
                      size="xs"
                      leftSection={<IconSearch size={14} />}
                      onClick={() =>
                        navigate({ to: "/games/$gameId", params: { gameId: d.game_id! } })
                      }
                    >
                      Open
                    </Button>
                  )}
                </Group>
              </Card>
            ))}
          </Stack>

          <Button
            variant="light"
            fullWidth
            mt="md"
            onClick={() => setUploadState({ status: "idle" })}
          >
            Upload another PDF
          </Button>
        </>
      )}
    </Container>
  );
}
