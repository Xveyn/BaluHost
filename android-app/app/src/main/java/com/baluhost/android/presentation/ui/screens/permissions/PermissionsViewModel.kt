package com.baluhost.android.presentation.ui.screens.permissions

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.data.remote.dto.FilePermissionRuleDto
import com.baluhost.android.data.remote.dto.FilePermissionsRequestDto
import com.baluhost.android.domain.usecase.files.GetFilePermissionsUseCase
import com.baluhost.android.domain.usecase.files.UpdateFilePermissionsUseCase
import com.baluhost.android.util.Result
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class PermissionsViewModel @Inject constructor(
    private val getFilePermissions: GetFilePermissionsUseCase,
    private val updateFilePermissions: UpdateFilePermissionsUseCase
) : ViewModel() {

    private val _path = MutableStateFlow("")
    val path: StateFlow<String> = _path.asStateFlow()

    private val _rules = MutableStateFlow<List<FilePermissionRuleDto>>(emptyList())
    val rules: StateFlow<List<FilePermissionRuleDto>> = _rules.asStateFlow()

    private val _ownerId = MutableStateFlow(0)
    val ownerId: StateFlow<Int> = _ownerId.asStateFlow()

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    fun setPath(p: String) { _path.value = p }

    fun loadPermissions() {
        val p = _path.value
        if (p.isBlank()) return
        viewModelScope.launch {
            _loading.value = true
            when (val res = getFilePermissions(p)) {
                is Result.Success -> {
                    _rules.value = res.data.rules
                    _ownerId.value = res.data.ownerId
                    _error.value = null
                }
                is Result.Error -> {
                    _error.value = res.exception.message
                }
                else -> {
                    // Handle other Result states (e.g., Loading) gracefully
                }
            }
            _loading.value = false
        }
    }

    fun toggleRule(index: Int, flipView: Boolean? = null, flipEdit: Boolean? = null, flipDelete: Boolean? = null) {
        val current = _rules.value.toMutableList()
        val rule = current[index]
        current[index] = FilePermissionRuleDto(
            userId = rule.userId,
            canView = flipView ?: rule.canView,
            canEdit = flipEdit ?: rule.canEdit,
            canDelete = flipDelete ?: rule.canDelete
        )
        _rules.value = current
    }

    fun addRule(userId: Int) {
        val current = _rules.value.toMutableList()
        current.add(FilePermissionRuleDto(userId = userId))
        _rules.value = current
    }

    fun savePermissions() {
        val p = _path.value
        if (p.isBlank()) return
        val request = FilePermissionsRequestDto(
            path = p,
            ownerId = _ownerId.value,
            rules = _rules.value
        )
        viewModelScope.launch {
            _loading.value = true
            when (val res = updateFilePermissions(request)) {
                is Result.Success -> {
                    _rules.value = res.data.rules
                    _error.value = null
                }
                is Result.Error -> {
                    _error.value = res.exception.message
                }
                else -> {
                    // Handle other Result states (e.g., Loading) gracefully
                }
            }
            _loading.value = false
        }
    }
}
