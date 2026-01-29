# Test-Plan: Refactoring-Verification

## Aufgabe
Umfassende Test-Strategie zur Verifikation der abgeschlossenen CRITICAL Refactorings:
- ✅ FilesRepositoryImpl (Commit 49f792e)
- ✅ AuthRepositoryImpl (Commit 7cedc6e)
- ✅ NetworkStateManager (Commit e8e4f50)
- ✅ Logger-Abstraction (Commit dc3cdc2)

## Kontext

**Abgeschlossene Änderungen (nicht gepusht, nur committed):**

1. **FilesRepositoryImpl** - 11 Methoden implementiert mit Cache-First Strategy
2. **AuthRepositoryImpl** - 6 Methoden mit Secure Token Storage
3. **NetworkStateManagerImpl** - Reactive VPN/Network Monitoring ohne Context in ViewModels
4. **Logger Interface + AndroidLogger** - 27 Log-Aufrufe in 5 Use Cases refactored

**Test-Infrastruktur vorhanden:**
- JUnit 4.13.2
- MockK 1.13.12 (Kotlin-native mocking)
- Coroutines Test 1.8.1
- Turbine 1.1.0 (Flow testing)
- Truth 1.4.4 (assertions)
- Hilt Testing 2.51.1
- MockWebServer 4.12.0

**Bestehende Tests:**
- 9 Test-Dateien in `test/` directory
- Beispiel-Pattern in GetFilesUseCaseTest.kt, DeleteFileUseCaseTest.kt

---

## Phase 1: Unit Tests (Isolation Testing)

**Ziel:** Teste jede neue Komponente isoliert mit Mocks.

### Test 1.1: FilesRepositoryImpl Tests 🟠 HIGH PRIORITY
**Zeitaufwand:** 2-3 Stunden | **Coverage-Ziel:** 80%+

**Neue Datei:** `app/src/test/java/com/baluhost/android/data/repository/FilesRepositoryImplTest.kt`

**Test-Cases:**

```kotlin
@Test
fun `getFiles returns cached data when cache is valid`() = runTest {
    // Setup: Cache mit gültigen Daten (vor 2 Minuten cached)
    // Mock: fileDao.getFilesByPath() returns cached entities
    // Verify: Kein API-Call, cached data returned
}

@Test
fun `getFiles refreshes when cache is stale (older than 5 minutes)`() = runTest {
    // Setup: Cache mit alten Daten (vor 6 Minuten cached)
    // Mock: fileDao returns stale entities, filesApi returns fresh data
    // Verify: API-Call erfolgt, cache wird aktualisiert
}

@Test
fun `getFiles forces refresh when forceRefresh is true`() = runTest {
    // Setup: Cache mit gültigen Daten
    // Mock: forceRefresh = true
    // Verify: API-Call trotz gültigem Cache
}

@Test
fun `refreshFiles updates cache on successful API call`() = runTest {
    // Mock: filesApi.listFiles() returns FileListResponse
    // Verify: fileDao.clearPath() + insertFiles() called
    // Verify: Result.Success returned
}

@Test
fun `uploadFile sends multipart request correctly`() = runTest {
    // Mock: filesApi.uploadFile() succeeds
    // Verify: Correct MultipartBody.Part created
    // Verify: Cache invalidated after upload
}

@Test
fun `uploadFile returns Error on network failure`() = runTest {
    // Mock: filesApi.uploadFile() throws IOException
    // Verify: Result.Error returned with message
}

@Test
fun `deleteFile invalidates cache after deletion`() = runTest {
    // Mock: filesApi.deleteFile() succeeds
    // Verify: fileDao.clearPath() called
    // Verify: Result.Success(true) returned
}

@Test
fun `moveFile invalidates both source and destination cache`() = runTest {
    // Mock: filesApi.moveFile() succeeds
    // Verify: cache cleared for both paths
}

@Test
fun `renameFile updates cache correctly`() = runTest {
    // Mock: filesApi.renameFile() returns updated FileItem
    // Verify: Old cache cleared, new item cached
}

@Test
fun `getFileMetadata returns cached data if available`() = runTest {
    // Mock: fileDao.getFileByPath() returns entity
    // Verify: No API call if cache valid
}

@Test
fun `clearCache deletes all cached files`() = runTest {
    // Mock: fileDao.clearAllFiles() succeeds
    // Verify: Result.Success returned
}

@Test
fun `cleanOldCache removes files older than specified days`() = runTest {
    // Mock: fileDao.deleteOlderThan() returns deleted count
    // Verify: Correct Instant calculation (daysOld = 7)
}
```

