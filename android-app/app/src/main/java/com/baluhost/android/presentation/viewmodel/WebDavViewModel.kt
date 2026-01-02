package com.baluhost.android.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baluhost.android.data.sync.WebDavAdapterFactory
import com.baluhost.android.domain.model.sync.FileEntry
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class WebDavViewModel @Inject constructor(private val factory: WebDavAdapterFactory) : ViewModel() {

    private val _listing = MutableStateFlow<List<FileEntry>>(emptyList())
    val listing: StateFlow<List<FileEntry>> = _listing

    private val _authOk = MutableStateFlow<Boolean?>(null)
    val authOk: StateFlow<Boolean?> = _authOk

    fun testCredentials(username: String?, password: String?) {
        viewModelScope.launch {
            val adapter = factory.create(username, password)
            val ok = try { adapter.authenticate() } catch (_: Exception) { false }
            _authOk.value = ok
        }
    }

    fun listRemote(path: String, username: String?, password: String?) {
        viewModelScope.launch {
            val adapter = factory.create(username, password)
            val items = try { adapter.list(path) } catch (_: Exception) { emptyList<FileEntry>() }
            _listing.value = items
        }
    }
}
