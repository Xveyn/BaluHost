# Nicht steuerbarer Lüfter → Board übernimmt (#534 Punkt 1)

Entwurf vom 2026-09-07. Setzt Punkt 1 um; Punkt 2 („Regelung fällt aus") bleibt offen und wird danach nur noch eine zweite Auslösebedingung an derselben Mechanik.

## Ausgangslage

BaluHost übernimmt beim Start jeden erkannten Lüfter (`pwm{n}_enable=1`). Beim Beenden gibt es die Kontrolle seit #556 zurück. **Im laufenden Betrieb nicht** — auch dann nicht, wenn feststeht, dass die eigene Regelung für diesen Kanal nicht funktioniert. Es bleibt ein Zustand, in dem niemand regelt: der Chip nicht, weil BaluHost seine Automatik abgeschaltet hat, und BaluHost nicht, weil es nicht schreiben kann.

Ein früherer Anlauf über alle drei Punkte sammelte **acht blockierende Befunde** ein und wurde auf Punkt 3 zurückgeschnitten. Die Befunde stehen in #534 und sind hier die Prüfliste, nicht der Hintergrund.

## Die geerbte Randbedingung

#556 gibt ausschliesslich einen Wert zurück, den BaluHost am selben Chip **selbst gelesen** hat (`pwm_enable >= 2`, vor dem ersten eigenen Write). Ein geratener Treibermodus wäre eine Annahme über fremde Hardware, und ein falsch geratener Wert stellte den Lüfter still ab.

Das gilt hier unverändert: **ein Kanal ohne Beobachtung wird nicht freigegeben.** Auf BaluNode betrifft das `pwm7` (kein beobachteter Wert) — dort bleibt es beim heutigen Verhalten, und das ist richtig so.

## Die acht Befunde und was der Entwurf ihnen entgegensetzt

| # | Befund | Antwort |
|---|---|---|
| 1 | Der Rückweg existiert nicht — eine UI-Sperre deaktiviert genau die Bedienelemente, über die man zurückkäme | Eigener Endpunkt `POST /api/fans/reacquire` und ein Knopf, den die Sperre **nicht** mitdeaktiviert |
| 2 | Der Auslöser ist von aussen nicht ablesbar (`_write_backoff` privat, kein Zugriff, Dev-Backend hat ihn nicht) | ABC-Erweiterung `write_failure_state(fan_id) -> (fail_count, at_cap)`, Linux liest das Backoff, Dev liefert `(0, False)` |
| 3 | „Erstmals am Deckel" feuert pro Prozess höchstens einmal | Die Bedingung ist ein **Zustand** („am Deckel **und** aktuell besessen"), keine Flanke |
| 4 | Nutzer-Klicks können die Freigabe auslösen — der Zähler steigt unabhängig von `force` | Erzwungene Writes (Nutzer, Notfall) zählen nicht mehr ins Backoff |
| 5 | Der Übersprung im Regelkreis darf den Sample-Puffer nicht mitnehmen | Kein `continue`: `target_pwm = fan.pwm_percent` wie bei `FIRMWARE_MANAGED` — der Write entfällt, der Sample läuft weiter |
| 6 | Vier Zustandsvariablen hängen daran | `_last_pwm_by_fan` bekommt den Ist-Wert (Folge von Punkt 5), `_hysteresis_state` wird bei der Freigabe gelöscht, `other_fan_pwms` bleibt der Ist-Wert (ein `sync`-Lüfter kopiert dann die Board-Kurve — plausibel), der Sample behält sein bestehendes Modus-Feld |
| 7 | Die Notfall-Emitter dürfen nicht mit übersprungen werden | Folge von Punkt 5: sie liegen oberhalb der Write-Entscheidung und laufen unverändert |
| 8 | Ein anzeigbarer Freigabe-Zustand braucht einen worker-übergreifenden Träger | Neue Spalte `fan_runtime_state.released_fans` (JSON), gelesen von jedem Worker — dasselbe Muster wie `denied_fan_ids` aus #568 |

## Auslösebedingung

Ein Kanal wird freigegeben, wenn **alle** vier Aussagen gelten:

1. Das Write-Backoff dieses Kanals steht am Deckel (`at_cap`) — mit den heutigen Konstanten der achte aufeinanderfolgende Fehlschlag aus dem Regelkreis.
2. BaluHost besitzt den Kanal gerade (er ist nicht schon freigegeben, nicht `FIRMWARE_MANAGED`).
3. Es gibt einen **beobachteten** Rückgabewert (`_restore_values[fan_id]`).
4. Der Lüfter ist aktiv konfiguriert (`config.is_active`).

Fehlt Nummer 3, bleibt der Kanal in Handsteuerung — sichtbar als eigener Zustand, damit die Oberfläche nicht „das Board regelt" behauptet, wo niemand regelt.

## Drei Zustände, nicht zwei

| Zustand | Bedeutung | Wer regelt |
|---|---|---|
| `owned` | Normalfall | BaluHost |
| `released` | Rückgabe geschrieben **und zurückgelesen** | die Board-Automatik |
| `abandoned` | Freigabe versucht, aber der Write scheiterte oder blieb wirkungslos | **niemand** |

`abandoned` ist bei einem nicht schreibbaren Kanal der wahrscheinliche Fall — es ist derselbe Knoten mit denselben Rechten. `release_to_board()` liefert diese Unterscheidung bereits: es schreibt, liest zurück und meldet `False`, wenn der Wert nicht anliegt.

Eine Oberfläche, die in diesem Fall „das Board regelt diesen Lüfter" anzeigt, lügt. Deshalb der dritte Zustand mit eigenem Text — und die Temperaturauswertung läuft in beiden Fällen weiter, die Notfallmeldung also auch.

## Rückweg

`POST /api/fans/reacquire` (Admin) entfernt den Kanal aus der veröffentlichten Menge. Der nächste Regelzyklus behandelt ihn wieder als besessen und **erzwingt genau einen Write** — sonst bliebe `pwm_enable` auf dem Auto-Wert stehen, falls das Board zufällig denselben PWM eingestellt hat wie die Kurve berechnet (der Regelkreis schreibt nur bei Wertänderung).

Der Knopf sitzt auf der Lüfterkarte und ist von der Sperre ausgenommen.

## Nicht-Ziele

- **Punkt 2** (Regelung fällt aus → Board). Braucht eine eigene, enger gefasste Bedingung (`mode`, `curve_type`, gesetzter Sensor) und eine Zeit- statt Zyklenschwelle. Die Mechanik hier ist so gebaut, dass Punkt 2 nur eine zweite Auslösebedingung ergänzt.
- **Automatische Wiederübernahme.** Ein Pendeln zwischen zwei Reglern ist der Zustand, den #534 ausdrücklich vermeiden will. Zurück geht es nur auf Knopfdruck.
- **Freigabe ohne beobachteten Wert.** Siehe die geerbte Randbedingung.
