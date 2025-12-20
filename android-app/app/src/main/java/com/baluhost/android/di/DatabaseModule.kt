package com.baluhost.android.di

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.preferencesDataStore
import androidx.room.Room
import com.baluhost.android.data.local.database.BaluHostDatabase
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.data.local.security.SecurePreferencesManager
import com.baluhost.android.data.local.security.SecureStorage
import com.baluhost.android.util.Constants
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * Provides local storage dependencies (Room, DataStore, SecureStorage).
 */
@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    
    private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(
        name = "baluhost_preferences"
    )
    
    @Provides
    @Singleton
    fun provideDataStore(
        @ApplicationContext context: Context
    ): DataStore<Preferences> = context.dataStore
    
    @Provides
    @Singleton
    fun providePreferencesManager(
        dataStore: DataStore<Preferences>,
        securePreferences: SecurePreferencesManager
    ): PreferencesManager = PreferencesManager(dataStore, securePreferences)
    
    @Provides
    @Singleton
    fun provideSecureStorage(
        @ApplicationContext context: Context
    ): SecureStorage = SecureStorage(context)
    
    @Provides
    @Singleton
    fun provideBaluHostDatabase(
        @ApplicationContext context: Context
    ): BaluHostDatabase {
        return Room.databaseBuilder(
            context,
            BaluHostDatabase::class.java,
            Constants.DATABASE_NAME
        )
            .fallbackToDestructiveMigration() // For development, remove in production
            .build()
    }
    
    @Provides
    @Singleton
    fun provideFileDao(database: BaluHostDatabase) = database.fileDao()
    
    @Provides
    @Singleton
    fun provideUserDao(database: BaluHostDatabase) = database.userDao()
    
    @Provides
    @Singleton
    fun providePendingOperationDao(database: BaluHostDatabase) = database.pendingOperationDao()
}
