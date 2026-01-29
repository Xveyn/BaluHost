# CLAUDE.md - BaluHost Android Client

This file provides guidance to Claude Code (claude.ai/code) when working with the Android client in this repository.

## Project Overview

BaluHost Android is a native mobile client for the BaluHost NAS management platform. Built with modern Android development practices, it provides secure file management, VPN connectivity, and device synchronization capabilities.

**Current Status**: ~60% production-ready (January 2026). Core features (authentication, file management, offline queue) are complete. VPN integration, settings, and camera backup are in progress.

**Package**: `com.baluhost.android`
**Min SDK**: 26 (Android 8.0 Oreo)
**Target SDK**: 35 (Android 15)
**Compile SDK**: 35

## Technology Stack

### Language & Build
- **Kotlin**: 1.9.x with coroutines for async operations
- **Gradle**: 8.1+ with Kotlin DSL (`build.gradle.kts`)
- **JDK**: 21 (required for Android Studio Hedgehog+)

### UI Framework
- **Jetpack Compose**: 2024.09 BOM (fully declarative UI)
- **Material 3**: Modern Material Design components
- **Navigation**: Jetpack Navigation Compose
- **Dark Mode**: System-responsive theme support

### Architecture & DI
- **Architecture**: Clean Architecture (Data/Domain/Presentation layers)
- **Pattern**: MVVM with ViewModels and StateFlow/Flow
- **Dependency Injection**: Hilt (Dagger wrapper for Android)

### Networking & Storage
- **HTTP Client**: Retrofit 2.9 + OkHttp 4.12
- **Serialization**: Gson for JSON parsing
- **Database**: Room 2.6.1 (SQLite wrapper with coroutines)
- **Preferences**: DataStore (modern SharedPreferences replacement)
- **Security**: EncryptedSharedPreferences for sensitive data

### Key Libraries
- **WireGuard VPN**: `com.wireguard.android:tunnel:1.0.20230706`
- **WorkManager**: 2.9.1 for background sync/retry
- **CameraX**: 1.3.4 for QR code scanning
- **ML Kit**: Barcode scanning for device registration
- **Coil**: 2.7.0 for image loading with Compose
- **ExoPlayer** (Media3): 1.4.1 for video/audio playback
- **Vico Charts**: 2.0.0-alpha.28 for data visualization
- **Biometric**: 1.2.0-alpha05 for fingerprint/face unlock
- **Firebase**: Cloud Messaging (FCM) for push notifications

## Project Structure

