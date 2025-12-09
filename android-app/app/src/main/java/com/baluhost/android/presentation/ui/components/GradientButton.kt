package com.baluhost.android.presentation.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.baluhost.android.presentation.ui.theme.*

/**
 * Button with gradient background matching web design.
 */
@Composable
fun GradientButton(
    onClick: () -> Unit,
    text: String,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    gradient: Brush = defaultGradient(),
    shape: RoundedCornerShape = RoundedCornerShape(8.dp),
    contentPadding: PaddingValues = PaddingValues(horizontal = 24.dp, vertical = 12.dp)
) {
    Button(
        onClick = onClick,
        modifier = modifier.height(48.dp),
        enabled = enabled,
        shape = shape,
        colors = ButtonDefaults.buttonColors(
            containerColor = Color.Transparent,
            disabledContainerColor = Slate700
        ),
        contentPadding = contentPadding,
        elevation = ButtonDefaults.buttonElevation(
            defaultElevation = 0.dp,
            pressedElevation = 2.dp
        )
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(gradient)
        ) {
            Row(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 8.dp),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
            ) {
                Text(
                    text = text,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White
                )
            }
        }
    }
}

/**
 * Small gradient button for secondary actions.
 */
@Composable
fun GradientButtonSmall(
    onClick: () -> Unit,
    text: String,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    gradient: Brush = secondaryGradient()
) {
    GradientButton(
        onClick = onClick,
        text = text,
        modifier = modifier.height(36.dp),
        enabled = enabled,
        gradient = gradient,
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp)
    )
}

/**
 * Default gradient: Sky → Indigo → Violet
 */
@Composable
fun defaultGradient(): Brush {
    return Brush.horizontalGradient(
        colors = listOf(
            Sky400,
            Indigo500,
            Violet500
        )
    )
}

/**
 * Secondary gradient: Indigo → Violet
 */
@Composable
fun secondaryGradient(): Brush {
    return Brush.horizontalGradient(
        colors = listOf(
            Indigo500,
            Violet500
        )
    )
}

/**
 * Success gradient: Green shades
 */
@Composable
fun successGradient(): Brush {
    return Brush.horizontalGradient(
        colors = listOf(
            Green400,
            Green500,
            Green600
        )
    )
}

/**
 * Error gradient: Red shades
 */
@Composable
fun errorGradient(): Brush {
    return Brush.horizontalGradient(
        colors = listOf(
            Red400,
            Red500,
            Red600
        )
    )
}

/**
 * Warning gradient: Yellow shades
 */
@Composable
fun warningGradient(): Brush {
    return Brush.horizontalGradient(
        colors = listOf(
            Yellow400,
            Yellow500,
            Yellow600
        )
    )
}
