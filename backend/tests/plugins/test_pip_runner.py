"""`_default_pip_runner` must not rely on its caller having validated the input.

The installer injects the runner (``pip_runner=``), and the resolver is a
different module; CodeQL (#104) and a future second caller cannot see that the
strings were already checked. The runner therefore re-checks and ends pip's
option parsing with ``--`` (#773).
"""
from unittest.mock import MagicMock, patch

import pytest

from app.plugins.installer import PipInstallError, _default_pip_runner


@pytest.fixture
def core():
    cv = MagicMock()
    cv.platform = "linux_x86_64"
    cv.python_version = "3.11"
    cv.abi = "cp311"
    return cv


def _run(requirements, tmp_path, core):
    with patch("app.plugins.installer.subprocess.run") as run:
        _default_pip_runner(requirements, tmp_path / "site-packages", core)
    return run


def test_requirements_follow_a_double_dash(tmp_path, core):
    run = _run(["requests==2.31.0", "tzdata"], tmp_path, core)

    cmd = run.call_args.args[0]
    assert "--" in cmd
    assert cmd[cmd.index("--") + 1:] == ["requests==2.31.0", "tzdata"]
    assert "--only-binary=:all:" in cmd[: cmd.index("--")]


def test_no_requirements_means_no_pip_call(tmp_path, core):
    run = _run([], tmp_path, core)

    run.assert_not_called()


@pytest.mark.parametrize("bad", [
    "--no-binary=:all:",
    "-r/etc/passwd",
    "--index-url=http://evil/simple",
    "--",
    "requests==2.31.0\n--no-binary=:all:",
    "pkg @ https://evil.example/pkg-1.0-py3-none-any.whl",
    "pkg @ file:///etc/pkg-1.0-py3-none-any.whl",
    "",
])
def test_unsafe_requirements_never_reach_subprocess(tmp_path, core, bad):
    with patch("app.plugins.installer.subprocess.run") as run:
        with pytest.raises(PipInstallError):
            _default_pip_runner(["requests==2.31.0", bad], tmp_path / "sp", core)

    run.assert_not_called()


def test_a_rejected_requirement_creates_no_target_directory(tmp_path, core):
    target = tmp_path / "sp"
    with patch("app.plugins.installer.subprocess.run"):
        with pytest.raises(PipInstallError):
            _default_pip_runner(["--no-binary=:all:"], target, core)

    assert not target.exists()