**Mocking Strategy:**
```kotlin
class FilesRepositoryImplTest {
    @get:Rule
    val instantExecutorRule = InstantTaskExecutorRule()

    private lateinit var filesApi: FilesApi
    private lateinit var fileDao: FileDao
    private lateinit var repository: FilesRepositoryImpl

    @Before
    fun setup() {
        filesApi = mockk()
        fileDao = mockk(relaxed = true)
        repository = FilesRepositoryImpl(filesApi, fileDao)
    }

    @After
    fun teardown() {
        clearAllMocks()
    }
}
```

**Verification Commands:**
```bash
# Run FilesRepositoryImpl tests
./gradlew test --tests "com.baluhost.android.data.repository.FilesRepositoryImplTest"

# Coverage report
./gradlew testDebugUnitTestCoverage
# Report: app/build/reports/coverage/test/debug/index.html
```

---

### Test 1.2: AuthRepositoryImpl Tests 🟠 HIGH PRIORITY
**Zeitaufwand:** 1-2 Stunden | **Coverage-Ziel:** 90%+

**Neue Datei:** `app/src/test/java/com/baluhost/android/data/repository/AuthRepositoryImplTest.kt`

**Test-Cases:**

```kotlin
@Test
fun `login saves tokens and user info on success`() = runTest {
    // Mock: authApi.login() returns LoginResponse
    // Verify: preferencesManager saves accessToken, refreshToken, userId, username, role
    // Verify: Result.Success with User domain model
}

@Test
fun `login returns Error on 401 Unauthorized`() = runTest {
    // Mock: authApi.login() throws HttpException(401)
    // Verify: Result.Error with "Invalid username or password"
}

@Test
fun `login returns Error on 403 Forbidden (inactive account)`() = runTest {
    // Mock: authApi.login() throws HttpException(403)
    // Verify: Result.Error with "Account is inactive"
}

@Test
fun `login handles network errors gracefully`() = runTest {
    // Mock: authApi.login() throws IOException
    // Verify: Result.Error with "Login failed: ..." message
}

@Test
fun `refreshToken updates access token on success`() = runTest {
    // Mock: preferencesManager.getRefreshToken() returns "refresh_token_123"
    // Mock: authApi.refreshToken() returns RefreshTokenResponse
    // Verify: preferencesManager.saveAccessToken() called
    // Verify: Result.Success with new access token
}

@Test
fun `refreshToken clears tokens on 401 error (expired refresh token)`() = runTest {
    // Mock: authApi.refreshToken() throws HttpException(401)
    // Verify: preferencesManager clears all tokens
    // Verify: Result.Error returned
}

@Test
fun `logout clears all tokens and user data`() = runTest {
    // Verify: preferencesManager.clearAccessToken(), clearRefreshToken(), etc. called
    // Verify: Result.Success returned
}

@Test
fun `isAuthenticated returns true when access token exists`() = runTest {
    // Mock: preferencesManager.getAccessToken() returns "token"
    // Verify: true returned
}

@Test
fun `isAuthenticated returns false when no access token`() = runTest {
    // Mock: preferencesManager.getAccessToken() returns null
    // Verify: false returned
}

@Test
fun `getAccessToken returns token from preferences`() = runTest {
    // Mock: preferencesManager.getAccessToken().first() returns "token_123"
    // Verify: "token_123" returned
}
```

