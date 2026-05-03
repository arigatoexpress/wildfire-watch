"""Tests for ml.fire_detection.synth.procedural.

The pure-stdlib value-noise primitive is exercised unconditionally. The
PIL-backed synthesizers are skipped when Pillow is unavailable, matching the
project-wide "lazy imports, tests still pass" rule.
"""

from __future__ import annotations

import importlib.util

import pytest

from ml.fire_detection.synth import procedural


HAS_PIL = importlib.util.find_spec("PIL") is not None


def test_value_noise_2d_is_deterministic() -> None:
    a = procedural.value_noise_2d(32, 24, seed=42, scale=8.0)
    b = procedural.value_noise_2d(32, 24, seed=42, scale=8.0)
    assert a == b


def test_value_noise_2d_seed_changes_grid() -> None:
    a = procedural.value_noise_2d(32, 24, seed=42, scale=8.0)
    b = procedural.value_noise_2d(32, 24, seed=43, scale=8.0)
    assert a != b


def test_value_noise_2d_in_unit_interval() -> None:
    grid = procedural.value_noise_2d(16, 16, seed=1, scale=4.0)
    flat = [v for row in grid for v in row]
    assert min(flat) >= 0.0
    assert max(flat) <= 1.0


def test_perlin_like_2d_is_deterministic() -> None:
    a = procedural.perlin_like_2d(24, 16, seed=7, octaves=3, scale=12.0, persistence=0.5)
    b = procedural.perlin_like_2d(24, 16, seed=7, octaves=3, scale=12.0, persistence=0.5)
    assert a == b


def test_perlin_like_2d_rejects_zero_octaves() -> None:
    with pytest.raises(ValueError):
        procedural.perlin_like_2d(8, 8, seed=0, octaves=0, scale=4.0)


@pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
def test_synthesize_smoke_plume_seed_determinism() -> None:
    a = procedural.synthesize_smoke_plume(64, 64, seed=42, anchor_xy=(32, 60), height=0.6)
    b = procedural.synthesize_smoke_plume(64, 64, seed=42, anchor_xy=(32, 60), height=0.6)
    assert a.tobytes() == b.tobytes()


@pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
def test_synthesize_smoke_plume_seed_changes_pixels() -> None:
    a = procedural.synthesize_smoke_plume(64, 64, seed=42, anchor_xy=(32, 60), height=0.6)
    b = procedural.synthesize_smoke_plume(64, 64, seed=99, anchor_xy=(32, 60), height=0.6)
    assert a.tobytes() != b.tobytes()


@pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
def test_synthesize_smoke_plume_validates_height() -> None:
    with pytest.raises(ValueError):
        procedural.synthesize_smoke_plume(64, 64, seed=0, anchor_xy=(0, 0), height=0.0)
    with pytest.raises(ValueError):
        procedural.synthesize_smoke_plume(64, 64, seed=0, anchor_xy=(0, 0), height=1.5)


@pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
def test_synthesize_smoke_plume_emits_nonzero_alpha() -> None:
    img = procedural.synthesize_smoke_plume(96, 96, seed=42, anchor_xy=(48, 90), height=0.8, density=0.9)
    alpha = img.getchannel("A")
    extrema = alpha.getextrema()
    assert extrema[1] > 0, "smoke plume produced no opaque pixels"


@pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
def test_synthesize_fire_glow_seed_determinism() -> None:
    a = procedural.synthesize_fire_glow(64, 64, seed=42, anchor_xy=(32, 32), scale=0.1)
    b = procedural.synthesize_fire_glow(64, 64, seed=42, anchor_xy=(32, 32), scale=0.1)
    assert a.tobytes() == b.tobytes()


@pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
def test_synthesize_fire_glow_validates_scale() -> None:
    with pytest.raises(ValueError):
        procedural.synthesize_fire_glow(64, 64, seed=0, anchor_xy=(32, 32), scale=0.0)
    with pytest.raises(ValueError):
        procedural.synthesize_fire_glow(64, 64, seed=0, anchor_xy=(32, 32), scale=0.6)


@pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
def test_synthesize_fire_glow_emits_warm_pixels() -> None:
    img = procedural.synthesize_fire_glow(64, 64, seed=1, anchor_xy=(32, 32), scale=0.15).convert("RGBA")
    raw = img.tobytes()
    has_warm = False
    for i in range(0, len(raw), 4):
        r, g, b, a = raw[i], raw[i + 1], raw[i + 2], raw[i + 3]
        if r > 180 and g >= 60 and b < 120 and a > 0:
            has_warm = True
            break
    assert has_warm, "fire glow produced no warm-toned pixels"


@pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
def test_synthesize_thermal_anomaly_seed_determinism() -> None:
    a = procedural.synthesize_thermal_anomaly(48, 48, seed=42, anchor_xy=(24, 24), scale=0.1)
    b = procedural.synthesize_thermal_anomaly(48, 48, seed=42, anchor_xy=(24, 24), scale=0.1)
    assert a.tobytes() == b.tobytes()


@pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
def test_synthesize_thermal_anomaly_validates_scale() -> None:
    with pytest.raises(ValueError):
        procedural.synthesize_thermal_anomaly(48, 48, seed=0, anchor_xy=(24, 24), scale=0.0)
