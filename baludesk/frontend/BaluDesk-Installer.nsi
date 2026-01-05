; BaluDesk NSIS Installer Script
; 2025-01-05
; Professional Windows Installer

!include "MUI2.nsh"
!include "x64.nsh"

; ============================================================================
; Configuration
; ============================================================================

Name "BaluDesk v1.0.0"
OutFile "dist-electron\BaluDesk-Setup-1.0.0.exe"
InstallDir "$PROGRAMFILES\BaluDesk"
InstallDirRegKey HKCU "Software\BaluDesk" "Install_Dir"

; Request admin privileges
RequestExecutionLevel admin

; ============================================================================
; UI Settings
; ============================================================================

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "German"

; ============================================================================
; Section: Installation
; ============================================================================

Section "Install"
  ; Copy entire Electron runtime
  SetOutPath "$INSTDIR"
  File /r "node_modules\electron\dist\*.*"
  
  ; Copy package.json so Electron can find the app
  File "package.json"
  
  ; Copy start scripts (Windows)
  File "start.bat"
  File "start.ps1"
  File "start.sh"
  
  ; Copy main app files - preserve directory structure
  SetOutPath "$INSTDIR\dist\assets"
  File /r "dist\assets\*"
  
  SetOutPath "$INSTDIR\dist\main"
  File /r "dist\main\*"
  
  SetOutPath "$INSTDIR\dist"
  File "dist\index.html"
  
  ; Create and copy backend
  CreateDirectory "$INSTDIR\backend"
  SetOutPath "$INSTDIR\backend"
  File "..\backend\build\Release\baludesk-backend.exe"
  File /r /x "*.exe" "..\backend\build\Release\*.dll"
  
  ; Create registry entry
  SetOutPath "$INSTDIR"
  WriteRegStr HKCU "Software\BaluDesk" "Install_Dir" "$INSTDIR"
  WriteRegStr HKCU "Software\BaluDesk" "Exe_Path" "$INSTDIR\electron.exe"
  
  ; Create uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"
  
  ; Create Start Menu shortcuts (using start.bat with admin)
  CreateDirectory "$SMPROGRAMS\BaluDesk"
  CreateShortcut "$SMPROGRAMS\BaluDesk\BaluDesk.lnk" "$INSTDIR\start.bat" "" "$INSTDIR\electron.exe" 0
  
  ; Set shortcut to run with admin privileges by writing registry entry
  WriteRegStr HKCU "Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers" "$INSTDIR\start.bat" "RUNASADMIN"
  WriteRegStr HKCU "Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers" "$INSTDIR\start.ps1" "RUNASADMIN"
  
  CreateShortcut "$SMPROGRAMS\BaluDesk\Uninstall.lnk" "$INSTDIR\uninstall.exe"
  
  ; Create Desktop shortcut (using start.bat)
  CreateShortcut "$DESKTOP\BaluDesk.lnk" "$INSTDIR\start.bat" "" "$INSTDIR\electron.exe" 0

SectionEnd

; ============================================================================
; Section: Uninstaller
; ============================================================================

Section "Uninstall"
  ; Remove Start Menu entries
  RMDir /r "$SMPROGRAMS\BaluDesk"
  
  ; Remove Desktop shortcut
  Delete "$DESKTOP\BaluDesk.lnk"
  
  ; Remove application files
  RMDir /r "$INSTDIR"
  
  ; Remove registry entry
  DeleteRegKey /ifempty HKCU "Software\BaluDesk"

SectionEnd

; ============================================================================
; Functions
; ============================================================================

Function .onInit
  ${If} ${RunningX64}
    ; 64-bit Windows
  ${Else}
    MessageBox MB_OK "BaluDesk requires 64-bit Windows"
    Abort
  ${EndIf}
FunctionEnd

Function un.onInit
  MessageBox MB_ICONQUESTION|MB_YESNO "Are you sure you want to uninstall BaluDesk?" IDYES +2
  Abort
FunctionEnd
