package com.baluhost.android.di

import android.content.Context
import com.baluhost.android.data.sync.SAFStorageAdapter
import com.baluhost.android.data.sync.SmbAdapter
import com.baluhost.android.data.sync.SyncRepositoryImpl
import com.baluhost.android.data.sync.WebDavAdapter
import com.baluhost.android.domain.adapter.CloudAdapter
import com.baluhost.android.domain.repo.SyncRepository
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object SyncModule {

    @Provides
    @Singleton
    fun provideExternalStorageHelper(): com.baluhost.android.data.sync.ExternalStorageHelper = com.baluhost.android.data.sync.ExternalStorageHelper()

    @Provides
    @Singleton
    fun provideSyncRepository(context: Context, helper: com.baluhost.android.data.sync.ExternalStorageHelper): SyncRepository = SyncRepositoryImpl(context, helper)

    @Provides
    @Singleton
    fun provideSafAdapter(context: Context): SAFStorageAdapter = SAFStorageAdapter(context)

    @Provides
    @Singleton
    fun provideWebDavAdapter(): WebDavAdapter = WebDavAdapter()

    @Provides
    @Singleton
    fun provideWebDavAdapterFactory(): com.baluhost.android.data.sync.WebDavAdapterFactory = com.baluhost.android.data.sync.WebDavAdapterFactoryImpl()

    @Provides
    @Singleton
    fun provideWebDavAccountManager(factory: com.baluhost.android.data.sync.WebDavAdapterFactory): com.baluhost.android.data.sync.WebDavAccountManager = com.baluhost.android.data.sync.WebDavAccountManager(factory)

    @Provides
    @Singleton
    fun provideSmbAdapter(): SmbAdapter = SmbAdapter()
}