```
android-app/
├── app/
│   ├── src/
│   │   ├── main/
│   │   │   ├── java/com/baluhost/android/
│   │   │   │   ├── BaluHostApplication.kt     # Application class (Hilt entry point)
│   │   │   │   ├── di/                        # Hilt dependency injection modules
│   │   │   │   │   ├── AppModule.kt           # App-level dependencies
│   │   │   │   │   ├── NetworkModule.kt       # Retrofit, OkHttp configuration
│   │   │   │   │   ├── DatabaseModule.kt      # Room database setup
│   │   │   │   │   ├── RepositoryModule.kt    # Repository bindings
│   │   │   │   │   ├── WorkerModule.kt        # WorkManager dependencies
│   │   │   │   │   └── ImageLoaderModule.kt   # Coil configuration
│   │   │   │   ├── data/                      # Data layer
│   │   │   │   │   ├── local/                 # Local data sources
│   │   │   │   │   │   ├── database/          # Room entities, DAOs
│   │   │   │   │   │   │   ├── BaluHostDatabase.kt
│   │   │   │   │   │   │   ├── dao/           # Data Access Objects
│   │   │   │   │   │   │   ├── entities/      # Room entities
│   │   │   │   │   │   │   └── converters/    # Type converters
│   │   │   │   │   │   └── security/          # Encryption, biometrics
│   │   │   │   │   │       ├── SecureStorage.kt
│   │   │   │   │   │       ├── AppLockManager.kt
│   │   │   │   │   │       ├── BiometricAuthManager.kt
│   │   │   │   │   │       └── PinManager.kt
│   │   │   │   │   ├── remote/                # Remote data sources
│   │   │   │   │   │   ├── api/               # Retrofit API interfaces
│   │   │   │   │   │   │   ├── AuthApi.kt
│   │   │   │   │   │   │   ├── MobileApi.kt
│   │   │   │   │   │   │   ├── SystemApi.kt
│   │   │   │   │   │   │   └── VpnApi.kt
│   │   │   │   │   │   ├── dto/               # Data Transfer Objects
│   │   │   │   │   │   └── interceptors/      # OkHttp interceptors
│   │   │   │   │   │       ├── AuthInterceptor.kt
│   │   │   │   │   │       ├── ErrorInterceptor.kt
│   │   │   │   │   │       └── DynamicBaseUrlInterceptor.kt
│   │   │   │   │   ├── repository/            # Repository implementations
│   │   │   │   │   │   ├── AuthRepositoryImpl.kt
│   │   │   │   │   │   ├── FilesRepositoryImpl.kt
│   │   │   │   │   │   ├── SystemRepositoryImpl.kt
│   │   │   │   │   │   └── OfflineQueueRepositoryImpl.kt
│   │   │   │   │   ├── network/               # Network monitoring
│   │   │   │   │   │   ├── NetworkMonitor.kt
│   │   │   │   │   │   └── ServerConnectivityChecker.kt
│   │   │   │   │   └── worker/                # Background workers
│   │   │   │   │       ├── OfflineQueueRetryWorker.kt
│   │   │   │   │       ├── CacheCleanupWorker.kt
│   │   │   │   │       └── OfflineQueueWorkScheduler.kt
│   │   │   │   ├── domain/                    # Domain layer (business logic)
│   │   │   │   │   ├── model/                 # Domain models
│   │   │   │   │   │   ├── User.kt
│   │   │   │   │   │   ├── FileItem.kt
│   │   │   │   │   │   ├── SystemInfo.kt
│   │   │   │   │   │   ├── MobileDevice.kt
│   │   │   │   │   │   └── PendingOperation.kt
│   │   │   │   │   ├── repository/            # Repository interfaces
│   │   │   │   │   │   ├── AuthRepository.kt
│   │   │   │   │   │   ├── FilesRepository.kt
│   │   │   │   │   │   ├── SystemRepository.kt
│   │   │   │   │   │   └── OfflineQueueRepository.kt
│   │   │   │   │   └── usecase/               # Use cases (single responsibility)
│   │   │   │   │       ├── auth/
│   │   │   │   │       │   ├── RegisterDeviceUseCase.kt
│   │   │   │   │       │   └── RefreshTokenUseCase.kt
│   │   │   │   │       ├── files/
│   │   │   │   │       │   ├── GetFilesUseCase.kt
│   │   │   │   │       │   ├── UploadFileUseCase.kt
│   │   │   │   │       │   ├── DownloadFileUseCase.kt
│   │   │   │   │       │   ├── DeleteFileUseCase.kt
│   │   │   │   │       │   └── MoveFileUseCase.kt
│   │   │   │   │       ├── vpn/
│   │   │   │   │       │   ├── ConnectVpnUseCase.kt
│   │   │   │   │       │   └── DisconnectVpnUseCase.kt
│   │   │   │   │       ├── cache/
│   │   │   │   │       │   ├── ClearCacheUseCase.kt
│   │   │   │   │       │   └── GetCacheStatsUseCase.kt
│   │   │   │   │       └── OfflineQueueManager.kt
│   │   │   │   ├── presentation/              # Presentation layer (UI)
│   │   │   │   │   ├── MainActivity.kt        # Single activity with Compose
│   │   │   │   │   ├── navigation/            # Navigation graph
│   │   │   │   │   │   ├── NavGraph.kt
│   │   │   │   │   │   └── Screen.kt
│   │   │   │   │   └── ui/
│   │   │   │   │       ├── components/        # Reusable UI components
│   │   │   │   │       │   ├── GlassCard.kt
│   │   │   │   │       │   ├── GlassTextField.kt
│   │   │   │   │       │   ├── GradientButton.kt
│   │   │   │   │       │   ├── FolderPickerDialog.kt
│   │   │   │   │       │   └── ConflictResolutionDialog.kt
│   │   │   │   │       ├── screens/           # Screen composables + ViewModels
│   │   │   │   │       │   ├── splash/
│   │   │   │   │       │   │   └── SplashScreen.kt
│   │   │   │   │       │   ├── onboarding/
│   │   │   │   │       │   │   ├── OnboardingScreen.kt
│   │   │   │   │       │   │   └── OnboardingViewModel.kt
│   │   │   │   │       │   ├── lock/
│   │   │   │   │       │   │   ├── LockScreen.kt
│   │   │   │   │       │   │   └── LockScreenViewModel.kt
│   │   │   │   │       │   ├── storage/
│   │   │   │   │       │   │   ├── StorageOverviewScreen.kt
│   │   │   │   │       │   │   └── StorageOverviewViewModel.kt
│   │   │   │   │       │   ├── media/
│   │   │   │   │       │   │   └── MediaViewerScreen.kt
│   │   │   │   │       │   └── settings/
│   │   │   │   │       │       └── PinSetupDialog.kt
│   │   │   │   │       └── theme/             # Compose theme
│   │   │   │   │           ├── Theme.kt
│   │   │   │   │           ├── Color.kt
│   │   │   │   │           └── Type.kt
│   │   │   │   ├── service/                   # Android Services
│   │   │   │   │   └── vpn/
│   │   │   │   │       └── BaluHostVpnService.kt
│   │   │   │   ├── services/                  # Other services
│   │   │   │   │   └── BaluFirebaseMessagingService.kt
│   │   │   │   └── util/                      # Utility classes
│   │   │   │       ├── NetworkMonitor.kt
│   │   │   │       ├── Result.kt
│   │   │   │       └── LocalFolderScanner.kt
│   │   │   ├── AndroidManifest.xml
│   │   │   └── res/                           # Resources (layouts, strings, etc.)
│   │   ├── test/                              # Unit tests
│   │   └── androidTest/                       # Instrumented tests
│   └── build.gradle.kts                       # App-level build config
├── build.gradle.kts                           # Project-level build config
├── settings.gradle.kts                        # Project settings
├── gradle.properties                          # Gradle configuration
├── README.md                                  # Project overview
├── QUICK_START.md                             # Quick reference (German)
├── STATUS_UND_ROADMAP.md                      # Detailed status
└── docs/                                      # Additional documentation

```

