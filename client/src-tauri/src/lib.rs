//! BaluHost Companion App — library crate.
//!
//! Boots an HTTP-to-UDS proxy and a Tauri webview. The webview receives
//! its API base URL via an injected `window.__BALU_API_BASE__` global
//! (set by initialization_script BEFORE the React bundle loads), so the
//! existing axios client in api.ts can pick it up synchronously.

pub mod proxy;

use std::path::PathBuf;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .expect("failed to build tokio runtime");

    let uds_path = PathBuf::from(
        std::env::var("BALUHOST_LOCAL_SOCKET")
            .unwrap_or_else(|_| "/run/baluhost/local.sock".to_string()),
    );

    let (proxy_port, _proxy_handle) = runtime
        .block_on(async { proxy::start(uds_path).await })
        .expect("proxy startup failed");

    // No `/api` suffix: the React client already prefixes paths with `/api`
    // (see api.ts), so the base URL must be the proxy origin only, otherwise
    // axios produces `/api/api/...` and the backend returns 404.
    let init_script = format!(
        "window.__BALU_API_BASE__ = 'http://127.0.0.1:{}';",
        proxy_port,
    );

    tauri::Builder::default()
        .setup(move |app| {
            // Inject the API base global into the main window before any
            // page script runs.
            use tauri::WebviewUrl;
            use tauri::webview::WebviewWindowBuilder;

            let main_window = WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::default(),
            )
            .title("BaluHost Companion")
            .inner_size(1280.0, 800.0)
            .min_inner_size(1024.0, 600.0)
            .resizable(true)
            .initialization_script(&init_script)
            .build()?;

            let _ = main_window;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running BaluHost Companion");
}
