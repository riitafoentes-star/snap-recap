// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;

use std::sync::Mutex;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(Mutex::new(commands::SidecarState::new()))
        .invoke_handler(tauri::generate_handler![
            commands::run_pipeline,
            commands::cancel_job,
            commands::get_job_status,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
