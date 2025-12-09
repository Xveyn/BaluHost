package com.baluhost.android.presentation.navigation

/**
 * Screen routes for navigation.
 */
sealed class Screen(val route: String) {
    object Splash : Screen("splash")
    object Onboarding : Screen("onboarding")
    object QrScanner : Screen("qr_scanner")
    object Files : Screen("files")
    object Vpn : Screen("vpn")
    object Settings : Screen("settings")
    object Lock : Screen("lock")
}
