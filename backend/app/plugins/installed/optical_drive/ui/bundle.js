// bundle_fixed.js
var { React, ui, icons, toast, api, utils } = window.BaluHost;
var { useState, useEffect, useCallback, useMemo } = React;
var { Button, Card, Badge, Modal, Input, Textarea, Select, ProgressBar, EmptyState, Tabs, LoadingOverlay } = ui;
var {
  Disc,
  Download,
  Flame,
  X,
  Music,
  RefreshCw,
  Check,
  AlertTriangle,
  Clock,
  HardDrive,
  Folder,
  FileAudio,
  Zap,
  ArrowBigUp,
  Loader2,
  FolderOpen,
  File,
  FileText,
  FileImage,
  ChevronRight,
  Home,
  ArrowLeft,
  Eye,
  Archive
} = icons;
var { formatBytes } = utils;
var PLUGIN_NAME = "optical_drive";
var pluginApi = {
  baseUrl: `/api/plugins/${PLUGIN_NAME}`,
  getDrives() {
    return api.get(`${this.baseUrl}/drives`);
  },
  getDriveInfo(device) {
    const devicePath = device.replace("/dev/", "");
    return api.get(`${this.baseUrl}/drives/${devicePath}/info`);
  },
  eject(device) {
    const devicePath = device.replace("/dev/", "");
    return api.post(`${this.baseUrl}/drives/${devicePath}/eject`);
  },
  closeTray(device) {
    const devicePath = device.replace("/dev/", "");
    return api.post(`${this.baseUrl}/drives/${devicePath}/close`);
  },
  readIso(device, outputPath) {
    const devicePath = device.replace("/dev/", "");
    return api.post(`${this.baseUrl}/drives/${devicePath}/read/iso`, { output_path: outputPath });
  },
  ripAudio(device, outputDir) {
    const devicePath = device.replace("/dev/", "");
    return api.post(`${this.baseUrl}/drives/${devicePath}/read/audio`, { output_dir: outputDir });
  },
  burnIso(device, isoPath, speed = 0) {
    const devicePath = device.replace("/dev/", "");
    return api.post(`${this.baseUrl}/drives/${devicePath}/burn/iso`, { iso_path: isoPath, speed });
  },
  burnAudio(device, wavFiles, speed = 0) {
    const devicePath = device.replace("/dev/", "");
    return api.post(`${this.baseUrl}/drives/${devicePath}/burn/audio`, { wav_files: wavFiles, speed });
  },
  blankDisc(device, mode = "fast") {
    const devicePath = device.replace("/dev/", "");
    return api.post(`${this.baseUrl}/drives/${devicePath}/blank`, { mode });
  },
  getJobs() {
    return api.get(`${this.baseUrl}/jobs`);
  },
  getJob(jobId) {
    return api.get(`${this.baseUrl}/jobs/${jobId}`);
  },
  cancelJob(jobId) {
    return api.post(`${this.baseUrl}/jobs/${jobId}/cancel`);
  },
  // File Explorer API
  listDiscFiles(device, path = "/") {
    const devicePath = device.replace("/dev/", "");
    const encodedPath = encodeURIComponent(path).replace(/%2F/g, "/");
    if (path === "/" || path === "") {
      return api.get(`${this.baseUrl}/drives/${devicePath}/files`);
    }
    return api.get(`${this.baseUrl}/drives/${devicePath}/files/${encodedPath}`);
  },
  extractFiles(device, paths, destination) {
    const devicePath = device.replace("/dev/", "");
    return api.post(`${this.baseUrl}/drives/${devicePath}/extract`, { paths, destination });
  },
  previewFile(device, path) {
    const devicePath = device.replace("/dev/", "");
    const encodedPath = encodeURIComponent(path).replace(/%2F/g, "/");
    return api.get(`${this.baseUrl}/drives/${devicePath}/preview/${encodedPath}`);
  },
  // ISO File API
  listIsoFiles(isoPath, path = "/") {
    return api.post(`${this.baseUrl}/iso/list`, { iso_path: isoPath, path });
  },
  extractFromIso(isoPath, paths, destination) {
    return api.post(`${this.baseUrl}/iso/extract`, { iso_path: isoPath, paths, destination });
  },
  previewIsoFile(isoPath, path) {
    return api.post(`${this.baseUrl}/iso/preview`, { iso_path: isoPath, path });
  }
};
var jobTypes = {
  "read_iso": { label: "Reading ISO", Icon: Download },
  "rip_audio": { label: "Ripping Audio", Icon: Music },
  "rip_track": { label: "Ripping Track", Icon: Music },
  "burn_iso": { label: "Burning ISO", Icon: Flame },
  "burn_audio": { label: "Burning Audio CD", Icon: Flame },
  "blank": { label: "Blanking Disc", Icon: RefreshCw }
};
var mediaTypes = {
  "cd_audio": { label: "Audio CD", Icon: Music, color: "info" },
  "cd_data": { label: "Data CD", Icon: HardDrive, color: "success" },
  "dvd_data": { label: "Data DVD", Icon: HardDrive, color: "success" },
  "cd_blank": { label: "Blank CD", Icon: Disc, color: "warning" },
  "dvd_blank": { label: "Blank DVD", Icon: Disc, color: "warning" },
  "bd_data": { label: "Blu-ray", Icon: HardDrive, color: "info" },
  "bd_blank": { label: "Blank BD", Icon: Disc, color: "warning" },
  "none": { label: "No Disc", Icon: Disc, color: "default" },
  "unknown": { label: "Unknown", Icon: AlertTriangle, color: "default" }
};
function PathDialog({ title, description, onConfirm, onCancel, isDirectory, defaultPath }) {
  const [path, setPath] = useState(defaultPath);
  return /* @__PURE__ */ React.createElement(Modal, { isOpen: true, onClose: onCancel, title, size: "md" }, description && /* @__PURE__ */ React.createElement("p", { className: "text-sm text-gray-500 dark:text-gray-400 mb-4" }, description), /* @__PURE__ */ React.createElement("div", { className: "mb-6" }, /* @__PURE__ */ React.createElement(
    Input,
    {
      label: isDirectory ? "Output Directory" : "Output File Path",
      value: path,
      onChange: (e) => setPath(e.target.value),
      placeholder: isDirectory ? "/storage/music" : "/storage/backup.iso"
    }
  )), /* @__PURE__ */ React.createElement("div", { className: "flex justify-end gap-3" }, /* @__PURE__ */ React.createElement(Button, { onClick: onCancel, variant: "secondary" }, "Cancel"), /* @__PURE__ */ React.createElement(Button, { onClick: () => onConfirm(path), variant: "primary", disabled: !path, icon: /* @__PURE__ */ React.createElement(Download, { className: "w-4 h-4" }) }, "Start")));
}
function BurnDialog({ drive, onClose }) {
  const [mode, setMode] = useState("iso");
  const [isoPath, setIsoPath] = useState("");
  const [wavFiles, setWavFiles] = useState("");
  const [speed, setSpeed] = useState("0");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const handleBurn = async () => {
    setIsLoading(true);
    setError(null);
    try {
      if (mode === "iso") {
        await pluginApi.burnIso(drive.device, isoPath, parseInt(speed));
      } else {
        const files = wavFiles.split("\n").map((f) => f.trim()).filter((f) => f);
        await pluginApi.burnAudio(drive.device, files, parseInt(speed));
      }
      toast.success("Burn job started");
      onClose();
    } catch (err) {
      setError(err.message || "Burn failed");
      toast.error("Failed to start burn");
    } finally {
      setIsLoading(false);
    }
  };
  const speedOptions = [
    { value: "0", label: "Auto (Recommended)" },
    { value: "4", label: "4x" },
    { value: "8", label: "8x" },
    { value: "16", label: "16x" },
    { value: "24", label: "24x" }
  ];
  return /* @__PURE__ */ React.createElement(Modal, { isOpen: true, onClose, title: "Burn Disc", size: "md" }, /* @__PURE__ */ React.createElement("div", { className: "mb-4" }, /* @__PURE__ */ React.createElement("label", { className: "block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2" }, "Burn Type"), /* @__PURE__ */ React.createElement("div", { className: "flex gap-2 p-1 bg-gray-100 dark:bg-gray-700 rounded-lg" }, /* @__PURE__ */ React.createElement(
    "button",
    {
      onClick: () => setMode("iso"),
      className: `flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-md text-sm font-medium transition-all ${mode === "iso" ? "bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm" : "text-gray-600 dark:text-gray-400"}`
    },
    /* @__PURE__ */ React.createElement(HardDrive, { className: "w-4 h-4" }),
    " Data (ISO)"
  ), /* @__PURE__ */ React.createElement(
    "button",
    {
      onClick: () => setMode("audio"),
      className: `flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-md text-sm font-medium transition-all ${mode === "audio" ? "bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm" : "text-gray-600 dark:text-gray-400"}`
    },
    /* @__PURE__ */ React.createElement(Music, { className: "w-4 h-4" }),
    " Audio CD"
  ))), mode === "iso" ? /* @__PURE__ */ React.createElement("div", { className: "mb-4" }, /* @__PURE__ */ React.createElement(Input, { label: "ISO File Path", value: isoPath, onChange: (e) => setIsoPath(e.target.value), placeholder: "/storage/backups/image.iso" })) : /* @__PURE__ */ React.createElement("div", { className: "mb-4" }, /* @__PURE__ */ React.createElement("label", { className: "block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2" }, "WAV Files (one per line)"), /* @__PURE__ */ React.createElement(
    "textarea",
    {
      value: wavFiles,
      onChange: (e) => setWavFiles(e.target.value),
      placeholder: "/storage/music/track01.wav\n/storage/music/track02.wav",
      rows: 4,
      className: "w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
    }
  )), /* @__PURE__ */ React.createElement("div", { className: "mb-4" }, /* @__PURE__ */ React.createElement(Select, { label: "Burn Speed", value: speed, onChange: (e) => setSpeed(e.target.value), options: speedOptions })), error && /* @__PURE__ */ React.createElement("div", { className: "mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg text-sm flex items-center gap-2" }, /* @__PURE__ */ React.createElement(AlertTriangle, { className: "w-4 h-4 flex-shrink-0" }), " ", error), /* @__PURE__ */ React.createElement("div", { className: "flex justify-end gap-3" }, /* @__PURE__ */ React.createElement(Button, { onClick: onClose, variant: "secondary", disabled: isLoading }, "Cancel"), /* @__PURE__ */ React.createElement(
    Button,
    {
      onClick: handleBurn,
      variant: "success",
      loading: isLoading,
      disabled: mode === "iso" && !isoPath || mode === "audio" && !wavFiles,
      icon: /* @__PURE__ */ React.createElement(Flame, { className: "w-4 h-4" })
    },
    isLoading ? "Starting..." : "Start Burn"
  )));
}
// File type icon mapping
function getFileIcon(file) {
  if (file.type === "directory") {
    return Folder;
  }
  const ext = file.name.split(".").pop()?.toLowerCase();
  if (["txt", "md", "json", "xml", "log", "csv"].includes(ext)) {
    return FileText;
  }
  if (["jpg", "jpeg", "png", "gif", "bmp", "webp"].includes(ext)) {
    return FileImage;
  }
  if (["wav", "mp3", "flac", "ogg"].includes(ext)) {
    return FileAudio;
  }
  if (["iso", "img"].includes(ext)) {
    return Archive;
  }
  return File;
}

