/**
 * Kernbetriebszeit-Kuerzung fuer den Always-Awake-Override.
 *
 * Reiner Intervallvergleich auf bereits aufgeloesten Fenster-Terminen — die
 * Wochentags- und Mitternachtslogik bleibt im Backend
 * (`services/power/core_uptime.py`). Ergebnisse muessen mit
 * `clamp_to_core_uptime_start()` dort uebereinstimmen; darum gewinnt bei
 * Ueberlappung ebenfalls der FRUEHESTE Start.
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

  let best: CoreUptimeOccurrence | null = null;
  let bestStart = Number.POSITIVE_INFINITY;

  for (const o of occurrences) {
    const start = new Date(o.start).getTime();
    const end = new Date(o.end).getTime();
    // Nur kuenftige Fensterbeginne kuerzen: ein bereits laufendes Fenster
    // hat seinen Beginn in der Vergangenheit, da gibt es nichts zu kuerzen.
    if (start > nowMs && until >= start && until < end && start < bestStart) {
      best = o;
      bestStart = start;
    }
  }

  if (best === null) return { until: untilIso, clampedTo: null };
  return { until: best.start, clampedTo: best };
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
