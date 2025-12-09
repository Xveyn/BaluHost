Plan: Android App Security & UX Overhaul
Modernize BaluHost Android app with web-matching design, secure device registration with token expiration (30 days–6 months), biometric authentication, onboarding flow, push notifications, comprehensive testing, and localhost-only device registration.

Steps
Implement localhost-only device registration with flexible token expiration

Update mobile.py: Add expires_at field to MobileDevice model with configurable duration (30 days min, 6 months max)
Modify backend/app/api/routes/mobile_routes.py: Add token_validity_days parameter to QR generation endpoint with validation (30-180 days range)
Update backend/app/services/mobile_service.py: Calculate device token expiration based on user input, store in MobileDevice.expires_at
Add localhost validation: Check request.client.host in registration endpoint, reject if not 127.0.0.1/::1/localhost
Create scheduled task in backend/app/services/notification_service.py: Background worker checking token expiration (7 days, 3 days, 1 hour warnings)
Frontend changes in MobileDevicesPage.tsx: Add token validity duration slider (30-180 days) to QR generation modal
Android API update in RegistrationDto.kt: Add expiresAt field to response model
Build push notification system for token expiration warnings

Backend Firebase setup: Add Firebase Admin SDK to pyproject.toml, create backend/app/services/firebase_service.py with FCM token registration & notification sending methods
Create backend/app/services/notification_scheduler.py: Celery/APScheduler task querying devices with expires_at approaching (7d/3d/1h), calling firebase_service.send_expiration_warning()
Add API endpoint POST /api/mobile/devices/{device_id}/push-token in mobile_routes.py for FCM token registration
Android FCM integration: Add Firebase dependencies to build.gradle.kts, create MyFirebaseMessagingService extending FirebaseMessagingService
Implement onMessageReceived() in MyFirebaseMessagingService: Parse notification payload, show system notification with NotificationCompat.Builder
Update PreferencesManager.kt: Store FCM token, send to backend on app startup/token refresh
Handle notification tap: Deep link to device settings screen showing expiration warning with "Renew Token" action
Add device self-removal from Android app with backend synchronization

Android UI: Add "Remove Device" button in settings screen (android-app/app/src/main/java/com/baluhost/android/presentation/ui/screens/settings/SettingsScreen.kt)
Create DeviceRepository.deleteDevice(deviceId) method in data/repository/DeviceRepositoryImpl.kt calling DELETE /api/mobile/devices/{device_id}
ViewModel logic in SettingsViewModel: Confirm dialog → API call → Clear local tokens/preferences → Navigate to QR scanner screen
Backend validation in mobile_routes.py: Verify requesting device JWT matches target device ID (prevent deleting other devices)
Cascade deletion: Ensure MobileDevice.on_delete="CASCADE" properly removes CameraBackup, SyncFolder, UploadQueue entries via SQLAlchemy relationships
Web frontend update in MobileDevicesPage.tsx: Real-time refresh device list after deletion, show toast notification
Implement biometric authentication with secure token storage

Add dependencies to build.gradle.kts: androidx.biometric:biometric-ktx:1.2.0-alpha05, androidx.security:security-crypto:1.1.0-alpha06
Create android-app/app/src/main/java/com/baluhost/android/data/local/security/SecurePreferencesManager.kt: Wrapper using EncryptedSharedPreferences for JWT tokens
Migrate PreferencesManager token storage: Move accessToken/refreshToken to SecurePreferencesManager, keep non-sensitive data in DataStore
Implement BiometricAuthManager.kt: Check biometric availability (BiometricManager.canAuthenticate()), show prompt with BiometricPrompt.Builder
App lock flow: Add LockScreen.kt composable showing fingerprint icon, call BiometricAuthManager.authenticate() on app resume (via LifecycleObserver)
Fallback PIN/pattern: If biometrics unavailable, create 4-digit PIN stored encrypted via EncryptedSharedPreferences, validate on unlock
Auto-lock timeout: Store last background timestamp in DataStore, require re-auth if >5 minutes elapsed
Settings toggle: Add biometric/PIN enable/disable option in SettingsScreen, allow biometric re-enrollment
Design onboarding wizard replacing immediate camera launch

Create android-app/app/src/main/java/com/baluhost/android/presentation/ui/screens/onboarding/ package with OnboardingScreen.kt, OnboardingViewModel.kt
Multi-step wizard with HorizontalPager:
Step 1: Welcome screen explaining BaluHost features (file access, camera backup, VPN)
Step 2: Server connection via QR code scan (integrate QrScannerScreen)
Step 3: Permission requests (camera for QR, notifications, media access for backup)
Step 4: Biometric/PIN setup screen (optional, skippable)
Step 5: Success confirmation with "Get Started" button
Onboarding state management: Store onboardingCompleted boolean in DataStore, check in MainActivity.onCreate() to route to onboarding vs main screen
Navigation update in NavGraph.kt: Set OnboardingScreen as start destination if not completed
Material 3 design: Use Surface cards with glassmorphism effects, animated illustrations (Lottie or vector drawables), progress indicator dots
Skip option: Allow skipping optional steps (biometric, backup settings), mark onboarding complete anyway
Match web frontend design system in Android app

