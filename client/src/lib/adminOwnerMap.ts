/**
 * Build an id → display-name map from a page of `users` rows.
 *
 * Extracted verbatim from AdminDatabase's owner-mapping loader so the id/name
 * coalescing precedence stays pinned. Mirrors the original guard exactly: a row
 * is included when its coalesced id is not `undefined`. Because the coalescing
 * uses `??`, an `id: null` with no other id field falls through to `undefined`
 * and is skipped; the `"null"` string key only appears when the coalesced value
 * is literally `null` (e.g. the final `userId` fallback is null). The name falls
 * back to an empty string when no name-like field is present.
 */
export function buildOwnerMap(rows: Array<Record<string, unknown>>): Record<string, string> {
  const map: Record<string, string> = {}
  for (const u of rows || []) {
    const id = u.id ?? u.ID ?? u.user_id ?? u.userId
    const name = u.username ?? u.user_name ?? u.name ?? u.display_name ?? u.displayName ?? ''
    if (id !== undefined) map[String(id)] = name as string
  }
  return map
}
