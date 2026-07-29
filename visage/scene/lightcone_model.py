from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista as pv

from visage.config import SimConfig
from visage.io.halo_reader import HaloSnapshot
from visage.io.lightcone_reader import load_lightcone_snapshot
from visage.io.snapshot_table import SnapshotTable
from visage.scene.galaxy_layer import GalaxyLayer
from visage.scene.halo_layer import HaloLayer
from visage.scene.model import Model, _OPTIONAL_FIELDS


class _LightconeLoader:
    """Minimal SnapshotLoader stand-in — the lightcone is a single static
    cloud, so every 'snapshot' returns the same halos + galaxies.  Scene uses
    this for camera spatial indices, focus masking, and info-panel picking."""

    def __init__(self, halos: HaloSnapshot, galaxies) -> None:
        self._halos = halos
        self._galaxies = galaxies

    def get(self, snap_num: int):
        return self._halos, self._galaxies

    def get_tree(self, snap_num: int):
        return None

    def preload_all(self):
        return []

    def shutdown(self) -> None:
        pass


class _SyntheticSnapTable:
    """SnapshotTable-compatible table derived from the cone's own per-galaxy
    (SnapNum, redshift), used when the SAGE a_list isn't resolvable on disk."""

    def __init__(self, snapnum: np.ndarray, redshift: np.ndarray) -> None:
        n = int(snapnum.max()) + 1 if len(snapnum) else 1
        z = np.zeros(n, dtype=np.float64)
        for s in range(n):
            m = snapnum == s
            z[s] = float(np.median(redshift[m])) if np.any(m) else np.nan
        # Fill gaps so snap_to_z is monotone-ish and never NaN.
        good = ~np.isnan(z)
        if good.any():
            xs = np.where(good)[0]
            z = np.interp(np.arange(n), xs, z[xs])
        else:
            z[:] = 0.0
        self._z = z
        self._a = 1.0 / (1.0 + z)

    @property
    def count(self) -> int:
        return len(self._z)

    @property
    def scale_factors(self) -> np.ndarray:
        return self._a

    @property
    def redshifts(self) -> np.ndarray:
        return self._z

    def snap_to_a(self, snap: int) -> float:
        return float(self._a[max(0, min(snap, self.count - 1))])

    def snap_to_z(self, snap: int) -> float:
        return float(self._z[max(0, min(snap, self.count - 1))])

    def z_to_snap(self, z: float) -> int:
        return int(np.argmin(np.abs(self._z - z)))

    def a_to_snap(self, a: float) -> int:
        return int(np.argmin(np.abs(self._a - a)))

    def label(self, snap: int) -> str:
        return f"Snap {snap}   z = {self.snap_to_z(snap):.3f}"


class LightconeModel(Model):
    """A lightcone rendered through the normal Model/Scene/UI stack.

    Duck-types :class:`~visage.scene.model.Model` so every Explore-mode panel
    works unchanged, but sources its galaxies + host haloes from a flat
    ``cli_lightcone`` HDF5 file instead of per-snapshot SAGE output.  The
    snapshot slider becomes a redshift/time highlight over the full cone
    ("full cone + highlight"): the whole cone stays visible, the selected
    SnapNum shell is brightened and the rest dimmed.
    """

    def __init__(
        self,
        lightcone_path: str | Path,
        plotter: pv.Plotter,
        loader_kwargs: dict,
    ) -> None:
        self.path = Path(lightcone_path)
        self.name = self.path.stem

        lc = load_lightcone_snapshot(
            lightcone_path,
            min_stellar_mass=loader_kwargs.get("min_stellar_mass", 0.0),
            min_halo_mass=loader_kwargs.get("min_halo_mass", 1.0e10),
            max_galaxies=loader_kwargs.get("max_galaxies", None),
        )
        self._lc = lc
        self._snapnum_per_gal = lc.snapnum
        self._snapnum_per_halo = lc.halo_snapnum
        # The slider only spans the snapshots actually present in the cone.
        if len(lc.snapnum):
            self._snap_lo = int(lc.snapnum.min())
            self._snap_hi = int(lc.snapnum.max())
        else:
            self._snap_lo, self._snap_hi = 0, 0

        # cfg: box_size := cone extent so camera/UI spatial defaults are sane.
        self.cfg = SimConfig(
            par_path=self.path,
            box_size=float(lc.box_extent),
            hubble_h=float(lc.hubble_h),
        )

        # snap↔z table: prefer the real SAGE a_list; else synthesize from data.
        if lc.a_list_path and Path(lc.a_list_path).is_file():
            try:
                self.snap_table = SnapshotTable(lc.a_list_path)
            except Exception:
                self.snap_table = _SyntheticSnapTable(lc.snapnum, lc.redshift)
        else:
            self.snap_table = _SyntheticSnapTable(lc.snapnum, lc.redshift)

        self.loader = _LightconeLoader(lc.halos, lc.galaxies)

        self.halo_layer = HaloLayer(plotter)
        self.galaxy_layer = GalaxyLayer(plotter)

        self.fields_available = {
            ui_key: (hdf_field in lc.present_fields)
            for ui_key, hdf_field in _OPTIONAL_FIELDS.items()
        }
        self.fields_available["mean_age"] = False

        self._current_snap = -1
        self._offset = np.zeros(3, dtype=np.float64)

        # Render IDENTICALLY to Explore mode: same GalaxyLayer, same Rvir-sized
        # gaussian splats (scale = 1.0), same structure layers, same colormaps.
        # Galaxies are small at full-cone zoom (the cone is ~10x a box) — the
        # user zooms in to see them exactly as in a box. No scale-up, so the
        # look matches Explore pixel-for-pixel.
        self.galaxy_layer.set_radius_scale(1.0)
        # Always draw the disk/bulge inner layers (Explore shows these only in
        # focus mode) so lightcone galaxies look a little more defined.
        self.galaxy_layer.set_show_inner_layers(True)

        # Load the (static) cone into the layers once.
        self.galaxy_layer.update(lc.galaxies)
        self.halo_layer.update(lc.halos)

    # ── snapshot slider bounds (only the snapshots present in the cone) ──
    @property
    def snap_min(self) -> int:
        return self._snap_lo

    @property
    def snap_max(self) -> int:
        return self._snap_hi

    # The cone is static; the slider is a redshift/time CUT.  "Near-side cut":
    # keep galaxies at redshift ≥ the slider (SnapNum ≤ slider, i.e. farther /
    # higher-z) and remove the nearer part.  Slider at snap_hi = full cone.
    def set_snapshot(self, snap_num: int) -> None:
        snap_num = max(self._snap_lo, min(int(snap_num), self._snap_hi))
        self._current_snap = snap_num
        gkeep = self._snapnum_per_gal <= snap_num
        hkeep = self._snapnum_per_halo <= snap_num
        # None when nothing is cut, so the render path is identical to Explore.
        self.galaxy_layer.set_slice_mask(None if gkeep.all() else gkeep)
        self.halo_layer.set_slice_mask(None if hkeep.all() else hkeep)

    @property
    def bounds(self) -> np.ndarray:
        return self._lc.bounds

    def _detect_fields(self):  # never called (fields set in __init__)
        return self.fields_available
