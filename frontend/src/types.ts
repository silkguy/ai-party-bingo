export type Entry = { name: string; aliases: string[] };
export type Bot = {
  id: string;
  name: string;
  personality: string;
  description: string;
  color: string;
  voice: string;
};
export type GameMode = "normal" | "chaos" | "impostor";
export type Message = {
  id?: string;
  kind?: string;
  replyToMessageId?: string | null;
  questionId?: string | null;
  createdAt?: number;
  botId: string;
  name: string;
  personality: string;
  color: string;
  message: string;
  subject: string;
  conversationAction: string;
  mentionedEntities?: string[];
  chaosEvent: string | null;
  relationships: Record<string, number>;
};
export type Settings = {
  manualSpeaker: boolean;
  pollsEnabled: boolean;
  transitionWeights: number[];
  chaosFrequency: string;
  timerEnabled: boolean;
  timerSeconds: number;
  url: string;
  model: string;
  temperature: number;
  maxTokens: number;
  memory: number;
  sentences: number;
  thinking: boolean;
  weights: number[];
  speed: number;
  clashes: boolean;
  intensity: number;
  showRelations: boolean;
  chaos: string;
  showChaos: boolean;
  tts: boolean;
  engine: string;
  rate: number;
  volume: number;
  pitch: number;
  autoSpeak: boolean;
  stopOnPause: boolean;
  sounds: boolean;
  free: boolean;
  detect: boolean;
  autoMark: boolean;
  animations: boolean;
  reduced: boolean;
  fontSize: number;
  scale: number;
};
export type State = {
  version: number;
  mode: GameMode;
  requiredLines: number;
  relationshipLocks: Record<string, boolean>;
  sessionId?: string;
  flagged: boolean[];
  eliminated: string[];
  timerRemaining: number | null;
  stage: number;
  topic: string;
  category: string;
  pool: Entry[];
  board: string[];
  marked: boolean[];
  locked: boolean[];
  bots: Bot[];
  messages: Message[];
  relationships: Record<string, number>;
  subject: string;
  lastChaos: string | null;
};
export const defaults: Settings = {
  manualSpeaker: false,
  pollsEnabled: false,
  transitionWeights: [60, 25, 15],
  chaosFrequency: "medium",
  timerEnabled: false,
  timerSeconds: 300,
  url: "http://localhost:11434",
  model: "qwen3:4b",
  temperature: 0.85,
  maxTokens: 768,
  memory: 12,
  sentences: 3,
  thinking: false,
  weights: [40, 25, 35],
  speed: 1,
  clashes: true,
  intensity: 1,
  showRelations: true,
  chaos: "off",
  showChaos: true,
  tts: false,
  engine: "auto",
  rate: 1,
  volume: 0.8,
  pitch: 1,
  autoSpeak: true,
  stopOnPause: false,
  sounds: true,
  free: false,
  detect: false,
  autoMark: false,
  animations: true,
  reduced: false,
  fontSize: 15,
  scale: 1,
};
export const initial: State = {
  version: 2,
  mode: "normal",
  requiredLines: 1,
  relationshipLocks: {},
  flagged: Array(25).fill(false),
  eliminated: [],
  timerRemaining: null,
  stage: 0,
  topic: "Zenless Zone Zero",
  category: "Characters",
  pool: [],
  board: Array(25).fill(""),
  marked: Array(25).fill(false),
  locked: Array(25).fill(false),
  bots: [],
  messages: [],
  relationships: {},
  subject: "",
  lastChaos: null,
};

export type Poll = {
  id: string;
  creatorId: string;
  creatorName: string;
  question: string;
  options: string[];
  totals: number[];
  votes: { botId: string; name: string; option: number; explanation: string }[];
};
export type Round = Omit<State, "stage" | "locked" | "version"> & {
  sessionId: string;
  status: string;
  completedLines: number;
  resultReason: string;
  polls: Poll[];
  forceNextSubject: boolean;
  settings: Settings;
  running: boolean;
  awaitingPlayback: boolean;
  generating: boolean;
  questionQueue: string[];
  pollPending: boolean;
  remainingImpostors: number;
  impostorCount: number;
  revealedRoles: Record<string, string>;
};