// Check if file can be previewed
function canPreview(file) {
  if (file.type === "directory") return false;
  const ext = file.name.split(".").pop()?.toLowerCase();
  const previewable = ["txt", "md", "json", "xml", "log", "csv", "html", "css", "js", "py", "jpg", "jpeg", "png", "gif", "bmp", "webp"];
  return previewable.includes(ext);
}

// File Preview Component
function FilePreview({ preview, onClose }) {
  const isImage = preview.content_type.startsWith("image/");

  return /* @__PURE__ */ React.createElement(Modal, { isOpen: true, onClose, title: preview.path.split("/").pop(), size: "lg" },
    /* @__PURE__ */ React.createElement("div", { className: "mb-4 flex items-center justify-between text-sm text-gray-500 dark:text-gray-400" },
      /* @__PURE__ */ React.createElement("span", null, preview.content_type),
      /* @__PURE__ */ React.createElement("span", null, formatBytes(preview.size), preview.is_truncated ? " (truncated)" : "")
    ),
    isImage ?
      /* @__PURE__ */ React.createElement("div", { className: "flex justify-center" },
        /* @__PURE__ */ React.createElement("img", {
          src: `data:${preview.content_type};base64,${preview.content}`,
          alt: preview.path,
          className: "max-w-full max-h-96 rounded-lg"
        })
      ) :
      /* @__PURE__ */ React.createElement("pre", { className: "p-4 bg-gray-50 dark:bg-gray-900 rounded-lg overflow-auto max-h-96 text-sm font-mono whitespace-pre-wrap" },
        preview.content
      ),
    /* @__PURE__ */ React.createElement("div", { className: "flex justify-end mt-4" },
      /* @__PURE__ */ React.createElement(Button, { onClick: onClose, variant: "secondary" }, "Close")
    )
  );
}

