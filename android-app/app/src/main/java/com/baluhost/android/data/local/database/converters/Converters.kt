package com.baluhost.android.data.local.database.converters

import androidx.room.TypeConverter
import java.time.Instant

/**
 * Room type converters for database entities.
 */
class Converters {
    
    @TypeConverter
    fun fromTimestamp(value: Long?): Instant? {
        return value?.let { Instant.ofEpochMilli(it) }
    }
    
    @TypeConverter
    fun instantToTimestamp(instant: Instant?): Long? {
        return instant?.toEpochMilli()
    }
}
