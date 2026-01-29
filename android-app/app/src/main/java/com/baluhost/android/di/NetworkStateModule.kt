package com.baluhost.android.di

import com.baluhost.android.data.network.NetworkStateManagerImpl
import com.baluhost.android.domain.network.NetworkStateManager
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * Binds network state management interfaces to their implementations.
 */
@Module
@InstallIn(SingletonComponent::class)
abstract class NetworkStateModule {

    @Binds
    @Singleton
    abstract fun bindNetworkStateManager(
        networkStateManagerImpl: NetworkStateManagerImpl
    ): NetworkStateManager
}
