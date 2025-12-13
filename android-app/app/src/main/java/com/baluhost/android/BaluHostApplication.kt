package com.baluhost.android

import android.app.Application
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import coil.ImageLoader
import coil.ImageLoaderFactory
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

/**
 * BaluHost Application class with Hilt dependency injection.
 * 
 * Responsibilities:
 * - Initialize Hilt for app-wide DI
 * - Configure WorkManager with Hilt
 * - Setup global application state
 * - Configure Coil ImageLoader with authentication
 */
@HiltAndroidApp
class BaluHostApplication : Application(), Configuration.Provider, ImageLoaderFactory {
    
    @Inject
    lateinit var workerFactory: HiltWorkerFactory
    
    @Inject
    lateinit var imageLoader: ImageLoader
    
    override fun onCreate() {
        super.onCreate()
        // Additional initialization if needed
    }
    
    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(workerFactory)
            .build()
    
    override fun newImageLoader(): ImageLoader {
        return imageLoader
    }
}
