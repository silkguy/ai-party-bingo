export function lines(marked: boolean[]) {
  const all = [
    ...Array.from({ length: 5 }, (_, r) =>
      Array.from({ length: 5 }, (_, c) => r * 5 + c),
    ),
    ...Array.from({ length: 5 }, (_, c) =>
      Array.from({ length: 5 }, (_, r) => r * 5 + c),
    ),
    [0, 6, 12, 18, 24],
    [4, 8, 12, 16, 20],
  ];
  return all.filter((l) => l.every((i) => marked[i]));
}
export function shuffled<T>(items: T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const buffer = new Uint32Array(1);
    crypto.getRandomValues(buffer);
    const limit = 2 ** 32 - (2 ** 32 % (i + 1));
    while (buffer[0] >= limit) crypto.getRandomValues(buffer);
    const j = buffer[0] % (i + 1);
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}
export function restore<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}