**Mocking with Flow:**
```kotlin
class AuthRepositoryImplTest {
    private lateinit var authApi: AuthApi
    private lateinit var preferencesManager: PreferencesManager
    private lateinit var repository: AuthRepositoryImpl

    @Before
    fun setup() {
        authApi = mockk()
        preferencesManager = mockk(relaxed = true)
        repository = AuthRepositoryImpl(authApi, preferencesManager)

        // Mock Flow returns
        coEvery { preferencesManager.getAccessToken() } returns flowOf("token")
        coEvery { preferencesManager.getRefreshToken() } returns flowOf("refresh")
    }
}
```

**Verification:**
```bash
./gradlew test --tests "com.baluhost.android.data.repository.AuthRepositoryImplTest"
```

---

### Test 1.3: NetworkStateManagerImpl Tests 🟡 MEDIUM PRIORITY
**Zeitaufwand:** 1-2 Stunden | **Coverage-Ziel:** 75%+

**Neue Datei:** `app/src/test/java/com/baluhost/android/data/network/NetworkStateManagerImplTest.kt`

**Test-Cases:**

```kotlin
@Test
fun `isVpnActive returns true when VPN transport is active`() {
    // Setup: Mock ConnectivityManager with VPN capabilities
    // Mock: networkCapabilities.hasTransport(TRANSPORT_VPN) returns true
    // Verify: isVpnActive() returns true
}

@Test
fun `isVpnActive returns false when no VPN transport`() {
    // Mock: networkCapabilities.hasTransport(TRANSPORT_VPN) returns false
    // Verify: isVpnActive() returns false
}

@Test
fun `isVpnActive returns false on exception`() {
    // Mock: connectivityManager.getActiveNetwork() throws SecurityException
    // Verify: isVpnActive() returns false (graceful error handling)
}

@Test
fun `observeVpnStatus emits true when VPN connects`() = runTest {
    // Mock: NetworkCallback receives onCapabilitiesChanged with VPN
    // Verify: Flow emits true
}

@Test
fun `observeVpnStatus emits false when VPN disconnects`() = runTest {
    // Mock: NetworkCallback receives onCapabilitiesChanged without VPN
    // Verify: Flow emits false
}

@Test
fun `observeVpnStatus emits initial state immediately`() = runTest {
    // Mock: Current VPN state is true
    // Verify: Flow emits true as first value
}

@Test
fun `observeVpnStatus uses distinctUntilChanged`() = runTest {
    // Mock: Multiple callbacks with same VPN state
    // Verify: Flow only emits on state changes (not duplicates)
}

@Test
fun `isOnline returns true when network is available`() {
    // Mock: networkCapabilities.hasCapability(NET_CAPABILITY_INTERNET)
    // Verify: true returned
}

@Test
fun `isWifi returns true when connected via WiFi`() {
    // Mock: networkCapabilities.hasTransport(TRANSPORT_WIFI)
    // Verify: true returned
}
```

**Mocking Android System Services:**
```kotlin
@RunWith(RobolectricTestRunner::class)
class NetworkStateManagerImplTest {
    private lateinit var context: Context
    private lateinit var connectivityManager: ConnectivityManager
    private lateinit var networkStateManager: NetworkStateManagerImpl

    @Before
    fun setup() {
        context = mockk()
        connectivityManager = mockk()

        every {
            context.getSystemService(Context.CONNECTIVITY_SERVICE)
        } returns connectivityManager

        networkStateManager = NetworkStateManagerImpl(context)
    }
}
```

**NOTE:** NetworkStateManager benötigt Android-spezifische Klassen (ConnectivityManager).
- **Option A:** Robolectric (Android emulation in JVM)
- **Option B:** Instrumented Test (auf Emulator/Device)
- **Empfehlung:** Option A für schnellere Tests

**Dependencies hinzufügen (falls Robolectric benötigt):**
```kotlin
// app/build.gradle.kts
testImplementation("org.robolectric:robolectric:4.11.1")
```

**Verification:**
```bash
./gradlew test --tests "com.baluhost.android.data.network.NetworkStateManagerImplTest"
```

---

### Test 1.4: Logger Tests 🟢 LOW PRIORITY
**Zeitaufwand:** 30 Minuten | **Coverage-Ziel:** 100%

