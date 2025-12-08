package com.baluhost.android.data.local.database.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.baluhost.android.data.local.database.entities.UserEntity
import kotlinx.coroutines.flow.Flow

/**
 * DAO for user operations.
 */
@Dao
interface UserDao {
    
    @Query("SELECT * FROM users WHERE id = :userId")
    fun getUserById(userId: Int): Flow<UserEntity?>
    
    @Query("SELECT * FROM users WHERE username = :username")
    suspend fun getUserByUsername(username: String): UserEntity?
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertUser(user: UserEntity)
    
    @Query("DELETE FROM users")
    suspend fun deleteAll()
}