// Extract Dialog Component
function ExtractDialog({ selectedFiles, totalSize, onExtract, onCancel, isLoading }) {
  const [destination, setDestination] = useState("/storage/extracted");

  return /* @__PURE__ */ React.createElement(Modal, { isOpen: true, onClose: onCancel, title: "Extract Files", size: "md" },
    /* @__PURE__ */ React.createElement("div", { className: "mb-4 p-3 bg-blue-50 dark:bg-blue-900/30 rounded-lg" },
      /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-2 text-blue-700 dark:text-blue-300" },
        /* @__PURE__ */ React.createElement(Download, { className: "w-4 h-4" }),
        /* @__PURE__ */ React.createElement("span", { className: "font-medium" }, selectedFiles.length, " file", selectedFiles.length > 1 ? "s" : "", " selected"),
        /* @__PURE__ */ React.createElement("span", { className: "text-blue-600 dark:text-blue-400" }, "(", formatBytes(totalSize), ")")
      )
    ),
    /* @__PURE__ */ React.createElement("div", { className: "mb-6" },
      /* @__PURE__ */ React.createElement(Input, {
        label: "Destination Directory",
        value: destination,
        onChange: (e) => setDestination(e.target.value),
        placeholder: "/storage/extracted"
      })
    ),
    /* @__PURE__ */ React.createElement("div", { className: "flex justify-end gap-3" },
      /* @__PURE__ */ React.createElement(Button, { onClick: onCancel, variant: "secondary", disabled: isLoading }, "Cancel"),
      /* @__PURE__ */ React.createElement(Button, {
        onClick: () => onExtract(destination),
        variant: "primary",
        loading: isLoading,
        disabled: !destination,
        icon: /* @__PURE__ */ React.createElement(Download, { className: "w-4 h-4" })
      }, isLoading ? "Extracting..." : "Extract")
    )
  );
}

// File Explorer Component
function FileExplorer({ drive, onClose }) {
  const [files, setFiles] = useState([]);
  const [currentPath, setCurrentPath] = useState("/");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [showExtractDialog, setShowExtractDialog] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [preview, setPreview] = useState(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);

  const fetchFiles = useCallback(async (path) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await pluginApi.listDiscFiles(drive.device, path);
      setFiles(response.files || []);
      setCurrentPath(response.current_path || path);
      setSelectedFiles([]);
    } catch (err) {
      setError(err.message || "Failed to load files");
    } finally {
      setIsLoading(false);
    }
  }, [drive.device]);

  useEffect(() => {
    fetchFiles("/");
  }, [fetchFiles]);

  const handleNavigate = (path) => {
    fetchFiles(path);
  };

  const handleFileClick = (file) => {
    if (file.type === "directory") {
      handleNavigate(file.path);
    }
  };

  const handleSelectFile = (file, checked) => {
    if (checked) {
      setSelectedFiles([...selectedFiles, file]);
    } else {
      setSelectedFiles(selectedFiles.filter(f => f.path !== file.path));
    }
  };

  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedFiles([...files]);
    } else {
      setSelectedFiles([]);
    }
  };

  const handlePreview = async (file) => {
    setIsLoadingPreview(true);
    try {
      const response = await pluginApi.previewFile(drive.device, file.path);
      setPreview(response);
    } catch (err) {
      toast.error(err.message || "Failed to load preview");
    } finally {
      setIsLoadingPreview(false);
    }
  };

  const handleExtract = async (destination) => {
    setIsExtracting(true);
    try {
      const paths = selectedFiles.map(f => f.path);
      await pluginApi.extractFiles(drive.device, paths, destination);
      toast.success("Extraction started");
      setShowExtractDialog(false);
      onClose();
    } catch (err) {
      toast.error(err.message || "Extraction failed");
    } finally {
      setIsExtracting(false);
    }
  };

  const totalSelectedSize = selectedFiles.reduce((sum, f) => sum + (f.size || 0), 0);

  // Breadcrumb parts
  const pathParts = currentPath.split("/").filter(Boolean);

  return /* @__PURE__ */ React.createElement(Modal, { isOpen: true, onClose, title: "Browse Disc", size: "xl" },
    /* @__PURE__ */ React.createElement("div", { className: "mb-4" },
      /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-1 text-sm" },
        /* @__PURE__ */ React.createElement("button", {
          onClick: () => handleNavigate("/"),
          className: "flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400"
        }, /* @__PURE__ */ React.createElement(Home, { className: "w-4 h-4" })),
        pathParts.map((part, index) => {
          const fullPath = "/" + pathParts.slice(0, index + 1).join("/");
          return /* @__PURE__ */ React.createElement(React.Fragment, { key: fullPath },
            /* @__PURE__ */ React.createElement(ChevronRight, { className: "w-4 h-4 text-gray-400" }),
            /* @__PURE__ */ React.createElement("button", {
              onClick: () => handleNavigate(fullPath),
              className: "px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
            }, part)
          );
        })
      )
    ),
    error && /* @__PURE__ */ React.createElement("div", { className: "mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg flex items-center gap-2" },
      /* @__PURE__ */ React.createElement(AlertTriangle, { className: "w-4 h-4" }),
      error
    ),
    isLoading ? /* @__PURE__ */ React.createElement("div", { className: "flex justify-center py-12" },
      /* @__PURE__ */ React.createElement(Loader2, { className: "w-8 h-8 animate-spin text-blue-500" })
    ) : files.length === 0 ? /* @__PURE__ */ React.createElement(EmptyState, {
      icon: Folder,
      title: "Empty directory",
      description: "This directory contains no files."
    }) : /* @__PURE__ */ React.createElement("div", { className: "border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden" },
      /* @__PURE__ */ React.createElement("div", { className: "bg-gray-50 dark:bg-gray-800 px-4 py-2 border-b border-gray-200 dark:border-gray-700 flex items-center gap-3" },
        /* @__PURE__ */ React.createElement("input", {
          type: "checkbox",
          checked: selectedFiles.length === files.length && files.length > 0,
          onChange: (e) => handleSelectAll(e.target.checked),
          className: "rounded border-gray-300 dark:border-gray-600"
        }),
        /* @__PURE__ */ React.createElement("span", { className: "text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider flex-1" }, "Name"),
        /* @__PURE__ */ React.createElement("span", { className: "text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider w-24 text-right" }, "Size"),
        /* @__PURE__ */ React.createElement("span", { className: "w-20" })
      ),
      /* @__PURE__ */ React.createElement("div", { className: "max-h-80 overflow-y-auto" },
        files.map((file) => {
          const FileIcon = getFileIcon(file);
          const isSelected = selectedFiles.some(f => f.path === file.path);
          const showPreview = canPreview(file);
          return /* @__PURE__ */ React.createElement("div", {
            key: file.path,
            className: `flex items-center gap-3 px-4 py-2 border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 ${isSelected ? "bg-blue-50 dark:bg-blue-900/20" : ""}`
          },
            /* @__PURE__ */ React.createElement("input", {
              type: "checkbox",
              checked: isSelected,
              onChange: (e) => handleSelectFile(file, e.target.checked),
              className: "rounded border-gray-300 dark:border-gray-600"
            }),
            /* @__PURE__ */ React.createElement("button", {
              onClick: () => handleFileClick(file),
              className: "flex items-center gap-2 flex-1 text-left",
              disabled: file.type !== "directory"
            },
              /* @__PURE__ */ React.createElement(FileIcon, {
                className: `w-5 h-5 ${file.type === "directory" ? "text-sky-500" : "text-gray-400"}`
              }),
              /* @__PURE__ */ React.createElement("span", {
                className: `${file.type === "directory" ? "text-gray-900 dark:text-white font-medium hover:text-blue-600 dark:hover:text-blue-400 cursor-pointer" : "text-gray-700 dark:text-gray-300"}`
              }, file.name)
            ),
            /* @__PURE__ */ React.createElement("span", { className: "text-sm text-gray-500 dark:text-gray-400 w-24 text-right" },
              file.type === "directory" ? "-" : formatBytes(file.size)
            ),
            /* @__PURE__ */ React.createElement("div", { className: "w-20 flex justify-end" },
              showPreview && /* @__PURE__ */ React.createElement(Button, {
                onClick: () => handlePreview(file),
                variant: "ghost",
                size: "sm",
                loading: isLoadingPreview,
                icon: /* @__PURE__ */ React.createElement(Eye, { className: "w-4 h-4" })
              })
            )
          );
        })
      )
    ),
    selectedFiles.length > 0 && /* @__PURE__ */ React.createElement("div", { className: "mt-4 flex items-center justify-between p-3 bg-blue-50 dark:bg-blue-900/30 rounded-lg" },
      /* @__PURE__ */ React.createElement("span", { className: "text-sm text-blue-700 dark:text-blue-300" },
        selectedFiles.length, " item", selectedFiles.length > 1 ? "s" : "", " selected (",
        formatBytes(totalSelectedSize), ")"
      ),
      /* @__PURE__ */ React.createElement(Button, {
        onClick: () => setShowExtractDialog(true),
        variant: "primary",
        icon: /* @__PURE__ */ React.createElement(Download, { className: "w-4 h-4" })
      }, "Extract Selected")
    ),
    /* @__PURE__ */ React.createElement("div", { className: "flex justify-end mt-4 gap-3" },
      /* @__PURE__ */ React.createElement(Button, { onClick: onClose, variant: "secondary" }, "Close")
    ),
    showExtractDialog && /* @__PURE__ */ React.createElement(ExtractDialog, {
      selectedFiles,
      totalSize: totalSelectedSize,
      onExtract: handleExtract,
      onCancel: () => setShowExtractDialog(false),
      isLoading: isExtracting
    }),
    preview && /* @__PURE__ */ React.createElement(FilePreview, {
      preview,
      onClose: () => setPreview(null)
    })
  );
}

