package com.baluhost.android.di

import com.baluhost.android.data.repository.AuthRepositoryImpl
import com.baluhost.android.data.repository.FilesRepositoryImpl
import com.baluhost.android.data.repository.VpnRepositoryImpl
import com.baluhost.android.domain.repository.AuthRepository
import com.baluhost.android.domain.repository.FilesRepository
import com.baluhost.android.domain.repository.VpnRepository
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * Binds repository interfaces to their implementations.
 */
@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {
    
    @Binds
    @Singleton
    abstract fun bindAuthRepository(
        authRepositoryImpl: AuthRepositoryImpl
    ): AuthRepository
    
    @Binds
    @Singleton
    abstract fun bindFilesRepository(
        filesRepositoryImpl: FilesRepositoryImpl
    ): FilesRepository
    
    @Binds
    @Singleton
    abstract fun bindVpnRepository(
        vpnRepositoryImpl: VpnRepositoryImpl
    ): VpnRepository
}
