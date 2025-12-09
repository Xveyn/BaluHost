package com.baluhost.android.presentation.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

/**
 * Dark color scheme matching web's glassmorphism design.
 */
private val DarkColorScheme = darkColorScheme(
    // Primary (Sky)
    primary = Sky400,
    onPrimary = Slate950,
    primaryContainer = Sky600,
    onPrimaryContainer = Sky100,
    
    // Secondary (Indigo)
    secondary = Indigo500,
    onSecondary = Slate950,
    secondaryContainer = Indigo600,
    onSecondaryContainer = Indigo100,
    
    // Tertiary (Violet)
    tertiary = Violet500,
    onTertiary = Slate950,
    tertiaryContainer = Violet600,
    onTertiaryContainer = Violet400,
    
    // Background & Surface
    background = Slate950,
    onBackground = Slate100,
    surface = Slate900,
    onSurface = Slate100,
    surfaceVariant = Slate800,
    onSurfaceVariant = Slate400,
    
    // Error
    error = Red500,
    onError = Slate950,
    errorContainer = Red600,
    onErrorContainer = Red400,
    
    // Outline & other
    outline = Slate600,
    outlineVariant = Slate700,
    scrim = Color.Black.copy(alpha = 0.5f),
    inverseSurface = Slate100,
    inverseOnSurface = Slate900,
    inversePrimary = Sky600,
    surfaceTint = Sky400
)

/**
 * Light color scheme (kept simple, app primarily uses dark theme).
 */
private val LightColorScheme = lightColorScheme(
    primary = Sky500,
    onPrimary = Color.White,
    secondary = Indigo500,
    onSecondary = Color.White,
    background = Slate100,
    onBackground = Slate900,
    surface = Color.White,
    onSurface = Slate900,
    error = Red500,
    onError = Color.White
)

@Composable
fun BaluHostTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    val colorScheme = when {
        darkTheme -> DarkColorScheme
        else -> LightColorScheme
    }
    
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = colorScheme.primary.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !darkTheme
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}
