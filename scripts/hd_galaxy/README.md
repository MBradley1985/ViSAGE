# HD isolate prototype

Procedural high-definition render of a single SAGE galaxy, built only from
its catalogue properties. Prototype for an HD button in the Structure tab,
followed by a Gas checkbox (gas overlay off by default).

SAGE has no resolved structure inside a galaxy, so arm patterns, cluster
positions and dust filaments are invented; the global quantities come from
the model. Treat the result as an artist's impression.

## Files

| File | Purpose |
|---|---|
| `model.py` | SAGE properties → recipe (morphology, sizes, luminosities) and the disk-plane maps / point populations |
| `render.py` | Emission + absorption ray-march, tone mapping, AGN, gas overlay (CGM, hot gas, cold streams, wind, jets) |
| `run_prototype.py` | Loader for SAGE26 HDF5 output (all `model_N.hdf5` files) plus a small gallery |
| `grid.py` | Type × stellar-mass grids (`--paired`, `--rvir`, `--inc`, `--out`) |
| `components.py` | Layer-by-layer breakdown for cold-regime and hot-regime galaxies |
| `features.py` | Side-by-side style options for the AGN and nuclear ring |
| `halo.py` | Gas overlay on/off demo |

## Regenerate

```bash
cd scripts/hd_galaxy
O=outputs_v4
python3 grid.py --paired --out $O --inc 0
python3 grid.py --paired --out $O --inc 60
python3 grid.py --paired --out $O --inc 0 --rvir
python3 grid.py --paired --out $O --inc 60 --rvir
python3 components.py --out $O
```

Data are read from `~/Documents/PhD/SAGE26/output/{millennium,microuchuu}`
(z = 0 snapshots 63 and 49). Grid cells Millennium can't fill fall back to
microUchuu.

## Locked configuration

| Element | Setting | Driven by |
|---|---|---|
| Disk vs elliptical | B/T > 0.75 (or > 0.5, hot regime, f_gas < 0.02) | `BulgeMass`, `Regime`, `ColdGas` |
| Size | Shen et al. (2003) size–mass, SAGE radius nudges ±30% | `StellarMass`, `DiskRadius`, `BulgeRadius` |
| Brightness | ∝ (M / 3e10)^0.7, common white point (AGN excluded) | `StellarMass` |
| Old stars | 40% light per unit mass (`OLD_LIGHT`), tinted by Z* | `MetalsStellarMass` |
| Bar | ≤ 8% of M*, rest of the instability bulge is a pseudobulge | `InstabilityBulgeMass` |
| Young stars / clusters | Scale with sSFR / SFR | `SfrDisk` |
| HII regions | Teal-green (Hubble SHO palette), number ∝ H2^0.8 | `H2gas` |
| Dust | Face-on τ from Σ_H2 + 0.4 Σ_HI times Z_cold, on the arms' inner edges | `H2gas`, `H1gas`, `MetalsColdGas` |
| Nuclear ring | Cluster ring + dusty annulus + bar dust lanes (no starburst ring) | `SfrBulge` > 0.05 and > 8% of SFR |
| AGN | Glow nucleus | `QuasarModeBHaccretionMass` > 0 |
| Merger debris | Shells (ellipticals) / tidal tails (disks) < 4 Gyr; stream < 2.5 Gyr | `TimeOfLastMajorMerger`, `TimeOfLastMinorMerger` |
| ICL | Extended envelope, half weight | `IntraClusterStars` |
| CGM (gas overlay) | Three inflow streams + filaments out to Rvir | `CGMgas` |
| Hot gas (gas overlay) | One textured look (core 0.15 Rvir); only opacity varies, 0.13 → 0.20 (cap at log M_hot ≥ 13) | `HotGas`, `Cooling`, `RcoolToRvir` |
| Cold streams in hot haloes | Same generator as the CGM streams | `mdot_stream` > 0 |
| Galactic wind | Biconical plumes along the spin axis | `OutflowRate`, `MassLoading` |
| Radio jets | Jets + lobes in the gas overlay | `Heating` > 10^40 erg/s |
