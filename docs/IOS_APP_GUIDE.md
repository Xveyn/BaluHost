# BaluHost iOS App Development Guide

## Overview

This guide covers the complete implementation of the **BaluHost iOS mobile client** (BaluMobile), including authentication, VPN integration, file management, and iOS Files app integration.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Setup & Prerequisites](#setup--prerequisites)
3. [Authentication Flow](#authentication-flow)
4. [VPN Integration (WireGuard)](#vpn-integration-wireguard)
5. [File Management](#file-management)
6. [iOS Files App Integration](#ios-files-app-integration)
7. [Camera Backup](#camera-backup)
8. [Background Sync](#background-sync)
9. [Security Best Practices](#security-best-practices)
10. [Testing](#testing)

---

## Architecture Overview

### Technology Stack

- **Language:** Swift 5.9+ (SwiftUI for UI)
- **Minimum iOS:** iOS 15.0+
- **Key Frameworks:**
  - `NetworkExtension` (VPN tunnel)
  - `WireGuardKit` (WireGuard implementation)
  - `FileProvider` (Files app integration)
  - `Photos` (Camera backup)
  - `BackgroundTasks` (Background sync)
  - `Combine` (Reactive programming)

### App Structure

```
BaluMobile/
├── Models/
│   ├── User.swift
│   ├── File.swift
│   ├── VPNConfig.swift
│   └── SyncFolder.swift
├── Services/
│   ├── APIClient.swift
│   ├── AuthService.swift
│   ├── VPNService.swift
│   ├── FileService.swift
│   └── SyncService.swift
├── Views/
│   ├── LoginView.swift
│   ├── QRScannerView.swift
│   ├── FileBrowserView.swift
│   ├── SettingsView.swift
│   └── VPNStatusView.swift
├── Extensions/
│   ├── FileProviderExtension/
│   │   ├── FileProviderExtension.swift
│   │   ├── FileProviderItem.swift
│   │   └── FileProviderEnumerator.swift
│   └── VPNTunnelExtension/
│       └── PacketTunnelProvider.swift
└── Utilities/
    ├── Keychain.swift
    ├── QRCodeScanner.swift
    └── BackgroundTaskManager.swift
```

---

## Setup & Prerequisites

### 1. Xcode Project Setup

```swift
// Package.swift dependencies
dependencies: [
    .package(url: "https://github.com/WireGuard/wireguard-apple.git", from: "1.0.16"),
    .package(url: "https://github.com/Alamofire/Alamofire.git", from: "5.8.0"),
]
```

### 2. App Capabilities

Enable in Xcode → Signing & Capabilities:

- ✅ **Network Extensions** (for VPN)
- ✅ **Keychain Sharing** (for secure credential storage)
- ✅ **Background Modes**:
  - Background fetch
  - Background processing
  - Remote notifications
- ✅ **Personal VPN** (for VPN tunnel)

### 3. Info.plist Permissions

```xml
<key>NSCameraUsageDescription</key>
<string>Scan QR code to connect to your BaluHost server</string>

<key>NSPhotoLibraryUsageDescription</key>
<string>Access your photos for automatic backup to BaluHost</string>

<key>NSPhotoLibraryAddUsageDescription</key>
<string>Download photos from BaluHost to your library</string>

<key>NSLocalNetworkUsageDescription</key>
<string>Connect to your BaluHost server on the local network</string>

<key>NSBonjourServices</key>
<array>
    <string>_baluhost._tcp</string>
</array>
```

---

## Authentication Flow

### 1. QR Code Registration

**Desktop generates QR code via:**  
`POST /api/mobile/token/generate?include_vpn=true&device_name=iPhone%2015%20Pro`

**QR Code Data Structure:**
```json
{
  "token": "reg_abc123...",
  "server": "https://192.168.1.100:3001",
  "expires_at": "2025-12-08T21:15:00Z",
  "vpn_config": "W0ludGVyZmFjZV0KUHJpdm..."  // Base64 WireGuard config
}
```

**Swift Implementation:**

```swift
import AVFoundation
import Vision

class QRCodeScanner: NSObject, AVCaptureMetadataOutputObjectsDelegate {
    private let session = AVCaptureSession()
    var onScanComplete: ((QRCodeData) -> Void)?
    
    struct QRCodeData: Codable {
        let token: String
        let server: String
        let expiresAt: Date
        let vpnConfig: String?
        
        enum CodingKeys: String, CodingKey {
            case token, server
            case expiresAt = "expires_at"
            case vpnConfig = "vpn_config"
        }
    }
    
    func startScanning() {
        guard let device = AVCaptureDevice.default(for: .video),
              let input = try? AVCaptureDeviceInput(device: device) else {
            return
        }
        
        session.addInput(input)
        
        let output = AVCaptureMetadataOutput()
        session.addOutput(output)
        output.setMetadataObjectsDelegate(self, queue: .main)
        output.metadataObjectTypes = [.qr]
        
        session.startRunning()
    }
    
    func metadataOutput(_ output: AVCaptureMetadataOutput,
                       didOutput metadataObjects: [AVMetadataObject],
                       from connection: AVCaptureConnection) {
        guard let object = metadataObjects.first as? AVMetadataMachineReadableCodeObject,
              let stringValue = object.stringValue,
              let data = stringValue.data(using: .utf8),
              let qrData = try? JSONDecoder().decode(QRCodeData.self, from: data) else {
            return
        }
        
        session.stopRunning()
        onScanComplete?(qrData)
    }
}
```

### 2. Device Registration

**API Endpoint:**  
`POST /api/mobile/register`

**Swift Implementation:**

```swift
class AuthService {
    private let baseURL: String
    private let keychain = KeychainManager()
    
    func registerDevice(qrData: QRCodeData, deviceInfo: DeviceInfo) async throws -> AuthResponse {
        let request = MobileDeviceCreate(
            registrationToken: qrData.token,
            deviceName: deviceInfo.name,
            deviceType: "ios",
            deviceModel: deviceInfo.model,
            osVersion: deviceInfo.osVersion,
            appVersion: Bundle.main.appVersion,
            pushToken: try? await getPushToken()
        )
        
        let response: MobileRegistrationResponse = try await APIClient.shared.post(
            "/api/mobile/register",
            body: request
        )
        
        // Save credentials
        try keychain.save(response.accessToken, for: .accessToken)
        try keychain.save(response.refreshToken, for: .refreshToken)
        try keychain.save(response.deviceId, for: .deviceId)
        
        // Setup VPN if config available
        if let vpnConfig = qrData.vpnConfig {
            try await VPNService.shared.importConfiguration(vpnConfig)
        }
        
        return response
    }
}

struct MobileDeviceCreate: Codable {
    let registrationToken: String
    let deviceName: String
    let deviceType: String
    let deviceModel: String
    let osVersion: String
    let appVersion: String
    let pushToken: String?
    
    enum CodingKeys: String, CodingKey {
        case registrationToken = "registration_token"
        case deviceName = "device_name"
        case deviceType = "device_type"
        case deviceModel = "device_model"
        case osVersion = "os_version"
        case appVersion = "app_version"
        case pushToken = "push_token"
    }
}
```

### 3. Token Refresh

**API Endpoint:**  
`POST /api/auth/refresh`

**Swift Implementation:**

```swift
extension AuthService {
    func refreshAccessToken() async throws -> String {
        guard let refreshToken = try? keychain.load(for: .refreshToken) else {
            throw AuthError.noRefreshToken
        }
        
        let response: TokenResponse = try await APIClient.shared.post(
            "/api/auth/refresh",
            body: ["refresh_token": refreshToken]
        )
        
        try keychain.save(response.accessToken, for: .accessToken)
        return response.accessToken
    }
}
```

### 4. Keychain Manager

```swift
import Security

class KeychainManager {
    enum Key: String {
        case accessToken = "com.baluhost.accessToken"
        case refreshToken = "com.baluhost.refreshToken"
        case deviceId = "com.baluhost.deviceId"
        case serverURL = "com.baluhost.serverURL"
    }
    
    func save(_ value: String, for key: Key) throws {
        let data = value.data(using: .utf8)!
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key.rawValue,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock
        ]
        
        SecItemDelete(query as CFDictionary)
        let status = SecItemAdd(query as CFDictionary, nil)
        
        guard status == errSecSuccess else {
            throw KeychainError.saveFailed
        }
    }
    
    func load(for key: Key) throws -> String {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key.rawValue,
            kSecReturnData as String: true
        ]
        
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        
        guard status == errSecSuccess,
              let data = result as? Data,
              let value = String(data: data, encoding: .utf8) else {
            throw KeychainError.loadFailed
        }
        
        return value
    }
}
```

---

## VPN Integration (WireGuard)

### 1. WireGuard Configuration

**API Endpoint (Optional):**  
`POST /api/vpn/generate-config`

**Swift Implementation:**

```swift
import NetworkExtension
import WireGuardKit

class VPNService {
    static let shared = VPNService()
    private let manager = NETunnelProviderManager()
    
    func importConfiguration(_ base64Config: String) throws {
        guard let configData = Data(base64Encoded: base64Config),
              let configString = String(data: configData, encoding: .utf8) else {
            throw VPNError.invalidConfig
        }
        
        let tunnelConfig = try TunnelConfiguration(fromWgQuickConfig: configString)
        try saveConfiguration(tunnelConfig)
    }
    
    private func saveConfiguration(_ config: TunnelConfiguration) throws {
        manager.loadFromPreferences { error in
            if let error = error {
                print("Failed to load preferences: \(error)")
                return
            }
            
            self.manager.localizedDescription = "BaluHost VPN"
            
            let protocolConfig = NETunnelProviderProtocol()
            protocolConfig.providerBundleIdentifier = "com.baluhost.mobile.VPNTunnel"
            protocolConfig.serverAddress = config.peers.first?.endpoint?.stringRepresentation ?? "Unknown"
            
            // Serialize config
            protocolConfig.providerConfiguration = [
                "wgQuickConfig": config.asWgQuickConfig()
            ]
            
            self.manager.protocolConfiguration = protocolConfig
            self.manager.isEnabled = true
            
            self.manager.saveToPreferences { error in
                if let error = error {
                    print("Failed to save VPN config: \(error)")
                } else {
                    print("VPN configuration saved successfully")
                }
            }
        }
    }
    
    func connect() async throws {
        try manager.connection.startVPNTunnel()
    }
    
    func disconnect() {
        manager.connection.stopVPNTunnel()
    }
    
    var isConnected: Bool {
        manager.connection.status == .connected
    }
}
```

### 2. Packet Tunnel Provider

Create **VPNTunnelExtension** target in Xcode.

**PacketTunnelProvider.swift:**

```swift
import NetworkExtension
import WireGuardKit

class PacketTunnelProvider: NEPacketTunnelProvider {
    private var adapter: WireGuardAdapter?
    
    override func startTunnel(options: [String : NSObject]?,
                            completionHandler: @escaping (Error?) -> Void) {
        guard let providerConfig = protocolConfiguration as? NETunnelProviderProtocol,
              let wgConfigString = providerConfig.providerConfiguration?["wgQuickConfig"] as? String,
              let tunnelConfig = try? TunnelConfiguration(fromWgQuickConfig: wgConfigString) else {
            completionHandler(VPNError.invalidConfig)
            return
        }
        
        adapter = WireGuardAdapter(with: self) { logLevel, message in
            print("WireGuard [\(logLevel)]: \(message)")
        }
        
        adapter?.start(tunnelConfiguration: tunnelConfig) { error in
            if let error = error {
                print("Failed to start WireGuard: \(error)")
            }
            completionHandler(error)
        }
    }
    
    override func stopTunnel(with reason: NEProviderStopReason,
                           completionHandler: @escaping () -> Void) {
        adapter?.stop { error in
            if let error = error {
                print("Failed to stop WireGuard: \(error)")
            }
            completionHandler()
        }
    }
}
```

### 3. VPN Status View

```swift
import SwiftUI

struct VPNStatusView: View {
    @StateObject private var vpnService = VPNService.shared
    @State private var isConnected = false
    
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: isConnected ? "lock.shield.fill" : "lock.shield")
                .font(.system(size: 80))
                .foregroundColor(isConnected ? .green : .gray)
            
            Text(isConnected ? "Connected" : "Disconnected")
                .font(.title)
            
            Button(action: toggleVPN) {
                Text(isConnected ? "Disconnect" : "Connect")
                    .frame(width: 200)
                    .padding()
                    .background(isConnected ? Color.red : Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(10)
            }
        }
        .onAppear {
            isConnected = vpnService.isConnected
        }
    }
    
    private func toggleVPN() {
        Task {
            do {
                if isConnected {
                    vpnService.disconnect()
                } else {
                    try await vpnService.connect()
                }
                isConnected = vpnService.isConnected
            } catch {
                print("VPN toggle failed: \(error)")
            }
        }
    }
}
```

---

## File Management

### 1. File Service

```swift
class FileService {
    private let baseURL: String
    private let apiClient = APIClient.shared
    
    func listFiles(path: String = "") async throws -> [FileItem] {
        let response: FileListResponse = try await apiClient.get(
            "/api/files/list",
            parameters: ["path": path]
        )
        return response.items
    }
    
    func uploadFile(_ fileURL: URL, toPath: String) async throws -> FileItem {
        let data = try Data(contentsOf: fileURL)
        let fileName = fileURL.lastPathComponent
        
        let response: FileItem = try await apiClient.upload(
            "/api/files/upload",
            fileName: fileName,
            data: data,
            parameters: ["path": toPath]
        )
        
        return response
    }
    
    func downloadFile(path: String) async throws -> Data {
        return try await apiClient.download(
            "/api/files/download",
            parameters: ["path": path]
        )
    }
    
    func deleteFile(path: String) async throws {
        try await apiClient.delete(
            "/api/files/delete",
            parameters: ["path": path]
        )
    }
}

struct FileItem: Codable, Identifiable {
    let id = UUID()
    let name: String
    let path: String
    let size: Int64
    let isDirectory: Bool
    let modifiedAt: Date
    let owner: String?
    
    enum CodingKeys: String, CodingKey {
        case name, path, size
        case isDirectory = "is_directory"
        case modifiedAt = "modified_at"
        case owner
    }
}
```

### 2. File Browser View

```swift
struct FileBrowserView: View {
    @StateObject private var fileService = FileService()
    @State private var files: [FileItem] = []
    @State private var currentPath = ""
    @State private var isLoading = false
    
    var body: some View {
        NavigationView {
            List {
                ForEach(files) { file in
                    FileRow(file: file)
                        .onTapGesture {
                            if file.isDirectory {
                                navigateToFolder(file.path)
                            }
                        }
                }
            }
            .navigationTitle(currentPath.isEmpty ? "Files" : currentPath)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: uploadFile) {
                        Image(systemName: "plus")
                    }
                }
            }
            .refreshable {
                await loadFiles()
            }
        }
        .task {
            await loadFiles()
        }
    }
    
    private func loadFiles() async {
        isLoading = true
        defer { isLoading = false }
        
        do {
            files = try await fileService.listFiles(path: currentPath)
        } catch {
            print("Failed to load files: \(error)")
        }
    }
    
    private func navigateToFolder(_ path: String) {
        currentPath = path
        Task {
            await loadFiles()
        }
    }
    
    private func uploadFile() {
        // Implement file picker
    }
}

struct FileRow: View {
    let file: FileItem
    
    var body: some View {
        HStack {
            Image(systemName: file.isDirectory ? "folder.fill" : "doc.fill")
                .foregroundColor(file.isDirectory ? .blue : .gray)
            
            VStack(alignment: .leading) {
                Text(file.name)
                    .font(.body)
                
                Text(file.formattedSize)
                    .font(.caption)
                    .foregroundColor(.gray)
            }
            
            Spacer()
        }
        .padding(.vertical, 4)
    }
}

extension FileItem {
    var formattedSize: String {
        ByteCountFormatter.string(fromByteCount: size, countStyle: .file)
    }
}
```

---

## iOS Files App Integration

### 1. File Provider Extension

Create **FileProviderExtension** target in Xcode.

**FileProviderExtension.swift:**

```swift
import FileProvider

class FileProviderExtension: NSFileProviderExtension {
    private let apiClient = APIClient.shared
    
    override func item(for identifier: NSFileProviderItemIdentifier) throws -> NSFileProviderItem {
        if identifier == .rootContainer {
            return FileProviderItem(
                identifier: .rootContainer,
                filename: "BaluHost",
                isDirectory: true
            )
        }
        
        // Fetch item metadata from API
        let path = identifier.rawValue
        let file = try await fileService.getFileMetadata(path: path)
        
        return FileProviderItem(from: file)
    }
    
    override func enumerator(for containerItemIdentifier: NSFileProviderItemIdentifier) throws -> NSFileProviderEnumerator {
        return FileProviderEnumerator(
            containerIdentifier: containerItemIdentifier,
            apiClient: apiClient
        )
    }
    
    override func createItem(basedOn itemTemplate: NSFileProviderItem,
                           fields: NSFileProviderItemFields,
                           contents url: URL?,
                           options: NSFileProviderCreateItemOptions,
                           request: NSFileProviderRequest,
                           completionHandler: @escaping (NSFileProviderItem?, NSFileProviderItemFields, Bool, Error?) -> Void) {
        Task {
            do {
                let uploadedFile = try await fileService.uploadFile(url!, toPath: itemTemplate.parentItemIdentifier.rawValue)
                let item = FileProviderItem(from: uploadedFile)
                completionHandler(item, [], false, nil)
            } catch {
                completionHandler(nil, [], false, error)
            }
        }
    }
}
```

**FileProviderItem.swift:**

```swift
import FileProvider

class FileProviderItem: NSObject, NSFileProviderItem {
    let itemIdentifier: NSFileProviderItemIdentifier
    let parentItemIdentifier: NSFileProviderItemIdentifier
    let filename: String
    let typeIdentifier: String
    let capabilities: NSFileProviderItemCapabilities
    let documentSize: NSNumber?
    let contentModificationDate: Date?
    
    init(identifier: NSFileProviderItemIdentifier,
         filename: String,
         isDirectory: Bool,
         size: Int64? = nil,
         modifiedAt: Date? = nil) {
        self.itemIdentifier = identifier
        self.parentItemIdentifier = .rootContainer
        self.filename = filename
        self.typeIdentifier = isDirectory ? "public.folder" : "public.data"
        self.capabilities = isDirectory ? [.allowsReading, .allowsContentEnumerating] : [.allowsReading, .allowsWriting]
        self.documentSize = size.map { NSNumber(value: $0) }
        self.contentModificationDate = modifiedAt
    }
    
    convenience init(from file: FileItem) {
        self.init(
            identifier: NSFileProviderItemIdentifier(file.path),
            filename: file.name,
            isDirectory: file.isDirectory,
            size: file.size,
            modifiedAt: file.modifiedAt
        )
    }
}
```

### 2. Enable in Info.plist

**FileProviderExtension/Info.plist:**

```xml
<key>NSExtension</key>
<dict>
    <key>NSExtensionPointIdentifier</key>
    <string>com.apple.fileprovider-nonui</string>
    <key>NSExtensionPrincipalClass</key>
    <string>$(PRODUCT_MODULE_NAME).FileProviderExtension</string>
</dict>
```

---

## Camera Backup

### 1. Camera Backup Service

```swift
import Photos

class CameraBackupService {
    private let fileService = FileService()
    
    func performBackup(settings: CameraBackupSettings) async throws {
        let fetchOptions = PHFetchOptions()
        fetchOptions.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        
        let assets = PHAsset.fetchAssets(with: .image, options: fetchOptions)
        
        for i in 0..<assets.count {
            let asset = assets[i]
            
            // Check if already uploaded
            if try await isAlreadyUploaded(asset) {
                continue
            }
            
            // Export and upload
            let imageData = try await exportAsset(asset, quality: settings.quality)
            let fileName = "\(asset.localIdentifier).jpg"
            
            try await fileService.uploadFile(
                data: imageData,
                fileName: fileName,
                toPath: "Camera Backup"
            )
            
            // Mark as uploaded
            try await markAsUploaded(asset)
        }
    }
    
    private func exportAsset(_ asset: PHAsset, quality: ImageQuality) async throws -> Data {
        return try await withCheckedThrowingContinuation { continuation in
            let options = PHImageRequestOptions()
            options.deliveryMode = .highQualityFormat
            options.isNetworkAccessAllowed = true
            
            PHImageManager.default().requestImage(
                for: asset,
                targetSize: quality.targetSize,
                contentMode: .aspectFit,
                options: options
            ) { image, _ in
                guard let image = image,
                      let data = image.jpegData(compressionQuality: quality.compressionQuality) else {
                    continuation.resume(throwing: BackupError.exportFailed)
                    return
                }
                continuation.resume(returning: data)
            }
        }
    }
}

enum ImageQuality {
    case original, high, medium
    
    var targetSize: CGSize {
        switch self {
        case .original: return PHImageManagerMaximumSize
        case .high: return CGSize(width: 2048, height: 2048)
        case .medium: return CGSize(width: 1024, height: 1024)
        }
    }
    
    var compressionQuality: CGFloat {
        switch self {
        case .original: return 1.0
        case .high: return 0.8
        case .medium: return 0.6
        }
    }
}
```

---

## Background Sync

### 1. Background Task Manager

```swift
import BackgroundTasks

class BackgroundTaskManager {
    static let shared = BackgroundTaskManager()
    
    private let taskIdentifier = "com.baluhost.mobile.sync"
    
    func registerTasks() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: taskIdentifier, using: nil) { task in
            self.handleSync(task: task as! BGProcessingTask)
        }
    }
    
    func scheduleSync() {
        let request = BGProcessingTaskRequest(identifier: taskIdentifier)
        request.requiresNetworkConnectivity = true
        request.requiresExternalPower = false
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60) // 15 minutes
        
        do {
            try BGTaskScheduler.shared.submit(request)
        } catch {
            print("Failed to schedule sync: \(error)")
        }
    }
    
    private func handleSync(task: BGProcessingTask) {
        task.expirationHandler = {
            task.setTaskCompleted(success: false)
        }
        
        Task {
            do {
                try await CameraBackupService().performBackup(settings: currentSettings)
                task.setTaskCompleted(success: true)
            } catch {
                task.setTaskCompleted(success: false)
            }
            
            scheduleSync()
        }
    }
}
```

---

## Security Best Practices

### 1. SSL Pinning

```swift
class APIClient {
    private let session: URLSession
    
    init() {
        let configuration = URLSessionConfiguration.default
        let delegate = SSLPinningDelegate()
        self.session = URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
    }
}

class SSLPinningDelegate: NSObject, URLSessionDelegate {
    func urlSession(_ session: URLSession,
                   didReceive challenge: URLAuthenticationChallenge,
                   completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let serverTrust = challenge.protectionSpace.serverTrust else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }
        
        // Validate certificate
        let policies = [SecPolicyCreateSSL(true, challenge.protectionSpace.host as CFString)]
        SecTrustSetPolicies(serverTrust, policies as CFTypeRef)
        
        var error: CFError?
        if SecTrustEvaluateWithError(serverTrust, &error) {
            completionHandler(.useCredential, URLCredential(trust: serverTrust))
        } else {
            completionHandler(.cancelAuthenticationChallenge, nil)
        }
    }
}
```

### 2. Biometric Authentication

```swift
import LocalAuthentication

class BiometricAuthService {
    func authenticate() async throws -> Bool {
        let context = LAContext()
        var error: NSError?
        
        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) else {
            throw BiometricError.notAvailable
        }
        
        return try await context.evaluatePolicy(
            .deviceOwnerAuthenticationWithBiometrics,
            localizedReason: "Unlock BaluHost"
        )
    }
}
```

---

## Testing

### 1. Unit Tests

```swift
import XCTest
@testable import BaluMobile

class AuthServiceTests: XCTestCase {
    var authService: AuthService!
    
    override func setUp() {
        super.setUp()
        authService = AuthService(baseURL: "https://test.local")
    }
    
    func testRegistrationSuccess() async throws {
        let qrData = QRCodeScanner.QRCodeData(
            token: "test_token",
            server: "https://test.local",
            expiresAt: Date().addingTimeInterval(300),
            vpnConfig: nil
        )
        
        let response = try await authService.registerDevice(
            qrData: qrData,
            deviceInfo: .testDevice
        )
        
        XCTAssertNotNil(response.accessToken)
    }
}
```

### 2. UI Tests

```swift
class FileBrowserUITests: XCTestCase {
    func testNavigateToFolder() throws {
        let app = XCUIApplication()
        app.launch()
        
        // Login
        app.buttons["Scan QR Code"].tap()
        // ... scan mock QR
        
        // Navigate to folder
        app.tables.cells.containing(.staticText, identifier: "Documents").tap()
        
        XCTAssert(app.navigationBars["Documents"].exists)
    }
}
```

---

## API Reference

### Endpoints Used by iOS App

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/mobile/token/generate` | Generate QR code (Desktop) |
| `POST` | `/api/mobile/register` | Register device |
| `POST` | `/api/auth/refresh` | Refresh access token |
| `POST` | `/api/vpn/generate-config` | Generate VPN config (optional) |
| `GET` | `/api/files/list` | List files |
| `POST` | `/api/files/upload` | Upload file |
| `GET` | `/api/files/download` | Download file |
| `DELETE` | `/api/files/delete` | Delete file |
| `GET` | `/api/mobile/camera/settings/{device_id}` | Get camera backup settings |
| `PUT` | `/api/mobile/camera/settings/{device_id}` | Update settings |

---

## Resources

- **WireGuard Apple:** https://github.com/WireGuard/wireguard-apple
- **Apple FileProvider:** https://developer.apple.com/documentation/fileprovider
- **Background Tasks:** https://developer.apple.com/documentation/backgroundtasks
- **NetworkExtension:** https://developer.apple.com/documentation/networkextension

---

**Last Updated:** December 2025  
**BaluHost Version:** 1.3.0  
**iOS SDK:** iOS 15.0+
