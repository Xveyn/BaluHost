# Android Best Practices - BaluHost Android App

**Stand:** Januar 2026
**App-Status:** ~60% fertig, produktionsreif für Core-Features
**Letzte Code-Analyse:** 29. Januar 2026

Dieses Dokument dokumentiert Best Practices Violations, die in der Code-Analyse gefunden wurden, sowie Empfehlungen zur Behebung.

---

## 📊 ZUSAMMENFASSUNG

### ✅ **Stärken der Codebase**

1. **Moderne Architecture:**
   - Clean Architecture (Data/Domain/Presentation) größtenteils korrekt umgesetzt
   - MVVM Pattern mit ViewModels und StateFlow
   - Hilt Dependency Injection durchgängig verwendet

2. **Gute Implementations:**
   - VpnRepository vollständig implementiert (208 Zeilen, funktional)
   - Result-Wrapper für Type-Safe Error Handling
   - Material 3 Theming korrekt umgesetzt

3. **Security:**
   - EncryptedSharedPreferences für sensitive Daten
   - Proper JWT Token Management
   - SecureStorage Abstraktion vorhanden

### 🔴 **Kritische Probleme**

| Problem | Severity | Anzahl Files | Impact |
|---------|----------|--------------|--------|
| Android-Imports in Domain Layer | 🔴 CRITICAL | 3+ | Testability, Portability |
| Leere Repository-Implementations | 🔴 CRITICAL | 2 | Funktionalität |
| Context in ViewModel | 🔴 CRITICAL | 1 | Architecture Violation |
| Fehlende `collectAsStateWithLifecycle()` | 🟠 HIGH | 5+ | Memory Leaks |
| Missing LazyColumn keys | 🟠 HIGH | 3+ | Performance |
| Hardcoded Strings | 🟡 MEDIUM | 100+ | Localization |

---

## 1. CLEAN ARCHITECTURE VIOLATIONS

### 🔴 Problem 1.1: Android-Imports in Domain Layer

**Betroffene Dateien:**

#### `domain/usecase/vpn/FetchVpnConfigUseCase.kt` (Line 3)
```kotlin
import android.util.Log  // ❌ Android-Import in Domain!

class FetchVpnConfigUseCase @Inject constructor(
    private val vpnRepository: VpnRepository
) {
    suspend operator fun invoke(): Result<VpnConfig> {
        Log.d(TAG, "Fetching VPN config")  // ❌ Direct Android API usage
        return vpnRepository.fetchVpnConfig()
    }
}
```

**Warum ist das ein Problem?**
- Domain Layer sollte **pure Kotlin** sein (kein Android, kein Framework)
- Tests können nicht ohne Android SDK laufen
- Code kann nicht in anderen Projekten (z.B. Desktop, Server) wiederverwendet werden

**✅ Lösung:**

1. **Erstelle Logger-Abstraktion:**
```kotlin
// domain/util/Logger.kt
interface Logger {
    fun debug(tag: String, message: String)
    fun error(tag: String, message: String, throwable: Throwable? = null)
    fun info(tag: String, message: String)
}
```

2. **Implementiere in Data Layer:**
```kotlin
// data/util/AndroidLogger.kt
import android.util.Log
import javax.inject.Inject

class AndroidLogger @Inject constructor() : Logger {
    override fun debug(tag: String, message: String) {
        Log.d(tag, message)
    }

    override fun error(tag: String, message: String, throwable: Throwable?) {
        Log.e(tag, message, throwable)
    }
}
```

3. **Injiziere in Use Case:**
```kotlin
// domain/usecase/vpn/FetchVpnConfigUseCase.kt
class FetchVpnConfigUseCase @Inject constructor(
    private val vpnRepository: VpnRepository,
    private val logger: Logger  // ✅ Abstraction
) {
    suspend operator fun invoke(): Result<VpnConfig> {
        logger.debug(TAG, "Fetching VPN config")
        return vpnRepository.fetchVpnConfig()
    }
}
```

4. **Provide in Hilt Module:**
```kotlin
// di/AppModule.kt
@Module
@InstallIn(SingletonComponent::class)
abstract class LoggingModule {
    @Binds
    @Singleton
    abstract fun bindLogger(impl: AndroidLogger): Logger
}
```

---

### 🔴 Problem 1.2: Context in ViewModel

