#!/usr/bin/env python3
"""
BaluHost Desktop Sync Client - Modern GUI v2
Beautiful, polished interface matching the website design
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
from sync_client import BaluHostSyncClient, SyncConfig
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
import socket

class ModernSyncGUI:
    """Ultra-modern sync client GUI with polished design."""
    
    # Color scheme matching website
    COLORS = {
        'bg_dark': '#0f172a',
        'bg_card': '#1e1b4b',
        'bg_input': '#1e293b',
        'accent': '#38bdf8',
        'accent_hover': '#0ea5e9',
        'success': '#10b981',
        'success_hover': '#059669',
        'text_primary': '#f8fafc',
        'text_secondary': '#94a3b8',
        'border': '#334155',
        'border_focus': '#38bdf8',
    }
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BaluHost Sync")
        self.root.geometry("800x700")
        self.root.configure(bg=self.COLORS['bg_dark'])
        self.root.minsize(700, 600)
        
        # Initialize sync client
        self.config = SyncConfig()
        self.sync_client = BaluHostSyncClient(self.config)
        
        # Try to set icon
        try:
            icon_path = Path(__file__).parent / 'baluhost-icon.ico'
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except:
            pass
        
        self.setup_ui()
        
    def setup_ui(self):
        """Build the beautiful UI."""
        # Header with logo
        header = tk.Frame(self.root, bg=self.COLORS['bg_dark'], height=80)
        header.pack(fill=tk.X, padx=30, pady=(20, 10))
        header.pack_propagate(False)
        
        tk.Label(header, text="BaluHost", 
                bg=self.COLORS['bg_dark'], 
                fg=self.COLORS['text_primary'],
                font=('Segoe UI', 24, 'bold')).pack(side=tk.LEFT, pady=20)
        
        tk.Label(header, text="Sync Client", 
                bg=self.COLORS['bg_dark'], 
                fg=self.COLORS['text_secondary'],
                font=('Segoe UI', 12)).pack(side=tk.LEFT, padx=(10, 0), pady=(28, 20))
        
        # Status indicator
        status_frame = tk.Frame(header, bg=self.COLORS['bg_card'], 
                               highlightbackground=self.COLORS['border'],
                               highlightthickness=1)
        status_frame.pack(side=tk.RIGHT, pady=20)
        
        self.status_dot = tk.Canvas(status_frame, width=10, height=10, 
                                   bg=self.COLORS['bg_card'], 
                                   highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=(12, 8), pady=10)
        self.dot = self.status_dot.create_oval(2, 2, 8, 8, 
                                               fill=self.COLORS['text_secondary'], 
                                               outline='')
        
        self.status_label = tk.Label(status_frame, text="Not connected",
                                     bg=self.COLORS['bg_card'],
                                     fg=self.COLORS['text_secondary'],
                                     font=('Segoe UI', 9))
        self.status_label.pack(side=tk.LEFT, padx=(0, 12), pady=10)
        
        # Main scrollable container
        main_canvas = tk.Canvas(self.root, bg=self.COLORS['bg_dark'], 
                               highlightthickness=0)
        main_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(self.root, orient=tk.VERTICAL, 
                                command=main_canvas.yview,
                                bg=self.COLORS['bg_dark'])
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        main_canvas.configure(yscrollcommand=scrollbar.set)
        
        main_frame = tk.Frame(main_canvas, bg=self.COLORS['bg_dark'])
        canvas_window = main_canvas.create_window((0, 0), window=main_frame, 
                                                 anchor=tk.NW)
        
        def configure_scroll_region(event):
            main_canvas.configure(scrollregion=main_canvas.bbox("all"))
            main_canvas.itemconfig(canvas_window, width=event.width)
        
        main_frame.bind("<Configure>", configure_scroll_region)
        main_canvas.bind("<Configure>", configure_scroll_region)
        
        # Connection Card
        conn_card = self.create_card(main_frame, "Server Connection")
        conn_card.pack(fill=tk.X, padx=30, pady=(0, 20))
        
        # Auto-discovery button
        discovery_frame = tk.Frame(conn_card, bg=self.COLORS['bg_card'])
        discovery_frame.pack(fill=tk.X, padx=25, pady=(0, 10))
        
        self.create_button(discovery_frame, "🔍 Find Servers on Network", 
                          self.auto_discover, width=200).pack(side=tk.LEFT)
        
        self.discovery_label = tk.Label(discovery_frame, text="",
                                       bg=self.COLORS['bg_card'],
                                       fg=self.COLORS['text_secondary'],
                                       font=('Segoe UI', 9))
        self.discovery_label.pack(side=tk.LEFT, padx=10)
        
        self.server_entry = self.create_input(conn_card, "Server URL", 
                                              "https://localhost:8000")
        self.username_entry = self.create_input(conn_card, "Username", 
                                                "admin")
        self.password_entry = self.create_input(conn_card, "Password", 
                                               "", show="●")
        
        # Connect Button - prominent
        btn_frame = tk.Frame(conn_card, bg=self.COLORS['bg_card'])
        btn_frame.pack(pady=(20, 25))
        
        self.connect_btn = self.create_button(btn_frame, "🔗 Connect to Server",
                                             self.connect, primary=True, width=280)
        self.connect_btn.pack()
        
        # Sync Folders Card
        folders_card = self.create_card(main_frame, "Sync Folders")
        folders_card.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 20))
        
        # Folders list
        list_frame = tk.Frame(folders_card, bg=self.COLORS['bg_input'],
                             highlightbackground=self.COLORS['border'],
                             highlightthickness=1)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=25, pady=(0, 15))
        
        list_scroll = tk.Scrollbar(list_frame)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.folders_list = tk.Listbox(list_frame,
                                       bg=self.COLORS['bg_input'],
                                       fg=self.COLORS['text_primary'],
                                       font=('Segoe UI', 10),
                                       selectbackground=self.COLORS['accent'],
                                       selectforeground='white',
                                       relief=tk.FLAT,
                                       highlightthickness=0,
                                       borderwidth=0,
                                       yscrollcommand=list_scroll.set)
        self.folders_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, 
                              padx=12, pady=12)
        list_scroll.config(command=self.folders_list.yview)
        
        # Folder buttons
        folder_btns = tk.Frame(folders_card, bg=self.COLORS['bg_card'])
        folder_btns.pack(pady=(0, 20))
        
        self.create_button(folder_btns, "📁 Add Folder", 
                          self.add_folder, width=150).pack(side=tk.LEFT, padx=5)
        self.create_button(folder_btns, "🗑 Remove", 
                          self.remove_folder, width=150).pack(side=tk.LEFT, padx=5)
        
        # Sync Control Card
        control_card = self.create_card(main_frame, "Synchronization")
        control_card.pack(fill=tk.X, padx=30, pady=(0, 20))
        
        ctrl_frame = tk.Frame(control_card, bg=self.COLORS['bg_card'])
        ctrl_frame.pack(pady=(10, 25))
        
        self.sync_btn = self.create_button(ctrl_frame, "⟳ Sync Now", 
                                          self.sync_now, primary=True, width=200)
        self.sync_btn.pack(side=tk.LEFT, padx=10)
        
        # Auto-sync toggle
        toggle_frame = tk.Frame(ctrl_frame, bg=self.COLORS['bg_input'],
                               highlightbackground=self.COLORS['border'],
                               highlightthickness=1)
        toggle_frame.pack(side=tk.LEFT, padx=10)
        
        self.auto_sync_var = tk.BooleanVar(value=False)
        toggle = tk.Checkbutton(toggle_frame, 
                               text="Auto-sync enabled",
                               variable=self.auto_sync_var,
                               bg=self.COLORS['bg_input'],
                               fg=self.COLORS['text_primary'],
                               selectcolor=self.COLORS['bg_input'],
                               activebackground=self.COLORS['bg_input'],
                               activeforeground=self.COLORS['accent'],
                               font=('Segoe UI', 10),
                               relief=tk.FLAT,
                               command=self.toggle_auto_sync)
        toggle.pack(padx=15, pady=10)
        
        # Activity Log Card
        log_card = self.create_card(main_frame, "Activity Log")
        log_card.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 30))
        
        log_frame = tk.Frame(log_card, bg=self.COLORS['bg_input'],
                            highlightbackground=self.COLORS['border'],
                            highlightthickness=1)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=25, pady=(0, 20))
        
        log_scroll = tk.Scrollbar(log_frame)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(log_frame,
                               bg=self.COLORS['bg_input'],
                               fg=self.COLORS['text_secondary'],
                               font=('Consolas', 9),
                               relief=tk.FLAT,
                               highlightthickness=0,
                               borderwidth=0,
                               height=8,
                               state=tk.DISABLED,
                               yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, 
                          padx=12, pady=12)
        log_scroll.config(command=self.log_text.yview)
        
        # Initial state
        self.set_connected(False)
        self.log("Welcome to BaluHost Sync Client")
        
    def create_card(self, parent, title):
        """Create a beautiful card container."""
        card = tk.Frame(parent, bg=self.COLORS['bg_card'],
                       highlightbackground=self.COLORS['border'],
                       highlightthickness=1)
        
        title_frame = tk.Frame(card, bg=self.COLORS['bg_card'])
        title_frame.pack(fill=tk.X, padx=25, pady=(20, 15))
        
        tk.Label(title_frame, text=title,
                bg=self.COLORS['bg_card'],
                fg=self.COLORS['text_primary'],
                font=('Segoe UI', 13, 'bold')).pack(side=tk.LEFT)
        
        # Separator
        tk.Frame(card, bg=self.COLORS['border'], 
                height=1).pack(fill=tk.X, padx=25, pady=(0, 20))
        
        return card
    
    def create_input(self, parent, label, default="", show=None):
        """Create a beautiful input field."""
        container = tk.Frame(parent, bg=self.COLORS['bg_card'])
        container.pack(fill=tk.X, padx=25, pady=8)
        
        tk.Label(container, text=label,
                bg=self.COLORS['bg_card'],
                fg=self.COLORS['text_primary'],
                font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W, pady=(0, 6))
        
        input_frame = tk.Frame(container, bg=self.COLORS['border'])
        input_frame.pack(fill=tk.X)
        
        entry = tk.Entry(input_frame,
                        bg=self.COLORS['bg_input'],
                        fg=self.COLORS['text_primary'],
                        font=('Segoe UI', 10),
                        relief=tk.FLAT,
                        borderwidth=0,
                        insertbackground=self.COLORS['accent'],
                        show=show)
        entry.insert(0, default)
        entry.pack(fill=tk.X, padx=1, pady=1, ipady=10)
        
        # Focus effects
        def on_focus(e):
            input_frame.config(bg=self.COLORS['border_focus'], 
                             highlightbackground=self.COLORS['border_focus'],
                             highlightthickness=2)
        def off_focus(e):
            input_frame.config(bg=self.COLORS['border'],
                             highlightbackground=self.COLORS['border'],
                             highlightthickness=0)
        
        entry.bind('<FocusIn>', on_focus)
        entry.bind('<FocusOut>', off_focus)
        
        return entry
    
    def create_button(self, parent, text, command, primary=False, width=None):
        """Create a beautiful button."""
        bg = self.COLORS['success'] if primary else self.COLORS['bg_input']
        hover_bg = self.COLORS['success_hover'] if primary else self.COLORS['border']
        fg = 'white' if primary else self.COLORS['text_primary']
        
        config = {
            'text': text,
            'command': command,
            'bg': bg,
            'fg': fg,
            'font': ('Segoe UI', 10, 'bold' if primary else 'normal'),
            'relief': tk.FLAT,
            'cursor': 'hand2',
            'borderwidth': 0,
            'highlightthickness': 0 if primary else 1,
            'highlightbackground': self.COLORS['border'],
            'pady': 12 if primary else 10
        }
        
        if width:
            config['width'] = width // 8  # Approximate width in characters
        
        btn = tk.Button(parent, **config)
        
        # Hover effect
        def on_enter(e):
            btn.config(bg=hover_bg, fg=self.COLORS['accent'] if not primary else 'white')
        def on_leave(e):
            btn.config(bg=bg, fg=fg)
        
        btn.bind('<Enter>', on_enter)
        btn.bind('<Leave>', on_leave)
        
        return btn
    
    def set_connected(self, connected):
        """Update connection status."""
        if connected:
            self.status_dot.itemconfig(self.dot, fill=self.COLORS['success'])
            self.status_label.config(text="Connected", fg=self.COLORS['success'])
            self.connect_btn.config(state=tk.DISABLED)
            self.sync_btn.config(state=tk.NORMAL)
        else:
            self.status_dot.itemconfig(self.dot, fill=self.COLORS['text_secondary'])
            self.status_label.config(text="Not connected", 
                                   fg=self.COLORS['text_secondary'])
            self.connect_btn.config(state=tk.NORMAL)
            self.sync_btn.config(state=tk.DISABLED)
    
    def log(self, message):
        """Add message to activity log."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def connect(self):
        """Connect to server."""
        def do_connect():
            server = self.server_entry.get()
            username = self.username_entry.get()
            password = self.password_entry.get()
            
            self.log(f"Connecting to {server}...")
            
            # Update config
            self.sync_client.config.config['server_url'] = server
            self.sync_client.config.config['username'] = username
            self.sync_client.config.save()
            
            # Try login
            if self.sync_client.login(username, password):
                self.log("✓ Logged in successfully")
                
                # Register device
                if self.sync_client.register_device():
                    self.log("✓ Device registered")
                    self.set_connected(True)
                    
                    # Load folders
                    for folder in self.sync_client.config.config.get('sync_folders', []):
                        self.folders_list.insert(tk.END, folder)
                else:
                    self.log("✗ Device registration failed")
            else:
                self.log("✗ Login failed")
                messagebox.showerror("Error", "Login failed. Check credentials.")
        
        threading.Thread(target=do_connect, daemon=True).start()
    
    def add_folder(self):
        """Add folder to sync."""
        folder = filedialog.askdirectory()
        if folder:
            self.folders_list.insert(tk.END, folder)
            folders = list(self.folders_list.get(0, tk.END))
            self.sync_client.config.config['sync_folders'] = folders
            self.sync_client.config.save()
            self.log(f"Added folder: {folder}")
    
    def remove_folder(self):
        """Remove selected folder."""
        selection = self.folders_list.curselection()
        if selection:
            folder = self.folders_list.get(selection[0])
            self.folders_list.delete(selection[0])
            folders = list(self.folders_list.get(0, tk.END))
            self.sync_client.config.config['sync_folders'] = folders
            self.sync_client.config.save()
            self.log(f"Removed folder: {folder}")
    
    def sync_now(self):
        """Start sync."""
        def do_sync():
            self.log("Starting sync...")
            self.sync_btn.config(state=tk.DISABLED)
            try:
                self.sync_client.sync()
                self.log("✓ Sync completed")
            except Exception as e:
                self.log(f"✗ Sync failed: {e}")
            finally:
                self.sync_btn.config(state=tk.NORMAL)
        
        threading.Thread(target=do_sync, daemon=True).start()
    
    def toggle_auto_sync(self):
        """Toggle auto-sync."""
        enabled = self.auto_sync_var.get()
        self.sync_client.config.config['auto_sync'] = enabled
        self.sync_client.config.save()
        self.log(f"Auto-sync {'enabled' if enabled else 'disabled'}")
    
    def auto_discover(self):
        """Discover BaluHost servers on the network."""
        def do_discover():
            self.discovery_label.config(text="Searching...", 
                                       fg=self.COLORS['accent'])
            self.log("🔍 Searching for servers on network...")
            
            try:
                class ServerFinder(ServiceListener):
                    def __init__(self):
                        self.found_servers = []
                    
                    def add_service(self, zc, type_, name):
                        info = zc.get_service_info(type_, name)
                        if info:
                            addresses = [socket.inet_ntoa(addr) for addr in info.addresses]
                            props = {}
                            if info.properties:
                                for key, value in info.properties.items():
                                    try:
                                        props[key.decode('utf-8')] = value.decode('utf-8')
                                    except:
                                        pass
                            
                            self.found_servers.append({
                                'hostname': props.get('hostname', 'Unknown'),
                                'api_url': props.get('api', f"https://{addresses[0]}:8000"),
                                'addresses': addresses
                            })
                    
                    def remove_service(self, zc, type_, name):
                        pass
                    
                    def update_service(self, zc, type_, name):
                        pass
                
                # Discover servers
                zeroconf = Zeroconf()
                listener = ServerFinder()
                browser = ServiceBrowser(zeroconf, "_baluhost._tcp.local.", listener)
                
                import time
                time.sleep(3)  # Wait for discovery
                
                zeroconf.close()
                
                # Update UI
                if listener.found_servers:
                    server = listener.found_servers[0]  # Use first found server
                    self.server_entry.delete(0, tk.END)
                    self.server_entry.insert(0, server['api_url'])
                    
                    self.discovery_label.config(
                        text=f"✓ Found: {server['hostname']}", 
                        fg=self.COLORS['success']
                    )
                    self.log(f"✓ Found server: {server['hostname']} at {server['api_url']}")
                    
                    if len(listener.found_servers) > 1:
                        self.log(f"  (Found {len(listener.found_servers)} servers total)")
                else:
                    self.discovery_label.config(
                        text="✗ No servers found", 
                        fg=self.COLORS['text_secondary']
                    )
                    self.log("✗ No servers found on network")
                    
            except Exception as e:
                self.discovery_label.config(
                    text="✗ Discovery failed", 
                    fg=self.COLORS['text_secondary']
                )
                self.log(f"✗ Discovery error: {e}")
        
        threading.Thread(target=do_discover, daemon=True).start()
    
    def run(self):
        """Start the GUI."""
        self.root.mainloop()

if __name__ == "__main__":
    app = ModernSyncGUI()
    app.run()