**Neue Datei:** `app/src/test/java/com/baluhost/android/data/util/AndroidLoggerTest.kt`

**Test-Cases:**

```kotlin
@Test
fun `debug logs with correct tag and message`() {
    // Call: logger.debug("MyTag", "Debug message")
    // Verify: Log.d() called with correct parameters (via Robolectric ShadowLog)
}

@Test
fun `error logs with throwable`() {
    // Call: logger.error("MyTag", "Error", exception)
    // Verify: Log.e() called with tag, message, throwable
}

@Test
fun `warn logs without throwable`() {
    // Call: logger.warn("MyTag", "Warning")
    // Verify: Log.w() called
}

@Test
fun `info logs correctly`() {
    // Call: logger.info("MyTag", "Info")
    // Verify: Log.i() called
}
```

**Robolectric Logging Verification:**
```kotlin
@RunWith(RobolectricTestRunner::class)
class AndroidLoggerTest {
    private lateinit var logger: AndroidLogger

    @Before
    fun setup() {
        logger = AndroidLogger()
        ShadowLog.stream = System.out  // Log to console
    }

    @Test
    fun `debug logs message`() {
        logger.debug("TEST", "Test message")

        val logs = ShadowLog.getLogsForTag("TEST")
        assertEquals(1, logs.size)
        assertEquals("Test message", logs[0].msg)
    }
}
```

**Verification:**
```bash
./gradlew test --tests "com.baluhost.android.data.util.AndroidLoggerTest"
```

---

## Phase 2: Integration Tests

**Ziel:** Teste Zusammenspiel der Komponenten (Use Cases → Repositories → API/DB).

### Test 2.1: GetFilesUseCase Integration Test
**Zeitaufwand:** 1 Stunde

**Erweitere:** `app/src/test/java/com/baluhost/android/domain/usecase/files/GetFilesUseCaseTest.kt`

**Neuer Test-Case:**
```kotlin
@Test
fun `GetFilesUseCase uses FilesRepository correctly`() = runTest {
    // Setup: Real FilesRepository mit mocked dependencies
    val filesApi = mockk<FilesApi>()
    val fileDao = mockk<FileDao>(relaxed = true)
    val repository = FilesRepositoryImpl(filesApi, fileDao)
    val useCase = GetFilesUseCase(repository)

    // Mock: API returns files
    coEvery { filesApi.listFiles("documents") } returns FileListResponse(
        files = listOf(
            FileItemDto(name = "file1.txt", path = "documents/file1.txt", ...)
        )
    )

    // Mock: DAO returns empty (cache miss)
    every { fileDao.getFilesByPath("documents") } returns flowOf(emptyList())

    // Execute
    val result = useCase("documents")

    // Verify: API called, cache updated, result correct
    assertTrue(result is Result.Success)
    coVerify { filesApi.listFiles("documents") }
    coVerify { fileDao.insertFiles(any()) }
}
```

---

### Test 2.2: VpnViewModel Integration Test (Context-Free)
**Zeitaufwand:** 1 Stunde

**Erweitere:** `app/src/test/java/com/baluhost/android/presentation/ui/screens/vpn/VpnViewModelTest.kt`

**Neuer Test-Case:**
```kotlin
@Test
fun `VpnViewModel uses NetworkStateManager without Context`() = runTest {
    // Setup: Real NetworkStateManager mock
    val networkStateManager = mockk<NetworkStateManager>()
    val vpnRepository = mockk<VpnRepository>()
    val preferencesManager = mockk<PreferencesManager>()

    every { networkStateManager.isVpnActive() } returns false
    every { networkStateManager.observeVpnStatus() } returns flowOf(false, true)

    val viewModel = VpnViewModel(
        fetchVpnConfigUseCase = mockk(),
        connectVpnUseCase = mockk(),
        disconnectVpnUseCase = mockk(),
        preferencesManager = preferencesManager,
        networkStateManager = networkStateManager  // ✅ No Context!
    )

    // Verify: ViewModel reacts to VPN status changes
    viewModel.uiState.test {
        val state1 = awaitItem()
        assertFalse(state1.isConnected)

        // Trigger VPN connection
        // ...

        val state2 = awaitItem()
        assertTrue(state2.isConnected)
    }
}
```