**Betroffene Datei:** `presentation/ui/screens/vpn/VpnViewModel.kt`

```kotlin
@HiltViewModel
class VpnViewModel @Inject constructor(
    private val fetchVpnConfigUseCase: FetchVpnConfigUseCase,
    private val connectVpnUseCase: ConnectVpnUseCase,
    private val disconnectVpnUseCase: DisconnectVpnUseCase,
    private val preferencesManager: PreferencesManager,
    @ApplicationContext private val context: Context  // ❌ Context in ViewModel!
) : ViewModel() {

    // Lines 176-188: Direct ConnectivityManager usage
    private fun isVpnActive(): Boolean {
        return try {
            val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            val activeNetwork = connectivityManager.activeNetwork ?: return false
            val networkCapabilities = connectivityManager.getNetworkCapabilities(activeNetwork) ?: return false
            networkCapabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN)
        } catch (e: Exception) {
            Log.e(TAG, "Error checking VPN status", e)
            false
        }
    }
}
```

**Warum ist das ein Problem?**
- ViewModel sollte **keine Android Context** haben
- Führt zu Schwierigkeiten beim Unit-Testing
- Verletzt MVVM-Prinzipien (ViewModel sollte Framework-agnostic sein)
- Potenzielle Memory Leaks bei längeren Context-Referenzen

**✅ Lösung:**

1. **Erstelle NetworkStateManager:**
```kotlin
// data/network/NetworkStateManager.kt
interface NetworkStateManager {
    fun isVpnActive(): Boolean
    fun observeVpnStatus(): Flow<Boolean>
}

class NetworkStateManagerImpl @Inject constructor(
    @ApplicationContext private val context: Context
) : NetworkStateManager {

    override fun isVpnActive(): Boolean {
        return try {
            val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE)
                as ConnectivityManager
            val activeNetwork = connectivityManager.activeNetwork ?: return false
            val networkCapabilities = connectivityManager.getNetworkCapabilities(activeNetwork)
                ?: return false
            networkCapabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN)
        } catch (e: Exception) {
            false
        }
    }

    override fun observeVpnStatus(): Flow<Boolean> = callbackFlow {
        val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE)
            as ConnectivityManager

        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onCapabilitiesChanged(
                network: Network,
                networkCapabilities: NetworkCapabilities
            ) {
                trySend(networkCapabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN))
            }
        }

        connectivityManager.registerDefaultNetworkCallback(callback)
        awaitClose { connectivityManager.unregisterNetworkCallback(callback) }
    }
}
```

2. **Refactore ViewModel:**
```kotlin
@HiltViewModel
class VpnViewModel @Inject constructor(
    private val fetchVpnConfigUseCase: FetchVpnConfigUseCase,
    private val connectVpnUseCase: ConnectVpnUseCase,
    private val disconnectVpnUseCase: DisconnectVpnUseCase,
    private val preferencesManager: PreferencesManager,
    private val networkStateManager: NetworkStateManager  // ✅ Abstraction
) : ViewModel() {

    private fun checkVpnStatus() {
        viewModelScope.launch {
            networkStateManager.observeVpnStatus().collect { isActive ->
                _uiState.value = _uiState.value.copy(isConnected = isActive)
            }
        }
    }
}
```

---

## 2. INCOMPLETE IMPLEMENTATIONS

### 🔴 Problem 2.1: Leere Repository-Implementations

#### `data/repository/FilesRepositoryImpl.kt`
```kotlin
class FilesRepositoryImpl @Inject constructor(
    private val filesApi: FilesApi
) : FilesRepository {
    // TODO: Implement file methods  // ❌ Nur TODO!
}
```

#### `data/repository/AuthRepositoryImpl.kt`
```kotlin
class AuthRepositoryImpl @Inject constructor(
    private val authApi: AuthApi
) : AuthRepository {
    // TODO: Implement auth methods  // ❌ Nur TODO!
}
```

**Status:** Diese Repositories werden injiziert, sind aber nicht funktional!

**✅ Es existiert:** `data/repository/FileRepository.kt` mit vollständiger Caching-Logik (~200 Zeilen)

**Sofortige Aktion erforderlich:**
1. Merge `FileRepository.kt` → `FilesRepositoryImpl.kt`
2. Implementiere `AuthRepositoryImpl` mit Login/Logout/RefreshToken
3. Lösche alte `FileRepository.kt` Datei