## Development Environment

### Prerequisites
1. **Android Studio**: Hedgehog (2023.1.1) or later (Iguana/Jellyfish recommended)
2. **JDK**: 21 (bundled with Android Studio or manual installation)
3. **Android SDK**: API 35 (Android 15) via SDK Manager
4. **Gradle**: 8.1+ (wrapper included, no manual installation needed)
5. **Device/Emulator**: Physical device or emulator with API 26+ (Android 8.0+)

### Setup Instructions

1. **Open Project**
   ```bash
   # From repository root
   cd android-app

   # Open in Android Studio: File → Open → select android-app/
   ```

2. **Sync Dependencies**
   - Android Studio will prompt to sync Gradle automatically
   - Or manually: File → Sync Project with Gradle Files
   - First sync may take 5-10 minutes to download dependencies

3. **Configure Backend URL**
   - Edit `app/build.gradle.kts` line 24:
     ```kotlin
     buildConfigField("String", "BASE_URL", "\"http://YOUR_SERVER_IP:8000/api/\"")
     ```
   - Replace `YOUR_SERVER_IP` with your BaluHost server address
   - Development: Use local network IP (e.g., `192.168.1.100`)
   - Production: Use domain or public IP with HTTPS

4. **Build Project**
   ```bash
   # Command line
   ./gradlew build

   # Or in Android Studio: Build → Make Project (Ctrl+F9 / Cmd+F9)
   ```

5. **Run App**
   - Select device/emulator from device dropdown
   - Click Run (▶️) button or press Shift+F10 (Win/Linux) / Ctrl+R (Mac)
   - App installs and launches automatically

### Common Development Commands

```bash
# Build debug APK
./gradlew assembleDebug
# Output: app/build/outputs/apk/debug/app-debug.apk

# Build release APK (signed)
./gradlew assembleRelease

# Install on connected device
./gradlew installDebug

# Run unit tests (JUnit, Mockito)
./gradlew test
./gradlew test --tests "com.baluhost.android.domain.usecase.*"

# Run instrumented tests (requires device/emulator)
./gradlew connectedAndroidTest

# Clean build directory
./gradlew clean

# List all tasks
./gradlew tasks
```

