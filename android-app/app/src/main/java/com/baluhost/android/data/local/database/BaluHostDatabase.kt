package com.baluhost.android.data.local.database

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import com.baluhost.android.data.local.database.converters.Converters
import com.baluhost.android.data.local.database.dao.FileDao
import com.baluhost.android.data.local.database.dao.UserDao
import com.baluhost.android.data.local.database.entities.FileEntity
import com.baluhost.android.data.local.database.entities.UserEntity

/**
 * BaluHost Room Database.
 * 
 * Stores cached file metadata and user info for offline access.
 */
@Database(
    entities = [
        FileEntity::class,
        UserEntity::class
    ],
    version = 2, // Incremented for parentPath column
    exportSchema = false
)
@TypeConverters(Converters::class)
abstract class BaluHostDatabase : RoomDatabase() {
    
    abstract fun fileDao(): FileDao
    abstract fun userDao(): UserDao
}
