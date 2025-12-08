# BaluHost Android App Development Guide

## Overview

This guide covers the complete implementation of the **BaluHost Android mobile client** using **Kotlin + Jetpack Compose**, including authentication, VPN integration, file management, and Android Files app integration.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Setup & Prerequisites](#setup--prerequisites)
3. [Project Structure](#project-structure)
4. [Authentication Flow](#authentication-flow)
5. [VPN Integration (WireGuard)](#vpn-integration-wireguard)
6. [File Management](#file-management)
7. [Android Files App Integration](#android-files-app-integration)
8. [Camera Backup](#camera-backup)
9. [Background Sync](#background-sync)
10. [Testing Strategy](#testing-strategy)
11. [Build & Deployment](#build--deployment)

---

## Architecture Overview

### Technology Stack

- **Language:** Kotlin 1.9+
- **UI:** Jetpack Compose (Material 3)
- **Architecture:** Clean Architecture + MVVM
- **Dependency Injection:** Hilt
- **Networking:** Retrofit + OkHttp
- **Local Storage:** Room + DataStore
- **Minimum SDK:** API 26 (Android 8.0)
- **Target SDK:** API 34 (Android 14)

### Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│                  Presentation Layer                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Composables  │  │  ViewModels  │  │   UIState    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    Domain Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Use Cases   │  │ Repositories │  │   Entities   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│                     Data Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  API Client  │  │  Local DB    │  │ Preferences  │  │
│  │  (Retrofit)  │  │  (Room)      │  │ (DataStore)  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Setup & Prerequisites

### 1. Build Configuration

**build.gradle.kts (Project)**

```kotlin
plugins {
    id("com.android.application") version "8.1.4" apply false
    id("org.jetbrains.kotlin.android") version "1.9.10" apply false
    id("com.google.dagger.hilt.android") version "2.48" apply false
}
```

**build.gradle.kts (Module: app)**

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("kotlin-kapt")
    id("dagger.hilt.android.plugin")
    id("kotlin-parcelize")
}

android {
    namespace = "com.baluhost.android"
    compileSdk = 34
    
    defaultConfig {
        applicationId = "com.baluhost.android"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
        
        testInstrumentationRunner = "com.baluhost.android.HiltTestRunner"
        
        buildConfigField("String", "BASE_URL", "\"https://baluhost.local:3001/api/\"")
    }
    
    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            isDebuggable = true
        }
    }
    
    buildFeatures {
        compose = true
        buildConfig = true
    }
    
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.3"
    }
    
    kotlinOptions {
        jvmTarget = "17"
    }
    
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    // Jetpack Compose
    val composeVersion = "1.5.4"
    implementation("androidx.compose.ui:ui:$composeVersion")
    implementation("androidx.compose.material3:material3:1.1.2")
    implementation("androidx.compose.ui:ui-tooling-preview:$composeVersion")
    implementation("androidx.activity:activity-compose:1.8.0")
    implementation("androidx.navigation:navigation-compose:2.7.5")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.6.2")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.6.2")
    
    // Dependency Injection - Hilt
    implementation("com.google.dagger:hilt-android:2.48")
    kapt("com.google.dagger:hilt-compiler:2.48")
    implementation("androidx.hilt:hilt-navigation-compose:1.1.0")
    implementation("androidx.hilt:hilt-work:1.1.0")
    kapt("androidx.hilt:hilt-compiler:1.1.0")
    
    // Networking
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("com.squareup.retrofit2:converter-gson:2.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    
    // Local Storage
    val roomVersion = "2.6.0"
    implementation("androidx.room:room-runtime:$roomVersion")
    implementation("androidx.room:room-ktx:$roomVersion")
    kapt("androidx.room:room-compiler:$roomVersion")
    implementation("androidx.datastore:datastore-preferences:1.0.0")
    
    // Security
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    
    // WireGuard VPN
    implementation("com.wireguard.android:tunnel:1.0.20230706")
    
    // WorkManager
    implementation("androidx.work:work-runtime-ktx:2.9.0")
    
    // Camera & Media
    val cameraxVersion = "1.3.0"
    implementation("androidx.camera:camera-camera2:$cameraxVersion")
    implementation("androidx.camera:camera-lifecycle:$cameraxVersion")
    implementation("androidx.camera:camera-view:$cameraxVersion")
    
    // QR Code Scanning
    implementation("com.google.mlkit:barcode-scanning:17.2.0")
    
    // Image Loading
    implementation("io.coil-kt:coil-compose:2.5.0")
    
    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.7.3")
    
    // Gson
    implementation("com.google.code.gson:gson:2.10.1")
    
    // Testing
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.mockito.kotlin:mockito-kotlin:5.1.0")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.7.3")
    testImplementation("app.cash.turbine:turbine:1.0.0")
    testImplementation("com.google.truth:truth:1.1.5")
    
    // Android Instrumented Tests
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.1")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4:$composeVersion")
    androidTestImplementation("com.google.dagger:hilt-android-testing:2.48")
    kaptAndroidTest("com.google.dagger:hilt-compiler:2.48")
    androidTestImplementation("androidx.work:work-testing:2.9.0")
    
    // Debug
    debugImplementation("androidx.compose.ui:ui-tooling:$composeVersion")
    debugImplementation("androidx.compose.ui:ui-test-manifest:$composeVersion")
}
```

### 2. Android Manifest Permissions

**AndroidManifest.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <!-- Network -->
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    
    <!-- Camera for QR scanning -->
    <uses-permission android:name="android.permission.CAMERA" />
    
    <!-- Storage -->
    <uses-permission android:name="android.permission.READ_MEDIA_IMAGES" />
    <uses-permission android:name="android.permission.READ_MEDIA_VIDEO" />
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE"
                     android:maxSdkVersion="32" />
    
    <!-- VPN -->
    <uses-permission android:name="android.permission.BIND_VPN_SERVICE" />
    
    <!-- Foreground Service for VPN -->
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_SPECIAL_USE" />
    
    <!-- Work Manager for background sync -->
    <uses-permission android:name="android.permission.WAKE_LOCK" />

    <application
        android:name=".BaluHostApplication"
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:roundIcon="@mipmap/ic_launcher_round"
        android:supportsRtl="true"
        android:theme="@style/Theme.BaluHost"
        android:usesCleartextTraffic="false"
        android:networkSecurityConfig="@xml/network_security_config">
        
        <!-- Main Activity -->
        <activity
            android:name=".presentation.MainActivity"
            android:exported="true"
            android:theme="@style/Theme.BaluHost">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
        
        <!-- VPN Service -->
        <service
            android:name=".service.vpn.BaluHostVpnService"
            android:permission="android.permission.BIND_VPN_SERVICE"
            android:exported="false"
            android:foregroundServiceType="specialUse">
            <intent-filter>
                <action android:name="android.net.VpnService" />
            </intent-filter>
            <meta-data
                android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"
                android:value="VPN Connection" />
        </service>
        
        <!-- DocumentsProvider for Files App -->
        <provider
            android:name=".service.provider.BaluHostDocumentProvider"
            android:authorities="com.baluhost.android.documents"
            android:exported="true"
            android:grantUriPermissions="true"
            android:permission="android.permission.MANAGE_DOCUMENTS">
            <intent-filter>
                <action android:name="android.content.action.DOCUMENTS_PROVIDER" />
            </intent-filter>
        </provider>
        
        <!-- WorkManager Initialization -->
        <provider
            android:name="androidx.startup.InitializationProvider"
            android:authorities="${applicationId}.androidx-startup"
            android:exported="false"
            tools:node="merge">
            <meta-data
                android:name="androidx.work.WorkManagerInitializer"
                android:value="androidx.startup" />
        </provider>

    </application>

</manifest>
```

### 3. Network Security Configuration

**res/xml/network_security_config.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <!-- Trust user-added CA certificates for HTTPS -->
    <base-config>
        <trust-anchors>
            <certificates src="system" />
            <certificates src="user" />
        </trust-anchors>
    </base-config>
    
    <!-- Allow cleartext traffic for local development (remove in production) -->
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="true">localhost</domain>
        <domain includeSubdomains="true">10.0.2.2</domain>
        <domain includeSubdomains="true">192.168.1.0/24</domain>
    </domain-config>
</network-security-config>
```

---

## Project Structure

```
app/src/main/java/com/baluhost/android/
├── BaluHostApplication.kt              # Application class with Hilt
│
├── di/                                  # Dependency Injection
│   ├── AppModule.kt                     
│   ├── NetworkModule.kt                 
│   ├── DatabaseModule.kt                
│   └── RepositoryModule.kt              
│
├── data/                                # Data Layer
│   ├── local/
│   │   ├── database/
│   │   │   ├── BaluHostDatabase.kt
│   │   │   ├── dao/
│   │   │   │   ├── FileDao.kt
│   │   │   │   └── UserDao.kt
│   │   │   └── entities/
│   │   │       ├── FileEntity.kt
│   │   │       └── UserEntity.kt
│   │   ├── datastore/
│   │   │   └── PreferencesManager.kt
│   │   └── security/
│   │       └── SecureStorage.kt
│   ├── remote/
│   │   ├── api/
│   │   │   ├── AuthApi.kt
│   │   │   ├── FilesApi.kt
│   │   │   ├── MobileApi.kt
│   │   │   └── VpnApi.kt
│   │   ├── interceptors/
│   │   │   ├── AuthInterceptor.kt
│   │   │   └── ErrorInterceptor.kt
│   │   └── dto/
│   │       ├── AuthDto.kt
│   │       ├── FileDto.kt
│   │       └── RegistrationDto.kt
│   └── repository/
│       ├── AuthRepositoryImpl.kt
│       ├── FilesRepositoryImpl.kt
│       └── VpnRepositoryImpl.kt
│
├── domain/                              # Domain Layer
│   ├── model/
│   │   ├── User.kt
│   │   ├── File.kt
│   │   └── VpnConfig.kt
│   ├── repository/
│   │   ├── AuthRepository.kt
│   │   ├── FilesRepository.kt
│   │   └── VpnRepository.kt
│   └── usecase/
│       ├── auth/
│       │   ├── RegisterDeviceUseCase.kt
│       │   └── RefreshTokenUseCase.kt
│       ├── files/
│       │   ├── GetFilesUseCase.kt
│       │   ├── UploadFileUseCase.kt
│       │   └── DownloadFileUseCase.kt
│       └── vpn/
│           ├── ConnectVpnUseCase.kt
│           └── ImportConfigUseCase.kt
│
├── presentation/                        # Presentation Layer
│   ├── MainActivity.kt
│   ├── navigation/
│   │   ├── NavGraph.kt
│   │   └── Screen.kt
│   ├── ui/
│   │   ├── theme/
│   │   │   ├── Color.kt
│   │   │   ├── Theme.kt
│   │   │   └── Type.kt
│   │   ├── components/
│   │   │   ├── LoadingButton.kt
│   │   │   └── FileListItem.kt
│   │   └── screens/
│   │       ├── splash/
│   │       │   ├── SplashScreen.kt
│   │       │   └── SplashViewModel.kt
│   │       ├── registration/
│   │       │   ├── QrScannerScreen.kt
│   │       │   └── QrScannerViewModel.kt
│   │       ├── files/
│   │       │   ├── FilesScreen.kt
│   │       │   └── FilesViewModel.kt
│   │       └── vpn/
│   │           ├── VpnScreen.kt
│   │           └── VpnViewModel.kt
│   └── util/
│       └── Extensions.kt
│
├── service/                             # Android Services
│   ├── vpn/
│   │   └── BaluHostVpnService.kt
│   ├── sync/
│   │   └── CameraBackupWorker.kt
│   └── provider/
│       └── BaluHostDocumentProvider.kt
│
└── util/
    ├── Constants.kt
    ├── Result.kt
    └── NetworkMonitor.kt
```

---

## Authentication Flow

### 1. QR Code Scanner with ML Kit

**presentation/ui/screens/registration/QrScannerScreen.kt**

```kotlin
@Composable
fun QrScannerScreen(
    onQrCodeScanned: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    
    val cameraProviderFuture = remember { ProcessCameraProvider.getInstance(context) }
    
    AndroidView(
        factory = { ctx ->
            val previewView = PreviewView(ctx)
            val preview = Preview.Builder().build()
            val selector = CameraSelector.Builder()
                .requireLensFacing(CameraSelector.LENS_FACING_BACK)
                .build()
            
            preview.setSurfaceProvider(previewView.surfaceProvider)
            
            val imageAnalysis = ImageAnalysis.Builder()
                .setTargetResolution(Size(1280, 720))
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
            
            val scanner = BarcodeScanning.getClient(
                BarcodeScannerOptions.Builder()
                    .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                    .build()
            )
            
            imageAnalysis.setAnalyzer(ContextCompat.getMainExecutor(ctx)) { imageProxy ->
                val mediaImage = imageProxy.image
                if (mediaImage != null) {
                    val image = InputImage.fromMediaImage(
                        mediaImage,
                        imageProxy.imageInfo.rotationDegrees
                    )
                    
                    scanner.process(image)
                        .addOnSuccessListener { barcodes ->
                            barcodes.firstOrNull()?.rawValue?.let { qrData ->
                                onQrCodeScanned(qrData)
                            }
                        }
                        .addOnCompleteListener {
                            imageProxy.close()
                        }
                }
            }
            
            try {
                cameraProviderFuture.get().bindToLifecycle(
                    lifecycleOwner,
                    selector,
                    preview,
                    imageAnalysis
                )
            } catch (e: Exception) {
                Log.e("QrScanner", "Camera binding failed", e)
            }
            
            previewView
        },
        modifier = modifier
    )
}
```

### 2. Device Registration ViewModel

**presentation/ui/screens/registration/QrScannerViewModel.kt**

```kotlin
@HiltViewModel
class QrScannerViewModel @Inject constructor(
    private val registerDeviceUseCase: RegisterDeviceUseCase,
    private val importVpnConfigUseCase: ImportConfigUseCase,
    private val preferencesManager: PreferencesManager
) : ViewModel() {

    private val _uiState = MutableStateFlow<QrScannerState>(QrScannerState.Scanning)
    val uiState: StateFlow<QrScannerState> = _uiState.asStateFlow()

    fun onQrCodeScanned(qrData: String) {
        if (_uiState.value !is QrScannerState.Scanning) return
        
        viewModelScope.launch {
            _uiState.value = QrScannerState.Processing
            
            try {
                val registrationData = Gson().fromJson(qrData, RegistrationData::class.java)
                
                val result = registerDeviceUseCase(
                    token = registrationData.token,
                    serverUrl = registrationData.server,
                    deviceInfo = getDeviceInfo()
                )
                
                when (result) {
                    is Result.Success -> {
                        // Save tokens
                        preferencesManager.saveAccessToken(result.data.accessToken)
                        preferencesManager.saveRefreshToken(result.data.refreshToken)
                        preferencesManager.saveServerUrl(registrationData.server)
                        
                        // Import VPN config if available
                        registrationData.vpnConfig?.let { vpnConfig ->
                            val decodedConfig = String(
                                Base64.decode(vpnConfig, Base64.DEFAULT),
                                Charsets.UTF_8
                            )
                            importVpnConfigUseCase(decodedConfig)
                        }
                        
                        _uiState.value = QrScannerState.Success(result.data.user)
                    }
                    is Result.Error -> {
                        _uiState.value = QrScannerState.Error(result.exception.message)
                    }
                }
            } catch (e: Exception) {
                _uiState.value = QrScannerState.Error(e.message ?: "Unknown error")
            }
        }
    }
    
    private fun getDeviceInfo(): DeviceInfo {
        return DeviceInfo(
            deviceName = "${Build.MANUFACTURER} ${Build.MODEL}",
            deviceType = "android",
            deviceModel = Build.MODEL,
            osVersion = "Android ${Build.VERSION.RELEASE}",
            appVersion = BuildConfig.VERSION_NAME
        )
    }
    
    fun resetScanner() {
        _uiState.value = QrScannerState.Scanning
    }
}

sealed class QrScannerState {
    object Scanning : QrScannerState()
    object Processing : QrScannerState()
    data class Success(val user: User) : QrScannerState()
    data class Error(val message: String?) : QrScannerState()
}

data class RegistrationData(
    val token: String,
    val server: String,
    @SerializedName("expires_at") val expiresAt: String,
    @SerializedName("vpn_config") val vpnConfig: String?
)
```

### 3. Auth Interceptor with Token Refresh

**data/remote/interceptors/AuthInterceptor.kt**

```kotlin
class AuthInterceptor @Inject constructor(
    private val preferencesManager: PreferencesManager,
    private val authApi: Lazy<AuthApi>
) : Interceptor {
    
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        
        // Skip auth for login/register endpoints
        if (request.url.encodedPath.contains("/auth/login") ||
            request.url.encodedPath.contains("/auth/register") ||
            request.url.encodedPath.contains("/mobile/register")) {
            return chain.proceed(request)
        }
        
        // Add access token
        val token = runBlocking { preferencesManager.getAccessToken() }
        val authenticatedRequest = if (token != null) {
            request.newBuilder()
                .header("Authorization", "Bearer $token")
                .build()
        } else {
            request
        }
        
        var response = chain.proceed(authenticatedRequest)
        
        // Handle 401 - Token expired
        if (response.code == 401 && token != null) {
            response.close()
            
            synchronized(this) {
                // Check if token was refreshed by another thread
                val currentToken = runBlocking { preferencesManager.getAccessToken() }
                if (currentToken != token) {
                    // Token was refreshed, retry with new token
                    return chain.proceed(
                        request.newBuilder()
                            .header("Authorization", "Bearer $currentToken")
                            .build()
                    )
                }
                
                // Try to refresh token
                val refreshToken = runBlocking { preferencesManager.getRefreshToken() }
                if (refreshToken != null) {
                    try {
                        val refreshResponse = runBlocking {
                            authApi.get().refreshToken(RefreshTokenRequest(refreshToken))
                        }
                        
                        // Save new access token
                        runBlocking {
                            preferencesManager.saveAccessToken(refreshResponse.accessToken)
                        }
                        
                        // Retry original request with new token
                        response = chain.proceed(
                            request.newBuilder()
                                .header("Authorization", "Bearer ${refreshResponse.accessToken}")
                                .build()
                        )
                    } catch (e: Exception) {
                        Log.e(TAG, "Token refresh failed", e)
                        // Clear tokens
                        runBlocking {
                            preferencesManager.clearTokens()
                        }
                    }
                }
            }
        }
        
        return response
    }
    
    companion object {
        private const val TAG = "AuthInterceptor"
    }
}
```

---

## VPN Integration (WireGuard)

### 1. VPN Service Implementation

**service/vpn/BaluHostVpnService.kt**

```kotlin
class BaluHostVpnService : VpnService() {
    
    private var tunnel: Tunnel? = null
    private val backend by lazy { Backend.create(this) }
    
    override fun onCreate() {
        super.onCreate()
        showNotification()
    }
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_CONNECT -> {
                val configString = intent.getStringExtra(EXTRA_CONFIG)
                if (configString != null) {
                    startVpn(configString)
                }
            }
            ACTION_DISCONNECT -> {
                stopVpn()
            }
        }
        return START_STICKY
    }
    
    private fun startVpn(configString: String) {
        try {
            val config = Config.parse(configString.byteInputStream())
            
            val builder = Builder()
                .setSession("BaluHost VPN")
                .setMtu(config.`interface`.mtu.orElse(1280))
            
            // Add addresses
            config.`interface`.addresses.forEach { address ->
                builder.addAddress(address.address, address.mask)
            }
            
            // Add DNS servers
            config.`interface`.dnsServers.forEach { dns ->
                builder.addDnsServer(dns.hostAddress)
            }
            
            // Add routes
            config.peers.forEach { peer ->
                peer.allowedIps.forEach { allowedIp ->
                    builder.addRoute(allowedIp.address, allowedIp.mask)
                }
            }
            
            // Establish VPN interface
            val vpnInterface = builder.establish()
                ?: throw IllegalStateException("Failed to establish VPN interface")
            
            // Create tunnel
            tunnel = Tunnel(
                name = "BaluHost",
                config = config,
                state = Tunnel.State.UP,
                statistics = null
            )
            
            // Start WireGuard backend
            backend.setState(tunnel!!, Tunnel.State.UP, config)
            
            // Update notification
            showConnectedNotification()
            
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start VPN", e)
            stopSelf()
        }
    }
    
    private fun stopVpn() {
        tunnel?.let {
            backend.setState(it, Tunnel.State.DOWN, null)
        }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }
    
    private fun showNotification() {
        val notification = createNotification("VPN Disconnected", "Tap to connect")
        startForeground(NOTIFICATION_ID, notification)
    }
    
    private fun showConnectedNotification() {
        val notification = createNotification("VPN Connected", "Connection active")
        val notificationManager = getSystemService(NotificationManager::class.java)
        notificationManager.notify(NOTIFICATION_ID, notification)
    }
    
    private fun createNotification(title: String, text: String): Notification {
        val channelId = "vpn_service_channel"
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "VPN Service",
                NotificationManager.IMPORTANCE_LOW
            )
            val notificationManager = getSystemService(NotificationManager::class.java)
            notificationManager.createNotificationChannel(channel)
        }
        
        return NotificationCompat.Builder(this, channelId)
            .setContentTitle(title)
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_vpn)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
    }
    
    override fun onDestroy() {
        stopVpn()
        super.onDestroy()
    }
    
    companion object {
        const val ACTION_CONNECT = "com.baluhost.android.vpn.CONNECT"
        const val ACTION_DISCONNECT = "com.baluhost.android.vpn.DISCONNECT"
        const val EXTRA_CONFIG = "config"
        private const val NOTIFICATION_ID = 1001
        private const val TAG = "BaluHostVpnService"
    }
}
```

### 2. VPN Connection UI

**presentation/ui/screens/vpn/VpnScreen.kt**

```kotlin
@Composable
fun VpnScreen(
    viewModel: VpnViewModel = hiltViewModel()
) {
    val vpnState by viewModel.vpnState.collectAsState()
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("VPN Connection") }
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            // VPN Status Icon
            Icon(
                imageVector = if (vpnState.isConnected) {
                    Icons.Filled.Lock
                } else {
                    Icons.Outlined.LockOpen
                },
                contentDescription = "VPN Status",
                modifier = Modifier.size(120.dp),
                tint = if (vpnState.isConnected) {
                    MaterialTheme.colorScheme.primary
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                }
            )
            
            Spacer(modifier = Modifier.height(24.dp))
            
            // Status Text
            Text(
                text = if (vpnState.isConnected) "Connected" else "Disconnected",
                style = MaterialTheme.typography.headlineMedium
            )
            
            Spacer(modifier = Modifier.height(8.dp))
            
            if (vpnState.serverEndpoint != null) {
                Text(
                    text = vpnState.serverEndpoint,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            
            Spacer(modifier = Modifier.height(32.dp))
            
            // Connect/Disconnect Button
            Button(
                onClick = {
                    if (vpnState.isConnected) {
                        viewModel.disconnect()
                    } else {
                        viewModel.connect()
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (vpnState.isConnected) {
                        MaterialTheme.colorScheme.error
                    } else {
                        MaterialTheme.colorScheme.primary
                    }
                ),
                enabled = !vpnState.isLoading
            ) {
                if (vpnState.isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(24.dp),
                        color = MaterialTheme.colorScheme.onPrimary
                    )
                } else {
                    Text(
                        text = if (vpnState.isConnected) "Disconnect" else "Connect",
                        style = MaterialTheme.typography.titleMedium
                    )
                }
            }
            
            // Error Message
            if (vpnState.error != null) {
                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = vpnState.error,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }
    }
}
```

---

## File Management

### 1. Files Screen with Compose

**presentation/ui/screens/files/FilesScreen.kt**

```kotlin
@Composable
fun FilesScreen(
    viewModel: FilesViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val currentPath by viewModel.currentPath.collectAsState()
    
    Scaffold(
        topBar = {
            FilesTopBar(
                currentPath = currentPath,
                onNavigateUp = viewModel::navigateUp
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { viewModel.showUploadDialog() }
            ) {
                Icon(Icons.Default.Add, contentDescription = "Upload")
            }
        }
    ) { paddingValues ->
        when (uiState) {
            is FilesUiState.Loading -> {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
            
            is FilesUiState.Success -> {
                val files = (uiState as FilesUiState.Success).files
                
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues)
                ) {
                    items(files) { file ->
                        FileListItem(
                            file = file,
                            onClick = {
                                if (file.isDirectory) {
                                    viewModel.navigateToFolder(file.path)
                                } else {
                                    viewModel.downloadFile(file)
                                }
                            },
                            onLongClick = {
                                viewModel.showFileOptions(file)
                            }
                        )
                    }
                }
            }
            
            is FilesUiState.Error -> {
                ErrorScreen(
                    message = (uiState as FilesUiState.Error).message,
                    onRetry = viewModel::refresh
                )
            }
        }
    }
}

