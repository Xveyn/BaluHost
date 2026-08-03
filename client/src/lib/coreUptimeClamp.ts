/**
 * Kernbetriebszeit-Kuerzung fuer den Always-Awake-Override.
 *
 * Reiner Intervallvergleich auf bereits aufgeloesten Fenster-Terminen — die
 * Wochentags- und Mitternachtslogik bleibt im Backend
 * (`services/power/core_uptime.py`). Muss `clamp_to_core_uptime_start()`
 * dort exakt spiegeln, in zwei getrennten Schritten:
 *
 * 1. Unter ALLEN Occurrences, die `until` enthalten (unabhaengig davon, ob
 *    ihr Start in Vergangenheit oder Zukunft liegt), den FRUEHESTEN Start
 *    finden (`window_start_containing`) — bei Ueberlappung gewinnt der
 *    fruehere Start, damit das Ergebnis nicht von der Listenreihenfolge
 *    abhaengt.
 * 2. Erst danach EINMAL prüfen, ob dieser eine gefundene Start noch in der
 *    Zukunft liegt. Ist er `<= now` (das Fenster laeuft schon), bleibt
 *    `until` unveraendert — auch wenn ein anderes, spaeter startendes
 *    Fenster `until` ebenfalls enthaelt.
 *
 * Ein Future/Past-Filter VOR der Minimum-Bildung (statt danach) waere ein
 * Bug: ein bereits laufendes Fenster A (Start in der Vergangenheit) kann ein
 * kuenftiges Fenster B ueberlappen, das `until` ebenfalls enthaelt. Dann
 * gewinnt (weil A vor now startet) fuer den Backend-Vergleich A — kein
 * Clamp. Wuerde man A vorab herausfiltern, saehe die Vorschau faelschlich
 * ein Clamp auf B vor, das das Backend nie durchsetzt.
 */
import type { CoreUptimeOccurrence } from '../api/sleep';

export interface ClampResult {
  /** ISO-Zeitstempel, der gespeichert werden soll (gekuerzt oder original). */
  until: string;
  /** Das Fenster, auf dessen Beginn gekuerzt wurde — null, wenn nicht gekuerzt. */
  clampedTo: CoreUptimeOccurrence | null;
}

export function clampToCoreUptime(
  untilIso: string,
  occurrences: CoreUptimeOccurrence[],
  now: Date = new Date(),
): ClampResult {
  const until = new Date(untilIso).getTime();
  const nowMs = now.getTime();

  // Schritt 1: fruehesten Start ueber ALLE Occurrences finden, die `until`
  // enthalten — kein Future/Past-Filter an dieser Stelle (mirrors
  // `window_start_containing`).
  let earliest: CoreUptimeOccurrence | null = null;
  let earliestStart = Number.POSITIVE_INFINITY;

  for (const o of occurrences) {
    const start = new Date(o.start).getTime();
    const end = new Date(o.end).getTime();
    if (until >= start && until < end && start < earliestStart) {
      earliest = o;
      earliestStart = start;
    }
  }

  // Schritt 2: genau EIN Gate auf dem gefundenen Kandidaten (mirrors
  // `clamp_to_core_uptime_start`'s `start_local <= now_local` check).
  if (earliest === null || earliestStart <= nowMs) {
    return { until: untilIso, clampedTo: null };
  }
  return { until: earliest.start, clampedTo: earliest };
}

export function findRunningOccurrence(
  occurrences: CoreUptimeOccurrence[],
  now: Date = new Date(),
): CoreUptimeOccurrence | null {
  const nowMs = now.getTime();
  for (const o of occurrences) {
    // start inklusiv, end exklusiv — wie im Backend.
    if (new Date(o.start).getTime() <= nowMs && nowMs < new Date(o.end).getTime()) {
      return o;
    }
  }
  return null;
}
