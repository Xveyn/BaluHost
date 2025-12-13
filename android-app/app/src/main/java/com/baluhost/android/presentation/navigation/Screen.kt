package com.baluhost.android.presentation.navigation

/**
 * Screen routes for navigation.
 */
sealed class Screen(val route: String) {
    object Splash : Screen("splash")
    object Onboarding : Screen("onboarding")
    object QrScanner : Screen("qr_scanner")
    object Storage : Screen("storage")
    object Files : Screen("files")
    object MediaViewer : Screen("media_viewer/{fileUrl}/{fileName}/{mimeType}") {
        fun createRoute(fileUrl: String, fileName: String, mimeType: String?): String {
            val encodedUrl = java.net.URLEncoder.encode(fileUrl, "UTF-8")
            val encodedName = java.net.URLEncoder.encode(fileName, "UTF-8")
            val encodedMime = java.net.URLEncoder.encode(mimeType ?: "unknown", "UTF-8")
            return "media_viewer/$encodedUrl/$encodedName/$encodedMime"
        }
    }
    object Vpn : Screen("vpn")
    object Settings : Screen("settings")
    object Lock : Screen("lock")
}
