# BaluHost Android ProGuard Rules

# Keep Retrofit annotations
-keepattributes Signature, InnerClasses, EnclosingMethod
-keepattributes RuntimeVisibleAnnotations, RuntimeVisibleParameterAnnotations
-keepattributes AnnotationDefault

-keepclassmembers,allowshrinking,allowobfuscation interface * {
    @retrofit2.http.* <methods>;
}

# Retrofit does reflection on generic parameters
-keepattributes Signature
-keepattributes Exceptions

# Keep Gson classes and annotations
-keep class com.google.gson.** { *; }
-keep class * implements com.google.gson.TypeAdapter
-keep class * implements com.google.gson.TypeAdapterFactory
-keep class * implements com.google.gson.JsonSerializer
-keep class * implements com.google.gson.JsonDeserializer

# Keep data models
-keep class com.baluhost.android.data.remote.dto.** { *; }
-keep class com.baluhost.android.domain.model.** { *; }

# Keep WireGuard
-keep class com.wireguard.** { *; }
-dontwarn com.wireguard.**

# Keep Hilt generated classes
-keep class dagger.hilt.** { *; }
-keep class javax.inject.** { *; }
-keep class * extends dagger.hilt.android.lifecycle.HiltViewModel
-keepclassmembers class * extends androidx.lifecycle.ViewModel {
    <init>(...);
}

# Keep Room
-keep class * extends androidx.room.RoomDatabase
-keep @androidx.room.Entity class *
-dontwarn androidx.room.paging.**

# OkHttp platform used only on JVM and when Conscrypt dependency is available
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# Keep Compose
-keep class androidx.compose.runtime.** { *; }

# Keep Kotlin metadata
-keep class kotlin.Metadata { *; }
