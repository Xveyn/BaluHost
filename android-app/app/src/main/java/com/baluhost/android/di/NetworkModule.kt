package com.baluhost.android.di

import com.baluhost.android.BuildConfig
import com.baluhost.android.data.local.datastore.PreferencesManager
import com.baluhost.android.data.remote.api.AuthApi
import com.baluhost.android.data.remote.api.FilesApi
import com.baluhost.android.data.remote.api.MobileApi
import com.baluhost.android.data.remote.api.VpnApi
import com.baluhost.android.data.remote.interceptors.AuthInterceptor
import com.baluhost.android.data.remote.interceptors.ErrorInterceptor
import com.baluhost.android.util.Constants
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

/**
 * Provides networking dependencies (Retrofit, OkHttp, API interfaces).
 */
@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    
    @Provides
    @Singleton
    fun provideLoggingInterceptor(): HttpLoggingInterceptor {
        return HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) {
                HttpLoggingInterceptor.Level.BODY
            } else {
                HttpLoggingInterceptor.Level.NONE
            }
        }
    }
    
    @Provides
    @Singleton
    fun provideAuthInterceptor(
        preferencesManager: PreferencesManager,
        authApi: dagger.Lazy<AuthApi>
    ): AuthInterceptor {
        return AuthInterceptor(preferencesManager, authApi)
    }
    
    @Provides
    @Singleton
    fun provideErrorInterceptor(): ErrorInterceptor {
        return ErrorInterceptor()
    }
    
    @Provides
    @Singleton
    fun provideOkHttpClient(
        loggingInterceptor: HttpLoggingInterceptor,
        authInterceptor: AuthInterceptor,
        errorInterceptor: ErrorInterceptor
    ): OkHttpClient {
        return OkHttpClient.Builder()
            .addInterceptor(errorInterceptor)
            .addInterceptor(authInterceptor)
            .addInterceptor(loggingInterceptor)
            .connectTimeout(Constants.CONNECT_TIMEOUT, TimeUnit.SECONDS)
            .readTimeout(Constants.READ_TIMEOUT, TimeUnit.SECONDS)
            .writeTimeout(Constants.WRITE_TIMEOUT, TimeUnit.SECONDS)
            .build()
    }
    
    @Provides
    @Singleton
    fun provideRetrofit(
        okHttpClient: OkHttpClient
    ): Retrofit {
        return Retrofit.Builder()
            .baseUrl(BuildConfig.BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }
    
    @Provides
    @Singleton
    fun provideAuthApi(retrofit: Retrofit): AuthApi {
        return retrofit.create(AuthApi::class.java)
    }
    
    @Provides
    @Singleton
    fun provideFilesApi(retrofit: Retrofit): FilesApi {
        return retrofit.create(FilesApi::class.java)
    }
    
    @Provides
    @Singleton
    fun provideMobileApi(retrofit: Retrofit): MobileApi {
        return retrofit.create(MobileApi::class.java)
    }
    
    @Provides
    @Singleton
    fun provideVpnApi(retrofit: Retrofit): VpnApi {
        return retrofit.create(VpnApi::class.java)
    }
}
