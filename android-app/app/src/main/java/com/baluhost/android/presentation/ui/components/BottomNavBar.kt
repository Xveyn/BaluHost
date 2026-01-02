package com.baluhost.android.presentation.ui.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.baluhost.android.presentation.ui.theme.Sky400
import com.baluhost.android.presentation.ui.theme.Slate400

/**
 * Bottom Navigation Bar with main app tabs.
 */
@Composable
fun BottomNavBar(
    currentRoute: String,
    onNavigate: (String) -> Unit
) {
    NavigationBar(
        containerColor = MaterialTheme.colorScheme.surface,
        tonalElevation = 8.dp
    ) {
        BottomNavItem.entries.forEach { item ->
            NavigationBarItem(
                selected = currentRoute.startsWith(item.route),
                onClick = { onNavigate(item.route) },
                icon = {
                    Icon(
                        imageVector = item.icon,
                        contentDescription = item.label
                    )
                },
                label = { Text(item.label) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = Sky400,
                    selectedTextColor = Sky400,
                    unselectedIconColor = Slate400,
                    unselectedTextColor = Slate400,
                    indicatorColor = Sky400.copy(alpha = 0.2f)
                )
            )
        }
    }
}

enum class BottomNavItem(
    val route: String,
    val label: String,
    val icon: ImageVector
) {
    HOME("dashboard", "Home", Icons.Default.Home),
    FILES("files", "Dateien", Icons.Default.Folder),
    SYNC("sync", "Sync", Icons.Default.Sync),
    SETTINGS("settings", "Einstellungen", Icons.Default.Settings)
}
