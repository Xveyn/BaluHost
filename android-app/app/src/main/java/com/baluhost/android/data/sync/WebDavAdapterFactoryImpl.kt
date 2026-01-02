package com.baluhost.android.data.sync

import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class WebDavAdapterFactoryImpl @Inject constructor() : WebDavAdapterFactory {
    override fun create(username: String?, password: String?): WebDavAdapter = WebDavAdapter(username, password)
}