// ISO Browser Component
function IsoBrowser({ isoPath, onClose }) {
  const [files, setFiles] = useState([]);
  const [currentPath, setCurrentPath] = useState("/");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [showExtractDialog, setShowExtractDialog] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [preview, setPreview] = useState(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);

  const fetchFiles = useCallback(async (path) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await pluginApi.listIsoFiles(isoPath, path);
      setFiles(response.files || []);
      setCurrentPath(response.current_path || path);
      setSelectedFiles([]);
    } catch (err) {
      setError(err.message || "Failed to load files");
    } finally {
      setIsLoading(false);
    }
  }, [isoPath]);

  useEffect(() => {
    fetchFiles("/");
  }, [fetchFiles]);

  const handleNavigate = (path) => {
    fetchFiles(path);
  };

  const handleFileClick = (file) => {
    if (file.type === "directory") {
      handleNavigate(file.path);
    }
  };

  const handleSelectFile = (file, checked) => {
    if (checked) {
      setSelectedFiles([...selectedFiles, file]);
    } else {
      setSelectedFiles(selectedFiles.filter(f => f.path !== file.path));
    }
  };

  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedFiles([...files]);
    } else {
      setSelectedFiles([]);
    }
  };

  const handlePreview = async (file) => {
    setIsLoadingPreview(true);
    try {
      const response = await pluginApi.previewIsoFile(isoPath, file.path);
      setPreview(response);
    } catch (err) {
      toast.error(err.message || "Failed to load preview");
    } finally {
      setIsLoadingPreview(false);
    }
  };

  const handleExtract = async (destination) => {
    setIsExtracting(true);
    try {
      const paths = selectedFiles.map(f => f.path);
      await pluginApi.extractFromIso(isoPath, paths, destination);
      toast.success("Extraction started");
      setShowExtractDialog(false);
      onClose();
    } catch (err) {
      toast.error(err.message || "Extraction failed");
    } finally {
      setIsExtracting(false);
    }
  };

  const totalSelectedSize = selectedFiles.reduce((sum, f) => sum + (f.size || 0), 0);
  const pathParts = currentPath.split("/").filter(Boolean);
  const isoName = isoPath.split("/").pop();

  return /* @__PURE__ */ React.createElement(Modal, { isOpen: true, onClose, title: `Browse: ${isoName}`, size: "xl" },
    /* @__PURE__ */ React.createElement("div", { className: "mb-4" },
      /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-1 text-sm" },
        /* @__PURE__ */ React.createElement("button", {
          onClick: () => handleNavigate("/"),
          className: "flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400"
        }, /* @__PURE__ */ React.createElement(Home, { className: "w-4 h-4" })),
        pathParts.map((part, index) => {
          const fullPath = "/" + pathParts.slice(0, index + 1).join("/");
          return /* @__PURE__ */ React.createElement(React.Fragment, { key: fullPath },
            /* @__PURE__ */ React.createElement(ChevronRight, { className: "w-4 h-4 text-gray-400" }),
            /* @__PURE__ */ React.createElement("button", {
              onClick: () => handleNavigate(fullPath),
              className: "px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
            }, part)
          );
        })
      )
    ),
    error && /* @__PURE__ */ React.createElement("div", { className: "mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg flex items-center gap-2" },
      /* @__PURE__ */ React.createElement(AlertTriangle, { className: "w-4 h-4" }),
      error
    ),
    isLoading ? /* @__PURE__ */ React.createElement("div", { className: "flex justify-center py-12" },
      /* @__PURE__ */ React.createElement(Loader2, { className: "w-8 h-8 animate-spin text-blue-500" })
    ) : files.length === 0 ? /* @__PURE__ */ React.createElement(EmptyState, {
      icon: Folder,
      title: "Empty directory",
      description: "This directory contains no files."
    }) : /* @__PURE__ */ React.createElement("div", { className: "border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden" },
      /* @__PURE__ */ React.createElement("div", { className: "bg-gray-50 dark:bg-gray-800 px-4 py-2 border-b border-gray-200 dark:border-gray-700 flex items-center gap-3" },
        /* @__PURE__ */ React.createElement("input", {
          type: "checkbox",
          checked: selectedFiles.length === files.length && files.length > 0,
          onChange: (e) => handleSelectAll(e.target.checked),
          className: "rounded border-gray-300 dark:border-gray-600"
        }),
        /* @__PURE__ */ React.createElement("span", { className: "text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider flex-1" }, "Name"),
        /* @__PURE__ */ React.createElement("span", { className: "text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider w-24 text-right" }, "Size"),
        /* @__PURE__ */ React.createElement("span", { className: "w-20" })
      ),
      /* @__PURE__ */ React.createElement("div", { className: "max-h-80 overflow-y-auto" },
        files.map((file) => {
          const FileIcon = getFileIcon(file);
          const isSelected = selectedFiles.some(f => f.path === file.path);
          const showPreview = canPreview(file);
          return /* @__PURE__ */ React.createElement("div", {
            key: file.path,
            className: `flex items-center gap-3 px-4 py-2 border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 ${isSelected ? "bg-blue-50 dark:bg-blue-900/20" : ""}`
          },
            /* @__PURE__ */ React.createElement("input", {
              type: "checkbox",
              checked: isSelected,
              onChange: (e) => handleSelectFile(file, e.target.checked),
              className: "rounded border-gray-300 dark:border-gray-600"
            }),
            /* @__PURE__ */ React.createElement("button", {
              onClick: () => handleFileClick(file),
              className: "flex items-center gap-2 flex-1 text-left",
              disabled: file.type !== "directory"
            },
              /* @__PURE__ */ React.createElement(FileIcon, {
                className: `w-5 h-5 ${file.type === "directory" ? "text-sky-500" : "text-gray-400"}`
              }),
              /* @__PURE__ */ React.createElement("span", {
                className: `${file.type === "directory" ? "text-gray-900 dark:text-white font-medium hover:text-blue-600 dark:hover:text-blue-400 cursor-pointer" : "text-gray-700 dark:text-gray-300"}`
              }, file.name)
            ),
            /* @__PURE__ */ React.createElement("span", { className: "text-sm text-gray-500 dark:text-gray-400 w-24 text-right" },
              file.type === "directory" ? "-" : formatBytes(file.size)
            ),
            /* @__PURE__ */ React.createElement("div", { className: "w-20 flex justify-end" },
              showPreview && /* @__PURE__ */ React.createElement(Button, {
                onClick: () => handlePreview(file),
                variant: "ghost",
                size: "sm",
                loading: isLoadingPreview,
                icon: /* @__PURE__ */ React.createElement(Eye, { className: "w-4 h-4" })
              })
            )
          );
        })
      )
    ),
    selectedFiles.length > 0 && /* @__PURE__ */ React.createElement("div", { className: "mt-4 flex items-center justify-between p-3 bg-blue-50 dark:bg-blue-900/30 rounded-lg" },
      /* @__PURE__ */ React.createElement("span", { className: "text-sm text-blue-700 dark:text-blue-300" },
        selectedFiles.length, " item", selectedFiles.length > 1 ? "s" : "", " selected (",
        formatBytes(totalSelectedSize), ")"
      ),
      /* @__PURE__ */ React.createElement(Button, {
        onClick: () => setShowExtractDialog(true),
        variant: "primary",
        icon: /* @__PURE__ */ React.createElement(Download, { className: "w-4 h-4" })
      }, "Extract Selected")
    ),
    /* @__PURE__ */ React.createElement("div", { className: "flex justify-end mt-4 gap-3" },
      /* @__PURE__ */ React.createElement(Button, { onClick: onClose, variant: "secondary" }, "Close")
    ),
    showExtractDialog && /* @__PURE__ */ React.createElement(ExtractDialog, {
      selectedFiles,
      totalSize: totalSelectedSize,
      onExtract: handleExtract,
      onCancel: () => setShowExtractDialog(false),
      isLoading: isExtracting
    }),
    preview && /* @__PURE__ */ React.createElement(FilePreview, {
      preview,
      onClose: () => setPreview(null)
    })
  );
}

