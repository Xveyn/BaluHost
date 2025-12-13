package com.baluhost.android.data.local.database

import androidx.room.Database
import androidx.room.RoomDatabase
import com.baluhost.android.data.local.database.dao.FileItemDao
import com.baluhost.android.data.local.database.entity.FileItemEntity

/**
 * Room Database for offline caching.
 */
@Database(
    entities = [
        FileItemEntity::class
    ],
    version = 1,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun fileItemDao(): FileItemDao
}
