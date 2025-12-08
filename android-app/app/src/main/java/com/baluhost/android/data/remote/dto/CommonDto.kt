package com.baluhost.android.data.remote.dto

import com.google.gson.annotations.SerializedName

// ==================== Error Response ====================

data class ErrorResponse(
    val detail: String? = null,
    val message: String? = null,
    val error: String? = null
) {
    fun getErrorMessage(): String {
        return detail ?: message ?: error ?: "Unknown error"
    }
}

// ==================== Generic Success Response ====================

data class SuccessResponse(
    val message: String,
    val success: Boolean = true
)