## Code Standards

### Kotlin Style
- **Naming**:
  - Classes: PascalCase (`UserRepository`, `FileItem`)
  - Functions/Variables: camelCase (`getUserList`, `isLoading`)
  - Constants: SCREAMING_SNAKE_CASE (`MAX_RETRIES`, `BASE_URL`)
  - Private properties: prefix with underscore optional (`_uiState`)

- **Formatting**:
  - Indentation: 4 spaces (default IntelliJ style)
  - Line length: 120 characters max
  - Use trailing commas in multi-line declarations

### Architecture Patterns

#### Clean Architecture Layers
```
Presentation → Domain ← Data
(ViewModels)   (UseCases)  (Repositories)
                 ↕
              (Models)
```

**Rules**:
- Presentation depends on Domain (ViewModels call UseCases)
- Data depends on Domain (Repositories implement Domain interfaces)
- Domain has NO dependencies (pure Kotlin, no Android imports)
- Data sources (API, Database) are implementation details

#### MVVM Pattern
```
View (Composable) → ViewModel → UseCase → Repository → DataSource
     ↑                 ↓
     └─── StateFlow ───┘
```

**Example ViewModel**:
```kotlin
@HiltViewModel
class FileListViewModel @Inject constructor(
    private val getFilesUseCase: GetFilesUseCase,
    private val deleteFileUseCase: DeleteFileUseCase
) : ViewModel() {

    private val _uiState = MutableStateFlow<UiState>(UiState.Loading)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    fun loadFiles(path: String) {
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            getFilesUseCase(path).collect { result ->
                _uiState.value = when (result) {
                    is Result.Success -> UiState.Success(result.data)
                    is Result.Error -> UiState.Error(result.message)
                }
            }
        }
    }

    sealed class UiState {
        object Loading : UiState()
        data class Success(val files: List<FileItem>) : UiState()
        data class Error(val message: String) : UiState()
    }
}
```

**Example Composable**:
```kotlin
@Composable
fun FileListScreen(
    viewModel: FileListViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    LaunchedEffect(Unit) {
        viewModel.loadFiles("/")
    }

    when (val state = uiState) {
        is UiState.Loading -> LoadingIndicator()
        is UiState.Success -> FileList(files = state.files)
        is UiState.Error -> ErrorMessage(message = state.message)
    }
}
```

### Compose Best Practices

1. **State Hoisting**: Lift state to parent composables
   ```kotlin
   @Composable
   fun SearchBar(
       query: String,
       onQueryChange: (String) -> Unit
   ) {
       TextField(value = query, onValueChange = onQueryChange)
   }
   ```

2. **Remember & Side Effects**:
   - `remember`: Preserve state across recompositions
   - `LaunchedEffect`: Run coroutines tied to composable lifecycle
   - `DisposableEffect`: Cleanup resources when composable leaves composition

3. **Modifiers**: Apply modifiers in consistent order
   ```kotlin
   Box(
       modifier = Modifier
           .fillMaxWidth()      // Size first
           .padding(16.dp)      // Spacing second
           .background(Color.White)  // Appearance third
           .clickable { }       // Behavior last
   )
   ```

4. **Performance**:
   - Use `derivedStateOf` for expensive calculations
   - Use `key()` for lists with stable identifiers
   - Avoid lambda allocations in frequent recompositions

### Dependency Injection (Hilt)

**Module Example**:
```kotlin
@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideOkHttpClient(
        authInterceptor: AuthInterceptor
    ): OkHttpClient {
        return OkHttpClient.Builder()
            .addInterceptor(authInterceptor)
            .build()
    }

    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient): Retrofit {
        return Retrofit.Builder()
            .baseUrl(BuildConfig.BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }
}
```

**Inject in ViewModel**:
```kotlin
@HiltViewModel
class MyViewModel @Inject constructor(
    private val repository: MyRepository
) : ViewModel()
```

**Inject in Activity/Fragment**:
```kotlin
@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    @Inject lateinit var appLockManager: AppLockManager
}
```

### Coroutines & Flow

