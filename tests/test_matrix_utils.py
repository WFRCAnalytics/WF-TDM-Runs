import numpy as np
import openmatrix as omx
import pytest

from tdmruns import matrix_utils
from tdmruns.exceptions import OutputCollectionError


def _make_full_omx(path, tables):
    f = omx.open_file(str(path), "w")
    try:
        for name, arr in tables.items():
            f[name] = arr
    finally:
        f.close()


def test_extract_matrix_tabs_keeps_only_named_tables(tmp_path, monkeypatch):
    # convert_mtx_to_omx would normally shell out to Cube Voyager -- stubbed
    # here to just materialize a pre-built synthetic OMX in its place, so
    # this test never needs a real .mtx file or a Cube Voyager license.
    full = {
        "GP_Dist": np.array([[0.0, 1.5], [1.5, 0.0]], dtype="float32"),
        "GP_Time": np.array([[0.0, 3.0], [3.0, 0.0]], dtype="float32"),
    }

    def fake_convert(mtx_path, omx_path, voyager_exe):
        _make_full_omx(omx_path, full)

    monkeypatch.setattr(matrix_utils, "convert_mtx_to_omx", fake_convert)

    source_mtx = tmp_path / "Skm_DY.mtx"
    source_mtx.write_bytes(b"fake")  # never actually read by the stub
    dest_omx = tmp_path / "curated" / "Skm_DY.omx"

    matrix_utils.extract_matrix_tabs(source_mtx, ["GP_Dist"], dest_omx, voyager_exe="fake.exe")

    assert dest_omx.is_file()
    f = omx.open_file(str(dest_omx), "r")
    try:
        assert f.list_matrices() == ["GP_Dist"]
        np.testing.assert_array_equal(np.array(f["GP_Dist"]), full["GP_Dist"])
    finally:
        f.close()

    # the full (untrimmed) temp conversion must not survive
    assert not (tmp_path / "_full_Skm_DY.omx").exists()


def test_extract_matrix_tabs_raises_clearly_for_missing_tab(tmp_path, monkeypatch):
    full = {"GP_Dist": np.array([[0.0, 1.0], [1.0, 0.0]], dtype="float32")}

    def fake_convert(mtx_path, omx_path, voyager_exe):
        _make_full_omx(omx_path, full)

    monkeypatch.setattr(matrix_utils, "convert_mtx_to_omx", fake_convert)

    source_mtx = tmp_path / "Skm_DY.mtx"
    source_mtx.write_bytes(b"fake")
    dest_omx = tmp_path / "curated" / "Skm_DY.omx"

    with pytest.raises(OutputCollectionError, match="NoSuchTab"):
        matrix_utils.extract_matrix_tabs(source_mtx, ["NoSuchTab"], dest_omx, voyager_exe="fake.exe")

    # nothing partially written, and the temp full conversion was cleaned up
    assert not dest_omx.exists()
    assert not (tmp_path / "_full_Skm_DY.omx").exists()