@Composable
fun FileListItem(
    file: FileItem,
    onClick: () -> Unit,
    onLongClick: () -> Unit
) {
    ListItem(
        headlineContent = { Text(file.name) },
        supportingContent = {
            Text(
                if (file.isDirectory) {
                    "Folder"
                } else {
                    formatFileSize(file.size)
                }
            )
        },
        leadingContent = {
            Icon(
                imageVector = if (file.isDirectory) {
                    Icons.Default.Folder
                } else {
                    Icons.Default.InsertDriveFile
                },
                contentDescription = null,
                tint = if (file.isDirectory) {
                    MaterialTheme.colorScheme.primary
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                }
            )
        },
        modifier = Modifier
            .clickable(onClick = onClick)
            .combinedClickable(
                onClick = onClick,
                onLongClick = onLongClick
            )
    )
}
```

---

## Android Files App Integration

### 1. DocumentsProvider Implementation

**service/provider/BaluHostDocumentProvider.kt**

```kotlin
class BaluHostDocumentProvider : DocumentsProvider() {
    
    private lateinit var filesRepository: FilesRepository
    
    override fun onCreate(): Boolean {
        // TODO: Inject repository via Hilt (requires custom initialization)
        return true
    }
    
    override fun queryRoots(projection: Array<String>?): Cursor {
        val result = MatrixCursor(projection ?: DEFAULT_ROOT_PROJECTION)
        
        result.newRow().apply {
            add(Root.COLUMN_ROOT_ID, ROOT_ID)
            add(Root.COLUMN_DOCUMENT_ID, ROOT_DOCUMENT_ID)
            add(Root.COLUMN_TITLE, "BaluHost")
            add(Root.COLUMN_SUMMARY, "Your NAS files")
            add(Root.COLUMN_ICON, R.drawable.ic_launcher_foreground)
            add(Root.COLUMN_FLAGS, 
                Root.FLAG_SUPPORTS_CREATE or 
                Root.FLAG_SUPPORTS_IS_CHILD or
                Root.FLAG_LOCAL_ONLY)
        }
        
        return result
    }
    
