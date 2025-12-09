"""BaluHost Desktop Sync Client - GUI Version."""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
from datetime import datetime

# Import the sync client
from sync_client import SyncConfig, BaluHostSyncClient, SyncFileSystemEventHandler
from watchdog.observers import Observer


class SyncClientGUI:
    """GUI for BaluHost Sync Client."""
    
    # Modern color scheme matching the website
    COLORS = {
        'bg_primary': '#0f172a',      # Dark blue-black
        'bg_secondary': '#1e293b',     # Slate
        'bg_card': '#1e1b4b',          # Deep indigo
        'border': '#334155',           # Slate border
        'text_primary': '#f8fafc',     # Almost white
        'text_secondary': '#cbd5e1',   # Light slate
        'accent': '#38bdf8',           # Sky blue
        'accent_hover': '#7dd3fc',     # Light sky
        'success': '#22c55e',          # Green
        'error': '#ef4444',            # Red
        'warning': '#f59e0b',          # Amber
    }
    
    def __init__(self, root):
        self.root = root
        self.root.title("BaluHost Sync Client")
        self.root.geometry("900x700")
        
        self.config = SyncConfig()
        self.sync_client = None
        self.observer = None
        self.sync_thread = None
        self.log_queue = queue.Queue()
        
        self.setup_ui()
        self.start_log_updater()
        
        # Auto-login if token exists
        if self.config.config.get('token'):
            self.sync_client = BaluHostSyncClient(self.config)
            self.update_status("Ready - Token loaded")
            self.toggle_controls(True)
    
    def setup_ui(self):
        """Setup the GUI layout."""
        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Settings", command=self.show_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Status bar
        self.status_var = tk.StringVar(value="Not connected")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Connection frame
        conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding="10")
        conn_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(conn_frame, text="Server:").grid(row=0, column=0, sticky=tk.W)
        self.server_entry = ttk.Entry(conn_frame, width=40)
        self.server_entry.insert(0, self.config.config.get('server_url', 'http://localhost:8000'))
        self.server_entry.grid(row=0, column=1, padx=5)
        
        ttk.Label(conn_frame, text="Username:").grid(row=1, column=0, sticky=tk.W)
        self.username_entry = ttk.Entry(conn_frame, width=40)
        self.username_entry.grid(row=1, column=1, padx=5)
        
        ttk.Label(conn_frame, text="Password:").grid(row=2, column=0, sticky=tk.W)
        self.password_entry = ttk.Entry(conn_frame, show="*", width=40)
        self.password_entry.grid(row=2, column=1, padx=5)
        
        self.login_btn = ttk.Button(conn_frame, text="Login", command=self.login)
        self.login_btn.grid(row=3, column=1, sticky=tk.E, pady=5)
        
        # Sync folders frame
        folders_frame = ttk.LabelFrame(main_frame, text="Sync Folders", padding="10")
        folders_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(folders_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.folders_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        self.folders_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.folders_listbox.yview)
        
        # Populate existing folders
        for folder in self.config.config.get('sync_folders', []):
            self.folders_listbox.insert(tk.END, folder)
        
        # Folder buttons
        folder_btn_frame = ttk.Frame(folders_frame)
        folder_btn_frame.pack(fill=tk.X, pady=5)
        
        self.add_folder_btn = ttk.Button(folder_btn_frame, text="Add Folder", command=self.add_folder)
        self.add_folder_btn.pack(side=tk.LEFT, padx=5)
        
        self.remove_folder_btn = ttk.Button(folder_btn_frame, text="Remove Folder", command=self.remove_folder)
        self.remove_folder_btn.pack(side=tk.LEFT)
        
        # Sync controls
        controls_frame = ttk.Frame(main_frame)
        controls_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.sync_now_btn = ttk.Button(controls_frame, text="Sync Now", command=self.sync_now, state=tk.DISABLED)
        self.sync_now_btn.pack(side=tk.LEFT, padx=5)
        
        self.auto_sync_var = tk.BooleanVar(value=self.config.config.get('auto_sync', True))
        self.auto_sync_check = ttk.Checkbutton(
            controls_frame, 
            text="Auto-sync enabled", 
            variable=self.auto_sync_var,
            command=self.toggle_auto_sync,
            state=tk.DISABLED
        )
        self.auto_sync_check.pack(side=tk.LEFT, padx=5)
        
        self.watch_btn = ttk.Button(controls_frame, text="Start Watching", command=self.toggle_watch, state=tk.DISABLED)
        self.watch_btn.pack(side=tk.LEFT, padx=5)
        
        # Log frame
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
    
    def toggle_controls(self, enabled: bool):
        """Enable/disable controls after login."""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.sync_now_btn.config(state=state)
        self.auto_sync_check.config(state=state)
        self.watch_btn.config(state=state)
        self.add_folder_btn.config(state=state)
        self.remove_folder_btn.config(state=state)
    
    def log(self, message: str):
        """Add message to log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {message}")
    
    def start_log_updater(self):
        """Start the log updater thread."""
        def update_log():
            try:
                while True:
                    message = self.log_queue.get_nowait()
                    self.log_text.config(state=tk.NORMAL)
                    self.log_text.insert(tk.END, message + "\n")
                    self.log_text.see(tk.END)
                    self.log_text.config(state=tk.DISABLED)
            except queue.Empty:
                pass
            self.root.after(100, update_log)
        
        update_log()
    
    def update_status(self, message: str):
        """Update status bar."""
        self.status_var.set(message)
    
    def login(self):
        """Login to server."""
        server_url = self.server_entry.get()
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        if not all([server_url, username, password]):
            messagebox.showerror("Error", "Please fill in all fields")
            return
        
        # Update config
        self.config.config['server_url'] = server_url
        self.config.save()
        
        self.log(f"Connecting to {server_url}...")
        self.update_status("Logging in...")
        
        # Create sync client
        self.sync_client = BaluHostSyncClient(self.config)
        
        # Login in thread to avoid blocking UI
        def do_login():
            success = self.sync_client.login(username, password)
            
            if success:
                # Register device
                self.sync_client.register_device()
                self.log("Login successful")
                self.update_status("Connected")
                self.toggle_controls(True)
                
                # Clear password
                self.password_entry.delete(0, tk.END)
            else:
                self.log("Login failed")
                self.update_status("Login failed")
                messagebox.showerror("Error", "Login failed. Check credentials.")
        
        threading.Thread(target=do_login, daemon=True).start()
    
    def add_folder(self):
        """Add a folder to sync."""
        folder = filedialog.askdirectory()
        if folder:
            self.config.add_sync_folder(folder)
            self.folders_listbox.insert(tk.END, folder)
            self.log(f"Added folder: {folder}")
    
    def remove_folder(self):
        """Remove selected folder."""
        selection = self.folders_listbox.curselection()
        if selection:
            folder = self.folders_listbox.get(selection[0])
            self.config.remove_sync_folder(folder)
            self.folders_listbox.delete(selection[0])
            self.log(f"Removed folder: {folder}")
    
    def sync_now(self):
        """Perform manual sync."""
        if not self.sync_client:
            return
        
        self.log("Starting manual sync...")
        self.update_status("Syncing...")
        
        def do_sync():
            self.sync_client.sync()
            self.log("Sync completed")
            self.update_status("Ready")
        
        threading.Thread(target=do_sync, daemon=True).start()
    
    def toggle_auto_sync(self):
        """Toggle auto-sync setting."""
        self.config.config['auto_sync'] = self.auto_sync_var.get()
        self.config.save()
        self.log(f"Auto-sync: {'enabled' if self.auto_sync_var.get() else 'disabled'}")
    
    def toggle_watch(self):
        """Start/stop file watching."""
        if self.observer is None:
            # Start watching
            self.log("Starting file watcher...")
            self.update_status("Watching for changes...")
            
            event_handler = SyncFileSystemEventHandler(self.sync_client)
            self.observer = Observer()
            
            for folder in self.config.config['sync_folders']:
                self.observer.schedule(event_handler, folder, recursive=True)
                self.log(f"Watching: {folder}")
            
            self.observer.start()
            self.watch_btn.config(text="Stop Watching")
            
            # Start processing pending changes
            self.process_changes()
        else:
            # Stop watching
            self.log("Stopping file watcher...")
            self.observer.stop()
            self.observer.join()
            self.observer = None
            self.watch_btn.config(text="Start Watching")
            self.update_status("Ready")
    
    def process_changes(self):
        """Process pending changes periodically."""
        if self.observer and self.sync_client:
            self.sync_client.process_pending_changes()
            self.root.after(1000, self.process_changes)
    
    def show_settings(self):
        """Show settings dialog."""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("400x300")
        
        frame = ttk.Frame(settings_window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Device ID:").grid(row=0, column=0, sticky=tk.W, pady=5)
        device_id_entry = ttk.Entry(frame, width=30)
        device_id_entry.insert(0, self.config.config.get('device_id', ''))
        device_id_entry.grid(row=0, column=1, pady=5)
        
        ttk.Label(frame, text="Device Name:").grid(row=1, column=0, sticky=tk.W, pady=5)
        device_name_entry = ttk.Entry(frame, width=30)
        device_name_entry.insert(0, self.config.config.get('device_name', ''))
        device_name_entry.grid(row=1, column=1, pady=5)
        
        ttk.Label(frame, text="Debounce Delay (s):").grid(row=2, column=0, sticky=tk.W, pady=5)
        debounce_entry = ttk.Entry(frame, width=30)
        debounce_entry.insert(0, str(self.config.config.get('debounce_delay', 2)))
        debounce_entry.grid(row=2, column=1, pady=5)
        
        def save_settings():
            self.config.config['device_id'] = device_id_entry.get()
            self.config.config['device_name'] = device_name_entry.get()
            self.config.config['debounce_delay'] = int(debounce_entry.get())
            self.config.save()
            self.log("Settings saved")
            settings_window.destroy()
        
        ttk.Button(frame, text="Save", command=save_settings).grid(row=3, column=1, sticky=tk.E, pady=10)


def main():
    """Main entry point for GUI."""
    root = tk.Tk()
    app = SyncClientGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
