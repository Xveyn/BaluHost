package com.baluhost.android.presentation.ui.screens.dashboard

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.baluhost.android.domain.model.FileItem
import com.baluhost.android.presentation.ui.components.GlassCard
import com.baluhost.android.presentation.ui.components.GlassIntensity
import com.baluhost.android.presentation.ui.components.VpnStatusBanner
import com.baluhost.android.presentation.ui.theme.*
import java.text.SimpleDateFormat
import java.util.*

/**
 * Dashboard Screen - System overview with telemetry stats.
 * Design based on the webapp dashboard with system insights.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    onNavigateToFiles: () -> Unit,
    onNavigateToSettings: () -> Unit,
    onNavigateToVpn: () -> Unit = {},
    viewModel: DashboardViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    
    // Collect VPN state for banner
    val isInHomeNetwork by viewModel.isInHomeNetwork.collectAsState()
    val hasVpnConfig by viewModel.hasVpnConfig.collectAsState()
    val vpnBannerDismissed by viewModel.vpnBannerDismissed.collectAsState()
    val isVpnActive by viewModel.isVpnActive.collectAsState()
    
    // Gradient background from dark blue to teal
    val gradientBrush = Brush.linearGradient(
        colors = listOf(
            Color(0xFF1E3A5F), // Dark blue
            Color(0xFF2C5F6F), // Mid blue-teal
            Color(0xFF1A4D5C)  // Teal
        ),
        start = Offset(0f, 0f),
        end = Offset(1000f, 1500f)
    )
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            "Dashboard",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            color = Color.White
                        )
                        Text(
                            "Secure personal cloud orchestration overview",
                            style = MaterialTheme.typography.bodySmall,
                            color = Color.White.copy(alpha = 0.7f)
                        )
                    }
                },
                actions = {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Refresh button
                        IconButton(
                            onClick = { viewModel.refresh() },
                            modifier = Modifier.size(36.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Refresh,
                                contentDescription = "Refresh telemetry",
                                tint = Color(0xFF94A3B8),
                                modifier = Modifier.size(20.dp)
                            )
                        }
                        
                        // Sync indicator
                        Surface(
                            shape = RoundedCornerShape(24.dp),
                            color = Color(0xFF0F172A).copy(alpha = 0.6f),
                            border = BorderStroke(1.dp, Color(0xFF1E293B))
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Box(
                                    modifier = Modifier
                                        .size(8.dp)
                                        .background(
                                            if (uiState.telemetry != null) Color(0xFF10B981) else Sky400,
                                            CircleShape
                                        )
                                )
                                Text(
                                    if (uiState.telemetry != null) "Synced" else "Loading...",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = Color(0xFF94A3B8)
                                )
                            }
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color.Transparent
                )
            )
        },
        containerColor = Color.Transparent
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(gradientBrush)
        ) {
            if (uiState.isLoading) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues),
                    contentAlignment = Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        CircularProgressIndicator(color = Sky400)
                        Text(
                            "Loading system insights...",
                            style = MaterialTheme.typography.bodyMedium,
                            color = Color.White.copy(alpha = 0.7f)
                        )
                    }
                }
            } else {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues)
                        .verticalScroll(rememberScrollState())
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    // VPN Status Banner (shows when outside home network)
                    VpnStatusBanner(
                        isInHomeNetwork = isInHomeNetwork,
                        isVpnActive = isVpnActive,
                        hasVpnConfig = hasVpnConfig,
                        onConnectVpn = onNavigateToVpn,
                        onDismiss = { viewModel.dismissVpnBanner() },
                        isDismissed = vpnBannerDismissed
                    )
                    
                    // System Metrics Grid - 2x2 layout like webapp
                    val telemetry = uiState.telemetry
                    Column(
                        modifier = Modifier.fillMaxWidth(),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            SystemMetricCard(
                                title = "CPU USAGE",
                                value = "${telemetry?.cpu?.usagePercent?.toInt() ?: 0}%",
                                meta = "${telemetry?.cpu?.cores ?: 0} cores active",
                                delta = "Live",
                                deltaTone = DeltaTone.LIVE,
                                progress = telemetry?.cpu?.usagePercent?.toFloat() ?: 0f,
                                icon = Icons.Default.Memory,
                                gradientColors = listOf(Color(0xFF8B5CF6), Color(0xFFD946EF)),
                                modifier = Modifier.weight(1f)
                            )
                            
                            SystemMetricCard(
                                title = "MEMORY",
                                value = formatFileSize(telemetry?.memory?.usedBytes ?: 0),
                                meta = "of ${formatFileSize(telemetry?.memory?.totalBytes ?: 0)}",
                                delta = "Live",
                                deltaTone = DeltaTone.LIVE,
                                progress = telemetry?.memory?.usagePercent?.toFloat() ?: 0f,
                                icon = Icons.Default.Storage,
                                gradientColors = listOf(Color(0xFF0EA5E9), Color(0xFF6366F1)),
                                modifier = Modifier.weight(1f)
                            )
                        }
                        
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            SystemMetricCard(
                                title = "TOTAL STORAGE",
                                value = formatFileSize(telemetry?.disk?.usedBytes ?: 0),
                                meta = "of ${formatFileSize(telemetry?.disk?.totalBytes ?: 0)} used",
                                delta = "Live",
                                deltaTone = DeltaTone.LIVE,
                                progress = telemetry?.disk?.usagePercent?.toFloat() ?: 0f,
                                icon = Icons.Default.Folder,
                                gradientColors = listOf(Color(0xFF06B6D4), Color(0xFF0284C7)),
                                modifier = Modifier.weight(1f)
                            )
                            
                            SystemMetricCard(
                                title = "UPTIME",
                                value = formatUptime(telemetry?.uptime?.toLong() ?: 0),
                                meta = "System availability",
                                delta = "Live",
                                deltaTone = DeltaTone.LIVE,
                                progress = 100f,
                                icon = Icons.Default.Power,
                                gradientColors = listOf(Color(0xFF10B981), Color(0xFF14B8A6)),
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }
                    
                    // RAID Arrays Section
                    if (uiState.raidArrays.isNotEmpty()) {
                        GlassCard(
                            modifier = Modifier.fillMaxWidth(),
                            intensity = GlassIntensity.Medium
                        ) {
                            Column(
                                modifier = Modifier.padding(16.dp),
                                verticalArrangement = Arrangement.spacedBy(12.dp)
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column {
                                        Text(
                                            text = "NAS CONFIGURATION",
                                            style = MaterialTheme.typography.labelSmall,
                                            color = Color(0xFF64748B),
                                            letterSpacing = 1.2.sp
                                        )
                                        Text(
                                            text = "RAID Arrays",
                                            style = MaterialTheme.typography.titleMedium,
                                            fontWeight = FontWeight.SemiBold,
                                            color = Color.White,
                                            modifier = Modifier.padding(top = 4.dp)
                                        )
                                    }
                                }
                                
                                uiState.raidArrays.forEach { raid ->
                                    RaidArrayCard(raid = raid)
                                }
                            }
                        }
                    }
                    
                    // Recent Activity Section
                    GlassCard(
                        modifier = Modifier.fillMaxWidth(),
                        intensity = GlassIntensity.Medium
                    ) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column {
                                    Text(
                                        text = "RECENT ACTIVITY",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = Color(0xFF64748B),
                                        letterSpacing = 1.2.sp
                                    )
                                    Text(
                                        text = "Recent Files",
                                        style = MaterialTheme.typography.titleMedium,
                                        fontWeight = FontWeight.SemiBold,
                                        color = Color.White,
                                        modifier = Modifier.padding(top = 4.dp)
                                    )
                                }
                                TextButton(onClick = onNavigateToFiles) {
                                    Text(
                                        "View All",
                                        color = Sky400,
                                        style = MaterialTheme.typography.labelMedium
                                    )
                                }
                            }
                            
                            if (uiState.recentFiles.isEmpty()) {
                                Box(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .height(120.dp)
                                        .clip(RoundedCornerShape(16.dp))
                                        .background(Color(0xFF0F172A).copy(alpha = 0.6f)),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text(
                                        "No recent files",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = Color(0xFF64748B)
                                    )
                                }
                            } else {
                                Column(
                                    verticalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    uiState.recentFiles.take(5).forEach { file ->
                                        RecentFileItem(file = file)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

enum class DeltaTone {
    INCREASE, DECREASE, STEADY, LIVE
}

@Composable
private fun SystemMetricCard(
    title: String,
    value: String,
    meta: String,
    delta: String,
    deltaTone: DeltaTone,
    progress: Float,
    icon: ImageVector,
    gradientColors: List<Color>,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier
            .height(160.dp),
        shape = RoundedCornerShape(16.dp),
        color = Color(0xFF0F172A).copy(alpha = 0.6f),
        border = BorderStroke(1.dp, Color(0xFF1E293B).copy(alpha = 0.4f))
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = title,
                        style = MaterialTheme.typography.labelSmall,
                        color = Color(0xFF64748B),
                        letterSpacing = 1.2.sp
                    )
                    Text(
                        text = value,
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.SemiBold,
                        color = Color.White,
                        modifier = Modifier.padding(top = 8.dp),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                
                Box(
                    modifier = Modifier
                        .size(44.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(Brush.linearGradient(gradientColors)),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = icon,
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(24.dp)
                    )
                }
            }
            
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = meta,
                        style = MaterialTheme.typography.bodySmall,
                        color = Color(0xFF94A3B8),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f)
                    )
                    Text(
                        text = delta,
                        style = MaterialTheme.typography.bodySmall,
                        color = when (deltaTone) {
                            DeltaTone.INCREASE -> Color(0xFFFDA4AF)
                            DeltaTone.DECREASE -> Color(0xFF86EFAC)
                            DeltaTone.STEADY -> Color(0xFF94A3B8)
                            DeltaTone.LIVE -> Sky400
                        }
                    )
                }
                
                // Progress bar
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(8.dp)
                        .clip(RoundedCornerShape(4.dp))
                        .background(Color(0xFF1E293B))
                ) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth(progress / 100f)
                            .fillMaxHeight()
                            .clip(RoundedCornerShape(4.dp))
                            .background(Brush.linearGradient(gradientColors))
                    )
                }
            }
        }
    }
}

private fun formatFileSize(bytes: Long): String {
    return when {
        bytes < 1024 -> "$bytes B"
        bytes < 1024 * 1024 -> "${bytes / 1024} KB"
        bytes < 1024 * 1024 * 1024 -> "${bytes / (1024 * 1024)} MB"
        else -> String.format("%.1f GB", bytes / (1024.0 * 1024 * 1024))
    }
}

private fun formatUptime(seconds: Long): String {
    val days = seconds / 86400
    val hours = (seconds % 86400) / 3600
    val minutes = (seconds % 3600) / 60
    return "${days}d ${hours}h ${minutes}m"
}

@Composable
private fun RaidArrayCard(raid: com.baluhost.android.domain.model.RaidArray) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(
                color = Color(0xFF0F172A).copy(alpha = 0.4f),
                shape = RoundedCornerShape(12.dp)
            )
            .padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // RAID Status Icon with gradient background
        Box(
            modifier = Modifier
                .size(48.dp)
                .background(
                    brush = Brush.linearGradient(
                        colors = when (raid.status) {
                            com.baluhost.android.domain.model.RaidStatus.OPTIMAL -> 
                                listOf(Color(0xFF10B981), Color(0xFF14B8A6))
                            com.baluhost.android.domain.model.RaidStatus.DEGRADED -> 
                                listOf(Color(0xFFFBBF24), Color(0xFFF59E0B))
                            com.baluhost.android.domain.model.RaidStatus.REBUILDING -> 
                                listOf(Color(0xFF3B82F6), Color(0xFF2563EB))
                            com.baluhost.android.domain.model.RaidStatus.FAILED -> 
                                listOf(Color(0xFFEF4444), Color(0xFFDC2626))
                            com.baluhost.android.domain.model.RaidStatus.UNKNOWN -> 
                                listOf(Color(0xFF64748B), Color(0xFF475569))
                        }
                    ),
                    shape = RoundedCornerShape(8.dp)
                ),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = Icons.Default.Storage,
                contentDescription = null,
                tint = Color.White,
                modifier = Modifier.size(24.dp)
            )
        }
        
        // RAID Info
        Column(
            modifier = Modifier.weight(1f)
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = raid.name,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White
                )
                Surface(
                    color = when (raid.status) {
                        com.baluhost.android.domain.model.RaidStatus.OPTIMAL -> 
                            Color(0xFF10B981).copy(alpha = 0.2f)
                        com.baluhost.android.domain.model.RaidStatus.DEGRADED -> 
                            Color(0xFFFBBF24).copy(alpha = 0.2f)
                        com.baluhost.android.domain.model.RaidStatus.REBUILDING -> 
                            Color(0xFF3B82F6).copy(alpha = 0.2f)
                        com.baluhost.android.domain.model.RaidStatus.FAILED -> 
                            Color(0xFFEF4444).copy(alpha = 0.2f)
                        com.baluhost.android.domain.model.RaidStatus.UNKNOWN -> 
                            Color(0xFF64748B).copy(alpha = 0.2f)
                    },
                    shape = RoundedCornerShape(4.dp),
                    contentColor = when (raid.status) {
                        com.baluhost.android.domain.model.RaidStatus.OPTIMAL -> Color(0xFF10B981)
                        com.baluhost.android.domain.model.RaidStatus.DEGRADED -> Color(0xFFFBBF24)
                        com.baluhost.android.domain.model.RaidStatus.REBUILDING -> Color(0xFF3B82F6)
                        com.baluhost.android.domain.model.RaidStatus.FAILED -> Color(0xFFEF4444)
                        com.baluhost.android.domain.model.RaidStatus.UNKNOWN -> Color(0xFF64748B)
                    }
                ) {
                    Text(
                        text = raid.status.name.lowercase().replaceFirstChar { it.uppercase() },
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                        fontWeight = FontWeight.Medium
                    )
                }
            }
            
            Text(
                text = "${raid.level} • ${formatFileSize(raid.sizeBytes)} • ${raid.devices.size} devices",
                style = MaterialTheme.typography.bodySmall,
                color = Color(0xFF94A3B8),
                modifier = Modifier.padding(top = 4.dp)
            )
            
            // Resync Progress
            if (raid.resyncProgress != null && raid.resyncProgress > 0) {
                Column(
                    modifier = Modifier.padding(top = 8.dp)
                ) {
                    Text(
                        text = "Resyncing: ${(raid.resyncProgress * 100).toInt()}%",
                        style = MaterialTheme.typography.labelSmall,
                        color = Color(0xFF94A3B8)
                    )
                    LinearProgressIndicator(
                        progress = { raid.resyncProgress.toFloat() },
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 4.dp)
                            .height(4.dp)
                            .clip(RoundedCornerShape(2.dp)),
                        color = Color(0xFF3B82F6),
                        trackColor = Color(0xFF1E293B),
                    )
                }
            }
        }
    }
}

@Composable
private fun RecentFileItem(file: FileItem) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(
            imageVector = when {
                file.isDirectory -> Icons.Default.Folder
                file.name.endsWith(".pdf") -> Icons.Default.Description
                file.name.endsWith(".jpg") || file.name.endsWith(".png") -> Icons.Default.Image
                file.name.endsWith(".mp4") -> Icons.Default.VideoFile
                else -> Icons.Default.InsertDriveFile
            },
            contentDescription = null,
            tint = if (file.isDirectory) Sky400 else Color(0xFF818CF8),
            modifier = Modifier.size(32.dp)
        )
        
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = file.name,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
                color = Color(0xFFF1F5F9)
            )
            Text(
                text = formatDate(file.modifiedAt.epochSecond),
                style = MaterialTheme.typography.bodySmall,
                color = Color(0xFF94A3B8)
            )
        }
        
        if (!file.isDirectory) {
            Text(
                text = formatFileSize(file.size),
                style = MaterialTheme.typography.bodySmall,
                color = Color(0xFF94A3B8)
            )
        }
    }
}

private fun formatDate(timestamp: Long): String {
    val sdf = SimpleDateFormat("dd.MM.yyyy", Locale.getDefault())
    return sdf.format(Date(timestamp * 1000))
}