**Beispiel-Implementation (AuthRepositoryImpl):**
```kotlin
@Singleton
class AuthRepositoryImpl @Inject constructor(
    private val authApi: AuthApi,
    private val secureStorage: SecureStorage
) : AuthRepository {

    override suspend fun login(username: String, password: String): Result<User> {
        return try {
            val response = authApi.login(LoginRequest(username, password))
            secureStorage.saveAccessToken(response.accessToken)
            secureStorage.saveRefreshToken(response.refreshToken)
            Result.Success(response.user.toDomain())
        } catch (e: HttpException) {
            Result.Error(Exception("Login failed: ${e.message()}"))
        } catch (e: IOException) {
            Result.Error(Exception("Network error"))
        }
    }

    override suspend fun refreshToken(): Result<String> {
        return try {
            val refreshToken = secureStorage.getRefreshToken()
                ?: return Result.Error(Exception("No refresh token"))

            val response = authApi.refreshToken(RefreshTokenRequest(refreshToken))
            secureStorage.saveAccessToken(response.accessToken)
            Result.Success(response.accessToken)
        } catch (e: Exception) {
            Result.Error(Exception("Token refresh failed: ${e.message}"))
        }
    }

    override suspend fun logout(): Result<Unit> {
        return try {
            secureStorage.clearTokens()
            Result.Success(Unit)
        } catch (e: Exception) {
            Result.Error(Exception("Logout failed"))
        }
    }
}
```

---

## 3. JETPACK COMPOSE BEST PRACTICES

### 🟠 Problem 3.1: Fehlende `collectAsStateWithLifecycle()`

**Betroffene Dateien:**
- `presentation/ui/screens/files/FilesScreen.kt` (Lines 57-68)
- `presentation/ui/screens/dashboard/DashboardScreen.kt` (Lines 42-55)
- Alle anderen Screen-Composables

```kotlin
@Composable
fun FilesScreen(viewModel: FilesViewModel = hiltViewModel()) {
    val uiState by viewModel.uiState.collectAsState()  // ❌ Falsch!

    // ...
}
```

**Warum ist das ein Problem?**
- `collectAsState()` collected auch wenn App im Hintergrund ist
- Führt zu **unnötigen Recompositions** und **Memory Leaks**
- Verschwendet Batterie und CPU-Ressourcen

**✅ Lösung:**

```kotlin
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun FilesScreen(viewModel: FilesViewModel = hiltViewModel()) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()  // ✅ Korrekt!

    // ...
}
```

**Dependency hinzufügen (falls noch nicht vorhanden):**
```kotlin
// app/build.gradle.kts
implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.6")
```

---

### 🟠 Problem 3.2: Missing LazyColumn `key` Parameter

**Betroffene Dateien:**
- `presentation/ui/screens/files/FilesScreen.kt` (Lines 302-352)
- `presentation/ui/screens/dashboard/DashboardScreen.kt` (RAID arrays, recent files)

```kotlin
LazyColumn {
    items(uiState.files) { file ->  // ❌ Kein key!
        GlassFileListItem(file = file, ...)
    }
}
```

**Warum ist das ein Problem?**
- **Alle Items recompose** bei jeder List-Änderung
- Schlechte Performance bei großen Listen
- Scroll-Position geht verloren bei Updates

**✅ Lösung:**

```kotlin
LazyColumn {
    items(uiState.files, key = { it.path }) { file ->  // ✅ Unique key
        GlassFileListItem(file = file, ...)
    }
}
```

**Regel:** Key sollte:
- **Unique** sein pro Item
- **Stabil** über List-Updates hinweg
- Idealerweise eine ID oder Pfad (nicht Index!)

---

### 🟡 Problem 3.3: Hardcoded Strings (Keine Lokalisierung)

**Beispiele aus Code:**

```kotlin
// DashboardScreen.kt
Text("Dashboard")  // ❌ Hardcoded
Text("Secure personal cloud orchestration overview")  // ❌ Hardcoded

// FilesScreen.kt
Text("Dateien")  // ❌ Hardcoded (Deutsch)
Text("Keine Dateien vorhanden")  // ❌ Hardcoded

// VpnScreen.kt
Text("Nicht im Heimnetzwerk")  // ❌ Hardcoded
```

