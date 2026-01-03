# BaluDesk - Desktop Sync Client

<div align="center">

![BaluDesk Logo](https://via.placeholder.com/200x200/0ea5e9/ffffff?text=BaluDesk)

**Modern Desktop Client for BaluHost NAS**

[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-blue.svg)](https://github.com/Xveyn/BaluHost)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Planning-red.svg)](TODO.md)

</div>

## 🌟 Overview

BaluDesk is a cross-platform desktop synchronization client for BaluHost NAS, providing seamless background file synchronization with a modern, intuitive GUI.

### Key Features

- 🔄 **Bidirectional Sync**: Real-time synchronization between local folders and BaluHost NAS
- 📁 **Selective Sync**: Choose which folders to synchronize
- 🎯 **Background Operation**: Runs in system tray with minimal resource usage
- ⚡ **High Performance**: Multi-threaded C++ sync engine
- 🔒 **Secure**: Encrypted credentials, HTTPS communication
- 🎨 **Modern UI**: Electron-based interface with React + TypeScript
- 🔔 **Smart Notifications**: Get notified about sync status and conflicts
- ⚙️ **Configurable**: Bandwidth limits, sync intervals, conflict resolution strategies

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────┐
│       Electron Frontend (React)          │
│  • User Interface                        │
│  • System Tray Integration               │
│  • Settings Management                   │
└──────────────┬───────────────────────────┘
               │ IPC (JSON Messages)
┌──────────────┴───────────────────────────┐
│      C++ Backend (Sync Engine)           │
│  • Filesystem Watcher                    │
│  • HTTP Client (libcurl)                 │
│  • SQLite Database                       │
│  • Conflict Resolution                   │
└──────────────┬───────────────────────────┘
               │ REST API
┌──────────────┴───────────────────────────┐
│      BaluHost NAS (FastAPI)              │
│  • File Storage                          │
│  • User Management                       │
│  • Sync Endpoints                        │
└──────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Backend Build**: CMake 3.20+, C++17 Compiler, vcpkg dependencies
- **Frontend Build**: Node.js 18+, npm 9+
- **Runtime**: BaluHost NAS instance (v1.0+)

### Development Mode

```bash
# Clone repository
git clone https://github.com/Xveyn/BaluHost.git
cd BaluHost/baludesk

# Quick Start (starts both Frontend and Backend)
python start.py

# Or start components separately:
python start.py --backend   # Only C++ Backend
python start.py --frontend  # Only Electron Frontend
```

### Build from Source

#### 1. Build C++ Backend

```bash
cd backend
mkdir build && cd build

# Configure with vcpkg
cmake .. -DCMAKE_TOOLCHAIN_FILE=[path-to-vcpkg]/scripts/buildsystems/vcpkg.cmake

# Build
cmake --build . --config Release
```

#### 2. Install Frontend Dependencies

```bash
cd ../../frontend
npm install
```

#### 3. Run Development

```bash
# From baludesk root
python start.py
```

The app will start with:
- **Backend**: C++ Sync Engine on stdin/stdout IPC
- **Frontend**: Electron app with Vite dev server (http://localhost:5173)
- **Login**: Use your BaluHost credentials

### Production Build

```bash
cd frontend
npm run build              # Creates production build
npm run package            # Creates installers in dist-electron/
```

---

## 📦 Installation

### Windows
Download `BaluDesk-Setup-x.x.x.exe` from [Releases](https://github.com/Xveyn/BaluHost/releases)

### macOS
Download `BaluDesk-x.x.x.dmg` from [Releases](https://github.com/Xveyn/BaluHost/releases)

### Linux
```bash
# AppImage (Universal)
chmod +x BaluDesk-x.x.x.AppImage
./BaluDesk-x.x.x.AppImage

# Debian/Ubuntu
sudo dpkg -i baludesk_x.x.x_amd64.deb

# Fedora/RHEL
sudo rpm -i baludesk-x.x.x.x86_64.rpm
```

---

## 🎯 Usage

### First Launch

1. **Connect to NAS**
   - Enter your BaluHost server URL (e.g., `https://nas.local:8000`)
   - Login with your credentials

2. **Add Sync Folder**
   - Click "Add Folder" in the dashboard
   - Select local folder
   - Choose remote path on NAS
   - Click "Start Sync"

3. **Configure Settings** (Optional)
   - Bandwidth limits
   - Auto-start on boot
   - Conflict resolution strategy

### System Tray

BaluDesk runs in the system tray with quick access:

- 🟢 **Green**: All synced
- 🔵 **Blue**: Syncing in progress
- 🟡 **Yellow**: Conflict detected
- 🔴 **Red**: Error occurred
- ⚪ **Gray**: Paused

**Right-click menu:**
- Open BaluDesk
- Pause/Resume Sync
- Open Sync Folder
- Settings
- Quit

---

## 🛠️ Technology Stack

### C++ Backend
- **Build**: CMake 3.20+
- **HTTP**: libcurl 8.5+
- **Database**: SQLite 3.40+
- **JSON**: nlohmann/json 3.11+
- **Logging**: spdlog 1.12+
- **Testing**: Google Test 1.14+

### Electron Frontend
- **Framework**: Electron 28
- **UI**: React 18 + TypeScript 5
- **Build**: Vite 5
- **Styling**: Tailwind CSS 3
- **State**: Zustand 4
- **Packaging**: Electron Forge 7

---

## 🔒 Security

- ✅ **Encrypted Credentials**: OS keychain integration (Windows Credential Manager, macOS Keychain, Linux libsecret)
- ✅ **HTTPS Only**: TLS 1.2+ with certificate validation
- ✅ **Secure IPC**: JSON schema validation, sandboxed renderer
- ✅ **Code Signing**: Windows Authenticode, macOS Developer Certificate

---

## 📊 Performance

- **Sync Speed**: Up to 100 MB/s (network dependent)
- **Memory Usage**: ~50-150 MB (idle/active)
- **CPU Usage**: <5% during sync
- **Disk Usage**: Minimal (SQLite metadata only)

---

## 🐛 Known Issues

See [GitHub Issues](https://github.com/Xveyn/BaluHost/issues?q=is%3Aissue+label%3Abaludesk)

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](../CONTRIBUTING.md) first.

### Development Setup

```bash
# Install dependencies
cd baludesk/backend
# Install C++ dependencies (system-specific)

cd ../frontend
npm install

# Run in development mode
npm run dev
```

---

## 📚 Documentation

- [TODO.md](TODO.md) - Development roadmap
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical architecture (coming soon)
- [API.md](API.md) - IPC and REST API documentation (coming soon)
- [BUILD.md](BUILD.md) - Build instructions (coming soon)

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Inspiration**: Dropbox, Google Drive, Syncthing
- **Technologies**: Electron, React, libcurl, SQLite
- **Community**: BaluHost contributors

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/Xveyn/BaluHost/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Xveyn/BaluHost/discussions)
- **Email**: support@baluhost.com (coming soon)

---

<div align="center">
Made with ❤️ by the BaluHost Team
</div>
