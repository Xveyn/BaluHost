package com.baluhost.android.presentation.ui.components

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import com.baluhost.android.presentation.ui.theme.*

/**
 * Text with gradient color effect.
 */
@Composable
fun GradientText(
    text: String,
    modifier: Modifier = Modifier,
    gradient: Brush = defaultTextGradient(),
    style: TextStyle = MaterialTheme.typography.headlineLarge,
    fontWeight: FontWeight = FontWeight.Bold
) {
    Text(
        text = text,
        modifier = modifier,
        style = style.copy(
            brush = gradient,
            fontWeight = fontWeight
        )
    )
}

/**
 * Default text gradient: Sky → Indigo
 */
@Composable
fun defaultTextGradient(): Brush {
    return Brush.linearGradient(
        colors = listOf(
            Sky400,
            Indigo500
        )
    )
}

/**
 * Secondary text gradient: Indigo → Violet
 */
@Composable
fun secondaryTextGradient(): Brush {
    return Brush.linearGradient(
        colors = listOf(
            Indigo500,
            Violet500
        )
    )
}

/**
 * Accent text gradient: Pink → Violet
 */
@Composable
fun accentTextGradient(): Brush {
    return Brush.linearGradient(
        colors = listOf(
            Pink500,
            Violet500
        )
    )
}
