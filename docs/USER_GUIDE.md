# BaluHost User Guide

Welcome to BaluHost! This guide will help you get started with your self-hosted NAS solution.

## 📚 Table of Contents

- [Getting Started](#getting-started)
- [First Login](#first-login)
- [Dashboard Overview](#dashboard-overview)
- [File Management](#file-management)
- [User Management](#user-management-admin-only)
- [RAID Management](#raid-management-admin-only)
- [System Monitoring](#system-monitoring)
- [Activity Logs](#activity-logs)
- [Troubleshooting](#troubleshooting)

## 🚀 Getting Started

### Installation

**Prerequisites:**
- Python 3.11 or higher
- Node.js 18 or higher

**Quick Start:**
```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/BaluHost.git
cd BaluHost

# Start the development environment
python start_dev.py
```

This will:
- Install all dependencies
- Start the backend server (port 3001)
- Start the frontend server (port 5173)
- Create a demo storage area

**Access the application:**
Open your browser and navigate to: `http://localhost:5173`

### Default Credentials

**Administrator Account:**
- Username: `admin`
- Password: `changeme`

**User Account:**
- Username: `user`
- Password: `user123`

⚠️ **Important:** Change these passwords immediately after first login!

## 🔐 First Login

1. Open `http://localhost:5173` in your browser
2. Enter your username and password
3. Click "Sign In"
4. You'll be redirected to the Dashboard

### Changing Your Password

_(Feature coming soon - see Settings page)_

## 📊 Dashboard Overview

The Dashboard provides a real-time overview of your NAS system:

### Storage Overview
- **Total Capacity:** Available storage space
- **Used Space:** Currently used storage
- **Available Space:** Remaining storage
- **Usage Percentage:** Visual indicator of storage utilization

### RAID Status
- **Array Health:** Status of your RAID arrays (healthy, degraded, rebuilding)
- **Number of Arrays:** Active RAID configurations
- **Protection Level:** RAID level (e.g., RAID1, RAID5)

### System Resources
- **CPU Usage:** Current processor utilization
- **Memory Usage:** RAM consumption
- **Active Processes:** Number of running processes

### Recent Activity
- Last 10 file operations
- User actions
- System events

## 📁 File Management

### Navigating Files

**File Browser:**
- Click on folders to navigate into them
- Use the breadcrumb navigation at the top to go back
- Files are displayed with name, size, and modification date

### Uploading Files

**Method 1: Drag & Drop**
1. Drag files from your computer
2. Drop them anywhere in the File Manager area
3. Files will upload automatically
4. A success message will appear when complete

**Method 2: Upload Button**
1. Click the "Upload Files" button
2. Select one or more files from the dialog
3. Click "Open"
4. Files will upload automatically

**Upload Folder:**
1. Click "Upload Folder"
2. Select a folder from the dialog
3. All files in the folder will be uploaded

### Creating Folders

1. Click the "New Folder" button
2. Enter a folder name
3. Click "Create"

### Previewing Files

Click on any file to preview it:

**Supported File Types:**
- **Images:** JPG, PNG, GIF, BMP, SVG, WebP
- **Videos:** MP4, WebM, OGG, MOV, AVI
- **Audio:** MP3, WAV, OGG, FLAC, M4A
- **PDFs:** Opens in-browser PDF viewer
- **Text Files:** TXT, MD, LOG, JSON, XML, etc.

**Preview Features:**
- Full-screen image viewing
- Video player with controls
- Audio player with controls
- Text editor for code files

### Downloading Files

1. Click the download icon (⬇️) next to a file
2. The file will download to your browser's download folder

### Renaming Files/Folders

1. Click the rename icon (✏️) next to a file or folder
2. Enter the new name
3. Click "Rename"

### Deleting Files/Folders

1. Click the delete icon (🗑️) next to a file or folder
2. Confirm the deletion in the dialog
3. The file/folder will be permanently deleted

⚠️ **Warning:** Deleted files cannot be recovered!

### File Permissions

**Ownership:**
- Every file has an owner (the user who uploaded it)
- Only the owner or an admin can modify or delete a file
- Other users cannot see files they don't own

## 👥 User Management (Admin Only)

Administrators can manage user accounts:

### Creating a User

1. Navigate to "User Access" in the sidebar
2. Click "Create User"
3. Fill in:
   - Username (unique)
   - Email address
   - Password
   - Role (Admin or User)
4. Click "Create User"

### Editing a User

1. Click the edit icon (✏️) next to a user
2. Modify the fields
3. Click "Save Changes"

### Deleting a User

1. Click the delete icon (🗑️) next to a user
2. Confirm the deletion
3. User will be removed

⚠️ **Warning:** Deleting a user does NOT delete their files!

### User Roles

**Admin:**
- Full access to all features
- Can manage users
- Can manage RAID arrays
- Can view all files
- Can modify/delete any file

**User:**
- Limited access
- Can only manage own files
- Cannot access RAID management
- Cannot access user management
- Cannot view other users' files

## 💾 RAID Management (Admin Only)

### Viewing RAID Status

Navigate to "RAID Control" to see:
- Active RAID arrays
- Array health status
- Member disks
- Sync status
- Configuration details

### RAID Array States

**Healthy:**
- ✅ All disks functioning normally
- No action required

**Degraded:**
- ⚠️ One or more disks have failed
- Array still functioning but at risk
- **Action Required:** Replace failed disk and rebuild

**Rebuilding:**
- 🔄 Array is recovering from degraded state
- Disk synchronization in progress
- System performance may be affected

**Failed:**
- ❌ Array is not operational
- Data may be at risk
- **Urgent Action Required:** Contact administrator

### RAID Actions (Dev Mode)

In development mode, you can simulate RAID failures for testing:

**Degrade Array:**
1. Click "Degrade" on an array
2. Simulates a disk failure
3. Array enters degraded state

**Rebuild Array:**
1. Click "Rebuild" on a degraded array
2. Simulates disk replacement and rebuild
3. Progress bar shows sync status

**Finalize Rebuild:**
1. Click "Finalize" when rebuild reaches 100%
2. Array returns to healthy state

⚠️ **Production Mode:** Real RAID operations require root access and affect actual hardware!

## 📈 System Monitoring

### System Monitor Page

Navigate to "Disk Monitor" to see:

**CPU Usage:**
- Real-time percentage
- Historical graph (last 60 samples)

**Memory Usage:**
- Current RAM consumption
- Available memory
- Historical trend

**Disk I/O:**
- Read speed (MB/s)
- Write speed (MB/s)
- Real-time activity

**Network Activity:**
- Download speed (Mbps)
- Upload speed (Mbps)
- Live bandwidth monitoring

### Disk Health (SMART)

View detailed disk health information:
- **Temperature:** Current disk temperature
- **Power-On Hours:** Total runtime
- **Power Cycles:** Number of startups
- **Reallocated Sectors:** Bad sector count
- **Health Status:** PASSED/FAILED

⚠️ **Warning:** FAILED status indicates imminent disk failure!

## 📋 Activity Logs

Navigate to "Logging" to view audit logs:

### Log Filters

**Time Range:**
- Last 24 hours
- Last 7 days
- Last 30 days
- Last 90 days

**Action Filter:**
- Upload
- Download
- Delete
- Create Folder
- Rename
- Move

**User Filter:**
- Select specific user
- View all users (admin only)

### Log Details

Each log entry shows:
- **Timestamp:** When action occurred
- **User:** Who performed the action
- **Action:** What was done
- **Resource:** Which file/folder
- **Status:** Success or failure
- **Details:** Additional information

### Log Visualization

**Activity Timeline:**
- Line chart showing actions over time
- Upload/download activity trends
- User activity patterns

**Top Users:**
- Most active users by action count
- Useful for usage monitoring

## 🛠️ Troubleshooting

### Cannot Login

**Problem:** "Invalid credentials" error

**Solutions:**
1. Check username and password (case-sensitive)
2. Try default credentials: `admin` / `changeme`
3. Check backend is running on port 3001
4. Clear browser cache and cookies

### Upload Fails

**Problem:** "Quota exceeded" error

**Solutions:**
1. Check available storage space in Dashboard
2. Delete unnecessary files to free space
3. Administrator can adjust quota settings

**Problem:** "Permission denied" error

**Solutions:**
1. Ensure you're uploading to a folder you own
2. Check you're logged in as the correct user
3. Administrators can access all folders

### File Not Showing

**Problem:** Uploaded file not visible

**Solutions:**
1. Refresh the page (F5)
2. Navigate away and back to File Manager
3. Check you're in the correct folder
4. Check file wasn't filtered out

### Slow Performance

**Problem:** Application feels sluggish

**Solutions:**
1. Check System Monitor for high CPU/RAM usage
2. Close other browser tabs
3. Check if RAID rebuild is in progress (reduces performance)
4. Restart the development server

### Page Not Loading

**Problem:** Blank page or "Cannot connect" error

**Solutions:**
1. Check backend is running: `http://localhost:3001`
2. Check frontend is running: `http://localhost:5173`
3. Run `python start_dev.py` to restart both
4. Check console for errors (F12)

### RAID Status Incorrect

**Problem:** RAID shows wrong state

**Solutions:**
1. Refresh the page
2. In dev mode, this is simulated data
3. In production mode, check actual `mdadm` status

## 🔒 Security Best Practices

### Passwords

✅ **Do:**
- Use strong, unique passwords
- Change default passwords immediately
- Use password manager

❌ **Don't:**
- Share passwords
- Use common passwords (e.g., "password123")
- Write passwords down

### File Access

✅ **Do:**
- Only share files with trusted users
- Regularly review file permissions
- Delete old/unnecessary files

❌ **Don't:**
- Upload sensitive data without encryption
- Share admin credentials
- Leave admin accounts logged in

### System Security

✅ **Do:**
- Keep software updated
- Monitor activity logs regularly
- Back up important data

❌ **Don't:**
- Expose NAS to public internet without proper security
- Disable authentication
- Ignore RAID degraded warnings

## 📞 Getting Help

### Documentation Resources

- **README.md** - Project overview and setup
- **TECHNICAL_DOCUMENTATION.md** - Complete feature documentation
- **ARCHITECTURE.md** - System architecture and design
- **CONTRIBUTING.md** - Development guidelines

### Support Channels

1. **GitHub Issues** - Bug reports and feature requests
2. **GitHub Discussions** - Questions and community support
3. **Documentation** - Check existing docs first

### Reporting Bugs

When reporting bugs, include:
- Description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Screenshots (if applicable)
- Browser and OS version
- Error messages from console (F12)

## 🎓 Tips & Tricks

### Keyboard Shortcuts

_(Coming soon)_

### Organizing Files

**Best Practices:**
- Create folder structure: `/Documents`, `/Media`, `/Photos`
- Use descriptive folder names
- Avoid deeply nested folders (3-4 levels max)
- Keep files organized by type or project

### Efficient Uploading

**Tips:**
- Upload entire folders instead of individual files
- Use drag & drop for speed
- Upload during off-peak hours for large files
- Check storage space before large uploads

### Monitoring Best Practices

**Regular Checks:**
- Daily: Check RAID status
- Weekly: Review disk health (SMART)
- Monthly: Check storage capacity trends
- Quarterly: Review user activity logs

## 🆕 What's New

### Current Version: 0.1.0

**Features:**
- ✅ File upload/download with drag & drop
- ✅ File preview (images, videos, PDFs, text)
- ✅ User management (admin)
- ✅ RAID monitoring and simulation
- ✅ System resource monitoring
- ✅ Audit logging
- ✅ File ownership and permissions

**Coming Soon:**
- 🔜 File sharing with public links
- 🔜 Upload progress indicator
- 🔜 Dark mode
- 🔜 Settings page
- 🔜 Batch file operations
- 🔜 Advanced search

See [TODO.md](../TODO.md) for complete roadmap.

## 📜 License

BaluHost is released under the MIT License.

---

**Need More Help?** Check the [TECHNICAL_DOCUMENTATION.md](../TECHNICAL_DOCUMENTATION.md) for detailed feature documentation!

**Last Updated:** November 2025  
**Version:** 0.1.0