---

## Phase 3: Architecture Verification Tests

**Ziel:** Automatisierte Architektur-Regeln testen.

### Test 3.1: Domain Layer Dependency Rule Test
**Zeitaufwand:** 1 Stunde

**Neue Datei:** `app/src/test/java/com/baluhost/android/ArchitectureTest.kt`

**Benötigt:** ArchUnit Library
```kotlin
// app/build.gradle.kts
testImplementation("com.tngtech.archunit:archunit-junit4:1.2.1")
```

**Test-Code:**
```kotlin
import com.tngtech.archunit.core.domain.JavaClasses
import com.tngtech.archunit.core.importer.ClassFileImporter
import com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses
import org.junit.Test

class ArchitectureTest {

    private val importedClasses: JavaClasses = ClassFileImporter()
        .importPackages("com.baluhost.android")

    @Test
    fun `domain layer should not depend on Android framework`() {
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat().resideInAnyPackage(
                "android..",
                "androidx..",
                "com.google.android.."
            )
            .because("Domain layer must be framework-independent")
            .check(importedClasses)
    }

    @Test
    fun `domain layer should not depend on data or presentation layer`() {
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat().resideInAnyPackage(
                "..data..",
                "..presentation.."
            )
            .because("Domain layer is the core, it should not depend on outer layers")
            .check(importedClasses)
    }

    @Test
    fun `repositories should have interfaces in domain layer`() {
        classes()
            .that().haveSimpleNameEndingWith("RepositoryImpl")
            .should().implement(assignableTo("..domain.repository.."))
            .because("All repositories must implement domain interfaces")
            .check(importedClasses)
    }

    @Test
    fun `ViewModels should extend ViewModel and use StateFlow`() {
        classes()
            .that().resideInAPackage("..presentation..")
            .and().haveSimpleNameEndingWith("ViewModel")
            .should().beAssignableTo("androidx.lifecycle.ViewModel")
            .check(importedClasses)
    }
}
```

**EXPECTED FAILURES (bekannte Violations):**
- 6 Dateien im Domain Layer haben noch Android-Dependencies (siehe Explore-Agent Report):
  - RegisterDeviceUseCase.kt (Build, OkHttp, Retrofit)
  - ImportVpnConfigUseCase.kt (Context, Base64)
  - ClearCacheUseCase.kt (Context)
  - ConnectVpnUseCase.kt (Context, Intent)
  - DisconnectVpnUseCase.kt (Context, Intent)
  - SyncModels.kt (android.net.Uri) - AKZEPTABEL

**Verification:**
```bash
./gradlew test --tests "com.baluhost.android.ArchitectureTest"

# Expected: 5 failures (RegisterDevice, ImportVpn, ClearCache, Connect/DisconnectVpn)
# SyncModels.kt Uri-Import ist akzeptabel für Models
```

---

### Test 3.2: Logger Usage Verification
**Zeitaufwand:** 30 Minuten

**Test:** Sicherstellen, dass keine `android.util.Log` Aufrufe mehr im Domain Layer existieren.

**Bash-Script:** `scripts/verify_no_android_log.sh`
```bash
#!/bin/bash

# Search for android.util.Log imports in domain layer
LOG_IMPORTS=$(grep -r "import android.util.Log" app/src/main/java/com/baluhost/android/domain/)

if [ -n "$LOG_IMPORTS" ]; then
    echo "❌ FAILED: Found android.util.Log imports in domain layer:"
    echo "$LOG_IMPORTS"
    exit 1
else
    echo "✅ PASSED: No android.util.Log imports in domain layer"
    exit 0
fi
```

**Verification:**
```bash
chmod +x scripts/verify_no_android_log.sh
./scripts/verify_no_android_log.sh
```

---

## Phase 4: Build & Compilation Tests

