from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pyvista as pv

from visage.config import SimConfig
from visage.io.par_reader import parse_par
from visage.io.snapshot_table import SnapshotTable
from visage.parallel.loader import SnapshotLoader
from visage.scene.galaxy_layer import GalaxyLayer
from visage.scene.halo_layer import HaloLayer

# HDF5 field names probed for availability, keyed by the filter UI state name
_OPTIONAL_FIELDS: dict[str, str] = {
    # Already-handled optionals
    "bh_mass": "BlackHoleMass",
    "ics_mass": "IntraClusterStars",
    "ffb_regime": "FFBRegime",
    "cgm_regime": "Regime",
    "central_mvir": "CentralMvir",
    "h2_mass": "H2gas",
    "cgm_gas": "CGMgas",
    "hot_gas": "HotGas",
    "galaxy_id": "GalaxyIndex",
    "central_id": "CentralGalaxyIndex",
    "time_of_infall": "TimeOfInfall",
    # Halo structural (written per-galaxy by SAGE)
    "len_particles": "Len",
    "vmax": "Vmax",
    "concentration": "Concentration",
    "spin": "Spin",
    # Galaxy structural
    "disk_radius": "DiskRadius",
    "bulge_radius": "BulgeRadius",
    "merger_bulge_mass": "MergerBulgeMass",
    "merger_bulge_radius": "MergerBulgeRadius",
    "instability_bulge_mass": "InstabilityBulgeMass",
    "instability_bulge_radius": "InstabilityBulgeRadius",
    # Gas / outflows
    "h1_gas": "H1gas",
    "ejected_mass": "EjectedMass",
    "outflow_rate": "OutflowRate",
    "mass_loading": "MassLoading",
    "cooling": "Cooling",
    "heating": "Heating",
    # SFR components
    "sfr_bulge": "SfrBulge",
    "sfr_disk": "SfrDisk",
    "sfr_bulge_z": "SfrBulgeZ",
    "sfr_disk_z": "SfrDiskZ",
    # Metals
    "metals_cold_gas": "MetalsColdGas",
    "metals_stellar_mass": "MetalsStellarMass",
    "metals_bulge_mass": "MetalsBulgeMass",
    "metals_hot_gas": "MetalsHotGas",
    "metals_ejected_mass": "MetalsEjectedMass",
    "metals_ics": "MetalsIntraClusterStars",
    "metals_cgm_gas": "MetalsCGMgas",
}

# Age availability requires BOTH SFH arrays — checked separately
_AGE_FIELDS = ("SFHMassDisk", "SFHMassBulge")


class Model:
    """A single SAGE simulation, with its own loader, layers, and metadata.

    Multiple Models share a single PyVista plotter (each adds its own actors).
    Visibility is per-model; the Scene owns several of these and decides which
    are rendered.
    """

    def __init__(
        self,
        par_path: str | Path,
        plotter: pv.Plotter,
        loader_kwargs: dict,
    ) -> None:
        self.path: Path = Path(par_path)
        self.name: str = self.path.stem
        self.cfg: SimConfig = parse_par(par_path)
        self.snap_table: SnapshotTable = SnapshotTable(self.cfg.snap_list_path)
        self.loader: SnapshotLoader = SnapshotLoader(
            config=self.cfg,
            snap_table=self.snap_table,
            **loader_kwargs,
        )
        self.halo_layer: HaloLayer = HaloLayer(plotter)
        self.galaxy_layer: GalaxyLayer = GalaxyLayer(plotter)
        self.fields_available: dict[str, bool] = self._detect_fields()
        self._current_snap: int = -1
        self._offset: np.ndarray = np.zeros(3, dtype=np.float64)

    # ------------------------------------------------------------------
    # Field availability detection
    # ------------------------------------------------------------------

    def _detect_fields(self) -> dict[str, bool]:
        """Probe the SAGE HDF5 to see which optional fields exist."""
        out = dict.fromkeys(_OPTIONAL_FIELDS, False)
        out["mean_age"] = False
        try:
            with h5py.File(self.cfg.hdf5_path, "r") as f:
                # Probe the last snapshot — most likely to contain all fields.
                snap_key = f"Snap_{self.snap_table.count - 1}"
                if snap_key not in f:
                    # Fall back to whichever group is present
                    for k in f.keys():
                        if k.startswith("Snap_"):
                            snap_key = k
                            break
                    else:
                        return out
                grp = f[snap_key]
                for ui_key, hdf_field in _OPTIONAL_FIELDS.items():
                    out[ui_key] = hdf_field in grp
                out["mean_age"] = all(k in grp for k in _AGE_FIELDS)
        except Exception:
            pass
        return out

    # ------------------------------------------------------------------
    # Snapshot loading
    # ------------------------------------------------------------------

    def set_snapshot(self, snap_num: int) -> None:
        snap_num = max(0, min(int(snap_num), self.snap_table.count - 1))
        if snap_num == self._current_snap:
            return
        halos, galaxies = self.loader.get(snap_num)
        self.halo_layer.update(halos)
        self.galaxy_layer.update(galaxies)
        self._current_snap = snap_num

    @property
    def current_snap(self) -> int:
        return self._current_snap

    @property
    def snap_count(self) -> int:
        return self.snap_table.count

    @property
    def box_size(self) -> float:
        return self.cfg.box_size

    # ------------------------------------------------------------------
    # Visibility (toggles both layers together)
    # ------------------------------------------------------------------

    @property
    def visible(self) -> bool:
        return self.halo_layer.visible or self.galaxy_layer.visible

    @visible.setter
    def visible(self, v: bool) -> None:
        v = bool(v)
        self.halo_layer.visible = v
        self.galaxy_layer.visible = v

    @property
    def offset(self) -> np.ndarray:
        return self._offset.copy()

    @offset.setter
    def offset(self, v: np.ndarray) -> None:
        self._offset = np.asarray(v, dtype=np.float64)
        f32 = self._offset.astype(np.float32)
        self.halo_layer.set_offset(f32)
        self.galaxy_layer.set_offset(f32)

    def shutdown(self) -> None:
        self.loader.shutdown()
