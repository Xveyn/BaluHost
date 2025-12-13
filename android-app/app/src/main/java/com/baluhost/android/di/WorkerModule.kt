package com.baluhost.android.di

import android.content.Context
import androidx.work.WorkManager
import com.baluhost.android.util.LocalFolderScanner
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * Hilt module for WorkManager and related dependencies.
 */
@Module
@InstallIn(SingletonComponent::class)
object WorkerModule {

    @Provides
    @Singleton
    fun provideWorkManager(
        @ApplicationContext context: Context
    ): WorkManager {
        return WorkManager.getInstance(context)
    }

    @Provides
    @Singleton
    fun provideLocalFolderScanner(
        @ApplicationContext context: Context
    ): LocalFolderScanner {
        return LocalFolderScanner(context)
    }
}