**Ziel:** Sicherstellen, dass die App kompiliert und keine Build-Errors existieren.

### Test 4.1: Gradle Build Test
**Zeitaufwand:** 5 Minuten

```bash
# Clean build
./gradlew clean

# Debug build (development)
./gradlew assembleDebug

# Verify APK exists
ls -lh app/build/outputs/apk/debug/app-debug.apk

# Release build (production)
./gradlew assembleRelease

# Verify release APK
ls -lh app/build/outputs/apk/release/app-release.apk
```

**Expected:**
- ✅ BUILD SUCCESSFUL in ~2-3 minutes
- ✅ APK size: ~20-30 MB (debug), ~8-15 MB (release)

**Troubleshooting:**
- Build failures: Check Gradle console for exact error
- Duplicate class errors: `./gradlew clean`
- Hilt errors: `./gradlew :app:kaptDebugKotlin --rerun-tasks`

---

### Test 4.2: Lint & Code Quality Check
**Zeitaufwand:** 5 Minuten

```bash
# Run Android Lint
./gradlew lint

# View report
cat app/build/reports/lint-results-debug.txt

# Kotlin code style check (detekt, if configured)
./gradlew detekt
```

**Expected Lint Warnings (bekannt):**
- Hardcoded Strings (geplant in MEDIUM Priority Tasks)
- Missing Content Descriptions (geplant in MEDIUM Priority Tasks)

---

## Phase 5: Manual Testing (Functional Verification)

**Ziel:** Teste die Funktionalität der refactored Komponenten in der laufenden App.

### Test 5.1: FilesRepositoryImpl Manual Test
**Zeitaufwand:** 15 Minuten

**Schritte:**
1. **App starten** auf Emulator/Device
2. **Login** mit QR-Code oder gespeicherten Credentials
3. **Navigiere zu Files Screen**
4. **Teste Cache-First Strategy:**
   - Lade Dateiliste (erwarte: API-Call)
   - Navigiere zurück, dann wieder zu Files (erwarte: Cache-Hit, kein Spinner)
   - Warte 5 Minuten
   - Pull-to-Refresh (erwarte: Cache-Invalidierung, API-Call)

5. **Teste Upload:**
   - Wähle Datei aus
   - Upload starten
   - Erwarte: Upload-Fortschritt, Success-Toast
   - Verify: Datei erscheint in Liste

6. **Teste Delete:**
   - Long-press auf Datei
   - Delete wählen
   - Erwarte: Datei verschwindet sofort (Optimistic UI)
   - Verify: Cache invalidiert

**Logcat-Filtering:**
```bash
# Watch FilesRepository logs
adb logcat | grep "FilesRepository"

# Expected logs:
# - "Fetching files from cache for path: documents"
# - "Cache stale, refreshing files from network"
# - "Uploaded file: test.txt, invalidating cache"
```

---

### Test 5.2: AuthRepositoryImpl Manual Test
**Zeitaufwand:** 10 Minuten

**Schritte:**
1. **Logout** (falls eingeloggt)
2. **Login mit korrekten Credentials**
   - Erwarte: Success, Navigation zum Dashboard
   - Verify Logcat: "Saved access token", "Saved refresh token"

3. **Login mit falschen Credentials**
   - Erwarte: Error-Toast "Invalid username or password"

4. **Token Refresh Test:**
   - Force token expiration (ändere Access Token in Preferences zu altem Wert)
   - API-Call durchführen (z.B. Dateiliste laden)
   - Erwarte: Automatic token refresh, API-Call erfolgt

5. **Logout Test:**
   - Logout-Button
   - Erwarte: Tokens gelöscht, Navigation zu QR-Screen
   - Verify: Erneuter Login erforderlich

**Logcat-Filtering:**
```bash
adb logcat | grep "AuthRepository\|AuthInterceptor"

# Expected logs:
# - "Login successful for user: admin"
# - "Token expired, refreshing..."
# - "Logout: Cleared all tokens"
```

---

### Test 5.3: NetworkStateManager Manual Test
**Zeitaufwand:** 10 Minuten

