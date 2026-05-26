//! BaluHost Companion App — binary entry point.
//!
//! Delegates to `baluhost_companion_lib::run()` for actual setup.

// Prevents additional console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    baluhost_companion_lib::run()
}
