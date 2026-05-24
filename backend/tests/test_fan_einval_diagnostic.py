"""When pwm write fails, capture driver name + pwm_enable in last_write_error."""
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.power.fan_backend_linux import LinuxFanControlBackend
from app.core.config import get_settings


@pytest.mark.asyncio
async def test_write_failure_captures_diagnostic(tmp_path, monkeypatch):
    d = tmp_path / "sys" / "class" / "hwmon" / "hwmon1"
    d.mkdir(parents=True)
    (d / "name").write_text("amdgpu\n")
    (d / "pwm1").write_text("128\n")
    (d / "fan1_input").write_text("1200\n")
    (d / "pwm1_enable").write_text("2\n")

    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", tmp_path / "sys" / "class" / "hwmon")
    await backend._scan_pwm_fans()

    fan_id = next(iter(backend._fan_cache))

    # Force direct write to fail with OSError(EINVAL) and sudo path to also fail
    def fail_write(self_, value):
        raise OSError(22, "Invalid argument")

    monkeypatch.setattr(Path, "write_text", fail_write)
    with patch("subprocess.run") as srun:
        srun.return_value.returncode = 1
        srun.return_value.stderr = b"Invalid argument"
        ok = await backend.set_pwm(fan_id, 80)
    assert ok is False
    assert backend._fan_cache[fan_id].get("last_write_error") is not None
    err = backend._fan_cache[fan_id]["last_write_error"]
    assert "amdgpu" in err
    assert "pwm_enable=2" in err
