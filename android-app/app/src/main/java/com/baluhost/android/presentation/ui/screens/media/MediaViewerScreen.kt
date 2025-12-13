package com.baluhost.android.presentation.ui.screens.media

import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import coil.compose.AsyncImage
import coil.request.ImageRequest

/**
 * Media Viewer Screen for displaying images, videos, and audio files.
 * 
 * Supports:
 * - Images: Pinch-to-zoom, pan gestures
 * - Videos: Full video player with controls
 * - Audio: Audio player with waveform visualization
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MediaViewerScreen(
    fileUrl: String,
    fileName: String,
    mimeType: String?,
    onNavigateBack: () -> Unit
) {
    android.util.Log.d("MediaViewerScreen", "Opening media: fileName=$fileName, mimeType=$mimeType, url=$fileUrl")
    
    val mediaType = when {
        mimeType?.startsWith("image/") == true -> MediaType.IMAGE
        mimeType?.startsWith("video/") == true -> MediaType.VIDEO
        mimeType?.startsWith("audio/") == true -> MediaType.AUDIO
        else -> MediaType.UNSUPPORTED
    }
    
    android.util.Log.d("MediaViewerScreen", "Detected media type: $mediaType")
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(fileName, maxLines = 1) },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color.Black.copy(alpha = 0.7f)
                )
            )
        },
        containerColor = Color.Black
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            when (mediaType) {
                MediaType.IMAGE -> ImageViewer(fileUrl)
                MediaType.VIDEO -> VideoPlayer(fileUrl)
                MediaType.AUDIO -> AudioPlayer(fileUrl, fileName)
                MediaType.UNSUPPORTED -> UnsupportedMediaType(mimeType)
            }
        }
    }
}

enum class MediaType {
    IMAGE, VIDEO, AUDIO, UNSUPPORTED
}

/**
 * Image viewer with pinch-to-zoom and pan gestures.
 */
@Composable
fun ImageViewer(imageUrl: String) {
    android.util.Log.d("MediaViewerScreen", "ImageViewer loading: $imageUrl")
    
    var scale by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    
    Box(
        modifier = Modifier
            .fillMaxSize()
            .pointerInput(Unit) {
                detectTransformGestures { _, pan, zoom, _ ->
                    scale = (scale * zoom).coerceIn(1f, 5f)
                    
                    if (scale > 1f) {
                        offset += pan
                    } else {
                        offset = Offset.Zero
                    }
                }
            },
        contentAlignment = Alignment.Center
    ) {
        AsyncImage(
            model = ImageRequest.Builder(LocalContext.current)
                .data(imageUrl)
                .crossfade(true)
                .build(),
            contentDescription = null,
            modifier = Modifier
                .fillMaxSize()
                .graphicsLayer(
                    scaleX = scale,
                    scaleY = scale,
                    translationX = offset.x,
                    translationY = offset.y
                ),
            contentScale = ContentScale.Fit
        )
        
        // Reset zoom button
        if (scale > 1f) {
            FloatingActionButton(
                onClick = {
                    scale = 1f
                    offset = Offset.Zero
                },
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .padding(16.dp),
                containerColor = MaterialTheme.colorScheme.primaryContainer
            ) {
                Icon(Icons.Default.ZoomOut, "Reset Zoom")
            }
        }
    }
}

/**
 * Video player using ExoPlayer with full controls.
 */
@Composable
fun VideoPlayer(videoUrl: String) {
    val context = LocalContext.current
    
    val exoPlayer = remember {
        ExoPlayer.Builder(context).build().apply {
            setMediaItem(MediaItem.fromUri(Uri.parse(videoUrl)))
            prepare()
            playWhenReady = true
        }
    }
    
    DisposableEffect(Unit) {
        onDispose {
            exoPlayer.release()
        }
    }
    
    AndroidView(
        factory = { ctx ->
            PlayerView(ctx).apply {
                player = exoPlayer
                useController = true
                controllerShowTimeoutMs = 3000
                controllerHideOnTouch = true
            }
        },
        modifier = Modifier.fillMaxSize()
    )
}

/**
 * Audio player with controls and progress.
 */