**Schritte:**
1. **App starten ohne VPN**
   - Erwarte: VPN-Status Banner "Nicht im Heimnetzwerk" (falls nicht im lokalen Netz)

2. **VPN aktivieren:**
   - Navigiere zu VPN Screen
   - "Verbinden" klicken
   - Erwarte: VPN-Status ändert sich zu "Verbunden"
   - Verify: VPN Banner verschwindet

3. **VPN deaktivieren:**
   - "Trennen" klicken
   - Erwarte: VPN-Status ändert sich zu "Getrennt"
   - Verify: VPN Banner erscheint wieder

4. **Network Status Test:**
   - Flugmodus aktivieren
   - Erwarte: Offline-Indicator erscheint
   - Flugmodus deaktivieren
   - Erwarte: Online-Indicator, Offline-Queue startet Retry

**Logcat-Filtering:**
```bash
adb logcat | grep "NetworkStateManager\|VpnViewModel"

# Expected logs:
# - "VPN status changed: true"
# - "Network online: true"
# - "WiFi connection detected"
```

---

### Test 5.4: Logger Integration Test
**Zeitaufwand:** 5 Minuten

**Schritte:**
1. **App starten**
2. **Navigiere durch verschiedene Screens**
3. **Trigger verschiedene Actions** (File Upload, VPN Connect, etc.)

**Logcat-Filtering:**
```bash
adb logcat | grep "GetFilesUseCase\|UploadFileUseCase\|FetchVpnConfigUseCase"

# Expected logs (mit Logger Interface):
# - "GetFilesUseCase: Loading files for path: documents"
# - "UploadFileUseCase: Uploading file: test.txt"
# - "FetchVpnConfigUseCase: Fetching VPN config"

# NICHT erwartet:
# - Keine direkten Log.d/Log.e Aufrufe aus Domain Layer
```

**Verification:**
- ✅ Alle Logs nutzen Logger Interface (TAG ist sichtbar)
- ✅ Keine android.util.Log Aufrufe im Domain Layer
- ✅ Logs sind strukturiert und konsistent

---

## Phase 6: Test Execution & Reporting

### Execution Plan

**Schritt 1: Unit Tests ausführen**
```bash
# Alle Unit Tests
./gradlew test

# Nur neue Repository Tests
./gradlew test --tests "*RepositoryImplTest"

# Nur Architecture Tests
./gradlew test --tests "ArchitectureTest"
```

**Schritt 2: Test Reports generieren**
```bash
# HTML Report
./gradlew test
# Öffne: app/build/reports/tests/testDebugUnitTest/index.html

# Coverage Report (falls JaCoCo konfiguriert)
./gradlew jacocoTestReport
# Öffne: app/build/reports/jacoco/test/html/index.html
```

**Schritt 3: CI/CD Integration (Optional)**
```yaml
# .github/workflows/android-tests.yml
name: Android Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up JDK 21
        uses: actions/setup-java@v3
        with:
          java-version: 21
      - name: Run Unit Tests
        run: ./gradlew test
      - name: Upload Test Report
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: app/build/reports/tests/
```

---

## Success Metrics

**Nach Phase 1 (Unit Tests):**
- ✅ FilesRepositoryImplTest: 12+ Test-Cases, 80%+ Coverage
- ✅ AuthRepositoryImplTest: 10+ Test-Cases, 90%+ Coverage
- ✅ NetworkStateManagerImplTest: 8+ Test-Cases, 75%+ Coverage
- ✅ AndroidLoggerTest: 4+ Test-Cases, 100% Coverage

**Nach Phase 2 (Integration Tests):**
- ✅ GetFilesUseCase nutzt FilesRepository korrekt
- ✅ VpnViewModel nutzt NetworkStateManager ohne Context

**Nach Phase 3 (Architecture Tests):**
- ✅ Domain Layer hat nur noch 5 bekannte Android-Dependencies (dokumentiert)
- ✅ Keine android.util.Log Imports im Domain Layer
- ✅ Alle Repositories implementieren Domain-Interfaces

