export function tokenize(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .split(/[^\p{L}\p{N}]+/u)
      .map((token) => token.trim())
      .filter(Boolean)
  );
}

export function scoreByTokenOverlap(query: string, content: string): number {
  const queryTokens = tokenize(query);
  const contentTokens = tokenize(content);
  if (queryTokens.size === 0 || contentTokens.size === 0) {
    return 0;
  }
  let overlap = 0;
  for (const token of queryTokens) {
    if (contentTokens.has(token)) {
      overlap += 1;
    }
  }
  return overlap / Math.max(1, queryTokens.size);
}

export function scoreByKeywordDensity(query: string, content: string): number {
  const queryTokens = [...tokenize(query)];
  if (queryTokens.length === 0) {
    return 0;
  }
  const normalized = content.toLowerCase();
  const hits = queryTokens.reduce((total, token) => total + (normalized.includes(token) ? 1 : 0), 0);
  return hits / queryTokens.length;
}

export function cosineSimilarity(left: number[], right: number[]): number {
  const length = Math.min(left.length, right.length);
  if (length === 0) {
    return 0;
  }
  let dot = 0;
  let leftNorm = 0;
  let rightNorm = 0;
  for (let index = 0; index < length; index += 1) {
    dot += left[index] * right[index];
    leftNorm += left[index] * left[index];
    rightNorm += right[index] * right[index];
  }
  const divisor = Math.sqrt(leftNorm) * Math.sqrt(rightNorm);
  return divisor === 0 ? 0 : dot / divisor;
}

export function truncateText(text: string, maxLength: number): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength)}...`;
}
