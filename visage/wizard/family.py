"""DarkSAGE and DustySAGE in Launch Mode: two more of the SAGE family, cloned,
built and run from GitHub like SAGE26. Neither is changed.

Their sample parameter files don't run as they stand (DustySAGE's lacks tags
its code requires), so a tested file for the mini-Millennium trees is written
into each checkout. Their binary output is converted once a run finishes
(visage.io.family_binary), after which a run opens as any other model.
"""

from __future__ import annotations

from pathlib import Path

PARS = Path(__file__).parent / "family_pars"
FAMILY = {
    "darksage": {
        "title": "DarkSAGE",
        "repo": "https://github.com/arhstevens/DarkSAGE.git",
        "branch": "astevens-disc",
        "folder": "DarkSAGE",
        "names": ("DarkSAGE", "DarkSage", "darksage"),
        "binary": "darksage",
        "header": "code/core_allvars.h",
        "make": ["make"],
        "par": "darksage.par",
    },
    "dustysage": {
        "title": "DustySAGE",
        "repo": "https://github.com/dptriani/dusty-sage.git",
        "branch": "",
        "folder": "dusty-sage",
        "names": ("dusty-sage", "DustySAGE", "dustysage"),
        "binary": "sage",
        "header": "src/core_allvars.h",
        # Their default adds x86-only flags.
        "make": ["make", "OPTIMIZE=-O2"],
        "par": "dustysage.par",
    },
}


class FamilyMixin:
    """Clone, install, run and find DarkSAGE and DustySAGE."""

    def _find_family(self, mode: str) -> Path | None:
        spec = FAMILY[mode]
        roots = [Path.cwd().parent, Path.cwd(), Path.home()]
        if self._sage26_dir:
            roots.insert(0, self._sage26_dir.parent)
        for root in roots:
            for name in spec["names"]:
                p = root / name
                if (p / spec["header"]).is_file():
                    return p
        return None

    def _family_built(self, mode: str) -> bool:
        d = self._family_dirs.get(mode)
        return bool(d) and (d / FAMILY[mode]["binary"]).is_file()

    async def _install_family(self, mode: str) -> tuple[bool, str]:
        spec = FAMILY[mode]
        d = self._family_dirs.get(mode)
        if not d:
            return False, f"{spec['title']} isn't cloned yet"
        self._inline_step(f"Compiling {spec['title']}")
        if await self._run_cmd(spec["make"], cwd=d) != 0:
            return False, "Compiling failed"
        return True, f"Installed: {spec['title']} compiled"

    def _family_trees(self, mode: str) -> Path | None:
        """The mini-Millennium trees: SAGE26's, else those DustySAGE ships."""
        here = self._family_dirs.get(mode)
        options = []
        if self._sage26_dir:
            options.append(self._sage26_dir / "input" / "millennium" / "trees")
        for d in (here, self._family_dirs.get("dustysage")):
            if d:
                options.append(
                    d / "src" / "auxdata" / "trees" / "mini-millennium"
                )
        for p in options:
            if (p / "trees_063.0").is_file():
                return p
        return None

    def _family_par(self, mode: str, trees: Path) -> Path:
        """Write the checkout's parameter file; its path."""
        spec = FAMILY[mode]
        d = self._family_dirs[mode]
        alist = sorted(trees.glob("*.a_list"))[0]
        out = d / "output" / "millennium"
        out.mkdir(parents=True, exist_ok=True)
        text = (PARS / spec["par"]).read_text()
        text = text.replace("@OUTPUT@", f"{self._tc_path(out)}/")
        text = text.replace("@TREES@", f"{self._tc_path(trees)}/")
        text = text.replace("@ALIST@", str(self._tc_path(alist)))
        par = d / "input" / "millennium.par"
        par.parent.mkdir(exist_ok=True)
        self._write_unix_text(par, text)
        return par

    async def _run_family(self, mode: str) -> None:
        from visage.io.family_binary import convert

        spec = FAMILY[mode]
        d = self._family_dirs.get(mode)
        back = [self._mode_back_choice(mode)]
        if not d or not self._family_built(mode):
            self._emit(f"{spec['title']} isn't compiled: use Install.", "err")
            self._set_choices(back)
            return
        trees = self._family_trees(mode)
        if trees is None:
            self._emit(
                "No mini-Millennium trees found. Install SAGE26 first: it "
                "downloads them.",
                "err",
            )
            self._set_choices(back)
            return
        par = self._family_par(mode, trees)
        for old in (d / "output" / "millennium").glob("model_*"):
            old.unlink()
        self._emit(f"Running {spec['title']} on mini-Millennium.", "info")
        rc = await self._run_cmd([d / spec["binary"], par], cwd=d)
        if rc != 0:
            self._emit(f"{spec['title']} exited with code {rc}.", "err")
            self._set_choices(back)
            return
        self._emit("Converting its output for ViSAGE ...", "info")
        try:
            convert(par, d / spec["header"], spec["title"])
        except (OSError, ValueError, KeyError) as exc:
            self._emit(f"Could not convert its output: {exc}", "err")
            self._set_choices(back)
            return
        self._emit(f"{spec['title']} run complete!", "ok")
        await self._launch_explore(
            par, model_name=f"{spec['title']} millennium"
        )
