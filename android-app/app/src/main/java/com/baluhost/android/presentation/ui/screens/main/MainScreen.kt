package com.baluhost.android.presentation.ui.screens.main

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.baluhost.android.presentation.navigation.Screen
import com.baluhost.android.presentation.ui.components.BottomNavBar
import com.baluhost.android.presentation.ui.screens.dashboard.DashboardScreen
import com.baluhost.android.presentation.ui.screens.files.FilesScreen
import com.baluhost.android.presentation.ui.screens.settings.SettingsScreen
import com.baluhost.android.presentation.ui.screens.shares.SharesScreen

/**
 * Main container screen that manages bottom navigation between
 * Dashboard, Files, Shares, and Settings screens
 */
@Composable
fun MainScreen(
    parentNavController: NavHostController
) {
    val navController = rememberNavController()
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route ?: Screen.Dashboard.route

    Scaffold(
        bottomBar = {
            BottomNavBar(
                currentRoute = currentRoute,
                onNavigate = { route ->
                    navController.navigate(route) {
                        // Pop up to the start destination to avoid building up a large stack
                        popUpTo(Screen.Dashboard.route) {
                            saveState = true
                        }
                        // Avoid multiple copies of the same destination
                        launchSingleTop = true
                        // Restore state when reselecting a previously selected item
                        restoreState = true
                    }
                }
            )
        }
    ) { innerPadding ->
        Box(modifier = Modifier.padding(innerPadding)) {
            NavHost(
                navController = navController,
                startDestination = Screen.Dashboard.route
            ) {
                composable(Screen.Dashboard.route) {
                    DashboardScreen(
                        onNavigateToFiles = {
                            navController.navigate(Screen.Files.route)
                        },
                        onNavigateToSettings = {
                            navController.navigate(Screen.Settings.route)
                        },
                        onNavigateToVpn = {
                            // Navigate using parent nav controller for screens outside bottom nav
                            parentNavController.navigate(Screen.Vpn.route)
                        }
                    )
                }

                composable(Screen.Files.route) {
                    FilesScreen(
                        onNavigateToVpn = {
                            // Navigate using parent nav controller for screens outside bottom nav
                            parentNavController.navigate(Screen.Vpn.route)
                        },
                        onNavigateToSettings = {
                            navController.navigate(Screen.Settings.route)
                        },
                        onNavigateToMediaViewer = { fileUrl, fileName, mimeType ->
                            // Navigate using parent nav controller for screens outside bottom nav
                            parentNavController.navigate(
                                Screen.MediaViewer.createRoute(fileUrl, fileName, mimeType)
                            )
                        },
                        onNavigateToPendingOperations = {
                            // Navigate using parent nav controller for screens outside bottom nav
                            parentNavController.navigate(Screen.PendingOperations.route)
                        }
                    )
                }

                composable(Screen.Shares.route) {
                    SharesScreen()
                }

                composable(Screen.Settings.route) {
                    SettingsScreen(
                        onNavigateBack = {
                            // Go back to Dashboard when back is pressed
                            navController.navigate(Screen.Dashboard.route) {
                                popUpTo(Screen.Dashboard.route) { inclusive = false }
                            }
                        },
                        onNavigateToSplash = {
                            // Navigate using parent nav controller to logout
                            parentNavController.navigate(Screen.Splash.route) {
                                popUpTo(0) { inclusive = true }
                            }
                        }
                    )
                }
            }
        }
    }
}