**Warum ist das ein Problem?**
- Keine Internationalisierung (i18n) möglich
- Mix aus Deutsch und Englisch
- Schwer zu pflegen

**✅ Lösung:**

1. **Erstelle `res/values/strings.xml`:**
```xml
<resources>
    <string name="dashboard_title">Dashboard</string>
    <string name="dashboard_subtitle">Secure personal cloud orchestration overview</string>
    <string name="files_title">Dateien</string>
    <string name="no_files_available">Keine Dateien vorhanden</string>
    <string name="vpn_not_in_home_network">Nicht im Heimnetzwerk</string>
</resources>
```

2. **Erstelle `res/values-en/strings.xml` für Englisch:**
```xml
<resources>
    <string name="dashboard_title">Dashboard</string>
    <string name="dashboard_subtitle">Secure personal cloud orchestration overview</string>
    <string name="files_title">Files</string>
    <string name="no_files_available">No files available</string>
    <string name="vpn_not_in_home_network">Not in home network</string>
</resources>
```

3. **Nutze in Composables:**
```kotlin
import androidx.compose.ui.res.stringResource

Text(stringResource(R.string.dashboard_title))  // ✅ Localized
```

---

### 🟡 Problem 3.4: Missing Content Descriptions (Accessibility)

**Beispiele:**

```kotlin
// DashboardScreen.kt (Line 416)
Icon(
    imageVector = Icons.Default.Memory,
    contentDescription = null,  // ❌ Nicht barrierefrei!
    tint = Color.White
)
```

**Warum ist das ein Problem?**
- **Nicht barrierefrei** für sehbehinderte Nutzer
- TalkBack kann Icons nicht vorlesen
- Verletzt Material Design Guidelines

**✅ Lösung:**

```kotlin
Icon(
    imageVector = Icons.Default.Memory,
    contentDescription = stringResource(R.string.cpu_usage_icon),  // ✅ Accessible
    tint = Color.White
)
```

**Regel:** **Jedes decorative Icon** braucht eine Content Description!

---

## 4. PERFORMANCE OPTIMIZATIONS

### 🟡 Problem 4.1: Brush Allocations bei jeder Recomposition

**Betroffen:** `presentation/ui/screens/dashboard/DashboardScreen.kt` (Lines 57-65)

```kotlin
@Composable
fun DashboardScreen() {
    val gradientBrush = Brush.linearGradient(  // ❌ Jede Recomposition!
        colors = listOf(
            Color(0xFF1E3A5F),
            Color(0xFF2C5F6F),
            Color(0xFF1A4D5C)
        ),
        start = Offset(0f, 0f),
        end = Offset(1000f, 1500f)
    )
}
```

**Warum ist das ein Problem?**
- Brush wird **bei jeder Recomposition neu erstellt**
- Unnötige Object Allocations
- Garbage Collection Overhead

**✅ Lösung:**

```kotlin
@Composable
fun DashboardScreen() {
    val gradientBrush = remember {  // ✅ Einmalig erstellt!
        Brush.linearGradient(
            colors = listOf(
                Color(0xFF1E3A5F),
                Color(0xFF2C5F6F),
                Color(0xFF1A4D5C)
            ),
            start = Offset(0f, 0f),
            end = Offset(1000f, 1500f)
        )
    }
}
```

---

## 5. CODE QUALITY & MAINTAINABILITY

### 🟡 Problem 5.1: Fehlende @Immutable Annotations

**Betroffen:** Alle UiState Data Classes

```kotlin
// VpnViewModel.kt (Line 285)
data class VpnUiState(  // ❌ Keine @Immutable
    val isConnected: Boolean = false,
    val isLoading: Boolean = false,
    val hasConfig: Boolean = false,
    // ...
)
```

**Warum ist das wichtig?**
- Compose Compiler kann **bessere Optimierungen** machen
- Reduziert unnötige Recompositions
- Macht Intent explizit (Daten sollten immutable sein)

**✅ Lösung:**

```kotlin
import androidx.compose.runtime.Immutable

@Immutable  // ✅ Compiler Optimization
data class VpnUiState(
    val isConnected: Boolean = false,
    val isLoading: Boolean = false,
    val hasConfig: Boolean = false,
    // ...
)
```

---

### 🟢 Problem 5.2: Fehlende @Preview Annotations

