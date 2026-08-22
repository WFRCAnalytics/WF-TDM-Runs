from tdmruns import general_parameters as gp


def test_load_baseline_parses_real_block_format(tmp_path):
    tdm_path = tmp_path / "tdm"
    gp_path = tdm_path / "1_Inputs" / "0_GlobalData" / "GeneralParameters.block"
    gp_path.parent.mkdir(parents=True)
    gp_path.write_text(
        ";General Parameters\n"
        "    ZoneMsgRate = 50\n"
        "    UsedZones = 3629\n"
    )
    baseline = gp.load_baseline(tdm_path, "1_Inputs/0_GlobalData/GeneralParameters.block")
    assert baseline == {"ZoneMsgRate": "50", "UsedZones": "3629"}


def test_write_override_file_writes_only_the_overridden_keys(tmp_path):
    out_path = tmp_path / "_GeneralParametersOverrides.block"
    gp.write_override_file({"ZoneMsgRate": 100, "UsedZones": 3629}, out_path)

    text = out_path.read_text()
    assert "ZoneMsgRate = 100" in text
    assert "UsedZones = 3629" in text
    assert "General Parameter overrides" in text


def test_write_override_file_creates_parent_dirs(tmp_path):
    out_path = tmp_path / "nested" / "scenario" / gp.OVERRIDE_FILENAME
    gp.write_override_file({"ZoneMsgRate": 100}, out_path)
    assert out_path.is_file()


def test_write_override_file_uses_crlf_line_endings(tmp_path):
    # Cube Voyager block files are read on Windows -- match write_block_file()'s
    # own newline="\r\n" convention rather than the platform default.
    out_path = tmp_path / gp.OVERRIDE_FILENAME
    gp.write_override_file({"ZoneMsgRate": 100}, out_path)
    raw = out_path.read_bytes()
    assert b"\r\n" in raw
