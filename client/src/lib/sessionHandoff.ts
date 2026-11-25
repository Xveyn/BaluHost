/**
 * Einmal-Code-Handoff vom Desktop-Tray in die Web-UI (#847).
 *
 * Das Tray oeffnet `${web_url}/login#handoff=<code>`. Der Code steht im
 * Fragment (geht nie an Server oder Referer) und wird vor dem Netzwerkaufruf
 * aus der Adressleiste entfernt, auch wenn das Einloesen scheitert.
 */

const PARAM = 'handoff';

function readCode(hash: string): string | null {
  const params = new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash);
  const code = params.get(PARAM);
  return code ? code : null;
}

export function hasHandoffFragment(hash: string): boolean {
  return readCode(hash) !== null;
}

export function takeHandoffCode(
  loc: Pick<Location, 'hash' | 'pathname' | 'search'>,
  hist: Pick<History, 'replaceState'>,
): string | null {
  const code = readCode(loc.hash);
  if (code === null) return null;
  hist.replaceState(null, '', loc.pathname + loc.search);
  return code;
}
