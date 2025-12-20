package com.baluhost.android.presentation.ui.screens.shares

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.baluhost.android.presentation.ui.components.GlassCard
import com.baluhost.android.presentation.ui.components.GlassIntensity
import com.baluhost.android.presentation.ui.theme.*

/**
 * Shares Screen - Displays shared files and public links.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SharesScreen() {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Geteilte Dateien") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Info Card
            GlassCard(
                modifier = Modifier.fillMaxWidth(),
                intensity = GlassIntensity.Medium
            ) {
                Row(
                    modifier = Modifier.padding(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Default.Info,
                        contentDescription = null,
                        tint = Sky400,
                        modifier = Modifier.size(32.dp)
                    )
                    Text(
                        text = "Feature kommt bald! Hier werden deine geteilten Dateien und Public Links angezeigt.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = Slate300
                    )
                }
            }
            
            // Placeholder Cards
            GlassCard(
                modifier = Modifier.fillMaxWidth(),
                intensity = GlassIntensity.Light
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text(
                        text = "Public Links",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Sky400
                    )
                    Text(
                        text = "Keine öffentlichen Links erstellt",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate400
                    )
                }
            }
            
            GlassCard(
                modifier = Modifier.fillMaxWidth(),
                intensity = GlassIntensity.Light
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text(
                        text = "Benutzerfreigaben",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Sky400
                    )
                    Text(
                        text = "Keine Dateien mit anderen Benutzern geteilt",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate400
                    )
                }
            }
        }
    }
}
