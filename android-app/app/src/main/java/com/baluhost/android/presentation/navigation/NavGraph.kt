package com.baluhost.android.presentation.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.baluhost.android.presentation.ui.screens.files.FilesScreen
import com.baluhost.android.presentation.ui.screens.lock.LockScreen
import com.baluhost.android.presentation.ui.screens.media.MediaViewerScreen
import com.baluhost.android.presentation.ui.screens.onboarding.OnboardingScreen
import com.baluhost.android.presentation.ui.screens.qrscanner.QrScannerScreen
import com.baluhost.android.presentation.ui.screens.settings.SettingsScreen
import com.baluhost.android.presentation.ui.screens.splash.SplashScreen
import com.baluhost.android.presentation.ui.screens.storage.StorageOverviewScreen
import com.baluhost.android.presentation.ui.screens.vpn.VpnScreen
import java.net.URLDecoder

/**
 * Main navigation graph for the app.
 */
@Composable
fun NavGraph(
    navController: NavHostController,
    startDestination: String = Screen.Splash.route
) {
    NavHost(
        navController = navController,
        startDestination = startDestination
    ) {
        composable(Screen.Splash.route) {
            SplashScreen(
                onNavigateToOnboarding = {
                    navController.navigate(Screen.Onboarding.route) {
                        popUpTo(Screen.Splash.route) { inclusive = true }
                    }
                },
                onNavigateToQrScanner = {
                    navController.navigate(Screen.QrScanner.route) {
                        popUpTo(Screen.Splash.route) { inclusive = true }
                    }
                },
                onNavigateToFiles = {
                    navController.navigate(Screen.Files.route) {
                        popUpTo(Screen.Splash.route) { inclusive = true }
                    }
                }
            )
        }
        
        composable(Screen.Onboarding.route) {
            OnboardingScreen(
                onNavigateToQrScanner = {
                    navController.navigate(Screen.QrScanner.route) {
                        launchSingleTop = true
                    }
                },
                onComplete = {
                    navController.navigate(Screen.Files.route) {
                        popUpTo(Screen.Onboarding.route) { inclusive = true }
                    }
                }
            )
        }
        
        composable(Screen.QrScanner.route) {
            QrScannerScreen(
                onNavigateToFiles = {
                    navController.navigate(Screen.Storage.route) {
                        popUpTo(Screen.QrScanner.route) { inclusive = true }
                    }
                },
                onNavigateBack = {
                    navController.popBackStack()
                }
            )
        }
        
        composable(Screen.Storage.route) {
            StorageOverviewScreen(
                onNavigateToFiles = {
                    navController.navigate(Screen.Files.route) {
                        popUpTo(Screen.Storage.route) { inclusive = true }
                    }
                },
                onNavigateBack = {
                    navController.popBackStack()
                }
            )
        }
        
        composable(Screen.Files.route) {
            FilesScreen(
                onNavigateToVpn = {
                    navController.navigate(Screen.Vpn.route)
                },
                onNavigateToSettings = {
                    navController.navigate(Screen.Settings.route)
                },
                onNavigateToMediaViewer = { fileUrl, fileName, mimeType ->
                    navController.navigate(
                        Screen.MediaViewer.createRoute(fileUrl, fileName, mimeType)
                    )
                }
            )
        }
        
        composable(
            route = Screen.MediaViewer.route,
            arguments = listOf(
                navArgument("fileUrl") { type = NavType.StringType },
                navArgument("fileName") { type = NavType.StringType },
                navArgument("mimeType") { type = NavType.StringType }
            )
        ) { backStackEntry ->
            val fileUrl = URLDecoder.decode(
                backStackEntry.arguments?.getString("fileUrl") ?: "",
                "UTF-8"
            )
            val fileName = URLDecoder.decode(
                backStackEntry.arguments?.getString("fileName") ?: "",
                "UTF-8"
            )
            val mimeType = URLDecoder.decode(
                backStackEntry.arguments?.getString("mimeType") ?: "",
                "UTF-8"
            ).takeIf { it != "unknown" }
            
            MediaViewerScreen(
                fileUrl = fileUrl,
                fileName = fileName,
                mimeType = mimeType,
                onNavigateBack = { navController.popBackStack() }
            )
        }
        
        composable(Screen.Vpn.route) {
            VpnScreen(
                onNavigateBack = {
                    navController.popBackStack()
                }
            )
        }
        
        composable(Screen.Settings.route) {
            SettingsScreen(
                onNavigateBack = {
                    navController.popBackStack()
                },
                onNavigateToSplash = {
                    navController.navigate(Screen.Splash.route) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }
        
        composable(Screen.Lock.route) {
            LockScreen(
                onUnlocked = {
                    navController.popBackStack()
                }
            )
        }
    }
}
