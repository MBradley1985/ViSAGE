# Dark Matter Haloes

## Source

Halo data is read from the same merger tree files SAGE26 consumes at runtime, in either of two formats — ViSAGE detects which from the file itself, so no extra configuration is needed:

- **lhalo_binary** (`TreeName.N`, e.g. `trees_063.0`) — the packed C struct described below.
- **lhalo_hdf5** (`TreeName.N.hdf5`) — one HDF5 group per tree (`Tree0`, `Tree1`, …), each holding the halo properties as separate datasets.

## Fields loaded by ViSAGE

| Field | Type | Units (raw) | Units (viewer) |
|---|---|---|---|
| `Pos[3]` | float32 | Mpc/h | Mpc/h (unchanged) |
| `Mvir` | float32 | 10¹⁰ Msun/h | Msun (×1e10/h) |
| `SnapNum` | int32 | — | — |

Only `Pos` and `Mvir` are used for rendering. All other fields in the struct (`Vel`, `Spin`, `VelDisp`, `Vmax`, etc.) are read but discarded after the per-snapshot filter.

### Halo mass is not always called `Mvir`

Tree files disagree on which column carries the halo mass, so ViSAGE tries several and uses the first one that is actually populated (present-but-all-zero columns are skipped):

| Format | Candidates, in order |
|---|---|
| lhalo_binary | `Mvir`, `M_TopHat`, `M_Mean200` |
| lhalo_hdf5 | `Mvir`, `Group_M_Crit200`, `M_Crit200`, `Mass_200crit`, `M200c`, `Group_M_TopHat200`, `M_TopHat200`, `M_TopHat`, `Group_M_Mean200`, `M_Mean200`, `Mass_200mean` |

The load line names the column whenever it isn't `Mvir`:

```
Haloes: 79,890 loaded (halo mass from Group_M_Crit200)
```

`Rvir`, `Vvir`, the mass floor, colouring and filtering all follow the column that was chosen. Positions and masses in HDF5 trees are likewise resolved by alias (`SubhaloPos`, `SubhaloVMax`, …), and positions stored in kpc/h are converted to Mpc/h automatically — detected by comparing against `BoxSize`.

!!! note "Host haloes only"
    ViSAGE renders FOF centrals. In lhalo_binary trees satellites carry `Mvir = 0`, so the mass floor excludes them on its own; in HDF5 trees the mass columns are populated for satellites too, so centrals are selected explicitly via `FirstHaloInFOFGroup`. For The300 at z=0 this gives 79,890 host haloes — exactly the number of `Type == 0` galaxies SAGE writes for that snapshot.

## Mass floor

The default mass floor is `1e10 Msun`. This removes very low-mass substructure that would otherwise dominate point count without contributing visible structure. Adjust with `--min-halo-mass`.

## lhalo_binary file format

Each tree file has the following binary layout:

```
int32   nforests
int32   nhalos_total
int32[nforests]  nhalos_per_forest
HaloStruct[nhalos_total]
```

`HaloStruct` is 19 fields; the full dtype is defined in `visage/io/halo_reader.py:HALO_DTYPE`.

## Parallel loading

ViSAGE reads the N lhalo_binary tree files in parallel (joblib). For miniMillennium with 8 files and 8 CPUs, all files load simultaneously.

HDF5 trees are handled differently: h5py serialises the per-tree reads, so parallelising them gains nothing (measured: threads no faster, processes ~4× slower). Instead each file is scanned **once** into an in-memory index of every snapshot, and each snapshot is then served from it. For The300 — 152k trees, 5.5M host haloes — that scan takes ~40 s on first load, after which every snapshot resolves in milliseconds, and preloading all 129 snapshots costs no further I/O.