@Composable
fun AudioPlayer(audioUrl: String, fileName: String) {
    val context = LocalContext.current
    
    val exoPlayer = remember {
        ExoPlayer.Builder(context).build().apply {
            setMediaItem(MediaItem.fromUri(Uri.parse(audioUrl)))
            prepare()
        }
    }
    
    var isPlaying by remember { mutableStateOf(false) }
    var currentPosition by remember { mutableLongStateOf(0L) }
    var duration by remember { mutableLongStateOf(0L) }
    
    // Update playback state
    LaunchedEffect(exoPlayer) {
        val listener = object : Player.Listener {
            override fun onIsPlayingChanged(playing: Boolean) {
                isPlaying = playing
            }
            
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_READY) {
                    duration = exoPlayer.duration
                }
            }
        }
        exoPlayer.addListener(listener)
    }
    
    // Update progress
    LaunchedEffect(isPlaying) {
        while (isPlaying) {
            currentPosition = exoPlayer.currentPosition
            kotlinx.coroutines.delay(100)
        }
    }
    
    DisposableEffect(Unit) {
        onDispose {
            exoPlayer.release()
        }
    }
    
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black)
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        // Album art placeholder
        Surface(
            modifier = Modifier.size(200.dp),
            shape = MaterialTheme.shapes.medium,
            color = MaterialTheme.colorScheme.surfaceVariant
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(
                    imageVector = Icons.Default.MusicNote,
                    contentDescription = null,
                    modifier = Modifier.size(80.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
        
        Spacer(modifier = Modifier.height(32.dp))
        
        // File name
        Text(
            text = fileName,
            style = MaterialTheme.typography.headlineSmall,
            color = Color.White
        )
        
        Spacer(modifier = Modifier.height(48.dp))
        
        // Progress slider
        Column(modifier = Modifier.fillMaxWidth()) {
            Slider(
                value = if (duration > 0) currentPosition.toFloat() / duration else 0f,
                onValueChange = { value ->
                    exoPlayer.seekTo((value * duration).toLong())
                },
                modifier = Modifier.fillMaxWidth()
            )
            
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = formatDuration(currentPosition),
                    style = MaterialTheme.typography.bodySmall,
                    color = Color.White
                )
                Text(
                    text = formatDuration(duration),
                    style = MaterialTheme.typography.bodySmall,
                    color = Color.White
                )
            }
        }
        
        Spacer(modifier = Modifier.height(24.dp))
        
        // Playback controls
        Row(
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Previous (seek -10s)
            IconButton(onClick = {
                exoPlayer.seekTo(maxOf(0, exoPlayer.currentPosition - 10000))
            }) {
                Icon(
                    Icons.Default.Replay10,
                    contentDescription = "Rewind 10s",
                    modifier = Modifier.size(32.dp),
                    tint = Color.White
                )
            }
            
            // Play/Pause
            FilledIconButton(
                onClick = {
                    if (isPlaying) exoPlayer.pause() else exoPlayer.play()
                },
                modifier = Modifier.size(64.dp)
            ) {
                Icon(
                    imageVector = if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                    contentDescription = if (isPlaying) "Pause" else "Play",
                    modifier = Modifier.size(32.dp)
                )
            }
            
            // Next (seek +10s)
            IconButton(onClick = {
                exoPlayer.seekTo(minOf(duration, exoPlayer.currentPosition + 10000))
            }) {
                Icon(
                    Icons.Default.Forward10,
                    contentDescription = "Forward 10s",
                    modifier = Modifier.size(32.dp),
                    tint = Color.White
                )
            }
        }
    }
}

/**
 * Unsupported media type message.
 */
@Composable
fun UnsupportedMediaType(mimeType: String?) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Icon(
                imageVector = Icons.Default.ErrorOutline,
                contentDescription = null,
                modifier = Modifier.size(64.dp),
                tint = MaterialTheme.colorScheme.error
            )
            Text(
                text = "Unsupported media type",
                style = MaterialTheme.typography.titleLarge,
                color = Color.White
            )
            if (mimeType != null) {
                Text(
                    text = mimeType,
                    style = MaterialTheme.typography.bodyMedium,
                    color = Color.White.copy(alpha = 0.7f)
                )
            }
        }
    }
}

/**
 * Format duration in mm:ss format.
 */
private fun formatDuration(millis: Long): String {
    val seconds = (millis / 1000).toInt()
    val minutes = seconds / 60
    val secs = seconds % 60
    return "%d:%02d".format(minutes, secs)
}
