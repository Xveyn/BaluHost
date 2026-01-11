import pytest

from app.services.raid import _parse_mdstat


def test_parse_simple_resync():
    mdstat = """
Personalities : [raid1]
md0 : active raid1 sdb1[1] sda1[0]
      2096128 blocks super 1.2 [2/2] [UU]
      [==>..................]  resync = 12.3% (259212/2096128) finish=1.2min speed=1040K/sec
unused devices: <none>
"""
    result = _parse_mdstat(mdstat)
    assert "md0" in result
    info = result["md0"]
    assert info.blocks == 2096128
    assert pytest.approx(info.resync_progress, rel=1e-3) == 12.3


def test_parse_multiple_arrays_and_no_resync():
    mdstat = """
Personalities : [raid1]
md0 : active raid1 sdb1[1] sda1[0]
      2096128 blocks super 1.2 [2/2] [UU]

md1 : inactive sdc1[2]
      1048576 blocks super 1.2 [1/0] [_U]
"""
    result = _parse_mdstat(mdstat)
    assert "md0" in result and "md1" in result
    assert result["md0"].blocks == 2096128
    assert result["md0"].resync_progress is None
    assert result["md1"].blocks == 1048576
    assert result["md1"].resync_progress is None


def test_parse_rescue_keywords():
    # Ensure keywords like 'reshape' and 'recover' are recognized
    mdstat = """
md2 : active raid5 sde1 sdf1 sdg1
      4192256 blocks super 1.2
      [==>..................]  reshape = 3.5% (14664/4192256) finish=50.0min speed=1000K/sec
"""
    result = _parse_mdstat(mdstat)
    assert "md2" in result
    assert pytest.approx(result["md2"].resync_progress, rel=1e-3) == 3.5


def test_parse_blocks_with_commas_and_fraction_progress():
    mdstat = """
md0 : active raid1 sdb1[1] sda1[0]
      2,096,128 blocks super 1.2 [2/2] [UU]
      [==>..................]  resync = (259212/2096128) finish=1.2min speed=1040K/sec
unused devices: <none>
"""
    result = _parse_mdstat(mdstat)
    assert "md0" in result
    info = result["md0"]
    assert info.blocks == 2096128
    # fraction 259212/2096128 ~= 12.361%
    assert pytest.approx(info.resync_progress, rel=1e-3) == pytest.approx((259212 / 2096128) * 100.0, rel=1e-6)


def test_parse_no_percent_or_fraction():
    mdstat = """
md3 : active raid1 sdh1 sdi1
      1048576 blocks super 1.2
      [==>..................]  resync ongoing finish=1.2min speed=1040K/sec
"""
    result = _parse_mdstat(mdstat)
    assert "md3" in result
    assert result["md3"].resync_progress is None