Update Color.kt: Replace Material default colors with web palette (slate-950 background #0F172A, sky-400 primary #38BDF8, indigo-500 secondary #6366F1)
Create custom Theme.kt dark scheme: darkColorScheme(primary = DarkPrimary, background = DarkBackground, surface = DarkSurface, ...) matching web's dark glassmorphism
Component styling: Build reusable composables in ui/components/:
GlassCard.kt: Semi-transparent surface with backdrop blur effect (Modifier.blur(), Color(0x8C1E293B))
GradientButton.kt: Horizontal gradient background (Brush.horizontalGradient() with sky-500 → indigo-500 → violet-500)
GlassTextField.kt: Dark slate background with sky-blue focus ring
Typography: Match web fonts with Roboto/System default, but use web's size scale (text-sm: 14sp, text-base: 16sp, text-lg: 18sp)
Icon consistency: Use Material Symbols matching Lucide icons from web (align icon names/styles)
Screen templates: Apply glassmorphism cards to FilesScreen, SettingsScreen, device list items, camera backup UI
Gradient accents: Add gradient text for headings using TextStyle(brush = Brush.linearGradient(...)), gradient dividers in lists
Implement comprehensive testing strategy (Unit + Integration + UI)

Unit Tests in test:
AuthRepositoryTest.kt: Mock AuthApi with MockWebServer, test login/register/token refresh flows, verify JWT handling
DeviceRepositoryTest.kt: Test device deletion API call, verify local data clearing
BiometricAuthManagerTest.kt: Mock BiometricPrompt, test authentication success/failure/cancellation paths
SecurePreferencesManagerTest.kt: Test encrypted token storage/retrieval, verify encryption
Integration Tests in android-app/app/src/androidTest/:
RegistrationFlowTest.kt: End-to-end QR scan → device registration → token storage → API authentication
CameraBackupWorkerTest.kt: Test WorkManager scheduling, media upload with mock backend, retry logic
PushNotificationTest.kt: Simulate FCM message reception, verify notification display
UI Tests with Espresso/Compose Testing:
OnboardingScreenTest.kt: Navigate through wizard steps, verify onboarding completion state
LockScreenTest.kt: Test biometric prompt triggering, PIN fallback, successful unlock navigation
SettingsScreenTest.kt: Test device removal confirmation dialog, biometric toggle
Test Coverage: Configure JaCoCo in build.gradle.kts, target 80%+ coverage for repositories/ViewModels
CI/CD: GitHub Actions workflow running ./gradlew test connectedAndroidTest lint on PR, generate test reports
Further Considerations
Security hardening - Certificate pinning & root detection? Recommendation: Add OkHttp CertificatePinner for backend API (pin leaf certificate or public key), use SafetyNet/Play Integrity API to detect rooted devices, add tamper detection via ProGuard obfuscation + runtime integrity checks (signature verification)

Token renewal UX - Auto-renew or manual? Recommendation: Option A (auto-renew): App shows notification → user taps → biometric auth → new QR generated in web app; Option B (manual renewal): User must access web app on localhost to regenerate QR, provides better security control; Suggest Option B to enforce localhost requirement consistently

Offline mode strategy - How long cache valid data? Recommendation: Room database caching file metadata for 24 hours, allow read-only file browsing offline, queue uploads/downloads via WorkManager with exponential backoff (sync when online), add "Offline Mode" indicator in UI

VPN always-on integration - Separate from main auth? Recommendation: Decouple VPN from device registration (optional feature), add VPN settings screen with connect/disconnect toggle, use Android VpnService with WireGuard-Android library, respect system always-on VPN settings, add connection status monitoring

Multi-device token management - Revoke all devices button? Recommendation: Add "Sign Out All Devices" button in web app settings (POST /api/mobile/devices/revoke-all), invalidate all device tokens in database, send FCM notification to all devices triggering logout, useful for security incidents

GDPR compliance - Data deletion handling? Recommendation: Add "Delete Account" option triggering CASCADE deletion of all MobileDevice, CameraBackup, uploaded files, audit logs; export user data endpoint (GET /api/users/me/export) returning JSON with all personal data; add privacy policy link in onboarding

Security Best Practices Summary:

🔐 Localhost-only registration prevents remote device hijacking
🔑 EncryptedSharedPreferences protects JWT tokens at rest
👆 Biometric auth adds layer against device theft/unauthorized access
📱 FCM push notifications enable timely expiration warnings
⏰ Token expiration (30d-6m) limits compromised token lifetime
🛡️ Certificate pinning prevents MITM attacks on API calls
🚫 Root detection protects against malicious apps extracting tokens
🔍 Audit logging tracks device registration/deletion for security review
🗑️ CASCADE deletion ensures no orphaned sensitive data