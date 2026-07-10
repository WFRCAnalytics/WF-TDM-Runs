"""Cube Voyager matrix conversion helpers -- shared by run_set-specific
scripts (e.g. scripts/redistribute_hbw_trips.py) and outputs.py's matrix-type
curation. numpy/openmatrix can't read Cube's native .mtx (TPP) format
directly, so CONVERTMAT is invoked by writing a one-line .s script plus a
.bat wrapper and shelling out to VOYAGER.EXE.
"""
import subprocess
import tempfile
from pathlib import Path

import openmatrix as omx

from tdmruns.exceptions import OutputCollectionError


def _run_convertmat(script_path: Path, bat_path: Path, voyager_exe: str):
    voyager_dir = str(Path(voyager_exe).parent)
    with open(bat_path, "w") as f:
        f.write(f'start /w "{voyager_dir}" VOYAGER.EXE "{script_path.resolve()}" /start -Report\n')
    subprocess.call(str(bat_path), cwd=str(bat_path.parent))


def convert_mtx_to_omx(mtx_path: Path, omx_path: Path, voyager_exe: str):
    # CONVERTMAT's own script/batch files and Voyager's TPPL*.PRN/.VAR/.PRJ
    # print logs land in whatever directory the .bat is run from -- a
    # dedicated temp dir keeps those out of omx_path's own directory (which,
    # for outputs.py's matrix curation, is the run's committed outputs/
    # folder; those incidental artifacts must never end up there).
    with tempfile.TemporaryDirectory(prefix="convertmat_") as work_dir_str:
        work_dir = Path(work_dir_str)
        script_path = work_dir / f"_convert_in_{mtx_path.stem}.s"
        bat_path = work_dir / f"_convert_in_{mtx_path.stem}.bat"
        with open(script_path, "w") as f:
            f.write(
                f'convertmat from="{mtx_path.resolve()}", to="{omx_path.resolve()}", '
                f'compression=2, format="omx"\n'
            )
        _run_convertmat(script_path, bat_path, voyager_exe)
        if not omx_path.exists():
            raise RuntimeError(f"CONVERTMAT did not produce {omx_path} -- check {bat_path} output")


def convert_omx_to_mtx(omx_path: Path, mtx_path: Path, voyager_exe: str):
    with tempfile.TemporaryDirectory(prefix="convertmat_") as work_dir_str:
        work_dir = Path(work_dir_str)
        script_path = work_dir / f"_convert_out_{mtx_path.stem}.s"
        bat_path = work_dir / f"_convert_out_{mtx_path.stem}.bat"
        with open(script_path, "w") as f:
            f.write(f'convertmat from="{omx_path.resolve()}", to="{mtx_path.resolve()}", format=TPP\n')
        _run_convertmat(script_path, bat_path, voyager_exe)
        if not mtx_path.exists():
            raise RuntimeError(f"CONVERTMAT did not produce {mtx_path} -- check {bat_path} output")


def extract_matrix_tabs(source_mtx: Path, tabs: list, dest_omx: Path, voyager_exe: str) -> None:
    """Converts source_mtx (a full, possibly huge, multi-table Cube matrix)
    to a temporary full OMX via CONVERTMAT, then writes a new, small OMX at
    dest_omx containing only the named tabs -- deleting the temporary full
    conversion afterward regardless of outcome. Raises OutputCollectionError
    naming the available tables if any requested tab isn't present, so a
    typo'd tabs: entry in run_set.yaml fails clearly rather than silently."""
    dest_omx.parent.mkdir(parents=True, exist_ok=True)
    temp_omx = dest_omx.parent / f"_full_{source_mtx.stem}.omx"
    convert_mtx_to_omx(source_mtx, temp_omx, voyager_exe)
    try:
        src = omx.open_file(str(temp_omx), "r")
        try:
            available = src.list_matrices()
            missing = [t for t in tabs if t not in available]
            if missing:
                raise OutputCollectionError(
                    f"tabs {missing} not found in {source_mtx.name} (available: {available})"
                )
            dst = omx.open_file(str(dest_omx), "w")
            try:
                for tab in tabs:
                    dst[tab] = src[tab]
            finally:
                dst.close()
        finally:
            src.close()
    finally:
        if temp_omx.exists():
            temp_omx.unlink()
