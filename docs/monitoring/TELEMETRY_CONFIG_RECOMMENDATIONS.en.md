# Telemetry Configuration Recommendations

## Benchmark Results (Your System - Windows)

```
Average Sample Time: 3.80ms
CPU Impact @ 1s:     0.38%
CPU Impact @ 3s:     0.13%
```

## Recommended Configuration

### For Development (Windows)
```env
# backend/.env
TELEMETRY_INTERVAL_SECONDS=2.0
TELEMETRY_HISTORY_SIZE=90
```

**Rationale:**
- 2s interval = 30 samples/min = 0.19% CPU
- 90 samples = 3 minutes history
- Good balance between resolution and performance
- Charts are smooth enough for development purposes

### For Production (Linux/NAS)
```env
# backend/.env
TELEMETRY_INTERVAL_SECONDS=3.0
TELEMETRY_HISTORY_SIZE=60
```

**Rationale:**
- Linux is ~10x faster with psutil (~0.3ms instead of 3.8ms)
- NAS hardware is often less powerful
- 20 samples/min is sufficient for production monitoring
- 60 samples = 3 minutes history

## Frontend Polling

**Current:** 5 seconds (optimal)

```typescript
// client/src/hooks/useSystemTelemetry.ts
const pollInterval = 5000; // 5s - DO NOT change
```

**Why keep 5s:**
- With 2s backend + 5s frontend: frontend fetches 10 new samples per request
- Drastically reduces API calls
- Browser performance remains optimal
- Network traffic minimized

## If You Want Smoother Charts

Option 1: **Reduce backend interval** (Recommended)
```env
TELEMETRY_INTERVAL_SECONDS=1.5  # 40 samples/min
TELEMETRY_HISTORY_SIZE=120      # 3 minutes
```
→ CPU impact: 0.25% (negligible)
→ Charts become smoother
→ Frontend unchanged

Option 2: **Increase frontend polling** (NOT recommended)
```typescript
const pollInterval = 2000; // 2s
```
→ 5x more API requests
→ 5x more re-renders
→ Higher battery consumption
→ More network traffic

## Practical Test

Start the backend with:
```bash
# Temporary test
TELEMETRY_INTERVAL_SECONDS=1.5 python -m uvicorn app.main:app --reload
```

Then observe in the dashboard:
- CPU sparklines should be smoother
- Network charts show more detail
- No noticeable performance degradation

## Final Recommendation for Your Setup

**Backend (Windows Dev):**
```python
# backend/app/core/config.py
telemetry_interval_seconds: float = 2.0  # Balanced
telemetry_history_size: int = 90         # 3 min history
```

**Frontend:**
```typescript
// UNCHANGED - 5s is optimal
const pollInterval = 5000;
```

**Result:**
- 30 samples/minute → 6 new samples per frontend request
- 0.19% CPU (negligible)
- Smooth charts
- Minimal network traffic
