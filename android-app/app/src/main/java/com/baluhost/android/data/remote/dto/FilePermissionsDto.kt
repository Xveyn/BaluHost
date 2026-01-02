package com.baluhost.android.data.remote.dto

import com.google.gson.annotations.SerializedName

data class FilePermissionRuleDto(
    @SerializedName("user_id")
    val userId: Int,
    @SerializedName("can_view")
    val canView: Boolean = true,
    @SerializedName("can_edit")
    val canEdit: Boolean = true,
    @SerializedName("can_delete")
    val canDelete: Boolean = true
)

data class FilePermissionsDto(
    val path: String,
    @SerializedName("owner_id")
    val ownerId: Int,
    val rules: List<FilePermissionRuleDto>
)

data class FilePermissionsRequestDto(
    val path: String,
    @SerializedName("owner_id")
    val ownerId: Int,
    val rules: List<FilePermissionRuleDto>
)