    override fun queryDocument(documentId: String, projection: Array<String>?): Cursor {
        val result = MatrixCursor(projection ?: DEFAULT_DOCUMENT_PROJECTION)
        
        runBlocking {
            try {
                val file = filesRepository.getFileMetadata(documentId)
                addFileRow(result, file)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to query document: $documentId", e)
            }
        }
        
        return result
    }
    
    override fun queryChildDocuments(
        parentDocumentId: String,
        projection: Array<String>?,
        sortOrder: String?
    ): Cursor {
        val result = MatrixCursor(projection ?: DEFAULT_DOCUMENT_PROJECTION)
        
        runBlocking {
            try {
                val files = filesRepository.listFiles(parentDocumentId)
                files.forEach { file ->
                    addFileRow(result, file)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to query children: $parentDocumentId", e)
            }
        }
        
        return result
    }
    
    override fun openDocument(
        documentId: String,
        mode: String,
        signal: CancellationSignal?
    ): ParcelFileDescriptor {
        val file = File(context!!.cacheDir, "temp_${System.currentTimeMillis()}")
        
        return when {
            mode.contains("w") -> {
                // Write mode - return file descriptor for upload later
                ParcelFileDescriptor.open(
                    file,
                    ParcelFileDescriptor.MODE_WRITE_ONLY or
                    ParcelFileDescriptor.MODE_CREATE or
                    ParcelFileDescriptor.MODE_TRUNCATE
                )
            }
            else -> {
                // Read mode - download file first
                runBlocking {
                    val data = filesRepository.downloadFile(documentId)
                    file.writeBytes(data)
                }
                
                ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
            }
        }
    }
    
    private fun addFileRow(cursor: MatrixCursor, file: FileItem) {
        cursor.newRow().apply {
            add(Document.COLUMN_DOCUMENT_ID, file.path)
            add(Document.COLUMN_DISPLAY_NAME, file.name)
            add(Document.COLUMN_MIME_TYPE, getMimeType(file))
            add(Document.COLUMN_SIZE, file.size)
            add(Document.COLUMN_LAST_MODIFIED, file.modifiedAt.toEpochMilli())
            add(Document.COLUMN_FLAGS, getDocumentFlags(file))
        }
    }
    
    private fun getMimeType(file: FileItem): String {
        return if (file.isDirectory) {
            Document.MIME_TYPE_DIR
        } else {
            file.mimeType ?: "application/octet-stream"
        }
    }
    
    private fun getDocumentFlags(file: FileItem): Int {
        var flags = 0
        if (file.isDirectory) {
            flags = flags or Document.FLAG_DIR_SUPPORTS_CREATE
        } else {
            flags = flags or Document.FLAG_SUPPORTS_WRITE or Document.FLAG_SUPPORTS_DELETE
        }
        return flags
    }
    
    companion object {
        private const val TAG = "BaluHostDocumentProvider"
        private const val ROOT_ID = "baluhost-root"
        private const val ROOT_DOCUMENT_ID = "/"
        
        private val DEFAULT_ROOT_PROJECTION = arrayOf(
            Root.COLUMN_ROOT_ID,
            Root.COLUMN_ICON,
            Root.COLUMN_TITLE,
            Root.COLUMN_FLAGS,
            Root.COLUMN_DOCUMENT_ID
        )
        
        private val DEFAULT_DOCUMENT_PROJECTION = arrayOf(
            Document.COLUMN_DOCUMENT_ID,
            Document.COLUMN_MIME_TYPE,
            Document.COLUMN_DISPLAY_NAME,
            Document.COLUMN_LAST_MODIFIED,
            Document.COLUMN_FLAGS,
            Document.COLUMN_SIZE
        )
    }
}
```

---

## Camera Backup

### 1. WorkManager Background Sync

**service/sync/CameraBackupWorker.kt**

```kotlin
@HiltWorker
class CameraBackupWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val filesRepository: FilesRepository,
    private val preferencesManager: PreferencesManager
) : CoroutineWorker(context, params) {
    
    override suspend fun doWork(): Result {
        if (!preferencesManager.isCameraBackupEnabled()) {
            return Result.success()
        }
        
        // Check network constraints
        if (preferencesManager.isWifiOnly() && !isWifiConnected()) {
            return Result.retry()
        }
        
        return try {
            val photos = getUnbackedUpPhotos()
            
            setProgress(workDataOf(
                "total" to photos.size,
                "current" to 0
            ))
            
            photos.forEachIndexed { index, photo ->
                uploadPhoto(photo)
                
                setProgress(workDataOf(
                    "total" to photos.size,
                    "current" to index + 1
                ))
            }
            
            Result.success()
        } catch (e: Exception) {
            Log.e(TAG, "Camera backup failed", e)
            if (runAttemptCount < MAX_RETRIES) {
                Result.retry()
            } else {
                Result.failure()
            }
        }
    }
    
    private suspend fun getUnbackedUpPhotos(): List<Photo> {
        val photos = mutableListOf<Photo>()
        val projection = arrayOf(
            MediaStore.Images.Media._ID,
            MediaStore.Images.Media.DISPLAY_NAME,
            MediaStore.Images.Media.DATE_ADDED,
            MediaStore.Images.Media.SIZE
        )
        
        val lastBackupTime = preferencesManager.getLastBackupTime()
        val selection = "${MediaStore.Images.Media.DATE_ADDED} > ?"
        val selectionArgs = arrayOf(lastBackupTime.toString())
        
        applicationContext.contentResolver.query(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            projection,
            selection,
            selectionArgs,
            "${MediaStore.Images.Media.DATE_ADDED} DESC"
        )?.use { cursor ->
            val idColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media._ID)
            val nameColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DISPLAY_NAME)
            val dateColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DATE_ADDED)
            val sizeColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.SIZE)
            
            while (cursor.moveToNext()) {
                photos.add(Photo(
                    id = cursor.getLong(idColumn),
                    name = cursor.getString(nameColumn),
                    dateAdded = cursor.getLong(dateColumn),
                    size = cursor.getLong(sizeColumn)
                ))
            }
        }
        
        return photos
    }
    
    private suspend fun uploadPhoto(photo: Photo) {
        val uri = ContentUris.withAppendedId(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            photo.id
        )
        
        applicationContext.contentResolver.openInputStream(uri)?.use { inputStream ->
            filesRepository.uploadFile(
                path = "Camera Backup/${photo.name}",
                data = inputStream.readBytes()
            )
        }
        
        preferencesManager.updateLastBackupTime(photo.dateAdded)
    }
    
    private fun isWifiConnected(): Boolean {
        val connectivityManager = applicationContext.getSystemService(
            Context.CONNECTIVITY_SERVICE
        ) as ConnectivityManager
        
        val network = connectivityManager.activeNetwork ?: return false
        val capabilities = connectivityManager.getNetworkCapabilities(network) ?: return false
        
        return capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
    }
    
    companion object {
        private const val TAG = "CameraBackupWorker"
        const val WORK_NAME = "camera_backup"
        private const val MAX_RETRIES = 3
    }
}

