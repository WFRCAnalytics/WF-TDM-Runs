import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString

from tdmruns import network_utils
from tdmruns.exceptions import OutputCollectionError


def _make_full_shapefile(path, fields):
    n = len(next(iter(fields.values())))
    geoms = [LineString([(i, i), (i + 1, i + 1)]) for i in range(n)]
    gdf = gpd.GeoDataFrame({**fields, "geometry": geoms}, crs="EPSG:4326")
    gdf.to_file(path)


def test_export_network_fields_keeps_only_named_fields(tmp_path, monkeypatch):
    # export_net_to_shapefile would normally shell out to Cube Voyager --
    # stubbed here to just materialize a pre-built synthetic shapefile in
    # its place, so this test never needs a real .net file or a Cube
    # Voyager license.
    fields = {"SEGID": ["0015_001.0", "0015_002.0"], "FTCLASS": ["Freeway", "Freeway"], "LANES": [3, 4]}

    def fake_export(net_path, geometry_shp, dest_shp, voyager_exe):
        _make_full_shapefile(dest_shp, fields)

    monkeypatch.setattr(network_utils, "export_net_to_shapefile", fake_export)

    net_path = tmp_path / "_Assigned.net"
    net_path.write_bytes(b"fake")
    geometry_shp = tmp_path / "geom.shp"
    dest_geojson = tmp_path / "curated" / "_Assigned.geojson"

    network_utils.export_network_fields(net_path, geometry_shp, ["SEGID", "LANES"], dest_geojson, voyager_exe="fake.exe")

    assert dest_geojson.is_file()
    gdf = gpd.read_file(dest_geojson)
    assert sorted(c for c in gdf.columns if c != "geometry") == ["LANES", "SEGID"]
    assert list(gdf["SEGID"]) == ["0015_001.0", "0015_002.0"]

    # the full (untrimmed) temp shapefile export must not survive
    assert not (tmp_path / "_Assigned.shp").exists()


def test_export_network_fields_raises_clearly_for_missing_field(tmp_path, monkeypatch):
    fields = {"SEGID": ["0015_001.0"]}

    def fake_export(net_path, geometry_shp, dest_shp, voyager_exe):
        _make_full_shapefile(dest_shp, fields)

    monkeypatch.setattr(network_utils, "export_net_to_shapefile", fake_export)

    net_path = tmp_path / "_Assigned.net"
    net_path.write_bytes(b"fake")
    geometry_shp = tmp_path / "geom.shp"
    dest_geojson = tmp_path / "curated" / "_Assigned.geojson"

    with pytest.raises(OutputCollectionError, match="NoSuchField"):
        network_utils.export_network_fields(
            net_path, geometry_shp, ["NoSuchField"], dest_geojson, voyager_exe="fake.exe"
        )

    assert not dest_geojson.exists()


def test_find_geometry_shapefile_globs_link_shp(tmp_path):
    geom_dir = tmp_path / "0_InputProcessing" / "UpdatedMasterNet" / "GIS"
    geom_dir.mkdir(parents=True)
    _make_full_shapefile(geom_dir / "WFv1000_MasterNet_20250821 - Link.shp", {"SEGID": ["0015_001.0"]})

    found = network_utils.find_geometry_shapefile(tmp_path)
    assert found.name == "WFv1000_MasterNet_20250821 - Link.shp"


def test_find_geometry_shapefile_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        network_utils.find_geometry_shapefile(tmp_path)


def test_find_geometry_shapefile_raises_when_ambiguous(tmp_path):
    geom_dir = tmp_path / "0_InputProcessing" / "UpdatedMasterNet" / "GIS"
    geom_dir.mkdir(parents=True)
    _make_full_shapefile(geom_dir / "A - Link.shp", {"SEGID": ["0015_001.0"]})
    _make_full_shapefile(geom_dir / "B - Link.shp", {"SEGID": ["0015_001.0"]})

    with pytest.raises(FileNotFoundError):
        network_utils.find_geometry_shapefile(tmp_path)


def test_export_network_fields_shp_format_writes_zipped_shapefile(tmp_path, monkeypatch):
    fields = {"SEGID": ["0015_001.0", "0015_002.0"], "LANES": [3, 4]}

    def fake_export(net_path, geometry_shp, dest_shp, voyager_exe):
        _make_full_shapefile(dest_shp, fields)

    monkeypatch.setattr(network_utils, "export_net_to_shapefile", fake_export)

    net_path = tmp_path / "_Assigned.net"
    net_path.write_bytes(b"fake")
    geometry_shp = tmp_path / "geom.shp"
    dest_zip = tmp_path / "curated" / "_Assigned.shp.zip"

    network_utils.export_network_fields(
        net_path, geometry_shp, ["SEGID", "LANES"], dest_zip, voyager_exe="fake.exe", output_format="shp"
    )

    assert dest_zip.is_file()
    with zipfile.ZipFile(dest_zip) as zf:
        names = {Path(n).suffix for n in zf.namelist()}
        assert ".shp" in names
        assert ".dbf" in names

    # a plain (unzipped) .shp read via the zip:// vsizip prefix should show
    # only the requested fields
    gdf = gpd.read_file(f"zip://{dest_zip}")
    assert sorted(c for c in gdf.columns if c != "geometry") == ["LANES", "SEGID"]


def test_export_network_fields_net_format_calls_field_filtered_export(tmp_path, monkeypatch):
    fields = {"SEGID": ["0015_001.0"], "FTCLASS": ["Freeway"], "LANES": [3]}
    field_filtered_calls = []

    def fake_export_shp(net_path, geometry_shp, dest_shp, voyager_exe):
        _make_full_shapefile(dest_shp, fields)

    def fake_export_net(net_path, geometry_shp, exclude_fields, dest_net, voyager_exe):
        field_filtered_calls.append(exclude_fields)
        dest_net.parent.mkdir(parents=True, exist_ok=True)
        dest_net.write_bytes(b"fake filtered net")

    monkeypatch.setattr(network_utils, "export_net_to_shapefile", fake_export_shp)
    monkeypatch.setattr(network_utils, "export_net_field_filtered", fake_export_net)

    net_path = tmp_path / "_Assigned.net"
    net_path.write_bytes(b"fake")
    geometry_shp = tmp_path / "geom.shp"
    dest_net = tmp_path / "curated" / "_Assigned.net"

    network_utils.export_network_fields(
        net_path, geometry_shp, ["SEGID"], dest_net, voyager_exe="fake.exe", output_format="net"
    )

    assert dest_net.read_bytes() == b"fake filtered net"
    # only SEGID was requested, so FTCLASS/LANES should be the exclude list
    assert field_filtered_calls == [["FTCLASS", "LANES"]]
