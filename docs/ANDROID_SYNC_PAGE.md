# Mobile Folder Sync - Best Practices & Features

## Übersicht

Die verbesserte **Folder Sync Page** in der BaluHost Android App bietet ein intuitives Interface zum Verwalten von Ordner-Synchronisationen zwischen Smartphone und NAS.

## Features der neuen Sync-Seite

### 1. **Sync Summary Card** (Zusammenfassungskarte oben)
Prominente Anzeige von:
- **Letzter Sync-Zeitpunkt** - "Gerade eben", "vor 5 Min", "vor 2 Std", etc.
- **Aktive Synchronisationen** - Badge mit Anzahl der laufenden Syncs
- **Gesamtanzahl Ordner** - Wie viele Ordner insgesamt konfiguriert sind
- **Fehleranzahl** - Rot markiert, wenn Syncs fehlgeschlagen sind

### 2. **Manuelles Hinzufügen von Ordnern**
- **FAB-Button** (Floating Action Button) mit + Symbol
- Öffnet **Ordnerpicker-Dialog** zum Auswählen eines lokalen Ordners
- Automatische Berechtigungsprüfung vor Öffnen des Dialogs

### 3. **Storage-Berechtigungen Handling**
- **Automatische Prüfung** beim App-Start
- **Adaptive Berechtigungen** je nach Android-Version:
  - Android 13+: `READ_MEDIA_IMAGES`, `READ_MEDIA_VIDEO`
  - Android 11-12: `READ_EXTERNAL_STORAGE`, `MANAGE_EXTERNAL_STORAGE`
  - Android 10 und älter: `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`
- **Benutzerfreundlicher Dialog** mit Erklärung
- **Rationale** ("Warum braucht die App diese Berechtigung?")

### 4. **Pull-to-Refresh**
- Ziehen Sie die Liste nach unten, um manuell zu aktualisieren
- Lädt aktuelle Sync-Status und letzte Sync-Zeiten
- Nützlich nach manuellen Änderungen auf dem Server

### 5. **Sync Folder Card**
Jeder konfigurierte Ordner zeigt:
- **Remote-Pfad** (auf dem NAS)
- **Sync-Typ** (Upload/Download/Bidirektional)
- **Letzter Sync** mit relativer Zeit
- **Status-Icon**:
  - ✓ Grün: Idle (bereit)
  - ↻ Blau: Syncing (läuft)
  - ⚠ Rot: Error
  - ⏸ Orange: Paused
- **Fortschrittsbalken** während des Syncs
- **Sync-Button** zum manuellen Starten
- **Delete-Button** zum Entfernen

### 6. **Empty State**
Wenn keine Ordner konfiguriert sind:
- Großes Folder-Icon
- Klare Fehlermeldung
- **Schritt-für-Schritt Anleitung**:
  1. Tippen Sie auf + um einen lokalen Ordner zu wählen
  2. Geben Sie einen Pfad auf dem NAS ein
  3. Wählen Sie die Synchronisationsart

### 7. **Upload Queue**
- Zeigt alle ausstehenden Uploads
- Status für jede Datei (Pending, Uploading, Completed, Failed)
- Möglichkeit zum Abbrechen oder Wiederholen fehlgeschlagener Uploads
- Fortschrittsbalken für aktive Uploads

## Android Version-spezifische Anforderungen

### Storage Permissions nach Android-Version

```kotlin
// Android 13+ (API 33)
- android.Manifest.permission.READ_MEDIA_IMAGES
- android.Manifest.permission.READ_MEDIA_VIDEO

// Android 11-12 (API 30-32)
- android.Manifest.permission.READ_EXTERNAL_STORAGE
- android.Manifest.permission.MANAGE_EXTERNAL_STORAGE

// Android 10 und älter (API < 30)
- android.Manifest.permission.READ_EXTERNAL_STORAGE
- android.Manifest.permission.WRITE_EXTERNAL_STORAGE
```

### AndroidManifest.xml
```xml
<!-- Medien Permissions -->
<uses-permission android:name="android.permission.READ_MEDIA_IMAGES" />
<uses-permission android:name="android.permission.READ_MEDIA_VIDEO" />
<uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" android:maxSdkVersion="32" />
```

## Best Practices implementiert

### 1. **Permissions First**
- Berechtigungen werden geprüft, bevor Dateioperationen beginnen
- Benutzerfreundliche Erklärung warum Berechtigungen nötig sind
- Dialog mit "Später"-Option (kann später wieder angezeigt werden)

### 2. **Last Sync Prominently Displayed**
- Nicht versteckt in Listeneinträgen
- Zentral in Summary Card mit großem Icon
- Relative Zeitformate ("vor 5 Min") statt absolute Zeiten

### 3. **Clear Visual Feedback**
- Status-Icons für jeden Ordner
- Farbcodierung (Grün = OK, Blau = Aktiv, Rot = Fehler)
- Fortschrittsbars während des Syncs
- Badge-Counts für schnellen Überblick

### 4. **User Guidance**
- Empty State mit Schritt-für-Schritt Anleitung
- Tooltips und Beschreibungen
- Rationale für Berechtigungen

### 5. **Pull-to-Refresh**
- Standard Android Pattern für Updates
- Keine nervige Auto-Refresh
- User kontrolliert wann aktualisiert wird

### 6. **Scalability**
- LazyColumn für performante Listen
- Auch mit 100+ Ordnern responsive
- Smooth Animations und Transitions

## Verwendung in Code

### FolderSyncScreen.kt
```kotlin
@Composable
fun FolderSyncScreen(
    onNavigateBack: () -> Unit,
    viewModel: FolderSyncViewModel = hiltViewModel()
)
```

### PermissionHelper.kt
```kotlin
// Berechtigungen prüfen
if (!PermissionHelper.hasStoragePermissions(context)) {
    showPermissionDialog = true
}

// Berechtigungen anfordern
val permissionLauncher = rememberLauncherForActivityResult(
    contract = ActivityResultContracts.RequestMultiplePermissions()
) { permissions ->
    if (permissions.values.all { it }) {
        // Alle Berechtigungen gewährt
    }
}
```

## Zukunft Improvements

- [ ] Migrieren auf native `Modifier.pullRefresh()` (statt Accompanist)
- [ ] WebDAV und SMB Adapter für Remote-Ordner-Selection
- [ ] Sync-Schedule UI (täglich, wöchentlich, etc.)
- [ ] Bandwidth-Limits UI
- [ ] Conflict-Resolution Dialog
- [ ] Detaillierte Sync-Logs
- [ ] Pause/Resume Sync Buttons
- [ ] Ordner-Icons für verschiedene Typen (Photos, Documents, etc.)

## Debug Logging

Die App nutzt einen `Logger` für Debug-Informationen:

```kotlin
Logger.i("FolderSyncViewModel", "loadSyncFolders: loaded ${folders.size} folders")
Logger.e("FolderSyncViewModel", "loadSyncFolders failed", exception)
```

## Testing

Zum Testen der Sync-Seite:

1. **App starten** - Berechtigung-Dialog sollte angezeigt werden
2. **Berechtigung erteilen** - Danach can Ordner hinzugefügt werden
3. **Ordner hinzufügen** - Tippen Sie auf + Button
4. **Ordner-Picker öffnen** - Wählen Sie einen Ordner
5. **Sync konfigurieren** - Geben Sie Remote-Pfad ein
6. **Manuell Sync starten** - Tippen Sie Sync-Button
7. **Pull-to-Refresh** - Ziehen Sie die Liste nach unten
8. **Letzter Sync anschauen** - Summary Card sollte Zeit anzeigen

