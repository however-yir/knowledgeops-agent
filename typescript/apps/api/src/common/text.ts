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

export function truncateText(text: string, maxLength: number): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength)}...`;
}
