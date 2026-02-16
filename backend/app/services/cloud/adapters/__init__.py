"""Cloud provider adapters."""
from app.services.cloud.adapters.base import CloudAdapter, CloudFile, DownloadResult

__all__ = ["CloudAdapter", "CloudFile", "DownloadResult"]
