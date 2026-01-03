# Sprint 3 - Build Errors - Inkomplett ⚠️

**Status:** ❌ Build fehlgeschlagen - zu viele Compile-Fehler

## Haupt-Probleme:

### 1. Logger API Mismatch
- `Logger::getInstance()` existiert nicht → Sollte static methods sein
- `spdlog::level::error` ist falsch → `spdlog::level::err`
- Missing `#include <iostream>` für std::cerr

### 2. Forward Declaration Issues
- FileWatcher/ConflictResolver als forward declarations aber incomplete types
- Sollten vollständige Includes sein in sync_engine.cpp

### 3. Database API Mismatch
- `getFileMetadata()` returns `FileMetadata` nicht `std::optional<FileMetadata>`
- `upsertFileMetadata()` hat falsche Signatur (5 statt 4 Parameter)
- `getFilesInFolder()` existiert nicht
- `updateSyncFolderTimestamp()` existiert nicht

### 4. Missing chrono includes in Headers
- conflict_resolver.h braucht `#include <chrono>`

### 5. Windows-spezifische Warnings als Errors
- size_t → int conversions
- Unreferenced parameters
- wchar_t → char string conversions

## Empfehlung:

**Sprint 3 ist zu komplex für initial build!**

Stattdessen:
1. ✅ Sprint 1 + 2 bauen (ohne ChangeDetector/ConflictResolver)
2. ✅ Database/Logger APIs stabilisieren
3. Dann Sprint 3 incrementell hinzufügen

## Next Steps:

1. Erstelle Simplified Build (nur Sprint 1 + 2)
2. Fixe alle API Mismatches
3. Dann Sprint 3 Step-by-Step

---

**Entwickelt:** 3. Januar 2026  
**Status:** Zurück zu Sprint 1+2 Build
