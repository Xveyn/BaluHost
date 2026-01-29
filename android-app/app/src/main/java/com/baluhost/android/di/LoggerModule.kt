package com.baluhost.android.di

import com.baluhost.android.data.util.AndroidLogger
import com.baluhost.android.domain.util.Logger
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * Binds logging interface to its implementation.
 */
@Module
@InstallIn(SingletonComponent::class)
abstract class LoggerModule {

    @Binds
    @Singleton
    abstract fun bindLogger(
        androidLogger: AndroidLogger
    ): Logger
}
