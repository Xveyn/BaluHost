package com.baluhost.android.di

import com.baluhost.android.data.repository.AuthRepositoryImpl
import com.baluhost.android.data.repository.DeviceRepositoryImpl
import com.baluhost.android.data.repository.FilesRepositoryImpl
import com.baluhost.android.data.repository.OfflineQueueRepositoryImpl
import com.baluhost.android.data.repository.SyncRepositoryImpl
import com.baluhost.android.data.repository.SystemRepositoryImpl
import com.baluhost.android.data.repository.VpnRepositoryImpl
import com.baluhost.android.domain.repository.AuthRepository
import com.baluhost.android.domain.repository.DeviceRepository
import com.baluhost.android.domain.repository.FilesRepository
import com.baluhost.android.domain.repository.OfflineQueueRepository
import com.baluhost.android.domain.repository.SyncRepository
import com.baluhost.android.domain.repository.SystemRepository
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
    
    @Binds
    @Singleton
    abstract fun bindDeviceRepository(
        deviceRepositoryImpl: DeviceRepositoryImpl
    ): DeviceRepository
    
    @Binds
    @Singleton
    abstract fun bindSystemRepository(
        systemRepositoryImpl: SystemRepositoryImpl
    ): SystemRepository
    
    @Binds
    @Singleton
    abstract fun bindSyncRepository(
        syncRepositoryImpl: SyncRepositoryImpl
    ): SyncRepository
    
    @Binds
    @Singleton
    abstract fun bindOfflineQueueRepository(
        offlineQueueRepositoryImpl: OfflineQueueRepositoryImpl
    ): OfflineQueueRepository
}