// ISO Browser Dialog (for opening ISO files)
function IsoOpenDialog({ onOpen, onCancel }) {
  const [isoPath, setIsoPath] = useState("");

  return /* @__PURE__ */ React.createElement(Modal, { isOpen: true, onClose: onCancel, title: "Open ISO File", size: "md" },
    /* @__PURE__ */ React.createElement("p", { className: "text-sm text-gray-500 dark:text-gray-400 mb-4" },
      "Enter the path to an ISO file on your system to browse its contents."
    ),
    /* @__PURE__ */ React.createElement("div", { className: "mb-6" },
      /* @__PURE__ */ React.createElement(Input, {
        label: "ISO File Path",
        value: isoPath,
        onChange: (e) => setIsoPath(e.target.value),
        placeholder: "/storage/backups/image.iso"
      })
    ),
    /* @__PURE__ */ React.createElement("div", { className: "flex justify-end gap-3" },
      /* @__PURE__ */ React.createElement(Button, { onClick: onCancel, variant: "secondary" }, "Cancel"),
      /* @__PURE__ */ React.createElement(Button, {
        onClick: () => onOpen(isoPath),
        variant: "primary",
        disabled: !isoPath,
        icon: /* @__PURE__ */ React.createElement(FolderOpen, { className: "w-4 h-4" })
      }, "Open")
    )
  );
}