data class Photo(
    val id: Long,
    val name: String,
    val dateAdded: Long,
    val size: Long
)
```

---

## Testing Strategy

### 1. Unit Tests (JUnit + MockK)

**domain/usecase/files/UploadFileUseCaseTest.kt**

```kotlin
@ExperimentalCoroutinesTest
class UploadFileUseCaseTest {
    
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()
    
    private lateinit var filesRepository: FilesRepository
    private lateinit var uploadFileUseCase: UploadFileUseCase
    
    @Before
    fun setup() {
        filesRepository = mockk()
        uploadFileUseCase = UploadFileUseCase(filesRepository)
    }
    
    @Test
    fun `upload file success returns success result`() = runTest {
        // Given
        val path = "documents/test.pdf"
        val data = byteArrayOf(1, 2, 3)
        val expectedFile = FileItem(
            name = "test.pdf",
            path = path,
            size = data.size.toLong(),
            isDirectory = false,
            modifiedAt = Instant.now(),
            owner = "user1"
        )
        
        coEvery { 
            filesRepository.uploadFile(path, data) 
        } returns Result.Success(expectedFile)
        
        // When
        val result = uploadFileUseCase(path, data)
        
        // Then
        assertThat(result).isInstanceOf(Result.Success::class.java)
        assertThat((result as Result.Success).data).isEqualTo(expectedFile)
        coVerify(exactly = 1) { filesRepository.uploadFile(path, data) }
    }
}
```

### 2. UI Tests (Compose Test)

**presentation/ui/screens/files/FilesScreenTest.kt**

```kotlin
@HiltAndroidTest
class FilesScreenTest {
    