**Use Cases Return Flow**:
```kotlin
class GetFilesUseCase @Inject constructor(
    private val repository: FilesRepository
) {
    operator fun invoke(path: String): Flow<Result<List<FileItem>>> = flow {
        emit(Result.Loading)
        try {
            val files = repository.getFiles(path)
            emit(Result.Success(files))
        } catch (e: Exception) {
            emit(Result.Error(e.message ?: "Unknown error"))
        }
    }
}
```

**ViewModels Collect Flow**:
```kotlin
viewModelScope.launch {
    useCase().collect { result ->
        _uiState.value = result
    }
}
```

**Composables Collect as State**:
```kotlin
val uiState by viewModel.uiState.collectAsStateWithLifecycle()
```

### Error Handling

**Result Wrapper**:
```kotlin
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val message: String, val exception: Throwable? = null) : Result<Nothing>()
    object Loading : Result<Nothing>()
}
```

**Repository Pattern**:
```kotlin
override suspend fun uploadFile(file: File): Result<Unit> {
    return try {
        api.uploadFile(file)
        Result.Success(Unit)
    } catch (e: HttpException) {
        Result.Error("HTTP ${e.code()}: ${e.message()}")
    } catch (e: IOException) {
        Result.Error("Network error: ${e.message}")
    } catch (e: Exception) {
        Result.Error("Unexpected error: ${e.message}")
    }
}
```

## Important Features & Patterns

### 1. Authentication Flow

**Device Registration** (QR Code):
1. User scans QR code generated by desktop/web app
2. QR contains: `server_url`, `registration_token`, `device_name`, `vpn_config` (optional)
3. App calls `POST /api/mobile/register` with registration token
4. Backend returns: `access_token`, `refresh_token` (30-day validity), `user_info`
5. Tokens stored in `EncryptedSharedPreferences`

**Token Refresh**:
- Access tokens expire after 12 hours
- `AuthInterceptor` automatically refreshes on 401 responses
- Refresh token valid for 30 days
- App notifies user 7 days before expiration

**Implementation**: `data/local/security/SecureStorage.kt`, `domain/usecase/auth/RegisterDeviceUseCase.kt`

### 2. Offline Queue System

**Key Feature**: All file operations work offline and sync when online.

**Architecture**:
- Operations stored in Room database (`PendingOperationEntity`)
- `OfflineQueueRetryWorker` runs every 15 minutes
- Manual retry button in UI
- Guaranteed execution order (FIFO with timestamps)

**Supported Operations**:
- Upload file
- Delete file
- Move/rename file
- Create folder

**Implementation**: `data/repository/OfflineQueueRepositoryImpl.kt`, `domain/usecase/OfflineQueueManager.kt`

### 3. File Management

**Features**:
- Hierarchical navigation with breadcrumbs
- Thumbnail generation for images/videos
- Upload with progress (multipart/form-data)
- Download with caching
- Optimistic UI updates (instant feedback)

**Implementation**: `presentation/ui/screens/storage/`, `domain/usecase/files/`

### 4. VPN Integration (In Progress)

**WireGuard Setup**:
- VPN config embedded in QR code or fetched from backend
- `BaluHostVpnService` extends `VpnService`
- Foreground service with persistent notification
- Auto-reconnect on network changes

**Status**: Service structure complete, config management TODO

**Implementation**: `service/vpn/BaluHostVpnService.kt`

### 5. Background Sync (WorkManager)

**Scheduled Workers**:
- **Offline Queue Retry**: Every 15 minutes (periodic)
- **Cache Cleanup**: Daily at 3 AM (LRU + age-based)
- **Camera Backup**: On new photos detected (TODO)

**Configuration**:
```kotlin
// In BaluHostApplication.onCreate()
OfflineQueueWorkScheduler.schedulePeriodicRetry(context)
OfflineQueueWorkScheduler.scheduleCacheCleanup(context)
```

**Implementation**: `data/worker/`

## Backend API Integration

**Base URL**: Configured in `app/build.gradle.kts` → `BuildConfig.BASE_URL`

**Authentication**: JWT Bearer token in `Authorization` header (automatic via `AuthInterceptor`)

### Key Endpoints

#### Authentication & Registration
```
POST /api/mobile/register
Body: { registration_token, device_name, device_id }
Response: { access_token, refresh_token, user: {...} }

POST /api/auth/refresh
Body: { refresh_token }
Response: { access_token }
```

