package com.baluhost.android.data.local.database

import androidx.room.TypeConverter
import java.time.Instant

/**
 * Room type converters for custom types.
 */
class Converters {
    
    @TypeConverter
    fun fromTimestamp(value: Long?): Instant? {
        return value?.let { Instant.ofEpochMilli(it) }
    }
    
    @TypeConverter
    fun dateToTimestamp(date: Instant?): Long? {
        return date?.toEpochMilli()
    }
}
