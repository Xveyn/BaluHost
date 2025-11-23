"""Tests for audit logging integration with disk monitor."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services import disk_monitor


class TestDiskMonitorLogging:
    """Test audit logging for disk monitor operations."""
    
    @pytest.mark.asyncio
    async def test_monitor_start_logs_audit_event(self):
        """Test that starting disk monitor creates audit log entry."""
        with patch('app.services.disk_monitor.get_audit_logger') as mock_audit:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Mock psutil
            with patch('app.services.disk_monitor.psutil'):
                # Start monitoring loop and let it run briefly
                task = asyncio.create_task(disk_monitor._monitor_loop())
                
                # Let it run for a moment
                await asyncio.sleep(0.1)
                
                # Stop the task
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                
                # Verify audit log was called for start
                calls = mock_logger.log_disk_monitor.call_args_list
                start_call = next((c for c in calls if c[1]["action"] == "monitor_started"), None)
                assert start_call is not None
    
    @pytest.mark.asyncio
    async def test_monitor_stop_logs_audit_event(self):
        """Test that stopping disk monitor creates audit log entry."""
        with patch('app.services.disk_monitor.get_audit_logger') as mock_audit:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Mock psutil
            with patch('app.services.disk_monitor.psutil'):
                # Start and stop monitoring loop
                task = asyncio.create_task(disk_monitor._monitor_loop())
                await asyncio.sleep(0.1)
                
                # Cancel the task
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                
                # Verify audit log was called for stop
                calls = mock_logger.log_disk_monitor.call_args_list
                stop_call = next((c for c in calls if c[1]["action"] == "monitor_stopped"), None)
                assert stop_call is not None
    
    @pytest.mark.asyncio
    async def test_monitor_error_logs_audit_event(self):
        """Test that disk monitor errors create audit log entries."""
        with patch('app.services.disk_monitor.get_audit_logger') as mock_audit:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Mock psutil to raise an exception
            with patch('app.services.disk_monitor.psutil.disk_io_counters', side_effect=Exception("Test error")):
                # Start monitoring loop
                task = asyncio.create_task(disk_monitor._monitor_loop())
                
                # Let it run long enough to encounter the error
                await asyncio.sleep(1.5)
                
                # Stop the task
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                
                # Verify audit log was called for error
                calls = mock_logger.log_disk_monitor.call_args_list
                # Look for sampling_error (from _sample_disk_io)
                error_call = next((c for c in calls if c[1]["action"] == "sampling_error"), None)
                assert error_call is not None
                assert error_call[1]["success"] is False
                assert "error_message" in error_call[1]
    
    def test_periodic_summary_logs_audit_event(self):
        """Test that periodic disk activity summary creates audit log entry."""
        with patch('app.services.disk_monitor.get_audit_logger') as mock_audit:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Populate some disk history
            with patch('app.services.disk_monitor._lock'):
                disk_monitor._disk_io_history["PhysicalDrive0"] = [
                    {
                        'timestamp': 1000,
                        'readMbps': 10.5,
                        'writeMbps': 5.2,
                        'readIops': 100,
                        'writeIops': 50,
                        'avgResponseMs': 2.0,
                        'activeTimePercent': 25.0
                    }
                ] * 60  # Simulate 60 samples
            
            # Call log function
            disk_monitor._log_disk_activity()
            
            # Verify audit log was called
            mock_logger.log_disk_monitor.assert_called_once()
            call_kwargs = mock_logger.log_disk_monitor.call_args[1]
            
            assert call_kwargs["action"] == "periodic_summary"
            assert "details" in call_kwargs
            assert "disks" in call_kwargs["details"]
            assert "PhysicalDrive0" in call_kwargs["details"]["disks"]
    
    def test_start_monitoring_logs_failure(self):
        """Test that start_monitoring logs failures."""
        with patch('app.services.disk_monitor.get_audit_logger') as mock_audit:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Mock asyncio.get_event_loop to raise exception
            with patch('asyncio.get_event_loop', side_effect=RuntimeError("No event loop")):
                disk_monitor.start_monitoring()
                
                # Verify audit log was called for failure
                mock_logger.log_disk_monitor.assert_called_once()
                call_kwargs = mock_logger.log_disk_monitor.call_args[1]
                
                assert call_kwargs["action"] == "start_failed"
                assert call_kwargs["success"] is False
                assert "error_message" in call_kwargs
    
    def test_stop_monitoring_logs_manual_stop(self):
        """Test that manually stopping monitoring creates audit log entry."""
        with patch('app.services.disk_monitor.get_audit_logger') as mock_audit:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Create a mock task
            mock_task = MagicMock()
            disk_monitor._monitor_task = mock_task
            
            # Stop monitoring
            disk_monitor.stop_monitoring()
            
            # Verify audit log was called
            mock_logger.log_disk_monitor.assert_called_once()
            call_kwargs = mock_logger.log_disk_monitor.call_args[1]
            
            assert call_kwargs["action"] == "monitor_stopped_manually"
    
    def test_disk_stats_included_in_periodic_summary(self):
        """Test that disk statistics are included in periodic summary."""
        with patch('app.services.disk_monitor.get_audit_logger') as mock_audit:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Populate disk history with varied data
            with patch('app.services.disk_monitor._lock'):
                disk_monitor._disk_io_history["PhysicalDrive0"] = [
                    {
                        'timestamp': i * 1000,
                        'readMbps': 10.0 + i * 0.5,
                        'writeMbps': 5.0 + i * 0.2,
                        'readIops': 100 + i * 10,
                        'writeIops': 50 + i * 5,
                        'avgResponseMs': 2.0,
                        'activeTimePercent': 25.0
                    }
                    for i in range(60)
                ]
            
            # Call log function
            disk_monitor._log_disk_activity()
            
            # Verify statistics are included
            call_kwargs = mock_logger.log_disk_monitor.call_args[1]
            disk_stats = call_kwargs["details"]["disks"]["PhysicalDrive0"]
            
            assert "avg_read_mbps" in disk_stats
            assert "avg_write_mbps" in disk_stats
            assert "max_read_mbps" in disk_stats
            assert "max_write_mbps" in disk_stats
            assert "avg_read_iops" in disk_stats
            assert "avg_write_iops" in disk_stats
            
            # Verify values are calculated correctly
            assert disk_stats["avg_read_mbps"] > 10.0
            assert disk_stats["max_read_mbps"] > disk_stats["avg_read_mbps"]
    
    def test_multiple_disks_logged_in_summary(self):
        """Test that multiple disks are included in periodic summary."""
        with patch('app.services.disk_monitor.get_audit_logger') as mock_audit:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger
            
            # Populate history for multiple disks
            with patch('app.services.disk_monitor._lock'):
                for disk in ["PhysicalDrive0", "PhysicalDrive1"]:
                    disk_monitor._disk_io_history[disk] = [
                        {
                            'timestamp': i * 1000,
                            'readMbps': 10.0,
                            'writeMbps': 5.0,
                            'readIops': 100,
                            'writeIops': 50,
                            'avgResponseMs': 2.0,
                            'activeTimePercent': 25.0
                        }
                        for i in range(60)
                    ]
            
            # Call log function
            disk_monitor._log_disk_activity()
            
            # Verify both disks are included
            call_kwargs = mock_logger.log_disk_monitor.call_args[1]
            disks = call_kwargs["details"]["disks"]
            
            assert "PhysicalDrive0" in disks
            assert "PhysicalDrive1" in disks
    
    def test_audit_logging_respects_dev_mode(self):
        """Test that audit logging respects dev mode setting."""
        with patch('app.services.disk_monitor.get_audit_logger') as mock_audit:
            mock_logger = MagicMock()
            mock_logger.is_enabled.return_value = False
            mock_audit.return_value = mock_logger
            
            # Populate some history
            with patch('app.services.disk_monitor._lock'):
                disk_monitor._disk_io_history["PhysicalDrive0"] = [
                    {
                        'timestamp': 1000,
                        'readMbps': 10.0,
                        'writeMbps': 5.0,
                        'readIops': 100,
                        'writeIops': 50,
                        'avgResponseMs': 2.0,
                        'activeTimePercent': 25.0
                    }
                ] * 60
            
            # Call log function (should still call audit logger)
            disk_monitor._log_disk_activity()
            
            # Verify audit logger was called even in dev mode
            mock_logger.log_disk_monitor.assert_called_once()
