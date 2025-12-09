"""BaluHost Desktop Sync Client - Modern GUI matching website design."""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
from datetime import datetime
from pathlib import Path

# Import the sync client
from sync_client import SyncConfig, BaluHostSyncClient, SyncFileSystemEventHandler
from watchdog.observers import Observer


class ModernSyncClientGUI:
    """Modern GUI for BaluHost Sync Client with website-matching design."""
    
    # Color scheme matching the website
    COLORS = {
        'bg_dark': '#0f172a',          # Dark blue-black background
        'bg_card': '#1e1b4b',          # Deep indigo cards
        'bg_secondary': '#1e293b',     # Slate secondary
        'border': '#334155',           # Slate border
        'border_light': '#475569',     # Light slate border
        'text_primary': '#f8fafc',     # Almost white
        'text_secondary': '#cbd5e1',   # Light slate
        'text_muted': '#64748b',       # Muted slate
        'accent': '#38bdf8',           # Sky blue
        'accent_hover': '#0ea5e9',     # Darker sky
        'success': '#22c55e',          # Green
        'error': '#ef4444',            # Red
        'warning': '#f59e0b',          # Amber
        'indigo': '#6366f1',           # Indigo
    }
    
    def __init__(self, root):
        self.root = root
        self.root.title("BaluHost Sync")
        self.root.geometry("950x750")
        self.root.configure(bg=self.COLORS['bg_dark'])
        
        # Set window icon if available
        self.set_window_icon()
        
        # Remove default window border for modern look
        self.root.overrideredirect(False)  # Keep system controls
        
        # Make window resizable
        self.root.resizable(True, True)
        self.root.minsize(800, 600)
        
        self.config = SyncConfig()
        self.sync_client = None
        self.observer = None
        self.sync_thread = None
        self.log_queue = queue.Queue()
        self.watching = False
        
        # Configure modern style
        self.setup_modern_style()
        self.setup_ui()
        self.start_log_updater()
        
        # Auto-login if token exists
        if self.config.config.get('token'):
            self.sync_client = BaluHostSyncClient(self.config)
            self.log_message("✓ Token loaded - Ready to sync", "success")
            self.toggle_controls(True)
    
    def set_window_icon(self):
        """Set window icon from logo."""
        try:
            # Try to load icon from parent directory
            icon_path = Path(__file__).parent.parent / 'client' / 'public' / 'baluhost-logo.svg'
            if not icon_path.exists():
                # Try alternative path
                icon_path = Path(__file__).parent.parent / 'dev-storage' / 'baluhost-icon.ico'
            
            # For Windows, try to use .ico if available
            if sys.platform == 'win32':
                ico_path = Path(__file__).parent / 'baluhost-icon.ico'
                if ico_path.exists():
                    self.root.iconbitmap(str(ico_path))
        except Exception as e:
            pass  # Icon loading is optional
    
    def setup_modern_style(self):
        """Configure modern ttk style."""
        style = ttk.Style()
        
        # Configure general style
        style.theme_use('clam')
        
        # Frame styles
        style.configure('Card.TFrame', background=self.COLORS['bg_card'], relief='flat')
        style.configure('Dark.TFrame', background=self.COLORS['bg_dark'])
        
        # Label styles
        style.configure('Title.TLabel', 
                       background=self.COLORS['bg_dark'],
                       foreground=self.COLORS['text_primary'],
                       font=('Segoe UI', 24, 'bold'))
        
        style.configure('Subtitle.TLabel',
                       background=self.COLORS['bg_dark'],
                       foreground=self.COLORS['text_secondary'],
                       font=('Segoe UI', 10))
        
        style.configure('CardTitle.TLabel',
                       background=self.COLORS['bg_card'],
                       foreground=self.COLORS['text_primary'],
                       font=('Segoe UI', 12, 'bold'))
        
        style.configure('Normal.TLabel',
                       background=self.COLORS['bg_card'],
                       foreground=self.COLORS['text_secondary'],
                       font=('Segoe UI', 10))
        
        style.configure('Status.TLabel',
                       background=self.COLORS['bg_secondary'],
                       foreground=self.COLORS['text_secondary'],
                       padding=(10, 5))
        
        # Button styles
        style.configure('Accent.TButton',
                       background=self.COLORS['accent'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       padding=(20, 10),
                       font=('Segoe UI', 10, 'bold'))
        
        style.map('Accent.TButton',
                 background=[('active', self.COLORS['accent_hover']),
                           ('disabled', self.COLORS['border'])])
        
        style.configure('Secondary.TButton',
                       background=self.COLORS['bg_secondary'],
                       foreground=self.COLORS['text_primary'],
                       borderwidth=1,
                       relief='flat',
                       padding=(15, 8),
                       font=('Segoe UI', 9))
        
        # Entry styles
        style.configure('Modern.TEntry',
                       fieldbackground=self.COLORS['bg_secondary'],
                       foreground=self.COLORS['text_primary'],
                       borderwidth=1,
                       relief='flat',
                       insertcolor=self.COLORS['accent'])
    
    def setup_ui(self):
        """Setup the modern GUI layout."""
        # Main container with padding
        main_container = tk.Frame(self.root, bg=self.COLORS['bg_dark'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header
        header_frame = tk.Frame(main_container, bg=self.COLORS['bg_dark'])
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_label = ttk.Label(header_frame, text="BaluHost", style='Title.TLabel')
        title_label.pack(side=tk.LEFT)
        
        subtitle_label = ttk.Label(header_frame, text="Desktop Sync Client", style='Subtitle.TLabel')
        subtitle_label.pack(side=tk.LEFT, padx=(10, 0), pady=(8, 0))
        
        # Status indicator
        self.status_frame = tk.Frame(header_frame, bg=self.COLORS['border'], height=32)
        self.status_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.status_indicator = tk.Canvas(self.status_frame, width=12, height=12, 
                                         bg=self.COLORS['border'], highlightthickness=0)
        self.status_indicator.pack(side=tk.LEFT, padx=8)
        self.status_dot = self.status_indicator.create_oval(2, 2, 10, 10, 
                                                            fill=self.COLORS['text_muted'], 
                                                            outline='')
        
        self.status_var = tk.StringVar(value="Not connected")
        status_label = tk.Label(self.status_frame, textvariable=self.status_var,
                               bg=self.COLORS['border'], fg=self.COLORS['text_secondary'],
                               font=('Segoe UI', 9), padx=8)
        status_label.pack(side=tk.LEFT)
        
        # Connection Card
        conn_card = self.create_card(main_container, "Connection")
        conn_card.pack(fill=tk.X, pady=(0, 15))
        
        # Server URL
        self.create_input_row(conn_card, "Server URL:", 
                             self.config.config.get('server_url', 'https://localhost:8000'),
                             var_name='server_entry')
        
        # Username
        self.create_input_row(conn_card, "Username:", "admin", var_name='username_entry')
        
        # Password
        self.create_input_row(conn_card, "Password:", "", show="•", var_name='password_entry')
        
        # Login button
        btn_frame = tk.Frame(conn_card, bg=self.COLORS['bg_card'])
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.login_btn = self.create_gradient_button(
            btn_frame,
            text="🔐 Connect & Login",
            command=self.login,
            bg=self.COLORS['accent'],
            fg='white'
        )
        self.login_btn.pack(side=tk.RIGHT)
        
        # Sync Folders Card
        folders_card = self.create_card(main_container, "Sync Folders")
        folders_card.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Folders listbox with modern styling
        list_container = tk.Frame(folders_card, bg=self.COLORS['bg_secondary'], 
                                 highlightbackground=self.COLORS['border'], 
                                 highlightthickness=1)
        list_container.pack(fill=tk.BOTH, expand=True, pady=(10, 10))
        
        scrollbar = tk.Scrollbar(list_container, bg=self.COLORS['bg_secondary'])
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.folders_listbox = tk.Listbox(list_container,
                                          bg=self.COLORS['bg_secondary'],
                                          fg=self.COLORS['text_primary'],
                                          selectbackground=self.COLORS['accent'],
                                          selectforeground='white',
                                          font=('Segoe UI', 10),
                                          relief='flat',
                                          borderwidth=0,
                                          yscrollcommand=scrollbar.set)
        self.folders_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        scrollbar.config(command=self.folders_listbox.yview)
        
        # Populate folders
        for folder in self.config.config.get('sync_folders', []):
            self.folders_listbox.insert(tk.END, folder)
        
        # Folder buttons
        folder_btn_frame = tk.Frame(folders_card, bg=self.COLORS['bg_card'])
        folder_btn_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        
        self.add_folder_btn = self.create_secondary_button(
            folder_btn_frame, "➕ Add Folder", 
            self.add_folder, state=tk.DISABLED
        )
        self.add_folder_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.remove_folder_btn = self.create_secondary_button(
            folder_btn_frame, "🗑️ Remove", 
            self.remove_folder, state=tk.DISABLED
        )
        self.remove_folder_btn.pack(side=tk.LEFT)
        
        # Controls Card
        controls_card = self.create_card(main_container, "Sync Controls")
        controls_card.pack(fill=tk.X, pady=(0, 15))
        
        controls_inner = tk.Frame(controls_card, bg=self.COLORS['bg_card'])
        controls_inner.pack(fill=tk.X, pady=(10, 0))
        
        self.sync_now_btn = self.create_gradient_button(
            controls_inner,
            text="⚡ Sync Now",
            command=self.sync_now,
            bg=self.COLORS['success'],
            fg='white',
            state=tk.DISABLED
        )
        self.sync_now_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.watch_btn = self.create_gradient_button(
            controls_inner,
            text="👁️ Start Watching",
            command=self.toggle_watch,
            bg=self.COLORS['indigo'],
            fg='white',
            state=tk.DISABLED
        )
        self.watch_btn.pack(side=tk.LEFT)
        
        # Auto-sync checkbox
        self.auto_sync_var = tk.BooleanVar(value=self.config.config.get('auto_sync', True))
        self.auto_sync_check = tk.Checkbutton(controls_inner,
                                              text="Auto-sync enabled",
                                              variable=self.auto_sync_var,
                                              command=self.toggle_auto_sync,
                                              bg=self.COLORS['bg_card'],
                                              fg=self.COLORS['text_secondary'],
                                              selectcolor=self.COLORS['bg_secondary'],
                                              activebackground=self.COLORS['bg_card'],
                                              activeforeground=self.COLORS['text_primary'],
                                              font=('Segoe UI', 10),
                                              state=tk.DISABLED)
        self.auto_sync_check.pack(side=tk.RIGHT)
        
        # Log Card
        log_card = self.create_card(main_container, "Activity Log")
        log_card.pack(fill=tk.BOTH, expand=True)
        
        log_container = tk.Frame(log_card, bg=self.COLORS['bg_secondary'],
                                highlightbackground=self.COLORS['border'],
                                highlightthickness=1)
        log_container.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        self.log_text = scrolledtext.ScrolledText(log_container,
                                                  height=8,
                                                  bg=self.COLORS['bg_secondary'],
                                                  fg=self.COLORS['text_secondary'],
                                                  font=('Consolas', 9),
                                                  relief='flat',
                                                  borderwidth=0,
                                                  padx=10, pady=10,
                                                  state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure log text tags
        self.log_text.tag_config('success', foreground=self.COLORS['success'])
        self.log_text.tag_config('error', foreground=self.COLORS['error'])
        self.log_text.tag_config('warning', foreground=self.COLORS['warning'])
        self.log_text.tag_config('info', foreground=self.COLORS['accent'])
    
    def create_gradient_button(self, parent, text, command, bg, fg='white', state=tk.NORMAL):
        """Create a modern gradient button with hover effects."""
        btn_container = tk.Frame(parent, bg=self.COLORS['bg_card'])
        
        btn = tk.Button(btn_container,
                       text=text,
                       command=command,
                       bg=bg,
                       fg=fg,
                       font=('Segoe UI', 10, 'bold'),
                       relief='flat',
                       cursor='hand2',
                       padx=25, pady=12,
                       borderwidth=0,
                       state=state)
        btn.pack()
        
        # Add hover effects
        def on_enter(e):
            if btn['state'] != tk.DISABLED:
                # Lighten color on hover
                if bg == self.COLORS['accent']:
                    btn.config(bg=self.COLORS['accent_hover'])
                elif bg == self.COLORS['success']:
                    btn.config(bg='#34d399')  # Lighter green
                elif bg == self.COLORS['indigo']:
                    btn.config(bg='#818cf8')  # Lighter indigo
        
        def on_leave(e):
            if btn['state'] != tk.DISABLED:
                btn.config(bg=bg)
        
        btn.bind('<Enter>', on_enter)
        btn.bind('<Leave>', on_leave)
        
        return btn
    
    def create_card(self, parent, title):
        """Create a modern card container with shadow effect."""        
        # Card frame with border
        card = tk.Frame(parent, bg=self.COLORS['bg_card'], 
                       highlightbackground=self.COLORS['border'],
                       highlightthickness=1,
                       relief='flat')
        
        # Title with accent color
        title_frame = tk.Frame(card, bg=self.COLORS['bg_card'])
        title_frame.pack(fill=tk.X)
        
        title_label = tk.Label(title_frame, text=title,
                              bg=self.COLORS['bg_card'],
                              fg=self.COLORS['text_primary'],
                              font=('Segoe UI', 12, 'bold'))
        title_label.pack(anchor=tk.W, padx=20, pady=(20, 8))
        
        # Gradient separator
        separator = tk.Frame(card, bg=self.COLORS['border'], height=2)
        separator.pack(fill=tk.X, padx=20, pady=(0, 15))
        
        return card
    
    def create_input_row(self, parent, label_text, default_value="", show=None, var_name=None):
        """Create a modern input row with focus effects."""
        row_frame = tk.Frame(parent, bg=self.COLORS['bg_card'])
        row_frame.pack(fill=tk.X, padx=20, pady=8)
        
        label = tk.Label(row_frame, text=label_text,
                        bg=self.COLORS['bg_card'],
                        fg=self.COLORS['text_secondary'],
                        font=('Segoe UI', 10, 'bold'),
                        width=12, anchor=tk.W)
        label.pack(side=tk.LEFT, padx=(0, 15))
        
        # Entry container for border effect
        entry_container = tk.Frame(row_frame, 
                                  bg=self.COLORS['border'],
                                  highlightthickness=1,
                                  highlightbackground=self.COLORS['border'])
        entry_container.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        entry = tk.Entry(entry_container,
                        bg=self.COLORS['bg_secondary'],
                        fg=self.COLORS['text_primary'],
                        font=('Segoe UI', 10),
                        relief='flat',
                        borderwidth=0,
                        insertbackground=self.COLORS['accent'])
        if show:
            entry.config(show=show)
        entry.insert(0, default_value)
        entry.pack(fill=tk.BOTH, padx=1, pady=1, ipady=10, ipadx=12)
        
        # Add focus effects
        def on_focus_in(e):
            entry_container.config(highlightbackground=self.COLORS['accent'],
                                 highlightthickness=2)
        
        def on_focus_out(e):
            entry_container.config(highlightbackground=self.COLORS['border'],
                                 highlightthickness=1)
        
        entry.bind('<FocusIn>', on_focus_in)
        entry.bind('<FocusOut>', on_focus_out)
        
        if var_name:
            setattr(self, var_name, entry)
        
        return entry
    
    def create_secondary_button(self, parent, text, command, state=tk.NORMAL):
        """Create a modern secondary button."""
        btn = tk.Button(parent, text=text,
                       command=command,
                       bg=self.COLORS['bg_secondary'],
                       fg=self.COLORS['text_primary'],
                       font=('Segoe UI', 9, 'bold'),
                       relief='flat',
                       cursor='hand2',
                       padx=18, pady=10,
                       borderwidth=0,
                       state=state)
        
        # Add hover effects
        def on_enter(e):
            if btn['state'] != tk.DISABLED:
                btn.config(bg=self.COLORS['border_light'])
        
        def on_leave(e):
            if btn['state'] != tk.DISABLED:
                btn.config(bg=self.COLORS['bg_secondary'])
        
        btn.bind('<Enter>', on_enter)
        btn.bind('<Leave>', on_leave)
        
        return btn
    
    def update_status(self, message, status='info'):
        """Update status bar and indicator."""
        self.status_var.set(message)
        
        color_map = {
            'success': self.COLORS['success'],
            'error': self.COLORS['error'],
            'warning': self.COLORS['warning'],
            'info': self.COLORS['accent'],
        }
        
        self.status_indicator.itemconfig(self.status_dot, fill=color_map.get(status, self.COLORS['text_muted']))
    
    def log_message(self, message, level='info'):
        """Add a message to the log."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_queue.put((f"[{timestamp}] {message}", level))
    
    def start_log_updater(self):
        """Start the log updater thread."""
        def update_log():
            while True:
                try:
                    message, level = self.log_queue.get(timeout=0.1)
                    self.log_text.config(state=tk.NORMAL)
                    self.log_text.insert(tk.END, message + '\n', level)
                    self.log_text.see(tk.END)
                    self.log_text.config(state=tk.DISABLED)
                except queue.Empty:
                    pass
                except:
                    break
        
        log_thread = threading.Thread(target=update_log, daemon=True)
        log_thread.start()
    
    def toggle_controls(self, enabled):
        """Enable/disable controls after login."""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.sync_now_btn.config(state=state)
        self.watch_btn.config(state=state)
        self.auto_sync_check.config(state=state)
        self.add_folder_btn.config(state=state)
        self.remove_folder_btn.config(state=state)
    
    def login(self):
        """Handle login."""
        username = self.username_entry.get()
        password = self.password_entry.get()
        server_url = self.server_entry.get()
        
        if not username or not password:
            self.log_message("❌ Please enter username and password", "error")
            return
        
        self.log_message(f"🔄 Connecting to {server_url}...", "info")
        self.update_status("Connecting...", "warning")
        
        # Update server URL
        self.config.config['server_url'] = server_url
        self.config.save()
        
        self.sync_client = BaluHostSyncClient(self.config)
        
        def do_login():
            success = self.sync_client.login(username, password)
            
            if success:
                self.log_message(f"✓ Logged in as {username}", "success")
                self.log_message("🔄 Registering device...", "info")
                
                reg_success = self.sync_client.register_device()
                if reg_success:
                    self.log_message("✓ Device registered successfully", "success")
                    self.update_status("Connected & Ready", "success")
                    self.root.after(0, lambda: self.toggle_controls(True))
                    self.root.after(0, lambda: self.login_btn.config(state=tk.DISABLED))
                else:
                    self.log_message("⚠️ Device registration failed", "warning")
                    self.update_status("Connected (registration failed)", "warning")
            else:
                self.log_message("❌ Login failed - Check credentials", "error")
                self.update_status("Login failed", "error")
        
        threading.Thread(target=do_login, daemon=True).start()
    
    def add_folder(self):
        """Add a folder to sync."""
        folder = filedialog.askdirectory()
        if folder:
            self.config.add_sync_folder(folder)
            self.folders_listbox.insert(tk.END, folder)
            self.log_message(f"✓ Added folder: {folder}", "success")
    
    def remove_folder(self):
        """Remove selected folder."""
        selection = self.folders_listbox.curselection()
        if selection:
            folder = self.folders_listbox.get(selection[0])
            self.config.remove_sync_folder(folder)
            self.folders_listbox.delete(selection[0])
            self.log_message(f"🗑️ Removed folder: {folder}", "info")
    
    def sync_now(self):
        """Trigger manual sync."""
        if not self.sync_client:
            return
        
        self.log_message("⚡ Starting manual sync...", "info")
        self.update_status("Syncing...", "warning")
        
        def do_sync():
            self.sync_client.sync()
            self.log_message("✓ Sync completed", "success")
            self.root.after(0, lambda: self.update_status("Connected & Ready", "success"))
        
        threading.Thread(target=do_sync, daemon=True).start()
    
    def toggle_watch(self):
        """Toggle file watching."""
        if not self.watching:
            self.start_watching()
        else:
            self.stop_watching()
    
    def start_watching(self):
        """Start file watching."""
        if not self.sync_client or not self.config.config['sync_folders']:
            self.log_message("⚠️ Add folders to sync first", "warning")
            return
        
        self.watching = True
        self.watch_btn.config(text="⏸️ Stop Watching")
        self.log_message("👁️ File watching started", "success")
        self.update_status("Watching for changes...", "success")
        
        self.observer = Observer()
        event_handler = SyncFileSystemEventHandler(self.sync_client)
        
        for folder in self.config.config['sync_folders']:
            self.observer.schedule(event_handler, folder, recursive=True)
            self.log_message(f"  Watching: {folder}", "info")
        
        self.observer.start()
    
    def stop_watching(self):
        """Stop file watching."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
        
        self.watching = False
        self.watch_btn.config(text="👁️ Start Watching")
        self.log_message("⏸️ File watching stopped", "info")
        self.update_status("Connected & Ready", "success")
    
    def toggle_auto_sync(self):
        """Toggle auto-sync setting."""
        self.config.config['auto_sync'] = self.auto_sync_var.get()
        self.config.save()
        status = "enabled" if self.auto_sync_var.get() else "disabled"
        self.log_message(f"⚙️ Auto-sync {status}", "info")


def main():
    """Main entry point."""
    root = tk.Tk()
    app = ModernSyncClientGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
