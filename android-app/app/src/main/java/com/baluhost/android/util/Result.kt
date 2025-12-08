package com.baluhost.android.util

/**
 * Generic Result wrapper for API calls and operations.
 * 
 * @param T The type of data returned on success
 */
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val exception: Exception) : Result<Nothing>()
    object Loading : Result<Nothing>()
    
    val isSuccess: Boolean
        get() = this is Success
    
    val isError: Boolean
        get() = this is Error
    
    val isLoading: Boolean
        get() = this is Loading
    
    fun getOrNull(): T? = when (this) {
        is Success -> data
        else -> null
    }
    
    fun exceptionOrNull(): Exception? = when (this) {
        is Error -> exception
        else -> null
    }
    
    inline fun <R> map(transform: (T) -> R): Result<R> = when (this) {
        is Success -> Success(transform(data))
        is Error -> Error(exception)
        is Loading -> Loading
    }
    
    inline fun onSuccess(action: (T) -> Unit): Result<T> {
        if (this is Success) action(data)
        return this
    }
    
    inline fun onError(action: (Exception) -> Unit): Result<T> {
        if (this is Error) action(exception)
        return this
    }
}