function DriveCard({ drive, onRefresh }) {
  const [isLoading, setIsLoading] = useState(false);
  const [showRipDialog, setShowRipDialog] = useState(false);
  const [showBurnDialog, setShowBurnDialog] = useState(false);
  const [showFileExplorer, setShowFileExplorer] = useState(false);
  const handleArrowBigUp = async () => {
    setIsLoading(true);
    try {
      await pluginApi.eject(drive.device);
      toast.success("Disc ejected");
      onRefresh();
    } catch (error) {
      toast.error("ArrowBigUp failed");
    } finally {
      setIsLoading(false);
    }
  };
  const handleRip = async (outputDir) => {
    setIsLoading(true);
    try {
      if (drive.media_type === "cd_audio") {
        await pluginApi.ripAudio(drive.device, outputDir);
      } else {
        await pluginApi.readIso(drive.device, outputDir + "/disc.iso");
      }
      toast.success("Rip job started");
      setShowRipDialog(false);
      onRefresh();
    } catch (error) {
      toast.error("Rip failed");
    } finally {
      setIsLoading(false);
    }
  };
  const mediaInfo = mediaTypes[drive.media_type] || mediaTypes.unknown;
  return /* @__PURE__ */ React.createElement(Card, { className: "p-5", hover: true }, /* @__PURE__ */ React.createElement("div", { className: "flex items-start justify-between mb-4" }, /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-4" }, /* @__PURE__ */ React.createElement("div", { className: `p-3 rounded-xl ${drive.is_ready ? "bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg shadow-blue-500/25" : "bg-gray-100 dark:bg-gray-700 text-gray-400"}` }, /* @__PURE__ */ React.createElement(Disc, { className: "w-6 h-6" })), /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h3", { className: "font-semibold text-gray-900 dark:text-white text-lg" }, drive.name || "Optical Drive"), /* @__PURE__ */ React.createElement("p", { className: "text-sm text-gray-500 dark:text-gray-400 font-mono" }, drive.device))), /* @__PURE__ */ React.createElement(Badge, { variant: drive.is_ready ? drive.is_blank ? "warning" : "success" : "default", pulse: drive.is_ready && !drive.is_blank }, mediaInfo.label)), drive.is_ready && /* @__PURE__ */ React.createElement("div", { className: "mb-4 p-4 bg-gray-50 dark:bg-gray-900/50 rounded-lg space-y-2" }, drive.media_label && /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-2 text-sm" }, /* @__PURE__ */ React.createElement(Folder, { className: "w-4 h-4 text-gray-400" }), /* @__PURE__ */ React.createElement("span", { className: "text-gray-600 dark:text-gray-400" }, "Label:"), /* @__PURE__ */ React.createElement("span", { className: "font-medium text-gray-900 dark:text-white" }, drive.media_label)), drive.total_tracks && /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-2 text-sm" }, /* @__PURE__ */ React.createElement(Music, { className: "w-4 h-4 text-gray-400" }), /* @__PURE__ */ React.createElement("span", { className: "text-gray-600 dark:text-gray-400" }, "Tracks:"), /* @__PURE__ */ React.createElement("span", { className: "font-medium text-gray-900 dark:text-white" }, drive.total_tracks)), drive.total_size_bytes && /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-2 text-sm" }, /* @__PURE__ */ React.createElement(HardDrive, { className: "w-4 h-4 text-gray-400" }), /* @__PURE__ */ React.createElement("span", { className: "text-gray-600 dark:text-gray-400" }, "Size:"), /* @__PURE__ */ React.createElement("span", { className: "font-medium text-gray-900 dark:text-white" }, formatBytes(drive.total_size_bytes))), drive.is_blank && /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-2 text-sm text-yellow-600 dark:text-yellow-400" }, /* @__PURE__ */ React.createElement(Zap, { className: "w-4 h-4" }), /* @__PURE__ */ React.createElement("span", null, "Ready for burning"))), !drive.is_ready && /* @__PURE__ */ React.createElement("div", { className: "mb-4 p-4 bg-gray-50 dark:bg-gray-900/50 rounded-lg text-center" }, /* @__PURE__ */ React.createElement("p", { className: "text-sm text-gray-500 dark:text-gray-400" }, "Insert a disc to see available options")), /* @__PURE__ */ React.createElement("div", { className: "flex flex-wrap gap-2" }, drive.is_ready && !drive.is_blank && /* @__PURE__ */ React.createElement(
    Button,
    {
      onClick: () => setShowRipDialog(true),
      disabled: isLoading,
      variant: "primary",
      icon: drive.media_type === "cd_audio" ? /* @__PURE__ */ React.createElement(Music, { className: "w-4 h-4" }) : /* @__PURE__ */ React.createElement(Download, { className: "w-4 h-4" })
    },
    drive.media_type === "cd_audio" ? "Rip Audio" : "Copy to ISO"
  ), drive.is_ready && !drive.is_blank && /* @__PURE__ */ React.createElement(Button, { onClick: () => setShowFileExplorer(true), disabled: isLoading, variant: "secondary", icon: /* @__PURE__ */ React.createElement(FolderOpen, { className: "w-4 h-4" }) }, "Browse"), drive.is_blank && drive.can_write && /* @__PURE__ */ React.createElement(Button, { onClick: () => setShowBurnDialog(true), disabled: isLoading, variant: "success", icon: /* @__PURE__ */ React.createElement(Flame, { className: "w-4 h-4" }) }, "Burn Disc"), /* @__PURE__ */ React.createElement(Button, { onClick: handleArrowBigUp, loading: isLoading, variant: "secondary", icon: /* @__PURE__ */ React.createElement(ArrowBigUp, { className: "w-4 h-4" }) }, "Eject")), showFileExplorer && /* @__PURE__ */ React.createElement(FileExplorer, { drive, onClose: () => { setShowFileExplorer(false); onRefresh(); } }), showRipDialog && /* @__PURE__ */ React.createElement(
    PathDialog,
    {
      title: drive.media_type === "cd_audio" ? "Rip Audio CD" : "Copy Disc to ISO",
      description: drive.media_type === "cd_audio" ? "Select output directory for WAV files" : "Select output path for ISO file",
      onConfirm: handleRip,
      onCancel: () => setShowRipDialog(false),
      isDirectory: drive.media_type === "cd_audio",
      defaultPath: "/storage/optical"
    }
  ), showBurnDialog && /* @__PURE__ */ React.createElement(BurnDialog, { drive, onClose: () => {
    setShowBurnDialog(false);
    onRefresh();
  } }));
}
function JobCard({ job, onRefresh }) {
  const [isCancelling, setIsCancelling] = useState(false);
  const handleCancel = async () => {
    setIsCancelling(true);
    try {
      await pluginApi.cancelJob(job.id);
      toast.success("Job cancelled");
      onRefresh();
    } catch (error) {
      toast.error("Cancel failed");
    } finally {
      setIsCancelling(false);
    }
  };
  const jobInfo = jobTypes[job.job_type] || { label: job.job_type, Icon: Disc };
  const JobIcon = jobInfo.Icon;
  const isActive = job.status === "running" || job.status === "pending";
  const statusConfig = {
    "running": { label: "Running", variant: "info", pulse: true },
    "pending": { label: "Pending", variant: "warning", pulse: true },
    "completed": { label: "Completed", variant: "success", pulse: false },
    "failed": { label: "Failed", variant: "danger", pulse: false },
    "cancelled": { label: "Cancelled", variant: "default", pulse: false }
  };
  const statusInfo = statusConfig[job.status] || statusConfig.pending;
  return /* @__PURE__ */ React.createElement(Card, { className: "p-4" }, /* @__PURE__ */ React.createElement("div", { className: "flex items-center justify-between mb-3" }, /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-3" }, /* @__PURE__ */ React.createElement("div", { className: `p-2 rounded-lg ${isActive ? "bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400" : job.status === "completed" ? "bg-green-100 dark:bg-green-900/50 text-green-600 dark:text-green-400" : "bg-gray-100 dark:bg-gray-700 text-gray-500"}` }, /* @__PURE__ */ React.createElement(JobIcon, { className: "w-5 h-5" })), /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h4", { className: "font-medium text-gray-900 dark:text-white" }, jobInfo.label), /* @__PURE__ */ React.createElement("p", { className: "text-xs text-gray-500 dark:text-gray-400 font-mono" }, job.device))), /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-2" }, /* @__PURE__ */ React.createElement(Badge, { variant: statusInfo.variant, pulse: statusInfo.pulse }, statusInfo.label), isActive && /* @__PURE__ */ React.createElement(Button, { onClick: handleCancel, variant: "ghost", size: "sm", loading: isCancelling, icon: /* @__PURE__ */ React.createElement(X, { className: "w-4 h-4" }) }))), isActive && /* @__PURE__ */ React.createElement("div", { className: "mb-3" }, /* @__PURE__ */ React.createElement(ProgressBar, { progress: job.progress_percent, variant: job.status === "running" ? "default" : "warning", animated: true }), /* @__PURE__ */ React.createElement("div", { className: "flex justify-between mt-2 text-xs text-gray-500 dark:text-gray-400" }, /* @__PURE__ */ React.createElement("span", null, job.current_track && job.total_tracks ? `Track ${job.current_track} of ${job.total_tracks}` : "Processing..."), /* @__PURE__ */ React.createElement("span", { className: "font-medium" }, Math.round(job.progress_percent), "%"))), job.status === "failed" && job.error && /* @__PURE__ */ React.createElement("div", { className: "p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg text-sm flex items-start gap-2" }, /* @__PURE__ */ React.createElement(AlertTriangle, { className: "w-4 h-4 flex-shrink-0 mt-0.5" }), /* @__PURE__ */ React.createElement("span", null, job.error)), job.status === "completed" && /* @__PURE__ */ React.createElement("div", { className: "p-3 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-400 rounded-lg text-sm flex items-center gap-2" }, /* @__PURE__ */ React.createElement(Check, { className: "w-4 h-4" }), " Operation completed successfully"), (job.input_path || job.output_path) && /* @__PURE__ */ React.createElement("div", { className: "mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 space-y-1 text-sm" }, job.input_path && /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-2 text-gray-500 dark:text-gray-400" }, /* @__PURE__ */ React.createElement("span", { className: "font-medium" }, "Source:"), /* @__PURE__ */ React.createElement("span", { className: "truncate font-mono text-xs" }, job.input_path)), job.output_path && /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-2 text-gray-500 dark:text-gray-400" }, /* @__PURE__ */ React.createElement("span", { className: "font-medium" }, "Output:"), /* @__PURE__ */ React.createElement("span", { className: "truncate font-mono text-xs" }, job.output_path))));
}
function OpticalDrivePage() {
  const [drives, setDrives] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("drives");
  const [showIsoOpenDialog, setShowIsoOpenDialog] = useState(false);
  const [isoPath, setIsoPath] = useState(null);
  const fetchData = useCallback(async () => {
    try {
      const [drivesResponse, jobsResponse] = await Promise.all([
        pluginApi.getDrives(),
        pluginApi.getJobs()
      ]);
      setDrives(drivesResponse.drives || []);
      setJobs(jobsResponse.jobs || []);
      setError(null);
    } catch (err) {
      setError(err.message || "Failed to load data");
    } finally {
      setIsLoading(false);
    }
  }, []);
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 2e3);
    return () => clearInterval(interval);
  }, [fetchData]);
  const activeJobs = useMemo(() => jobs.filter((j) => j.status === "running" || j.status === "pending"), [jobs]);
  const recentJobs = useMemo(() => jobs.filter((j) => j.status !== "running" && j.status !== "pending").slice(0, 10), [jobs]);
  const tabs = [
    { id: "drives", label: "Drives", icon: Disc, count: drives.length },
    { id: "jobs", label: "Jobs", icon: Clock, count: activeJobs.length || void 0 },
    { id: "iso", label: "ISO Browser", icon: Archive }
  ];
  if (isLoading) {
    return /* @__PURE__ */ React.createElement(LoadingOverlay, { label: "Loading drives..." });
  }
  return /* @__PURE__ */ React.createElement("div", { className: "p-6 max-w-6xl mx-auto" }, /* @__PURE__ */ React.createElement("div", { className: "flex items-center justify-between mb-6" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h1", { className: "text-2xl font-bold text-gray-900 dark:text-white" }, "Optical Drive Manager"), /* @__PURE__ */ React.createElement("p", { className: "text-sm text-gray-500 dark:text-gray-400 mt-1" }, "Rip, burn, and manage your optical media")), /* @__PURE__ */ React.createElement(Button, { onClick: fetchData, variant: "secondary", icon: /* @__PURE__ */ React.createElement(RefreshCw, { className: "w-4 h-4" }) }, "Refresh")), error && /* @__PURE__ */ React.createElement("div", { className: "mb-6 p-4 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-xl flex items-center gap-3" }, /* @__PURE__ */ React.createElement(AlertTriangle, { className: "w-5 h-5 flex-shrink-0" }), /* @__PURE__ */ React.createElement("span", null, error)), activeJobs.length > 0 && /* @__PURE__ */ React.createElement("div", { className: "mb-6 p-4 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-xl" }, /* @__PURE__ */ React.createElement("div", { className: "flex items-center justify-between mb-2" }, /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-2" }, /* @__PURE__ */ React.createElement("div", { className: "w-2 h-2 rounded-full bg-blue-500 animate-pulse" }), /* @__PURE__ */ React.createElement("span", { className: "font-medium text-blue-900 dark:text-blue-100" }, activeJobs.length, " active job", activeJobs.length > 1 ? "s" : "")), /* @__PURE__ */ React.createElement("button", { onClick: () => setActiveTab("jobs"), className: "text-sm text-blue-600 dark:text-blue-400 hover:underline" }, "View all")), activeJobs[0] && /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement(ProgressBar, { progress: activeJobs[0].progress_percent, animated: true }), /* @__PURE__ */ React.createElement("p", { className: "text-xs text-blue-700 dark:text-blue-300 mt-1" }, jobTypes[activeJobs[0].job_type]?.label || activeJobs[0].job_type, " - ", Math.round(activeJobs[0].progress_percent), "%"))), /* @__PURE__ */ React.createElement("div", { className: "mb-6" }, /* @__PURE__ */ React.createElement(Tabs, { tabs, activeTab, onChange: setActiveTab })), activeTab === "drives" && /* @__PURE__ */ React.createElement("div", null, drives.length === 0 ? /* @__PURE__ */ React.createElement(
    EmptyState,
    {
      icon: Disc,
      title: "No optical drives detected",
      description: "Connect an optical drive to your system to get started with ripping and burning discs.",
      action: /* @__PURE__ */ React.createElement(Button, { onClick: fetchData, variant: "secondary", icon: /* @__PURE__ */ React.createElement(RefreshCw, { className: "w-4 h-4" }) }, "Scan for drives")
    }
  ) : /* @__PURE__ */ React.createElement("div", { className: "grid gap-4 md:grid-cols-2" }, drives.map((drive) => /* @__PURE__ */ React.createElement(DriveCard, { key: drive.device, drive, onRefresh: fetchData })))), activeTab === "jobs" && /* @__PURE__ */ React.createElement("div", null, activeJobs.length > 0 && /* @__PURE__ */ React.createElement("div", { className: "mb-6" }, /* @__PURE__ */ React.createElement("h3", { className: "text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3" }, "Active"), /* @__PURE__ */ React.createElement("div", { className: "space-y-3" }, activeJobs.map((job) => /* @__PURE__ */ React.createElement(JobCard, { key: job.id, job, onRefresh: fetchData })))), recentJobs.length > 0 && /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("h3", { className: "text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3" }, "History"), /* @__PURE__ */ React.createElement("div", { className: "space-y-3" }, recentJobs.map((job) => /* @__PURE__ */ React.createElement(JobCard, { key: job.id, job, onRefresh: fetchData })))), jobs.length === 0 && /* @__PURE__ */ React.createElement(EmptyState, { icon: Clock, title: "No jobs yet", description: "Start ripping or burning a disc to see job progress here." })), activeTab === "iso" && /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement(Card, { className: "p-6" }, /* @__PURE__ */ React.createElement("div", { className: "text-center" }, /* @__PURE__ */ React.createElement("div", { className: "mx-auto w-12 h-12 rounded-full bg-purple-100 dark:bg-purple-900/50 flex items-center justify-center mb-4" }, /* @__PURE__ */ React.createElement(Archive, { className: "w-6 h-6 text-purple-600 dark:text-purple-400" })), /* @__PURE__ */ React.createElement("h3", { className: "text-lg font-semibold text-gray-900 dark:text-white mb-2" }, "Browse ISO Files"), /* @__PURE__ */ React.createElement("p", { className: "text-sm text-gray-500 dark:text-gray-400 mb-6" }, "Open ISO files from your storage to browse and extract their contents."), /* @__PURE__ */ React.createElement(Button, { onClick: () => setShowIsoOpenDialog(true), variant: "primary", icon: /* @__PURE__ */ React.createElement(FolderOpen, { className: "w-4 h-4" }) }, "Open ISO File")))), showIsoOpenDialog && /* @__PURE__ */ React.createElement(IsoOpenDialog, { onOpen: (path) => { setIsoPath(path); setShowIsoOpenDialog(false); }, onCancel: () => setShowIsoOpenDialog(false) }), isoPath && /* @__PURE__ */ React.createElement(IsoBrowser, { isoPath, onClose: () => setIsoPath(null) }));
}
function OpticalDriveWidget() {
  const [drives, setDrives] = useState([]);
  const [jobs, setJobs] = useState([]);
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [drivesResponse, jobsResponse] = await Promise.all([
          pluginApi.getDrives(),
          pluginApi.getJobs()
        ]);
        setDrives(drivesResponse.drives || []);
        setJobs(jobsResponse.jobs || []);
      } catch (err) {
        console.error("Failed to fetch optical drive data:", err);
      }
    };
    fetchData();
    const interval = setInterval(fetchData, 5e3);
    return () => clearInterval(interval);
  }, []);
  const activeJobs = jobs.filter((j) => j.status === "running");
  const readyDrives = drives.filter((d) => d.is_ready);
  return /* @__PURE__ */ React.createElement(Card, { className: "p-4" }, /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-3 mb-4" }, /* @__PURE__ */ React.createElement("div", { className: "p-2 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 text-white" }, /* @__PURE__ */ React.createElement(Disc, { className: "w-5 h-5" })), /* @__PURE__ */ React.createElement("h3", { className: "font-semibold text-gray-900 dark:text-white" }, "Optical Drives")), /* @__PURE__ */ React.createElement("div", { className: "space-y-3" }, /* @__PURE__ */ React.createElement("div", { className: "flex items-center justify-between text-sm" }, /* @__PURE__ */ React.createElement("span", { className: "text-gray-500 dark:text-gray-400" }, "Drives"), /* @__PURE__ */ React.createElement("span", { className: "font-medium text-gray-900 dark:text-white" }, drives.length)), readyDrives.length > 0 && /* @__PURE__ */ React.createElement("div", { className: "flex items-center justify-between text-sm" }, /* @__PURE__ */ React.createElement("span", { className: "text-gray-500 dark:text-gray-400" }, "With media"), /* @__PURE__ */ React.createElement(Badge, { variant: "success" }, readyDrives.length)), activeJobs.length > 0 && /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { className: "flex items-center justify-between text-sm mb-2" }, /* @__PURE__ */ React.createElement("span", { className: "text-gray-500 dark:text-gray-400" }, "Active jobs"), /* @__PURE__ */ React.createElement(Badge, { variant: "info", pulse: true }, activeJobs.length)), /* @__PURE__ */ React.createElement(ProgressBar, { progress: activeJobs[0].progress_percent, animated: true }))));
}
window.BaluHostPlugins = window.BaluHostPlugins || {};
window.BaluHostPlugins[PLUGIN_NAME] = {
  routes: { "drives": OpticalDrivePage },
  widgets: { "OpticalDriveWidget": OpticalDriveWidget }
};
var bundle_fixed_default = OpticalDrivePage;
export {
  OpticalDrivePage,
  OpticalDriveWidget,
  bundle_fixed_default as default
};