    @get:Rule(order = 0)
    val hiltRule = HiltAndroidRule(this)
    
    @get:Rule(order = 1)
    val composeTestRule = createAndroidComposeRule<MainActivity>()
    
    @Test
    fun filesScreen_displaysFileList() {
        composeTestRule.setContent {
            BaluHostTheme {
                FilesScreen()
            }
        }
        
        composeTestRule
            .onNodeWithText("document.pdf")
            .assertIsDisplayed()
        
        composeTestRule
            .onNodeWithText("folder")
            .assertIsDisplayed()
    }
}
```

---

## Build & Deployment

### 1. ProGuard Rules

**proguard-rules.pro**

```proguard
# Keep Retrofit annotations
-keepattributes Signature, InnerClasses, EnclosingMethod
-keepattributes RuntimeVisibleAnnotations, RuntimeVisibleParameterAnnotations
-keepclassmembers,allowshrinking,allowobfuscation interface * {
    @retrofit2.http.* <methods>;
}

# Keep Gson classes
-keep class com.google.gson.** { *; }
-keep class com.baluhost.android.data.remote.dto.** { *; }

# Keep WireGuard
-keep class com.wireguard.** { *; }

# Keep Hilt
-keep class dagger.hilt.** { *; }
-keep class javax.inject.** { *; }
```

### 2. Gradle Tasks

```bash
# Build debug APK
./gradlew assembleDebug