#### File Operations
```
GET  /api/files/list?path={path}
Response: { files: [{name, size, type, modified, ...}] }

POST /api/files/upload
Body: multipart/form-data (file + path)
Response: { success, path }

GET  /api/files/download?path={path}
Response: Binary file data

DELETE /api/files/delete?path={path}
Response: { success }

POST /api/files/move
Body: { source, destination }
Response: { success }
```

#### System Information
```
GET /api/system/info
Response: { hostname, os, cpu, memory, storage, ... }

GET /api/system/telemetry
Response: { cpu_usage, memory_usage, network_stats, ... }
```

#### VPN (TODO on backend)
```
GET /api/mobile/vpn/config
Response: { config: "<WireGuard config>", ... }
```

**API Interfaces**: `data/remote/api/*.kt`
**DTOs**: `data/remote/dto/*.kt`

## Testing Strategy

### Unit Tests (`test/`)
- **Target**: Use cases, ViewModels, repositories
- **Frameworks**: JUnit 4, Mockito-Kotlin, MockK, Turbine (Flow testing)
- **Mocking**: Mock repositories/APIs, test business logic in isolation

**Example**:
```kotlin
@Test
fun `uploadFile emits Success on successful upload`() = runTest {
    // Arrange
    val mockRepo = mock<FilesRepository>()
    whenever(mockRepo.uploadFile(any())).thenReturn(Result.Success(Unit))
    val useCase = UploadFileUseCase(mockRepo)

    // Act
    val result = useCase(File("test.txt")).first()

    // Assert
    assertTrue(result is Result.Success)
}
```

### Instrumented Tests (`androidTest/`)
- **Target**: UI components, database, integration tests
- **Frameworks**: Espresso, Compose UI Test, Hilt Testing, MockWebServer
- **Requires**: Android device or emulator

**Example Compose Test**:
```kotlin
@Test
fun fileListScreen_displaysFiles() {
    composeTestRule.setContent {
        FileListScreen()
    }

    composeTestRule.onNodeWithText("Documents").assertIsDisplayed()
    composeTestRule.onNodeWithText("test.txt").assertIsDisplayed()
}
```

### Running Tests
```bash
# Unit tests (fast, no device needed)
./gradlew test

# Instrumented tests (slow, requires device)
./gradlew connectedAndroidTest

# Specific test class
./gradlew test --tests "com.baluhost.android.domain.usecase.files.UploadFileUseCaseTest"
```

## Feature Status

### ✅ Complete (Production Ready)
- [x] QR code scanner with ML Kit
- [x] Device registration flow
- [x] JWT authentication with automatic refresh
- [x] Secure token storage (EncryptedSharedPreferences)
- [x] File browser with hierarchical navigation
- [x] Upload/download with progress tracking
- [x] Delete files with optimistic UI
- [x] Offline queue system (operations persist across app restarts)
- [x] WorkManager integration (periodic retry, cache cleanup)
- [x] Material 3 UI with dark mode
- [x] Jetpack Compose navigation
- [x] Hilt dependency injection
- [x] Room database
- [x] Network monitoring

### ⏳ In Progress (50-80% Complete)
- [ ] VPN integration (service structure done, config management TODO)
- [ ] Settings screen (repository scaffolded, UI pending)
- [ ] App lock with PIN/biometric (managers implemented, full flow pending)
- [ ] Media viewer (ExoPlayer dependencies added, screens TODO)

### 🔴 Not Started (Planned)
- [ ] Camera backup (WorkManager scaffold exists, logic TODO)
- [ ] Search & filter for file browser
- [ ] Share links (public links + permissions)
- [ ] DocumentsProvider (Android Files app integration)
- [ ] Multi-select for batch operations
- [ ] Notifications for sync/backup events
- [ ] Conflict resolution UI for sync
- [ ] Storage usage visualization

**Detailed Status**: See `STATUS_UND_ROADMAP.md` for comprehensive breakdown.

## Common Development Tasks

### Adding a New Screen

1. **Create Screen & ViewModel**
   ```kotlin
   // presentation/ui/screens/mysection/MyScreen.kt
   @Composable
   fun MyScreen(navController: NavController) {
       val viewModel: MyViewModel = hiltViewModel()
       // Compose UI
   }

   // presentation/ui/screens/mysection/MyViewModel.kt
   @HiltViewModel
   class MyViewModel @Inject constructor() : ViewModel() {
       // State & logic
   }
   ```

