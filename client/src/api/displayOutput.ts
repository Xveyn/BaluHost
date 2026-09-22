/**
 * API-Client der Displaysteuerung (bundled Plugin `display_output`).
 *
 * Alle Routen liegen hinter dem Recht `can_manage_displays` — auch die
 * lesende, weil die Ausgangsliste die angeschlossene Hardware verrät.
 *
 * Modi werden über `id` adressiert, nie über `name`: KWin bildet den Namen mit
 * gerundeter Bildwiederholrate, weshalb 119,88 und 120,00 Hz beide
 * „3840x2160@120" heißen. `mode_name` reist nur als Gegenprobe mit.
 */

import { apiClient } from '../lib/api';

const BASE = '/api/plugins/display_output';

export interface DisplayMode {
  /** Lebende KWin-Mode-ID. Nie speichern — sie gilt nur für diesen Abruf. */
  id: string;
  /** "3840x2160@120" — NICHT eindeutig. */
  name: string;
  width: number;
  height: number;
  /** Ungerundet, z. B. 119.87999725341797. */
  refresh_rate: number;
}

export interface DisplayOutput {
  name: string;
  connected: boolean;
  /** KWin-Ebene: ist dieser Ausgang gewählt? */
  selected: boolean;
  /** DRM-Ebene: werden Pixel getrieben? null = nicht zuordenbar. */
  lit: boolean | null;
  current_mode_id: string | null;
  preferred_mode_id: string | null;
  scale: number;
  priority: number;
  modes: DisplayMode[];
}

/**
 * Untergrenze, die die Oberfläche setzen darf.
 *
 * KDE selbst erlaubt 0. Hier ist es bewusst enger: ein Regler aus der Ferne
 * darf den Menschen am Schreibtisch nicht vor einem schwarzen Bildschirm
 * sitzen lassen. Das Backend lehnt alles darunter mit 422 ab — diese Konstante
 * ist dieselbe Zusage im `min`-Attribut des Reglers.
 */
export const MIN_BRIGHTNESS_PERCENT = 5;

export interface BrightnessDisplay {
  /**
   * Lebender powerdevil-Objektname, z. B. „display13". Nie speichern — er
   * hängt am KWin-Output und ist nach einem Neustart ein anderer.
   */
  id: string;
  /** EDID-Name; fällt serverseitig auf die ID zurück, wenn er leer ist. */
  label: string;
  /** Eingebautes Panel statt externem Bildschirm. */
  internal: boolean;
  /** 0–100. Die Geräteskala bleibt serverseitig. */
  percent: number;
}

export interface BrightnessInfo {
  /**
   * Getrennt von `DisplayLayout.available`: KWin kann laufen, während
   * powerdevil fehlt. `false` mit leerer Liste heißt „keine Auskunft",
   * `true` mit leerer Liste heißt „nichts steuerbar" — zwei verschiedene
   * Aussagen, die die UI verschieden anzeigt.
   */
  available: boolean;
  displays: BrightnessDisplay[];
  detail: string | null;
}

export interface DisplayLayout {
  outputs: DisplayOutput[];
  displays_powered: boolean;
  available: boolean;
  detail: string | null;
  /**
   * Die Helligkeit reist im Zustand mit, statt in einer eigenen Route zu
   * liegen: das Popover pollt alle 5 s gegen ein Limit von 60/min.
   *
   * Nicht deckungsgleich mit `outputs` — powerdevil führt nur eingeschaltete,
   * steuerbare Bildschirme und vergibt eigene Objektnamen. Eine Zuordnung
   * Objekt ↔ Connector gibt die Schnittstelle nicht her.
   */
  brightness: BrightnessInfo;
}

export interface DisplayOutputWish {
  name: string;
  selected: boolean;
  mode_id?: string;
  /** Pflicht, sobald mode_id gesetzt ist. */
  mode_name?: string;
}

/** Liest Ausgänge, Modi und den globalen DPMS-Zustand in einem Rundlauf. */
export async function getDisplayLayout(): Promise<DisplayLayout> {
  const { data } = await apiClient.get<DisplayLayout>(`${BASE}/state`);
  return data;
}

/** Setzt Auswahl und Modus — ein Aufruf, den das Backend atomar anwendet. */
export async function applyDisplayLayout(outputs: DisplayOutputWish[]): Promise<void> {
  await apiClient.post(`${BASE}/apply`, { outputs });
}

/**
 * Setzt die Helligkeit eines Bildschirms.
 *
 * `id` muss aus der letzten Antwort von `getDisplayLayout()` stammen: das
 * Backend prüft sie gegen die Enumeration desselben Vorgangs und antwortet mit
 * 400, wenn sie dort nicht steht. Aufrufer entprellen — ein Reglerzug erzeugt
 * Dutzende Änderungen, und jede wäre ein D-Bus-Aufruf.
 */
export async function setDisplayBrightness(id: string, percent: number): Promise<void> {
  await apiClient.post(`${BASE}/brightness`, { id, percent });
}

/**
 * Beschriftet einen Modus für das Auswahlfeld.
 *
 * Zwei Nachkommastellen sind nicht Kosmetik: sie sind das Einzige, woran ein
 * Mensch die beiden 4K-Modi von DP-3 auseinanderhält. Formatiert wird hier und
 * nicht im Backend, weil das Dezimaltrennzeichen sprachabhängig ist.
 */
export function formatMode(mode: DisplayMode, locale: string): string {
  const hz = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(mode.refresh_rate);
  return `${mode.width} × ${mode.height} @ ${hz} Hz`;
}
