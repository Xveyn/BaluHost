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
  SetOutPath "$INSTDIR"
  
  ; Copy frontend files
  File /r "dist\*.*"
  
  ; Copy Electron runtime
  File /r "node_modules\electron\dist\*.*"
  
  ; Create backend directory
  CreateDirectory "$INSTDIR\backend"
  File /oname=backend\baludesk-backend.exe "..\backend\build\Release\baludesk-backend.exe"
  
  ; Copy DLLs (if any)
  File /r /x "*.exe" "..\backend\build\Release\*.dll"
  
  ; Create registry entry
  WriteRegStr HKCU "Software\BaluDesk" "Install_Dir" "$INSTDIR"
  
  ; Create uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"
  
  ; Create Start Menu shortcuts
  CreateDirectory "$SMPROGRAMS\BaluDesk"
  CreateShortcut "$SMPROGRAMS\BaluDesk\BaluDesk.lnk" "$INSTDIR\electron.exe" "" "$INSTDIR\resources\app\public\icon.ico" 0
  CreateShortcut "$SMPROGRAMS\BaluDesk\Uninstall.lnk" "$INSTDIR\uninstall.exe"
  
  ; Create Desktop shortcut
  CreateShortcut "$DESKTOP\BaluDesk.lnk" "$INSTDIR\electron.exe" "" "$INSTDIR\resources\app\public\icon.ico" 0
  
  ; Create program files menu entry
  CreateDirectory "$SMPROGRAMS\BaluDesk"
  CreateShortcut "$SMPROGRAMS\BaluDesk\BaluDesk.lnk" "$INSTDIR\electron.exe"

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