2. **Add Route to Navigation**
   ```kotlin
   // presentation/navigation/Screen.kt
   sealed class Screen(val route: String) {
       object MyScreen : Screen("my_screen")
   }

   // presentation/navigation/NavGraph.kt
   composable(Screen.MyScreen.route) {
       MyScreen(navController)
   }
   ```

3. **Navigate to Screen**
   ```kotlin
   navController.navigate(Screen.MyScreen.route)
   ```

### Adding a New API Endpoint

1. **Create DTO**
   ```kotlin
   // data/remote/dto/MyDto.kt
   data class MyResponseDto(
       val data: String
   )
   ```

2. **Define API Interface**
   ```kotlin
   // data/remote/api/MyApi.kt
   interface MyApi {
       @GET("my-endpoint")
       suspend fun getData(): MyResponseDto
   }
   ```

3. **Provide in Hilt Module**
   ```kotlin
   // di/NetworkModule.kt
   @Provides
   fun provideMyApi(retrofit: Retrofit): MyApi {
       return retrofit.create(MyApi::class.java)
   }
   ```

4. **Use in Repository**
   ```kotlin
   // data/repository/MyRepositoryImpl.kt
   class MyRepositoryImpl @Inject constructor(
       private val api: MyApi
   ) : MyRepository {
       override suspend fun getData(): Result<String> {
           return try {
               val response = api.getData()
               Result.Success(response.data)
           } catch (e: Exception) {
               Result.Error(e.message ?: "Unknown error")
           }
       }
   }
   ```

### Adding a Database Entity

1. **Create Entity**
   ```kotlin
   // data/local/database/entities/MyEntity.kt
   @Entity(tableName = "my_table")
   data class MyEntity(
       @PrimaryKey val id: String,
       @ColumnInfo(name = "name") val name: String
   )
   ```

2. **Create DAO**
   ```kotlin
   // data/local/database/dao/MyDao.kt
   @Dao
   interface MyDao {
       @Query("SELECT * FROM my_table")
       fun getAll(): Flow<List<MyEntity>>

       @Insert(onConflict = OnConflictStrategy.REPLACE)
       suspend fun insert(entity: MyEntity)
   }
   ```

3. **Add to Database**
   ```kotlin
   // data/local/database/BaluHostDatabase.kt
   @Database(
       entities = [MyEntity::class, /* ... */],
       version = 2
   )
   abstract class BaluHostDatabase : RoomDatabase() {
       abstract fun myDao(): MyDao
   }
   ```

4. **Provide in Hilt Module**
   ```kotlin
   // di/DatabaseModule.kt
   @Provides
   fun provideMyDao(db: BaluHostDatabase): MyDao {
       return db.myDao()
   }
   ```

### Adding a Background Worker

1. **Create Worker**
   ```kotlin
   // data/worker/MyWorker.kt
   @HiltWorker
   class MyWorker @AssistedInject constructor(
       @Assisted context: Context,
       @Assisted params: WorkerParameters,
       private val repository: MyRepository
   ) : CoroutineWorker(context, params) {

       override suspend fun doWork(): Result {
           return try {
               repository.doWork()
               Result.success()
           } catch (e: Exception) {
               Result.retry()
           }
       }
   }
   ```

2. **Schedule Worker**
   ```kotlin
   // BaluHostApplication.kt or scheduler class
   val workRequest = PeriodicWorkRequestBuilder<MyWorker>(15, TimeUnit.MINUTES)
       .setConstraints(
           Constraints.Builder()
               .setRequiredNetworkType(NetworkType.CONNECTED)
               .build()
       )
       .build()

   WorkManager.getInstance(context)
       .enqueueUniquePeriodicWork(
           "my_work",
           ExistingPeriodicWorkPolicy.KEEP,
           workRequest
       )
   ```

## Known Issues & Solutions

### Issue: Build fails with "Duplicate class" error
**Solution**: Clean build and rebuild
```bash
./gradlew clean
./gradlew build
```