**Nach Phase 4 (Build Tests):**
- ✅ App kompiliert erfolgreich (Debug + Release)
- ✅ Keine Duplicate Class Errors
- ✅ Lint-Report zeigt nur bekannte Warnings

**Nach Phase 5 (Manual Tests):**
- ✅ Files Screen: Cache funktioniert, Upload/Delete erfolgreich
- ✅ Auth: Login/Logout/Refresh funktioniert
- ✅ VPN: Status-Monitoring reaktiv, kein Context in ViewModel
- ✅ Logger: Alle Logs strukturiert, kein android.util.Log im Domain

---

## Kritische Dateien

### Zu erstellen (Test-Files):
- `app/src/test/java/com/baluhost/android/data/repository/FilesRepositoryImplTest.kt`
- `app/src/test/java/com/baluhost/android/data/repository/AuthRepositoryImplTest.kt`
- `app/src/test/java/com/baluhost/android/data/network/NetworkStateManagerImplTest.kt`
- `app/src/test/java/com/baluhost/android/data/util/AndroidLoggerTest.kt`
- `app/src/test/java/com/baluhost/android/ArchitectureTest.kt`
- `scripts/verify_no_android_log.sh`

### Zu erweitern (Integration Tests):
- `app/src/test/java/com/baluhost/android/domain/usecase/files/GetFilesUseCaseTest.kt`
- `app/src/test/java/com/baluhost/android/presentation/ui/screens/vpn/VpnViewModelTest.kt`

### Zu prüfen (Production Code):
- `app/src/main/java/com/baluhost/android/data/repository/FilesRepositoryImpl.kt`
- `app/src/main/java/com/baluhost/android/data/repository/AuthRepositoryImpl.kt`
- `app/src/main/java/com/baluhost/android/data/network/NetworkStateManagerImpl.kt`
- `app/src/main/java/com/baluhost/android/data/util/AndroidLogger.kt`
- `app/src/main/java/com/baluhost/android/domain/util/Logger.kt`

---

## Zeitplan

### Quick Test (30 Minuten):
1. Build-Test (5 min)
2. Existing Unit Tests (5 min)
3. Architecture Test erstellen & ausführen (10 min)
4. Manual Test: Files + Auth (10 min)

### Comprehensive Test (4-6 Stunden):
1. **Phase 1:** Unit Tests schreiben & ausführen (3-4h)
2. **Phase 2:** Integration Tests (2h)
3. **Phase 3:** Architecture Tests (1h)
4. **Phase 4:** Build & Lint (10 min)
5. **Phase 5:** Manual Testing (40 min)

### Minimal Test (10 Minuten):
1. `./gradlew clean build` (5 min)
2. Manual App Start & Login Test (5 min)
3. Verify: Keine Crashes, Login funktioniert

---

## Empfehlung: Start-Strategie

**Option A: Quick Verification (empfohlen für JETZT)**
1. Build-Test ausführen (`./gradlew clean assembleDebug`)
2. App auf Emulator installieren & manuell testen
3. Architecture-Test erstellen & ausführen (zeigt bekannte Violations)

**Zeitaufwand:** 30 Minuten
**Ziel:** Sicherstellen, dass alle Änderungen kompilieren und grundlegend funktionieren

**Option B: Comprehensive Testing (empfohlen für MORGEN)**
1. Alle Unit Tests schreiben (Phase 1)
2. Integration Tests erweitern (Phase 2)
3. Vollständiges Manual Testing (Phase 5)

**Zeitaufwand:** 4-6 Stunden
**Ziel:** Vollständige Test-Coverage für refactored Components

---

## Nächster Schritt

**Nach User-Approval des Plans:**

1. **Erstelle Architecture-Test** (zeigt aktuelle Violations)
2. **Run Build Test** (verify compilation)
3. **Erstelle FilesRepositoryImplTest** (höchste Priorität)
4. **Erstelle AuthRepositoryImplTest**
5. **Manual Testing Guide ausführen**

**Oder:** User entscheidet sich für Quick Verification (Option A) für sofortiges Feedback.
