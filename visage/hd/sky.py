"""HD galaxies on the sky: a lightcone galaxy's HD model as a survey
camera would record it, for mock images (visage.sed.mock_image).

The model is seen from the observer at the cone's apex, oriented on the
sky (x west, y north, as the mock image's pixel grid), at its angular size
(its physical size over the angular-diameter distance), on the survey's
pixels.  Its three channels stand in for the survey's three bands (reddest
first, as HD's I, V, B); the mock image scales each to the galaxy's own
magnitude in that band and blurs it by the survey's seeing.
"""

from __future__ import annotations

import numpy as np

# Longest side (pixels) a model is ray-marched at; a galaxy larger than
# that on the survey's pixels is rendered at this size and resampled.
MAX_RENDER = 768
# At least this many render pixels across a galaxy (each survey pixel
# averages several, so a small galaxy keeps its overall shape).
MIN_RENDER = 96


def sky_rotation(pos, spin, seed) -> np.ndarray:
    """Galaxy frame -> sky frame (x west, y north, z toward the observer
    at the origin)."""
    from visage.hd.layer import galaxy_basis

    p = np.asarray(pos, float)
    out = p / max(np.linalg.norm(p), 1e-12)
    east = np.cross([0.0, 0.0, 1.0], out)
    if np.linalg.norm(east) < 1e-9:
        east = np.cross([0.0, 1.0, 0.0], out)
    east /= np.linalg.norm(east)
    north = np.cross(out, east)
    return np.vstack([-east, north, -out]) @ galaxy_basis(spin, seed)


def sky_stamp(
    gal,
    spin,
    pos,
    d_a_kpc: float,
    pixel_arcsec: float,
    quality: str = "group",
) -> np.ndarray:
    """(n, n, 3) linear light of galaxy `gal`'s HD model on pixels of
    `pixel_arcsec`, centred on it, rows running north (as the mock
    image's arrays); channels I, V, B."""
    from visage.hd.layer import HDGalaxyLayer
    from visage.hd.raymarch import render

    prep = HDGalaxyLayer.prepare(gal, quality, {"spin": spin})
    rc = prep["rc"]
    px = pixel_arcsec / 206264.8 * d_a_kpc / rc.unit_kpc  # model units
    half = rc.extent * (1.3 if rc.kind == "disk" else 1.0)
    n = int(np.ceil(2 * half / px)) | 1
    ss = max(1, int(np.ceil(MIN_RENDER / n)))
    n_r = min(n * ss, MAX_RENDER)
    lay = render(
        rc,
        prep["maps"],
        prep["pts"],
        R=sky_rotation(pos, spin, rc.seed),
        npix=n_r,
        half_width=n * px / 2,
        threads=4,
    )
    img = lay.total * np.asarray(rc.col_gain)[None, None, :]
    img = np.asarray(img[::-1], float)  # row 0 = south
    if n_r == n * ss:
        img = img.reshape(n, ss, n, ss, 3).sum(axis=(1, 3))
    else:
        from scipy.ndimage import zoom

        img = zoom(img, (n / n_r, n / n_r, 1), order=1)
    # Fade the outer 30% to zero (as the mock image's own profiles), so
    # a stretched image shows no edge where the model's frame ends.
    g = np.arange(n) + 0.5 - n / 2
    r = np.hypot(*np.meshgrid(g, g)) / (n / 2)
    edge = np.clip((r - 0.7) / 0.3, 0.0, 1.0)
    img *= (0.5 * (1 + np.cos(np.pi * edge)))[..., None]
    return np.clip(img, 0.0, None)


def sky_stamp_job(args) -> np.ndarray | None:
    """Pool worker: sky_stamp(*args), None if it fails."""
    try:
        return sky_stamp(*args)
    except Exception:
        return None


def stamps_for_rows(
    galaxies,
    snap_table,
    hubble_h: float,
    omega_m: float,
    rows,
    pixel_arcsec: float,
    d_a_kpc,
    executor=None,
) -> dict:
    """{HDF5 row: sky_stamp} for those rows of a loaded lightcone
    `galaxies` (rows not loaded, e.g. below the resolution cut, are left
    out), built in parallel on `executor` if given."""
    from visage.hd.adapter import (
        prefetch_sfh,
        sage_galaxy_from_snapshot,
        spin_vector,
    )

    raw = np.asarray(galaxies.sage_indices)
    where = {int(r): i for i, r in enumerate(raw)} if len(raw) else {}
    jobs, keys = [], []
    idx = [where.get(int(r)) for r in rows]
    prefetch_sfh(
        galaxies,
        [i for i in idx if i is not None],
        snap_table,
        hubble_h,
        omega_m,
    )
    for r, i, da in zip(rows, idx, d_a_kpc, strict=True):
        if i is None:
            continue
        gal = sage_galaxy_from_snapshot(
            galaxies, i, hubble_h, snap_table, omega_m
        )
        jobs.append(
            (
                gal,
                spin_vector(galaxies, i),
                np.asarray(galaxies.positions[i], float),
                float(da),
                float(pixel_arcsec),
            )
        )
        keys.append(int(r))
    if executor is not None:
        out = list(executor.map(sky_stamp_job, jobs))
    else:
        out = [sky_stamp_job(j) for j in jobs]
    return dict(zip(keys, out, strict=True))
