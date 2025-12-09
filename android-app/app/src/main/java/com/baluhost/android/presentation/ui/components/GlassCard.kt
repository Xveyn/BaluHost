package com.baluhost.android.presentation.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.baluhost.android.presentation.ui.theme.GlassLight
import com.baluhost.android.presentation.ui.theme.GlassMedium
import com.baluhost.android.presentation.ui.theme.Slate700
import com.baluhost.android.presentation.ui.theme.Slate800

/**
 * Glassmorphism card component matching web design.
 * 
 * Semi-transparent surface with subtle border and backdrop blur effect.
 */
@Composable
fun GlassCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    enabled: Boolean = true,
    intensity: GlassIntensity = GlassIntensity.Medium,
    shape: RoundedCornerShape = RoundedCornerShape(12.dp),
    padding: PaddingValues = PaddingValues(16.dp),
    content: @Composable ColumnScope.() -> Unit
) {
    val backgroundColor = when (intensity) {
        GlassIntensity.Light -> GlassLight
        GlassIntensity.Medium -> GlassMedium
        GlassIntensity.Heavy -> Slate800.copy(alpha = 0.6f)
    }
    
    val borderColor = when (intensity) {
        GlassIntensity.Light -> Slate700.copy(alpha = 0.3f)
        GlassIntensity.Medium -> Slate700.copy(alpha = 0.5f)
        GlassIntensity.Heavy -> Slate700.copy(alpha = 0.7f)
    }
    
    Card(
        modifier = modifier
            .border(
                width = 1.dp,
                color = borderColor,
                shape = shape
            ),
        onClick = onClick ?: {},
        enabled = enabled && onClick != null,
        shape = shape,
        colors = CardDefaults.cardColors(
            containerColor = backgroundColor
        ),
        elevation = CardDefaults.cardElevation(
            defaultElevation = 0.dp,
            pressedElevation = if (onClick != null) 2.dp else 0.dp
        )
    ) {
        Column(
            modifier = Modifier.padding(padding),
            content = content
        )
    }
}

/**
 * Glassmorphism intensity levels.
 */
enum class GlassIntensity {
    Light,   // Subtle transparency
    Medium,  // Standard glassmorphism
    Heavy    // More opaque for elevated content
}

/**
 * Gradient glass card with colorful border.
 */
@Composable
fun GradientGlassCard(
    modifier: Modifier = Modifier,
    gradient: Brush,
    borderWidth: Dp = 2.dp,
    shape: RoundedCornerShape = RoundedCornerShape(12.dp),
    padding: PaddingValues = PaddingValues(16.dp),
    content: @Composable ColumnScope.() -> Unit
) {
    Box(
        modifier = modifier
            .clip(shape)
            .background(gradient)
    ) {
        Column(
            modifier = Modifier
                .padding(borderWidth)
                .clip(shape)
                .background(Slate800.copy(alpha = 0.9f))
                .padding(padding),
            content = content
        )
    }
}

/**
 * Simple glass surface without Card wrapper.
 */
@Composable
fun GlassSurface(
    modifier: Modifier = Modifier,
    intensity: GlassIntensity = GlassIntensity.Medium,
    shape: RoundedCornerShape = RoundedCornerShape(12.dp),
    content: @Composable BoxScope.() -> Unit
) {
    val backgroundColor = when (intensity) {
        GlassIntensity.Light -> GlassLight
        GlassIntensity.Medium -> GlassMedium
        GlassIntensity.Heavy -> Slate800.copy(alpha = 0.6f)
    }
    
    Box(
        modifier = modifier
            .clip(shape)
            .background(backgroundColor)
            .border(
                width = 1.dp,
                color = Slate700.copy(alpha = 0.5f),
                shape = shape
            ),
        content = content
    )
}
