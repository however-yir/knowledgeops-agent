/**
 * TypeScript mirror of the Java `SqlLikeUtils` (0c64312): escape MySQL LIKE
 * wildcards so user-supplied keywords cannot widen a search into a full-table
 * match. The TS runtime currently scores keywords in memory and issues no raw
 * SQL, but the escape semantics stay available (and verified) for any storage
 * backend that translates `contains` filters into SQL LIKE patterns.
 */
export function escapeForLike(keyword: string | undefined): string | undefined {
  if (!keyword) {
    return keyword;
  }
  return keyword.replace(/\\/g, "\\\\").replace(/%/g, "\\%").replace(/_/g, "\\_");
}
