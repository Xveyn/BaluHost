package com.baluhost.android.presentation

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.lifecycleScope
import androidx.navigation.compose.rememberNavController
import com.baluhost.android.data.local.security.AppLockManager
import com.baluhost.android.presentation.navigation.NavGraph
import com.baluhost.android.presentation.navigation.Screen
import com.baluhost.android.presentation.ui.theme.BaluHostTheme
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Main activity for the BaluHost app.
 * Handles notification deep links, intent routing, and app lock lifecycle.
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    
    @Inject
    lateinit var appLockManager: AppLockManager
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        setContent {
            BaluHostTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val navController = rememberNavController()
                    var initialRoute by remember { mutableStateOf<String?>(null) }
                    var shouldShowLock by remember { mutableStateOf(false) }
                    
                    // Check if we should show lock screen on app startup
                    LaunchedEffect(Unit) {
                        shouldShowLock = appLockManager.shouldShowLockScreen()
                        if (shouldShowLock) {
                            Log.d(TAG, "App lock timeout exceeded, showing lock screen")
                        }
                    }
                    
                    // Handle initial intent on first composition
                    LaunchedEffect(Unit) {
                        initialRoute = handleIntent(intent)
                    }
                    
                    // Navigate to lock screen if needed
                    LaunchedEffect(shouldShowLock) {
                        if (shouldShowLock) {
                            navController.navigate(Screen.Lock.route) {
                                launchSingleTop = true
                            }
                            shouldShowLock = false
                        }
                    }
                    
                    // Navigate to initial route if provided
                    LaunchedEffect(initialRoute) {
                        initialRoute?.let { route ->
                            navController.navigate(route) {
                                // Clear back stack if coming from notification
                                popUpTo(navController.graph.startDestinationId) {
                                    inclusive = false
                                }
                                launchSingleTop = true
                            }
                        }
                    }
                    
                    NavGraph(navController = navController)
                }
            }
        }
    }
    
    override fun onStop() {
        super.onStop()
        // Record timestamp when app goes to background
        lifecycleScope.launch {
            appLockManager.onAppBackground()
            Log.d(TAG, "App moved to background, recording timestamp")
        }
    }
    
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        // Intent will be handled on next recomposition
    }
    
    /**
     * Handle incoming intents from notifications and deep links.
     * Returns the navigation route to open, or null if no special handling needed.
     */
    private fun handleIntent(intent: Intent?): String? {
        if (intent == null) return null
        
        val notificationType = intent.getStringExtra("notification_type")
        val action = intent.getStringExtra("action")
        val deepLink = intent.getStringExtra("deep_link")
        
        Log.d(TAG, "Handling intent: type=$notificationType, action=$action, deepLink=$deepLink")
        
        // Handle notification intents
        when (notificationType) {
            "expiration_warning" -> {
                Log.i(TAG, "Opening device settings for expiration warning")
                // TODO: Navigate to device settings or re-registration screen
                // return "device_settings" or "qr_scanner"
                return null // Placeholder until navigation routes are defined
            }
            "device_removed" -> {
                Log.i(TAG, "Device was removed, clearing local data")
                // TODO: Clear stored credentials and navigate to login
                // preferencesManager.clearAll()
                // return "qr_scanner"
                return null // Placeholder
            }
        }
        
        // Handle action intents
        when (action) {
            "renew_device" -> {
                Log.i(TAG, "Opening device renewal flow")
                // TODO: Navigate to re-registration screen
                return null // Placeholder
            }
        }
        
        // Handle deep links (baluhost:// scheme)
        if (intent.action == Intent.ACTION_VIEW) {
            val uri: Uri? = intent.data
            if (uri != null) {
                Log.i(TAG, "Handling deep link: $uri")
                return handleDeepLink(uri)
            }
        }
        
        return null
    }
    
    /**
     * Parse deep link URI and return navigation route.
     * Supports:
     * - baluhost://files -> File browser
     * - baluhost://settings -> Settings screen
     * - baluhost://device_settings -> Device settings
     * - baluhost://scan -> QR code scanner
     */
    private fun handleDeepLink(uri: Uri): String? {
        return when (uri.host) {
            "files" -> {
                Log.d(TAG, "Deep link to files")
                // TODO: Return file browser route
                null
            }
            "settings" -> {
                Log.d(TAG, "Deep link to settings")
                // TODO: Return settings route
                null
            }
            "device_settings" -> {
                Log.d(TAG, "Deep link to device settings")
                // TODO: Return device settings route
                null
            }
            "scan" -> {
                Log.d(TAG, "Deep link to QR scanner")
                // TODO: Return QR scanner route
                null
            }
            else -> {
                Log.w(TAG, "Unknown deep link host: ${uri.host}")
                null
            }
        }
    }
    
    companion object {
        private const val TAG = "MainActivity"
    }
}
