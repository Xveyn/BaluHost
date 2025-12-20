package com.baluhost.android.presentation.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * Banner that shows VPN connection hint when user is outside home network.
 * 
 * Displays warning message and "Connect VPN" button to guide user.
 * Can be dismissed with "Don't show again" option.
 */
@Composable
fun VpnStatusBanner(
    isInHomeNetwork: Boolean?,
    hasVpnConfig: Boolean,
    onConnectVpn: () -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
    isDismissed: Boolean = false
) {
    // Show banner when:
    // 1. User is NOT in home network (isInHomeNetwork == false)
    // 2. VPN config is available
    // 3. Banner was not dismissed
    val shouldShow = isInHomeNetwork == false && hasVpnConfig && !isDismissed
    
    AnimatedVisibility(
        visible = shouldShow,
        enter = fadeIn() + expandVertically(),
        exit = fadeOut() + shrinkVertically()
    ) {
        Surface(
            modifier = modifier.fillMaxWidth(),
            color = Color(0xFFFF9800).copy(alpha = 0.15f), // Orange with transparency
            contentColor = Color(0xFFFF9800)
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Icon + Message
                Row(
                    modifier = Modifier.weight(1f),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Warning,
                        contentDescription = "Warning",
                        modifier = Modifier.size(24.dp),
                        tint = Color(0xFFFF9800)
                    )
                    
                    Column(
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Text(
                            text = "Nicht im Heimnetzwerk",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = Color(0xFFFF9800)
                        )
                        Text(
                            text = "Aktiviere VPN für sicheren Zugriff",
                            style = MaterialTheme.typography.bodySmall,
                            color = Color(0xFFFF9800).copy(alpha = 0.8f)
                        )
                    }
                }
                
                // Actions
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Connect VPN Button
                    Button(
                        onClick = onConnectVpn,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Color(0xFFFF9800),
                            contentColor = Color.White
                        ),
                        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Wifi,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(
                            text = "Verbinden",
                            style = MaterialTheme.typography.labelMedium
                        )
                    }
                    
                    // Dismiss Button
                    IconButton(
                        onClick = onDismiss,
                        modifier = Modifier.size(32.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "Dismiss",
                            modifier = Modifier.size(20.dp),
                            tint = Color(0xFFFF9800).copy(alpha = 0.7f)
                        )
                    }
                }
            }
        }
    }
}

/**
 * Compact version of VPN status banner for smaller screens.
 */
@Composable
fun VpnStatusBannerCompact(
    isInHomeNetwork: Boolean?,
    hasVpnConfig: Boolean,
    onConnectVpn: () -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
    isDismissed: Boolean = false
) {
    val shouldShow = isInHomeNetwork == false && hasVpnConfig && !isDismissed
    
    AnimatedVisibility(
        visible = shouldShow,
        enter = fadeIn() + expandVertically(),
        exit = fadeOut() + shrinkVertically()
    ) {
        Surface(
            modifier = modifier.fillMaxWidth(),
            color = Color(0xFFFF9800).copy(alpha = 0.15f),
            contentColor = Color(0xFFFF9800)
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    modifier = Modifier.weight(1f),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Warning,
                        contentDescription = null,
                        modifier = Modifier.size(20.dp),
                        tint = Color(0xFFFF9800)
                    )
                    Text(
                        text = "VPN aktivieren",
                        style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.Medium,
                        color = Color(0xFFFF9800)
                    )
                }
                
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    TextButton(
                        onClick = onConnectVpn,
                        colors = ButtonDefaults.textButtonColors(
                            contentColor = Color(0xFFFF9800)
                        ),
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)
                    ) {
                        Text(
                            text = "Verbinden",
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    
                    IconButton(
                        onClick = onDismiss,
                        modifier = Modifier.size(28.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "Dismiss",
                            modifier = Modifier.size(16.dp),
                            tint = Color(0xFFFF9800).copy(alpha = 0.7f)
                        )
                    }
                }
            }
        }
    }
}
