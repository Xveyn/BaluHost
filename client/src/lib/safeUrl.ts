/**
 * URL sanitization for user/plugin-supplied links rendered as <a href>.
 *
 * A plugin's `homepage` (and similar untrusted fields) is attacker-controlled.
 * Rendering it directly into an href allows `javascript:` (and `data:`/`vbscript:`)
 * URLs that execute on click in the app's origin — enough to read the JWT from
 * localStorage and exfiltrate it (account takeover). `rel="noopener"` does NOT
 * protect against this.
 */
export function safeExternalUrl(url: string | null | undefined): string | null {
  if (!url) return null
  try {
    const parsed = new URL(url.trim())
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return parsed.href
    }
    return null
  } catch {
    // Relative URLs / malformed input throw — treat as unsafe.
    return null
  }
}