# Build release APK
./gradlew assembleRelease

# Run unit tests
./gradlew test

# Run instrumented tests
./gradlew connectedAndroidTest

# Generate test coverage report
./gradlew jacocoTestReport
```

---

## API Reference

### Endpoints Used by Android App

All endpoints are documented in the backend at `/docs` (Swagger UI).

**Key Endpoints:**
- `POST /api/mobile/token/generate?include_vpn=true` - Generate QR code (Desktop)
- `POST /api/mobile/register` - Register device
- `POST /api/auth/refresh` - Refresh access token
- `POST /api/vpn/generate-config` - Generate VPN config (optional)
- `GET /api/files/list?path=<path>` - List files
- `POST /api/files/upload` - Upload file
- `GET /api/files/download?path=<path>` - Download file
- `DELETE /api/files/delete?path=<path>` - Delete file

---

## Resources

- **Android Developers:** https://developer.android.com
- **Jetpack Compose:** https://developer.android.com/jetpack/compose
- **Hilt:** https://dagger.dev/hilt/
- **WireGuard Android:** https://git.zx2c4.com/wireguard-android/
- **ML Kit Barcode Scanning:** https://developers.google.com/ml-kit/vision/barcode-scanning
- **WorkManager:** https://developer.android.com/topic/libraries/architecture/workmanager

---

**Last Updated:** December 2025  
**BaluHost Version:** 1.3.0  
**Android Target SDK:** 34 (Android 14)  
**Minimum SDK:** 26 (Android 8.0)