**Status:** Keine einzige Composable hat `@Preview`!

**Warum ist das wichtig?**
- Android Studio kann Previews **nicht anzeigen**
- Längere Entwicklungszyklen (muss App builden um UI zu sehen)
- Schwieriger UI-Testing

**✅ Lösung:**

```kotlin
@Composable
private fun WelcomeStep() {
    // Composable content
}

@Preview(showBackground = true, name = "Welcome Step - Light")
@Preview(showBackground = true, name = "Welcome Step - Dark", uiMode = Configuration.UI_MODE_NIGHT_YES)
@Composable
private fun WelcomeStepPreview() {
    BaluHostTheme {
        WelcomeStep()
    }
}
```

---

## 6. AUTOMATED VERIFICATION

### Architecture Tests mit ArchUnit

**Erstelle:** `androidTest/java/com/baluhost/android/ArchitectureTest.kt`

```kotlin
import com.tngtech.archunit.core.importer.ClassFileImporter
import com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses
import org.junit.Test

class ArchitectureTest {

    private val importedClasses = ClassFileImporter()
        .importPackages("com.baluhost.android")

    @Test
    fun `domain layer should not depend on Android framework`() {
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat().resideInAPackage("android..")
            .check(importedClasses)
    }

    @Test
    fun `ViewModels should not have Context dependency`() {
        noClasses()
            .that().resideInAPackage("..presentation..")
            .and().haveSimpleNameEndingWith("ViewModel")
            .should().dependOnClassesThat().haveSimpleName("Context")
            .check(importedClasses)
    }

    @Test
    fun `repositories should have interface`() {
        classes()
            .that().haveSimpleNameEndingWith("RepositoryImpl")
            .should().implement(MatchersKt.assignableTo("..Repository"))
            .check(importedClasses)
    }
}
```

**Dependency hinzufügen:**
```kotlin
// app/build.gradle.kts
androidTestImplementation("com.tngtech.archunit:archunit:1.2.1")
```

---

## 7. PRIORITÄTS-MATRIX

### 🔴 CRITICAL (Sofort beheben)
- [ ] **FilesRepositoryImpl & AuthRepositoryImpl implementieren** (2-3h)
- [ ] **Context aus VpnViewModel entfernen** (1-2h)
- [ ] **Android-Imports aus Domain Layer entfernen** (2-3h)

### 🟠 HIGH (Diese Woche)
- [ ] **collectAsStateWithLifecycle() überall nutzen** (1h)
- [ ] **LazyColumn keys hinzufügen** (30min)
- [ ] **NetworkStateManager Abstraktion erstellen** (1-2h)

### 🟡 MEDIUM (Nächste Woche)
- [ ] **strings.xml erstellen & alle Strings migrieren** (2-3h)
- [ ] **Content Descriptions hinzufügen** (1-2h)
- [ ] **Brush Allocations in remember() wrappen** (30min)

### 🟢 LOW (Nice to have)
- [ ] **@Immutable Annotations hinzufügen** (30min)
- [ ] **@Preview Annotations erstellen** (1-2h)
- [ ] **Architecture Tests schreiben** (2h)

---

## 8. POSITIVE BEISPIELE (Keep These!)

### ✅ Gut gemacht:

1. **VpnRepositoryImpl** - Vollständige Implementation mit Error Handling
2. **Result Wrapper Pattern** - Type-Safe Error Handling
3. **Material 3 Theming** - Korrekt implementiert mit Dark Mode
4. **Hilt Dependency Injection** - Durchgängig verwendet
5. **SecureStorage** - EncryptedSharedPreferences für Sensitive Daten

---

## 9. REFERENZEN

### Offizielle Guidelines
- [Android Architecture Components](https://developer.android.com/topic/architecture)
- [Jetpack Compose Best Practices](https://developer.android.com/jetpack/compose/performance)
- [Material Design 3](https://m3.material.io/)
- [Clean Architecture by Uncle Bob](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)

### Interne Dokumentation
- `CLAUDE.md` - Android Development Guide
- `TODO.md` - Top 3 Priority Tasks
- `STATUS_UND_ROADMAP.md` - Feature Status & Roadmap

---

**Letzte Aktualisierung:** 29. Januar 2026
**Nächstes Review:** Nach Implementierung der Critical Tasks
