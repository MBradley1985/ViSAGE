# ViSAGE

**Interactive 3D visualization for SAGE semi-analytic galaxy formation outputs.**

ViSAGE renders dark matter haloes and SAGE galaxies together in a browser-based interactive viewer, powered by [PyVista](https://pyvista.org) and [Trame](https://kitware.github.io/trame/). It is designed to work directly with the output of [SAGE26](https://github.com/MBradley1985/SAGE26), and includes guided setup flows for two companion tools: [SAGEswarm](https://github.com/MBradley1985/SAGEswarm) (PSO calibration) and **LightSAGE** (lightcone extraction, upstream repo [`sage-home/sage-lightcone`](https://github.com/sage-home/sage-lightcone)).

---

## Key features

| Feature | Description |
|---|---|
| Dual layers | Haloes and galaxies rendered simultaneously as world-space gaussian splats |
| Timeline | Scrub, play, pause, and step through every snapshot at 0.1×–5× speeds |
| Layer controls | Toggle visibility, adjust opacity, choose colour-by mode, pick from 27 colormaps |
| Structure mode | Layered galaxies: cold-gas envelope + outer CGM/Hot envelope, sized by SAGE fields |
| Navigation | Fly to halo index, galaxy index, coordinates, or sub-box — focus mode masks everything outside |
| Tab-aware Focus | One button that does the right thing on whatever tab you're in |
| Double-click any point | Populates Target halo + galaxy IDs and (if Focus is active) carries the camera to the selection |
| Point picking | Double-click anywhere in the viewport — works on every tab |
| Multi-model | Switch between SAGE flavours of the same sim; overlay two compatible models simultaneously |
| Lightcone Mode | Open a LightSAGE lightcone output in the same Explore UI; the snapshot slider becomes a redshift/time cut over the cone, plus an optional false-colour synthetic-photometry (SED) imaging layer |
| Launch Mode wizard | Guided flows to clone/build/configure/run SAGE26, SAGEswarm, or LightSAGE, with a labelled parameter form for every config file |
| Story Mode | Author JSON "stories" and play them back as full presentations over the live 3D view — text/media/equation overlays, camera motions, time sweeps |
| Embedded console | Real shell terminal + Python REPL + natural-language SAGE commands in one tab, with multi-session tabs, script loading, and a pop-out window |
| Output | Screenshots (PNG/JPG/TIFF), movies (GIF/MOV/PNG-sequence) at 1–60 fps, 1×/2×/4× supersampling |
| Camera bookmarks | Save / restore / delete arbitrary viewpoints |
| Multi-CPU loading | Snapshot prefetch pool keeps playback smooth |
| Remote use | Trame web server — run on a cluster, view in any browser |
| Enter to run | Every input submits on Enter, equivalent to clicking its action button |

---

## Quick example

```bash
pip install sage-viewer
visage --par input/millennium.par
# → Open http://localhost:8080
```

---

## Supported simulations

- **miniMillennium** — 62.5 Mpc/h box, 64 snapshots, lhalo_binary trees
- **microUchuu** — 96 Mpc/h box, 50 snapshots, lhalo_binary trees

---

## Documentation sections

- **[Getting Started](getting_started/installation.md)** — install and launch
- **[User Guide](user_guide/interface.md)** — UI reference and navigation controls
- **[Launch Mode](user_guide/launch_mode.md)** — guided SAGE26 / SAGEswarm / LightSAGE setup flows
- **[Lightcone Mode](user_guide/lightcone.md)** — visualize a LightSAGE lightcone output
- **[Story Mode](user_guide/story_mode.md)** — author and present data-driven talks in the viewer
- **[Physics Reference](physics/haloes.md)** — field definitions and units
- **[API Reference](api/index.md)** — Python API for scripting and integration
