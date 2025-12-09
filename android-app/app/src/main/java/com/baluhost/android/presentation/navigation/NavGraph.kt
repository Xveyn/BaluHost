package com.baluhost.android.presentation.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import com.baluhost.android.presentation.ui.screens.files.FilesScreen
import com.baluhost.android.presentation.ui.screens.lock.LockScreen
import com.baluhost.android.presentation.ui.screens.onboarding.OnboardingScreen
import com.baluhost.android.presentation.ui.screens.qrscanner.QrScannerScreen
import com.baluhost.android.presentation.ui.screens.settings.SettingsScreen
import com.baluhost.android.presentation.ui.screens.splash.SplashScreen
import com.baluhost.android.presentation.ui.screens.vpn.VpnScreen

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
                    navController.navigate(Screen.Files.route) {
                        popUpTo(Screen.QrScanner.route) { inclusive = true }
                    }
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
                }
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
