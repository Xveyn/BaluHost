# Telemetrie-Konfiguration Empfehlungen

## Benchmark-Ergebnisse (Dein System - Windows)

```
Average Sample Time: 3.80ms
CPU Impact @ 1s:     0.38%
CPU Impact @ 3s:     0.13%
```

## Empfohlene Konfiguration

### Für Development (Windows)
```env
# backend/.env
TELEMETRY_INTERVAL_SECONDS=2.0
TELEMETRY_HISTORY_SIZE=90
```

**Begründung:**
- 2s Intervall = 30 samples/min = 0.19% CPU
- 90 Samples = 3 Minuten History
- Guter Kompromiss zwischen Auflösung und Performance
- Charts sind flüssig genug für Dev-Zwecke

### Für Production (Linux/NAS)
```env
# backend/.env
TELEMETRY_INTERVAL_SECONDS=3.0
TELEMETRY_HISTORY_SIZE=60
```

**Begründung:**
- Linux ist ~10x schneller bei psutil (~0.3ms statt 3.8ms)
- NAS-Hardware ist oft schwächer
- 20 samples/min reichen für Production-Monitoring
- 60 Samples = 3 Minuten History

## Frontend-Polling

**Aktuell:** 5 Sekunden (optimal)

```typescript
// client/src/hooks/useSystemTelemetry.ts
const pollInterval = 5000; // 5s - NICHT ändern
```

**Warum 5s beibehalten:**
- Bei 2s Backend + 5s Frontend: Frontend holt 10 neue Samples pro Request
- Reduziert API-Calls drastisch
- Browser-Performance bleibt optimal
- Netzwerk-Traffic minimiert

## Wenn du flüssigere Charts willst

Option 1: **Backend-Intervall reduzieren** (Empfohlen)
```env
TELEMETRY_INTERVAL_SECONDS=1.5  # 40 samples/min
TELEMETRY_HISTORY_SIZE=120      # 3 Minuten
```
→ CPU Impact: 0.25% (völlig egal)
→ Charts werden flüssiger
→ Frontend unverändert

Option 2: **Frontend-Polling erhöhen** (NICHT empfohlen)
```typescript
const pollInterval = 2000; // 2s
```
→ 5x mehr API-Requests
→ 5x mehr Re-Renders
→ Höherer Batterieverbrauch
→ Mehr Netzwerk-Traffic

## Praktischer Test

Starte den Backend mit:
```bash
# Temporär testen
TELEMETRY_INTERVAL_SECONDS=1.5 python -m uvicorn app.main:app --reload
```

Dann im Dashboard beobachten:
- CPU-Sparklines sollten flüssiger sein
- Netzwerk-Charts zeigen mehr Detail
- Keine spürbare Performance-Verschlechterung

## Finale Empfehlung für dein Setup

**Backend (Windows Dev):**
```python
# backend/app/core/config.py
telemetry_interval_seconds: float = 2.0  # Ausgewogen
telemetry_history_size: int = 90         # 3 Min History
```

**Frontend:**
```typescript
// UNCHANGED - 5s ist optimal
const pollInterval = 5000;
```

**Resultat:**
- 30 Samples/Minute → 6 neue Samples pro Frontend-Request
- 0.19% CPU (vernachlässigbar)
- Flüssige Charts
- Minimaler Netzwerk-Traffic
