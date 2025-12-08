package com.baluhost.android.presentation.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import com.baluhost.android.presentation.ui.screens.files.FilesScreen
import com.baluhost.android.presentation.ui.screens.qrscanner.QrScannerScreen
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
    }
}