### Issue: Hilt injection fails at runtime
**Solution**:
- Ensure class is annotated with `@AndroidEntryPoint` (Activity/Fragment) or `@HiltViewModel` (ViewModel)
- Verify module is installed in correct component (`@InstallIn(SingletonComponent::class)`)
- Rebuild project

### Issue: Compose preview not rendering
**Solution**:
- Ensure preview function is annotated with `@Preview`
- Use `@PreviewParameter` for complex data
- Try "Build & Refresh" in preview pane

### Issue: App crashes on API call with SSL error
**Solution**:
- For dev mode with self-signed certificates, enable cleartext traffic in `AndroidManifest.xml`:
  ```xml
  <application android:usesCleartextTraffic="true">
  ```
- For production, implement certificate pinning in `NetworkModule.kt`

### Issue: Room database version conflict
**Solution**: Increment database version in `@Database` annotation and create migration:
```kotlin
val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(database: SupportSQLiteDatabase) {
        database.execSQL("ALTER TABLE my_table ADD COLUMN new_column TEXT")
    }
}
```

## Quick Reference

### File Locations
- **Application class**: `BaluHostApplication.kt`
- **Main activity**: `presentation/MainActivity.kt`
- **Navigation**: `presentation/navigation/NavGraph.kt`
- **Theme**: `presentation/ui/theme/Theme.kt`
- **Build config**: `app/build.gradle.kts`
- **Dependencies**: `app/build.gradle.kts` dependencies block
- **Manifest**: `app/src/main/AndroidManifest.xml`

### Key Classes
- **Authentication**: `domain/usecase/auth/RegisterDeviceUseCase.kt`, `data/local/security/SecureStorage.kt`
- **File operations**: `domain/usecase/files/*.kt`, `data/repository/FilesRepositoryImpl.kt`
- **Offline queue**: `domain/usecase/OfflineQueueManager.kt`, `data/repository/OfflineQueueRepositoryImpl.kt`
- **Network interceptors**: `data/remote/interceptors/AuthInterceptor.kt`
- **Database**: `data/local/database/BaluHostDatabase.kt`

### Useful Commands
```bash
# Launch app on connected device
adb shell am start -n com.baluhost.android/.presentation.MainActivity

# View logs
adb logcat -s BaluHost

# Clear app data
adb shell pm clear com.baluhost.android

# Install APK
adb install -r app/build/outputs/apk/debug/app-debug.apk

# Take screenshot
adb exec-out screencap -p > screenshot.png
```

## Project Conventions

### DO:
- Use `StateFlow` for UI state in ViewModels
- Use `Flow` for data streams (repositories, use cases)
- Use `suspend` functions for one-shot operations
- Keep composables small and focused (single responsibility)
- Hoist state to parent composables
- Write meaningful commit messages
- Add KDoc comments for public APIs
- Use `sealed class` for UI states and navigation
- Handle loading/error states explicitly

### DON'T:
- Don't use `LiveData` (prefer `StateFlow`/`Flow`)
- Don't call `viewModelScope.launch` in composables (use `LaunchedEffect`)
- Don't use `GlobalScope` (use `viewModelScope`/`lifecycleScope`)
- Don't hardcode strings (use `strings.xml`)
- Don't perform I/O on main thread
- Don't suppress warnings without good reason
- Don't store sensitive data in plain text
- Don't use `!!` operator (use safe calls or `requireNotNull()` with message)

## Additional Documentation

- **README.md**: Project overview, features, setup
- **QUICK_START.md**: Fast reference guide (German)
- **TODO.md**: Top 3 priority tasks for current development cycle
- **STATUS_UND_ROADMAP.md**: Detailed feature status and roadmap
- **IMPLEMENTIERUNGS_PLAN.md**: Implementation guide
- **OFFLINE_QUEUE_COMPLETE.md**: Offline queue system documentation
- **docs/sync_backend_spec.md**: Sync backend specification

## Contact & Support

- **Issues**: GitHub Issues (repository URL needed)
- **Documentation**: See `docs/` directory and backend `TECHNICAL_DOCUMENTATION.md`
- **Maintainer**: Xveyn
- **Version**: 1.0.0 (60% complete as of Jan 2026)

---

**Last Updated**: January 29, 2026
**Current Branch**: `development`
**Backend Compatibility**: BaluHost Backend v1.4.0+
