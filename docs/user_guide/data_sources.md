# Data Sources

## miniMillennium

- Box size: 62.5 Mpc/h
- Snapshots: 64 (z ≈ 127 → 0)
- Tree format: lhalo_binary (`trees_063.0` – `trees_063.7`)
- Scale factor file: `millennium.a_list`
- SAGE output: `model_0.hdf5` with groups `Snap_0` – `Snap_63`

Launch:

```bash
visage --par input/millennium.par
```

## microUchuu

- Box size: 96 Mpc/h
- Snapshots: 50 (z ≈ 13.9 → 0)
- Tree format: lhalo_binary (`tree_0_0_0.dat`)
- Scale factor file: `Uchuu100_scalefactor.txt`

Launch:

```bash
visage --par input/microuchuu.par
```

## LightSAGE lightcone output

A [LightSAGE](https://github.com/sage-home/sage-lightcone) `cli_lightcone` run produces a single flat HDF5 file — no periodic box, no per-snapshot groups, one array per field at the root:

- Pass-through SAGE fields keep their original CamelCase names — `Posx`/`Posy`/`Posz`, `StellarMass`, `SnapNum`, `Type`, `Mvir`, `Rvir`, `SfrDisk`/`SfrBulge`, …
- Computed fields are lowercase — `ra`, `dec`, `distance`, `redshift_cosmological`, `redshift_observed`, `sfr`
- Mass fields are in `10^10 Msun/h` (same convention as SAGE HDF5 output); positions are observer-frame comoving Mpc/h
- Cosmology and provenance are recorded in the `SageOutputHeader` and `LightconeOutputHeader` groups

Launch:

```bash
visage --lightcone /path/to/lightcone.h5
```

See [Lightcone Mode](lightcone.md) for what's different about viewing a lightcone versus a SAGE box.

## How the par file is used

ViSAGE's `parse_par()` reads the `.par` file you pass to the CLI. Relative paths in the par file are resolved relative to the par file's parent directory (your SAGE26 root), so you can run `visage` from anywhere as long as you give it the absolute or correctly relative path to the par file.

## Data that is never committed

Tree files, HDF5 outputs, and scale-factor lists are all listed in `.gitignore`. ViSAGE only reads them at runtime.
