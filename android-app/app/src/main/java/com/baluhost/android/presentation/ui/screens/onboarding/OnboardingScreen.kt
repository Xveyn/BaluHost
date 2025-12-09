package com.baluhost.android.presentation.ui.screens.onboarding

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import kotlinx.coroutines.launch

/**
 * Onboarding wizard screen with multi-step flow.
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun OnboardingScreen(
    onNavigateToQrScanner: () -> Unit,
    onComplete: () -> Unit,
    viewModel: OnboardingViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val pagerState = rememberPagerState(pageCount = { OnboardingStep.values().size })
    val scope = rememberCoroutineScope()
    
    // Sync ViewModel state with pager state
    LaunchedEffect(pagerState.currentPage) {
        viewModel.goToStep(pagerState.currentPage)
    }
    
    // Navigate on completion
    LaunchedEffect(uiState.isCompleted) {
        if (uiState.isCompleted) {
            onComplete()
        }
    }
    
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                brush = Brush.verticalGradient(
                    colors = listOf(
                        Color(0xFF0F172A), // slate-950
                        Color(0xFF1E293B)  // slate-900
                    )
                )
            )
    ) {
        Column(
            modifier = Modifier.fillMaxSize()
        ) {
            // Progress Indicators
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 48.dp, bottom = 24.dp),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically
            ) {
                repeat(OnboardingStep.values().size) { index ->
                    Box(
                        modifier = Modifier
                            .size(if (index == pagerState.currentPage) 12.dp else 8.dp)
                            .clip(CircleShape)
                            .background(
                                if (index == pagerState.currentPage)
                                    Color(0xFF38BDF8) // sky-400
                                else
                                    Color(0xFF475569) // slate-600
                            )
                    )
                    
                    if (index < OnboardingStep.values().size - 1) {
                        Spacer(modifier = Modifier.width(8.dp))
                    }
                }
            }
            
            // Pager Content
            HorizontalPager(
                state = pagerState,
                modifier = Modifier.weight(1f),
                userScrollEnabled = false // Disable swipe, use buttons only
            ) { page ->
                when (OnboardingStep.values()[page]) {
                    OnboardingStep.WELCOME -> WelcomeStep()
                    OnboardingStep.QR_SCAN -> QrScanStep(onNavigateToQrScanner)
                    OnboardingStep.PERMISSIONS -> PermissionsStep()
                    OnboardingStep.BIOMETRIC_SETUP -> BiometricSetupStep(
                        onSkip = {
                            viewModel.skipBiometricSetup()
                            scope.launch {
                                pagerState.animateScrollToPage(page + 1)
                            }
                        }
                    )
                    OnboardingStep.SUCCESS -> SuccessStep()
                }
            }
            
            // Navigation Buttons
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp, vertical = 32.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Back Button
                if (pagerState.currentPage > 0 && pagerState.currentPage < OnboardingStep.values().size - 1) {
                    TextButton(onClick = {
                        scope.launch {
                            pagerState.animateScrollToPage(pagerState.currentPage - 1)
                        }
                    }) {
                        Icon(
                            Icons.Default.ArrowBack,
                            contentDescription = "Zurück",
                            modifier = Modifier.size(20.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Zurück")
                    }
                } else {
                    Spacer(modifier = Modifier.width(1.dp))
                }
                
                // Next/Complete Button
                Button(
                    onClick = {
                        if (pagerState.currentPage == OnboardingStep.values().size - 1) {
                            viewModel.completeOnboarding()
                        } else {
                            scope.launch {
                                pagerState.animateScrollToPage(pagerState.currentPage + 1)
                            }
                        }
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFF38BDF8) // sky-400
                    ),
                    modifier = Modifier.height(48.dp)
                ) {
                    Text(
                        text = if (pagerState.currentPage == OnboardingStep.values().size - 1)
                            "Los geht's!"
                        else
                            "Weiter",
                        fontWeight = FontWeight.SemiBold
                    )
                    if (pagerState.currentPage < OnboardingStep.values().size - 1) {
                        Spacer(modifier = Modifier.width(4.dp))
                        Icon(
                            Icons.Default.ArrowForward,
                            contentDescription = null,
                            modifier = Modifier.size(20.dp)
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun WelcomeStep() {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 32.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            Icons.Default.Cloud,
            contentDescription = null,
            modifier = Modifier.size(120.dp),
            tint = Color(0xFF38BDF8)
        )
        
        Spacer(modifier = Modifier.height(32.dp))
        
        Text(
            text = "Willkommen bei BaluHost",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
            color = Color.White,
            textAlign = TextAlign.Center
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = "Ihr persönliches NAS-System",
            style = MaterialTheme.typography.titleMedium,
            color = Color(0xFF94A3B8), // slate-400
            textAlign = TextAlign.Center
        )
        
        Spacer(modifier = Modifier.height(48.dp))
        
        FeatureCard(
            icon = Icons.Default.Folder,
            title = "Dateiverwaltung",
            description = "Greifen Sie von überall auf Ihre Dateien zu"
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        FeatureCard(
            icon = Icons.Default.CameraAlt,
            title = "Automatisches Backup",
            description = "Sichern Sie Ihre Fotos automatisch"
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        FeatureCard(
            icon = Icons.Default.VpnKey,
            title = "Sichere Verbindung",
            description = "VPN-Zugriff für maximale Sicherheit"
        )
    }
}

@Composable
private fun QrScanStep(onNavigateToQrScanner: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 32.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            Icons.Default.QrCodeScanner,
            contentDescription = null,
            modifier = Modifier.size(120.dp),
            tint = Color(0xFF6366F1) // indigo-500
        )
        
        Spacer(modifier = Modifier.height(32.dp))
        
        Text(
            text = "Server verbinden",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
            color = Color.White,
            textAlign = TextAlign.Center
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = "Scannen Sie den QR-Code aus der BaluHost Web-Oberfläche, um Ihr Gerät zu registrieren.",
            style = MaterialTheme.typography.bodyLarge,
            color = Color(0xFF94A3B8),
            textAlign = TextAlign.Center
        )
        
        Spacer(modifier = Modifier.height(48.dp))
        
        Button(
            onClick = onNavigateToQrScanner,
            colors = ButtonDefaults.buttonColors(
                containerColor = Color(0xFF6366F1)
            ),
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp)
        ) {
            Icon(
                Icons.Default.QrCodeScanner,
                contentDescription = null,
                modifier = Modifier.size(24.dp)
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = "QR-Code scannen",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold
            )
        }
        
        Spacer(modifier = Modifier.height(24.dp))
        
        InfoCard(
            title = "Wo finde ich den QR-Code?",
            description = "1. Öffnen Sie BaluHost im Browser (localhost)\n" +
                    "2. Navigieren Sie zu Einstellungen → Mobile Geräte\n" +
                    "3. Klicken Sie auf \"Neues Gerät registrieren\""
        )
    }
}

@Composable
private fun PermissionsStep() {
    var cameraGranted by remember { mutableStateOf(false) }
    var notificationsGranted by remember { mutableStateOf(false) }
    var mediaGranted by remember { mutableStateOf(false) }
    
    val cameraPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted -> cameraGranted = isGranted }
    
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted -> notificationsGranted = isGranted }
    
    val mediaPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions -> 
        mediaGranted = permissions.values.all { it }
    }
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 32.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            Icons.Default.Security,
            contentDescription = null,
            modifier = Modifier.size(120.dp),
            tint = Color(0xFFA855F7) // purple-500
        )
        
        Spacer(modifier = Modifier.height(32.dp))
        
        Text(
            text = "Berechtigungen",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
            color = Color.White,
            textAlign = TextAlign.Center
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = "Für die beste Erfahrung benötigen wir einige Berechtigungen.",
            style = MaterialTheme.typography.bodyLarge,
            color = Color(0xFF94A3B8),
            textAlign = TextAlign.Center
        )
        
        Spacer(modifier = Modifier.height(48.dp))
        
        PermissionCard(
            icon = Icons.Default.CameraAlt,
            title = "Kamera",
            description = "Zum Scannen von QR-Codes",
            isGranted = cameraGranted,
            onClick = { cameraPermissionLauncher.launch(Manifest.permission.CAMERA) }
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        PermissionCard(
            icon = Icons.Default.Notifications,
            title = "Benachrichtigungen",
            description = "Für wichtige Updates und Warnungen",
            isGranted = notificationsGranted,
            onClick = {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                } else {
                    notificationsGranted = true
                }
            }
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        PermissionCard(
            icon = Icons.Default.Photo,
            title = "Medienzugriff",
            description = "Für automatisches Foto-Backup",
            isGranted = mediaGranted,
            onClick = {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    mediaPermissionLauncher.launch(
                        arrayOf(
                            Manifest.permission.READ_MEDIA_IMAGES,
                            Manifest.permission.READ_MEDIA_VIDEO
                        )
                    )
                } else {
                    mediaPermissionLauncher.launch(
                        arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
                    )
                }
            }
        )
    }
}

@Composable
private fun BiometricSetupStep(onSkip: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 32.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            Icons.Default.Fingerprint,
            contentDescription = null,
            modifier = Modifier.size(120.dp),
            tint = Color(0xFFEC4899) // pink-500
        )
        
        Spacer(modifier = Modifier.height(32.dp))
        
        Text(
            text = "Biometrische Sicherheit",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
            color = Color.White,
            textAlign = TextAlign.Center
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = "Schützen Sie Ihre Daten mit Fingerabdruck oder Gesichtserkennung.",
            style = MaterialTheme.typography.bodyLarge,
            color = Color(0xFF94A3B8),
            textAlign = TextAlign.Center
        )
        
        Spacer(modifier = Modifier.height(48.dp))
        
        InfoCard(
            title = "Warum biometrische Sicherheit?",
            description = "• Schneller und sicherer Zugriff\n" +
                    "• Schutz vor unbefugtem Zugriff\n" +
                    "• Automatische Sperre nach Inaktivität\n" +
                    "• Optional: Zusätzliche PIN als Backup"
        )
        
        Spacer(modifier = Modifier.height(24.dp))
        
        TextButton(
            onClick = onSkip,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(
                text = "Später einrichten",
                color = Color(0xFF94A3B8)
            )
        }
        
        Spacer(modifier = Modifier.height(8.dp))
        
        Text(
            text = "Sie können dies jederzeit in den Einstellungen aktivieren.",
            style = MaterialTheme.typography.bodySmall,
            color = Color(0xFF64748B),
            textAlign = TextAlign.Center
        )
    }
}

@Composable
private fun SuccessStep() {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            Icons.Default.CheckCircle,
            contentDescription = null,
            modifier = Modifier.size(120.dp),
            tint = Color(0xFF10B981) // green-500
        )
        
        Spacer(modifier = Modifier.height(32.dp))
        
        Text(
            text = "Alles bereit!",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
            color = Color.White,
            textAlign = TextAlign.Center
        )
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Text(
            text = "Ihr BaluHost ist einsatzbereit. Viel Spaß beim Verwalten Ihrer Dateien!",
            style = MaterialTheme.typography.bodyLarge,
            color = Color(0xFF94A3B8),
            textAlign = TextAlign.Center
        )
    }
}

@Composable
private fun FeatureCard(
    icon: ImageVector,
    title: String,
    description: String
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = Color(0x1A38BDF8) // sky-400 with 10% opacity
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                icon,
                contentDescription = null,
                modifier = Modifier.size(32.dp),
                tint = Color(0xFF38BDF8)
            )
            
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White
                )
                Text(
                    text = description,
                    style = MaterialTheme.typography.bodySmall,
                    color = Color(0xFF94A3B8)
                )
            }
        }
    }
}

@Composable
private fun InfoCard(
    title: String,
    description: String
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = Color(0x1A6366F1)
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                color = Color.White
            )
            Text(
                text = description,
                style = MaterialTheme.typography.bodyMedium,
                color = Color(0xFF94A3B8)
            )
        }
    }
}

@Composable
private fun PermissionCard(
    icon: ImageVector,
    title: String,
    description: String,
    isGranted: Boolean,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (isGranted)
                Color(0x1A10B981) // green with opacity
            else
                Color(0x1AA855F7) // purple with opacity
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                icon,
                contentDescription = null,
                modifier = Modifier.size(32.dp),
                tint = if (isGranted) Color(0xFF10B981) else Color(0xFFA855F7)
            )
            
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White
                )
                Text(
                    text = description,
                    style = MaterialTheme.typography.bodySmall,
                    color = Color(0xFF94A3B8)
                )
            }
            
            if (!isGranted) {
                Button(
                    onClick = onClick,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFFA855F7)
                    )
                ) {
                    Text("Erlauben")
                }
            } else {
                Icon(
                    Icons.Default.CheckCircle,
                    contentDescription = "Erteilt",
                    tint = Color(0xFF10B981),
                    modifier = Modifier.size(24.dp)
                )
            }
        }
    }
}
