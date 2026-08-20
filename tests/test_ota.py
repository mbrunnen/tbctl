import json
import re
from unittest.mock import ANY, MagicMock, patch

from typer.testing import CliRunner

from tbctl.cli import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _mock_package(
    pkg_id="abc-123",
    title="Firmware 1.0",
    version="1.0",
    pkg_type="FIRMWARE",
    size=1024,
    profile_id=None,
):
    pkg = MagicMock()
    pkg.id.id = pkg_id
    pkg.title = title
    pkg.version = version
    pkg.type = pkg_type
    pkg.data_size = size
    if profile_id is None:
        pkg.device_profile_id = None
    else:
        pkg.device_profile_id.id = profile_id
    return pkg


def test_list():
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = [_mock_package()]
    mock_api.get_ota_packages.return_value.total_elements = 1

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list"])

    assert result.exit_code == 0
    assert "Firmware 1.0" in result.output


def test_list_empty():
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = []

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list"])

    assert result.exit_code == 0
    assert "No OTA packages found" in result.output


def test_get_renders_a_table_by_default():
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_package()

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "get", "abc-123"])

    assert result.exit_code == 0
    mock_api.get_ota_package_info_by_id.assert_called_once_with(ota_package_id="abc-123")
    output = _strip_ansi(result.output)
    assert "Firmware 1.0" in output
    assert not output.lstrip().startswith("{")


def test_get_json():
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value.to_dict.return_value = {
        "title": "Firmware 1.0",
        "version": "1.0",
    }

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "get", "abc-123", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"title": "Firmware 1.0", "version": "1.0"}


def test_delete():
    mock_api = MagicMock()

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "delete", "abc-123", "--yes"])

    assert result.exit_code == 0
    mock_api.delete_ota_package.assert_called_once_with(ota_package_id="abc-123")
    assert "Deleted abc-123" in result.output


def test_delete_confirm():
    mock_api = MagicMock()

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "delete", "abc-123"], input="y\n")

    assert result.exit_code == 0
    mock_api.delete_ota_package.assert_called_once_with(ota_package_id="abc-123")


def test_delete_abort():
    mock_api = MagicMock()

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "delete", "abc-123"], input="n\n")

    assert result.exit_code != 0
    mock_api.delete_ota_package.assert_not_called()


# --- JSON output (regression: model_dump vs to_dict) ---


def test_list_json():
    mock_api = MagicMock()
    pkg = _mock_package()
    pkg.model_dump.return_value = {
        "title": "Firmware 1.0",
        "version": "1.0",
        "type": "FIRMWARE",
        "id": {"id": "abc-123"},
    }
    mock_api.get_ota_packages.return_value.data = [pkg]
    mock_api.get_ota_packages.return_value.total_elements = 1

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["version"] == "1.0"
    assert data[0]["type"] == "FIRMWARE"
    pkg.model_dump.assert_called_once_with(by_alias=True, exclude_none=True)


def test_list_json_empty():
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = []

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list", "--json"])

    assert result.exit_code == 0
    assert result.output.strip() == "[]"


def test_list_json_multiple():
    mock_api = MagicMock()
    pkgs = [
        _mock_package("id-1", "FW 1.0", "1.0", "FIRMWARE"),
        _mock_package("id-2", "SW 2.0", "2.0", "SOFTWARE"),
    ]
    for pkg in pkgs:
        pkg.model_dump.return_value = {
            "title": pkg.title,
            "version": pkg.version,
            "type": pkg.type,
        }
    mock_api.get_ota_packages.return_value.data = pkgs
    mock_api.get_ota_packages.return_value.total_elements = 2

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2
    assert data[1]["type"] == "SOFTWARE"


# --- Exception handling (regression: ApiException caught) ---


def test_list_api_exception():
    from tb_client.exceptions import ApiException

    mock_api = MagicMock()
    mock_api.get_ota_packages.side_effect = ApiException(status=401, reason="Unauthorized")

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list"])

    assert result.exit_code != 0
    assert "401" in result.stderr


def test_get_api_exception():
    from tb_client.exceptions import ApiException

    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.side_effect = ApiException(status=404, reason="Not Found")

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "get", "no-such-id"])

    assert result.exit_code != 0
    assert "404" in result.stderr


def test_delete_api_exception():
    from tb_client.exceptions import ApiException

    mock_api = MagicMock()
    mock_api.delete_ota_package.side_effect = ApiException(status=403, reason="Forbidden")

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "delete", "abc-123", "--yes"])

    assert result.exit_code != 0
    assert "403" in result.stderr


# --- Filter validation ---


_LIST_PROFILE_UUID = "11111111-1111-1111-1111-111111111111"


def test_list_device_profile_without_type_lists_both():
    mock_api = MagicMock()
    mock_api.get_ota_packages1.return_value.data = [_mock_package()]
    mock_api.get_ota_packages1.return_value.total_elements = 1

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list", "--device-profile", _LIST_PROFILE_UUID])

    assert result.exit_code == 0
    called_types = {c.kwargs["type"] for c in mock_api.get_ota_packages1.call_args_list}
    assert called_types == {"FIRMWARE", "SOFTWARE"}
    mock_api.get_ota_packages.assert_not_called()


def test_list_type_without_device_profile():
    mock_api = MagicMock()

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list", "--type", "FIRMWARE"])

    assert result.exit_code != 0
    mock_api.get_ota_packages.assert_not_called()
    mock_api.get_ota_packages1.assert_not_called()


def test_list_device_profile_and_type():
    mock_api = MagicMock()
    mock_api.get_ota_packages1.return_value.data = [_mock_package()]
    mock_api.get_ota_packages1.return_value.total_elements = 1

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(
            app, ["ota", "list", "--device-profile", _LIST_PROFILE_UUID, "--type", "FIRMWARE"]
        )

    assert result.exit_code == 0
    mock_api.get_ota_packages1.assert_called_once_with(
        device_profile_id=_LIST_PROFILE_UUID,
        type="FIRMWARE",
        page_size=20,
        page=0,
        text_search=None,
        sort_property=None,
        sort_order=None,
    )
    mock_api.get_ota_packages.assert_not_called()


def test_list_device_profile_by_name_resolves():
    mock_api = MagicMock()
    mock_api.get_ota_packages1.return_value.data = [_mock_package()]
    mock_api.get_ota_packages1.return_value.total_elements = 1

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.resolve_profile_id", return_value=_LIST_PROFILE_UUID) as resolve,
    ):
        result = runner.invoke(
            app, ["ota", "list", "--device-profile", "Sensor-V1", "--type", "FIRMWARE"]
        )

    assert result.exit_code == 0
    resolve.assert_called_once_with("default", "Sensor-V1")
    assert mock_api.get_ota_packages1.call_args.kwargs["device_profile_id"] == _LIST_PROFILE_UUID


def test_list_shows_device_profile_column():
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = [_mock_package(profile_id=_LIST_PROFILE_UUID)]
    mock_api.get_ota_packages.return_value.total_elements = 1

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch(
            "tbctl.commands.ota.profile_name_map",
            return_value={_LIST_PROFILE_UUID: "Sensor-V1"},
        ) as names,
    ):
        result = runner.invoke(app, ["ota", "list"])

    assert result.exit_code == 0
    assert "Sensor-V1" in result.output
    names.assert_called_once()


def test_list_device_profile_column_falls_back_to_uuid():
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = [_mock_package(profile_id="dp-xyz")]
    mock_api.get_ota_packages.return_value.total_elements = 1

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.profile_name_map", return_value={}),
    ):
        result = runner.invoke(app, ["ota", "list"])

    assert result.exit_code == 0
    assert "dp-xyz" in result.output


def test_list_search_filter():
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = [_mock_package(title="SpecialFW")]
    mock_api.get_ota_packages.return_value.total_elements = 1

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list", "--search", "Special"])

    assert result.exit_code == 0
    mock_api.get_ota_packages.assert_called_once_with(
        page_size=20,
        page=0,
        text_search="Special",
        sort_property=None,
        sort_order=None,
    )


# --- Missing / incomplete configuration ---


def test_list_no_config(config_dir):
    result = runner.invoke(app, ["ota", "list"])
    assert result.exit_code != 0
    assert "not configured" in result.stderr


# --- download command ---


def _mock_info(
    pkg_id="abc-123", title="Firmware", version="1.0", pkg_type="FIRMWARE", file_name="fw_1.0.bin"
):
    info = MagicMock()
    info.id.id = pkg_id
    info.title = title
    info.version = version
    info.type = pkg_type
    info.file_name = file_name
    return info


def test_download_by_id(tmp_path):
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info()
    mock_api.download_ota_package.return_value = b"BINARY"
    out = tmp_path / "out.bin"

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "abc-123", "-o", str(out)])

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="abc-123")
    assert out.read_bytes() == b"BINARY"


def test_download_passes_string_id(tmp_path):
    import uuid

    uid = uuid.UUID("1332f070-59ee-11f1-841f-31b578843dc8")
    info = _mock_info()
    info.id.id = uid
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = info
    mock_api.download_ota_package.return_value = b"BINARY"
    out = tmp_path / "out.bin"

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", str(uid), "-o", str(out)])

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id=str(uid))


def test_download_default_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(file_name="fw_1.0.bin")
    mock_api.download_ota_package.return_value = b"BINARY"

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "abc-123"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "fw_1.0.bin").read_bytes() == b"BINARY"


def test_download_fallback_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(file_name=None)
    mock_api.download_ota_package.return_value = b"BINARY"

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "abc-123"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "Firmware-1.0.bin").read_bytes() == b"BINARY"


def test_download_refuses_overwrite(tmp_path):
    out = tmp_path / "out.bin"
    out.write_bytes(b"OLD")
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info()
    mock_api.download_ota_package.return_value = b"NEW"

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "abc-123", "-o", str(out)])

    assert result.exit_code != 0
    assert "exists" in result.stderr
    assert out.read_bytes() == b"OLD"


def test_download_force_overwrite(tmp_path):
    out = tmp_path / "out.bin"
    out.write_bytes(b"OLD")
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info()
    mock_api.download_ota_package.return_value = b"NEW"

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "abc-123", "-o", str(out), "--force"])

    assert result.exit_code == 0, result.output
    assert out.read_bytes() == b"NEW"


def test_download_no_selector():
    with patch("tbctl.commands.ota._get_api", return_value=MagicMock()):
        result = runner.invoke(app, ["ota", "download"])
    assert result.exit_code != 0
    assert "Provide exactly one" in result.stderr


def test_download_multiple_selectors():
    with patch("tbctl.commands.ota._get_api", return_value=MagicMock()):
        result = runner.invoke(app, ["ota", "download", "abc-123", "--name", "fw"])
    assert result.exit_code != 0
    assert "exactly one" in result.stderr


def test_download_version_and_latest():
    with patch("tbctl.commands.ota._get_api", return_value=MagicMock()):
        result = runner.invoke(
            app, ["ota", "download", "--name", "fw", "--version", "1.0", "--latest"]
        )
    assert result.exit_code != 0
    assert "--version" in result.stderr and "--latest" in result.stderr


def test_download_latest_without_name():
    with patch("tbctl.commands.ota._get_api", return_value=MagicMock()):
        result = runner.invoke(app, ["ota", "download", "abc-123", "--latest"])
    assert result.exit_code != 0
    assert "--latest" in result.stderr


def test_download_version_with_id():
    with patch("tbctl.commands.ota._get_api", return_value=MagicMock()):
        result = runner.invoke(app, ["ota", "download", "abc-123", "--version", "1.0"])
    assert result.exit_code != 0
    assert "--version" in result.stderr


def test_download_by_name_latest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old = _mock_info(pkg_id="old", version="1.0", file_name="fw_1.0.bin")
    old.created_time = 100
    new = _mock_info(pkg_id="new", version="2.0", file_name="fw_2.0.bin")
    new.created_time = 200
    extra = _mock_info(
        pkg_id="extra", title="Firmware Extra", version="3.0", file_name="fw_3.0.bin"
    )
    extra.created_time = 300
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = [old, new, extra]
    mock_api.download_ota_package.return_value = b"NEW"

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "--name", "Firmware"])

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="new")


def test_download_by_name_version(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old = _mock_info(pkg_id="old", version="1.0", file_name="fw_1.0.bin")
    old.created_time = 100
    new = _mock_info(pkg_id="new", version="2.0", file_name="fw_2.0.bin")
    new.created_time = 200
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = [old, new]
    mock_api.download_ota_package.return_value = b"OLD"

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "--name", "Firmware", "--version", "1.0"])

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="old")


def test_download_by_name_type_filter(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fw = _mock_info(pkg_id="fw", pkg_type="FIRMWARE", file_name="fw.bin")
    fw.created_time = 100
    sw = _mock_info(pkg_id="sw", pkg_type="SOFTWARE", file_name="sw.bin")
    sw.created_time = 200
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = [fw, sw]
    mock_api.download_ota_package.return_value = b"SW"

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "--name", "Firmware", "--type", "SOFTWARE"])

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="sw")


def test_download_by_name_case_insensitive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    info = _mock_info(pkg_id="fw", title="Firmware", file_name="fw.bin")
    info.created_time = 100
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = [info]
    mock_api.download_ota_package.return_value = b"FW"

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "--name", "firmware"])

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="fw")


def test_download_by_name_not_found():
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = []

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "--name", "Nope"])

    assert result.exit_code != 0
    assert "Nope" in result.stderr


def test_download_by_name_version_not_found():
    info = _mock_info(version="1.0")
    info.created_time = 100
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = [info]

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "--name", "Firmware", "--version", "9.9"])

    assert result.exit_code != 0
    assert "9.9" in result.stderr


PROFILE_UUID = "11111111-1111-1111-1111-111111111111"


def test_download_by_profile_current_firmware(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(pkg_id="fw-id")
    mock_api.download_ota_package.return_value = b"FW"
    profile = {"firmwareId": {"id": "fw-id"}, "softwareId": {"id": "sw-id"}}

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.raw_get", return_value=profile),
    ):
        result = runner.invoke(app, ["ota", "download", "--device-profile", PROFILE_UUID])

    assert result.exit_code == 0, result.output
    mock_api.get_ota_package_info_by_id.assert_called_once_with(ota_package_id="fw-id")
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="fw-id")


def test_download_by_profile_current_software(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(
        pkg_id="sw-id", pkg_type="SOFTWARE"
    )
    mock_api.download_ota_package.return_value = b"SW"
    profile = {"firmwareId": {"id": "fw-id"}, "softwareId": {"id": "sw-id"}}

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.raw_get", return_value=profile),
    ):
        result = runner.invoke(
            app, ["ota", "download", "--device-profile", PROFILE_UUID, "--type", "SOFTWARE"]
        )

    assert result.exit_code == 0, result.output
    mock_api.get_ota_package_info_by_id.assert_called_once_with(ota_package_id="sw-id")


def test_download_by_profile_name_resolves(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(pkg_id="fw-id")
    mock_api.download_ota_package.return_value = b"FW"
    profile = {"firmwareId": {"id": "fw-id"}}

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.resolve_profile_id", return_value=PROFILE_UUID) as rp,
        patch("tbctl.commands.ota.raw_get", return_value=profile),
    ):
        result = runner.invoke(app, ["ota", "download", "--device-profile", "sensor-v2"])

    assert result.exit_code == 0, result.output
    rp.assert_called_once_with(ANY, "sensor-v2")


def test_download_by_profile_version(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pkg = _mock_info(pkg_id="v2", version="2.0")
    pkg.created_time = 200
    mock_api = MagicMock()
    mock_api.get_ota_packages1.return_value.data = [pkg]
    mock_api.download_ota_package.return_value = b"V2"

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
    ):
        result = runner.invoke(
            app, ["ota", "download", "--device-profile", PROFILE_UUID, "--version", "2.0"]
        )

    assert result.exit_code == 0, result.output
    mock_api.get_ota_packages1.assert_called_once_with(
        device_profile_id=PROFILE_UUID,
        type="FIRMWARE",
        page_size=100,
        page=0,
        text_search=None,
        sort_property=None,
        sort_order=None,
    )
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="v2")


def test_download_by_profile_no_assignment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    profile = {"firmwareId": None, "softwareId": None}

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.raw_get", return_value=profile),
    ):
        result = runner.invoke(app, ["ota", "download", "--device-profile", PROFILE_UUID])

    assert result.exit_code != 0
    assert "no FIRMWARE" in result.stderr


DEVICE_UUID = "22222222-2222-2222-2222-222222222222"


def test_download_by_device_current_direct(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(pkg_id="dev-fw")
    mock_api.download_ota_package.return_value = b"FW"
    device = {
        "firmwareId": {"id": "dev-fw"},
        "softwareId": None,
        "deviceProfileId": {"id": PROFILE_UUID},
    }

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.resolve_device_id", return_value=DEVICE_UUID),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.raw_get", return_value=device),
    ):
        result = runner.invoke(app, ["ota", "download", "--device", "thermostat-01"])

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="dev-fw")


def test_download_by_device_current_profile_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(pkg_id="prof-fw")
    mock_api.download_ota_package.return_value = b"FW"
    device = {
        "firmwareId": None,
        "softwareId": None,
        "deviceProfileId": {"id": PROFILE_UUID},
    }
    profile = {"firmwareId": {"id": "prof-fw"}, "softwareId": None}

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.resolve_device_id", return_value=DEVICE_UUID),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.raw_get", side_effect=[device, profile]),
    ):
        result = runner.invoke(app, ["ota", "download", "--device", "thermostat-01"])

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="prof-fw")


def test_download_by_device_version(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pkg = _mock_info(pkg_id="v3", version="3.0")
    pkg.created_time = 300
    mock_api = MagicMock()
    mock_api.get_ota_packages1.return_value.data = [pkg]
    mock_api.download_ota_package.return_value = b"V3"
    device = {
        "firmwareId": {"id": "ignored"},
        "softwareId": None,
        "deviceProfileId": {"id": PROFILE_UUID},
    }

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.resolve_device_id", return_value=DEVICE_UUID),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.raw_get", return_value=device),
    ):
        result = runner.invoke(
            app, ["ota", "download", "--device", "thermostat-01", "--version", "3.0"]
        )

    assert result.exit_code == 0, result.output
    mock_api.get_ota_packages1.assert_called_once_with(
        device_profile_id=PROFILE_UUID,
        type="FIRMWARE",
        page_size=100,
        page=0,
        text_search=None,
        sort_property=None,
        sort_order=None,
    )
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="v3")


def test_download_by_device_no_assignment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    device = {
        "firmwareId": None,
        "softwareId": None,
        "deviceProfileId": {"id": PROFILE_UUID},
    }
    profile = {"firmwareId": None, "softwareId": None}

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.resolve_device_id", return_value=DEVICE_UUID),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.raw_get", side_effect=[device, profile]),
    ):
        result = runner.invoke(app, ["ota", "download", "--device", "thermostat-01"])

    assert result.exit_code != 0
    assert "no FIRMWARE" in result.stderr


# --- assign command ---

ASSIGN_DEVICE_UUID = "1332f070-59ee-11f1-841f-31b578843dc8"
PKG_UUID = "1332f070-59ee-11f1-841f-000000000001"


def _uuid_package(pkg_type="FIRMWARE"):
    pkg = _mock_package(pkg_type=pkg_type)
    pkg.id.id = PKG_UUID
    return pkg


def test_assign_by_id_sets_firmware():
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _uuid_package()

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.resolve_device_id", return_value=ASSIGN_DEVICE_UUID),
        patch("tbctl.commands.ota.raw_get", return_value={"id": {"id": ASSIGN_DEVICE_UUID}}),
        patch("tbctl.commands.ota._save_device_raw", return_value={}) as save_raw,
    ):
        result = runner.invoke(app, ["ota", "assign", PKG_UUID, ASSIGN_DEVICE_UUID])

    assert result.exit_code == 0, result.output
    body = save_raw.call_args.args[1]
    assert body["firmwareId"] == {"id": PKG_UUID, "entityType": "OTA_PACKAGE"}
    assert "Assigned Firmware 1.0 1.0" in result.output


def test_assign_by_title_latest():
    mock_api = MagicMock()
    page = MagicMock()
    page.data = [
        _mock_package(pkg_id="old", version="1.0"),
        _mock_package(pkg_id="new", version="2.0"),
    ]
    page.data[0].created_time = 100
    page.data[1].created_time = 200
    mock_api.get_ota_packages.return_value = page

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.resolve_device_id", return_value=ASSIGN_DEVICE_UUID),
        patch("tbctl.commands.ota.raw_get", return_value={"id": {"id": ASSIGN_DEVICE_UUID}}),
        patch("tbctl.commands.ota._save_device_raw", return_value={}) as save_raw,
    ):
        result = runner.invoke(app, ["ota", "assign", "Firmware 1.0", ASSIGN_DEVICE_UUID])

    assert result.exit_code == 0, result.output
    assert save_raw.call_args.args[1]["firmwareId"]["id"] == "new"


def test_assign_by_title_version():
    mock_api = MagicMock()
    page = MagicMock()
    page.data = [
        _mock_package(pkg_id="v1", version="1.0"),
        _mock_package(pkg_id="v2", version="2.0"),
    ]
    page.data[0].created_time = 100
    page.data[1].created_time = 200
    mock_api.get_ota_packages.return_value = page

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.resolve_device_id", return_value=ASSIGN_DEVICE_UUID),
        patch("tbctl.commands.ota.raw_get", return_value={"id": {"id": ASSIGN_DEVICE_UUID}}),
        patch("tbctl.commands.ota._save_device_raw", return_value={}) as save_raw,
    ):
        result = runner.invoke(
            app, ["ota", "assign", "Firmware 1.0", ASSIGN_DEVICE_UUID, "--version", "1.0"]
        )

    assert result.exit_code == 0, result.output
    assert save_raw.call_args.args[1]["firmwareId"]["id"] == "v1"


def test_assign_type_software_sets_software_field():
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _uuid_package(pkg_type="SOFTWARE")

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.resolve_device_id", return_value=ASSIGN_DEVICE_UUID),
        patch("tbctl.commands.ota.raw_get", return_value={"id": {"id": ASSIGN_DEVICE_UUID}}),
        patch("tbctl.commands.ota._save_device_raw", return_value={}) as save_raw,
    ):
        result = runner.invoke(
            app, ["ota", "assign", PKG_UUID, ASSIGN_DEVICE_UUID, "--type", "SOFTWARE"]
        )

    assert result.exit_code == 0, result.output
    body = save_raw.call_args.args[1]
    assert body["softwareId"] == {"id": PKG_UUID, "entityType": "OTA_PACKAGE"}
    assert "firmwareId" not in body


def test_assign_type_mismatch_fails():
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _uuid_package(pkg_type="SOFTWARE")

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.resolve_device_id", return_value=ASSIGN_DEVICE_UUID),
        patch("tbctl.commands.ota.raw_get", return_value={"id": {"id": ASSIGN_DEVICE_UUID}}),
        patch("tbctl.commands.ota._save_device_raw", return_value={}) as save_raw,
    ):
        result = runner.invoke(app, ["ota", "assign", PKG_UUID, ASSIGN_DEVICE_UUID])

    assert result.exit_code == 1
    assert "SOFTWARE" in result.stderr
    save_raw.assert_not_called()


def test_assign_version_with_uuid_fails():
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _uuid_package()

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.resolve_device_id", return_value=ASSIGN_DEVICE_UUID),
        patch("tbctl.commands.ota.raw_get", return_value={"id": {"id": ASSIGN_DEVICE_UUID}}),
        patch("tbctl.commands.ota._save_device_raw", return_value={}) as save_raw,
    ):
        result = runner.invoke(
            app, ["ota", "assign", PKG_UUID, ASSIGN_DEVICE_UUID, "--version", "1.0"]
        )

    assert result.exit_code == 1
    assert "cannot" in result.stderr
    save_raw.assert_not_called()


def test_assign_version_and_latest_fails():
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _uuid_package()

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.resolve_device_id", return_value=ASSIGN_DEVICE_UUID),
        patch("tbctl.commands.ota.raw_get", return_value={"id": {"id": ASSIGN_DEVICE_UUID}}),
        patch("tbctl.commands.ota._save_device_raw", return_value={}) as save_raw,
    ):
        result = runner.invoke(
            app,
            [
                "ota",
                "assign",
                "Firmware 1.0",
                ASSIGN_DEVICE_UUID,
                "--version",
                "1.0",
                "--latest",
            ],
        )

    assert result.exit_code == 1
    assert "mutually exclusive" in result.stderr
    save_raw.assert_not_called()


def test_assign_resolves_device_name():
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _uuid_package()

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.resolve_device_id", return_value=ASSIGN_DEVICE_UUID) as resolve,
        patch("tbctl.commands.ota.raw_get", return_value={"id": {"id": ASSIGN_DEVICE_UUID}}),
        patch("tbctl.commands.ota._save_device_raw", return_value={}),
    ):
        result = runner.invoke(app, ["ota", "assign", PKG_UUID, "sensor-1"])

    assert result.exit_code == 0, result.output
    resolve.assert_called_once_with("default", "sensor-1")


# --- unassign command ---


def test_unassign_clears_firmware():
    device = {"id": {"id": ASSIGN_DEVICE_UUID}, "firmwareId": {"id": "abc-123"}}

    with (
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.resolve_device_id", return_value=ASSIGN_DEVICE_UUID),
        patch("tbctl.commands.ota.raw_get", return_value=device),
        patch("tbctl.commands.ota._save_device_raw", return_value={}) as save_raw,
    ):
        result = runner.invoke(app, ["ota", "unassign", ASSIGN_DEVICE_UUID])

    assert result.exit_code == 0, result.output
    assert save_raw.call_args.args[1]["firmwareId"] is None
    assert "Cleared FIRMWARE" in result.output


def test_unassign_idempotent_when_unset():
    device = {"id": {"id": ASSIGN_DEVICE_UUID}}

    with (
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.resolve_device_id", return_value=ASSIGN_DEVICE_UUID),
        patch("tbctl.commands.ota.raw_get", return_value=device),
        patch("tbctl.commands.ota._save_device_raw", return_value={}) as save_raw,
    ):
        result = runner.invoke(app, ["ota", "unassign", ASSIGN_DEVICE_UUID])

    assert result.exit_code == 0, result.output
    save_raw.assert_not_called()
    assert "no FIRMWARE package" in result.output


def test_unassign_software():
    device = {"id": {"id": ASSIGN_DEVICE_UUID}, "softwareId": {"id": "abc-123"}}

    with (
        patch("tbctl.commands.ota.device_api", return_value=MagicMock()),
        patch("tbctl.commands.ota.resolve_device_id", return_value=ASSIGN_DEVICE_UUID),
        patch("tbctl.commands.ota.raw_get", return_value=device),
        patch("tbctl.commands.ota._save_device_raw", return_value={}) as save_raw,
    ):
        result = runner.invoke(app, ["ota", "unassign", ASSIGN_DEVICE_UUID, "--type", "SOFTWARE"])

    assert result.exit_code == 0, result.output
    assert save_raw.call_args.args[1]["softwareId"] is None
    assert "Cleared SOFTWARE" in result.output


# --- Upload ---


def test_upload_file(tmp_path, monkeypatch):
    import hashlib

    monkeypatch.chdir(tmp_path)
    fw = tmp_path / "firmware.bin"
    payload = b"\x01\x02\x03firmware-bytes"
    fw.write_bytes(payload)
    expected_checksum = hashlib.sha256(payload).hexdigest()

    mock_api = MagicMock()

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.raw_post", return_value={"id": {"id": "new-pkg-id"}}) as post,
    ):
        result = runner.invoke(
            app,
            ["ota", "upload", str(fw), "-T", "fw", "-v", "1.0", "-p", PROFILE_UUID],
        )

    assert result.exit_code == 0, result.output
    path_arg, body = post.call_args.args[1], post.call_args.args[2]
    assert path_arg == "/api/otaPackage"
    assert body["title"] == "fw"
    assert body["version"] == "1.0"
    assert body["type"] == "FIRMWARE"
    assert body["usesUrl"] is False
    assert body["deviceProfileId"]["id"] == PROFILE_UUID
    # fileName and checksumAlgorithm are set by the data step, not the info step
    assert "fileName" not in body
    assert "checksumAlgorithm" not in body
    mock_api.save_ota_package_data.assert_called_once_with(
        ota_package_id="new-pkg-id",
        checksum_algorithm="SHA256",
        file=("firmware.bin", payload),
        checksum=expected_checksum,
    )
    assert "new-pkg-id" in result.output


def test_upload_url():
    mock_api = MagicMock()

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.raw_post", return_value={"id": {"id": "url-pkg-id"}}) as post,
    ):
        result = runner.invoke(
            app,
            [
                "ota",
                "upload",
                "--url",
                "http://example.com/fw.bin",
                "-T",
                "fw",
                "-v",
                "2.0",
                "-p",
                PROFILE_UUID,
            ],
        )

    assert result.exit_code == 0, result.output
    body = post.call_args.args[2]
    assert body["usesUrl"] is True
    assert body["url"] == "http://example.com/fw.bin"
    mock_api.save_ota_package_data.assert_not_called()
    assert "url-pkg-id" in result.output


def test_upload_requires_device_profile(tmp_path):
    fw = tmp_path / "firmware.bin"
    fw.write_bytes(b"data")
    mock_api = MagicMock()

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.raw_post") as post,
    ):
        result = runner.invoke(app, ["ota", "upload", str(fw), "-T", "fw", "-v", "1.0"])

    assert result.exit_code != 0
    assert "device-profile" in _strip_ansi(result.output).lower()
    post.assert_not_called()


def test_upload_requires_source():
    mock_api = MagicMock()

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.raw_post") as post,
    ):
        result = runner.invoke(app, ["ota", "upload", "-T", "fw", "-v", "1.0", "-p", PROFILE_UUID])

    assert result.exit_code != 0
    assert "exactly one" in result.stderr.lower()
    post.assert_not_called()


def test_upload_file_and_url_conflict(tmp_path):
    fw = tmp_path / "firmware.bin"
    fw.write_bytes(b"data")
    mock_api = MagicMock()

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.raw_post") as post,
    ):
        result = runner.invoke(
            app,
            [
                "ota",
                "upload",
                str(fw),
                "--url",
                "http://example.com/fw.bin",
                "-T",
                "fw",
                "-v",
                "1.0",
                "-p",
                PROFILE_UUID,
            ],
        )

    assert result.exit_code != 0
    assert "exactly one" in result.stderr.lower()
    post.assert_not_called()


def test_upload_invalid_type(tmp_path):
    fw = tmp_path / "firmware.bin"
    fw.write_bytes(b"data")
    mock_api = MagicMock()

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.raw_post") as post,
    ):
        result = runner.invoke(
            app,
            ["ota", "upload", str(fw), "-T", "fw", "-v", "1.0", "-p", PROFILE_UUID, "-t", "BOGUS"],
        )

    assert result.exit_code != 0
    assert "FIRMWARE or SOFTWARE" in result.stderr
    post.assert_not_called()


def test_upload_resolves_device_profile_name(tmp_path):
    fw = tmp_path / "firmware.bin"
    fw.write_bytes(b"data")
    mock_api = MagicMock()

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.raw_post", return_value={"id": {"id": "new-pkg-id"}}) as post,
        patch("tbctl.commands.ota.resolve_profile_id", return_value=PROFILE_UUID) as rp,
    ):
        result = runner.invoke(
            app,
            ["ota", "upload", str(fw), "-T", "fw", "-v", "1.0", "-p", "thermostat"],
        )

    assert result.exit_code == 0, result.output
    rp.assert_called_once()
    body = post.call_args.args[2]
    assert body["deviceProfileId"]["id"] == PROFILE_UUID
    assert body["deviceProfileId"]["entityType"] == "DEVICE_PROFILE"


def test_upload_api_exception(tmp_path):
    from tb_client.exceptions import ApiException

    fw = tmp_path / "firmware.bin"
    fw.write_bytes(b"data")
    mock_api = MagicMock()

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch(
            "tbctl.commands.ota.raw_post",
            side_effect=ApiException(status=400, reason="Bad Request"),
        ),
    ):
        result = runner.invoke(
            app, ["ota", "upload", str(fw), "-T", "fw", "-v", "1.0", "-p", PROFILE_UUID]
        )

    assert result.exit_code != 0
    assert "400" in result.stderr


def test_upload_rolls_back_on_data_failure(tmp_path):
    from tb_client.exceptions import ApiException

    fw = tmp_path / "firmware.bin"
    fw.write_bytes(b"data")
    mock_api = MagicMock()
    mock_api.save_ota_package_data.side_effect = ApiException(status=400, reason="Bad Request")

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch("tbctl.commands.ota.raw_post", return_value={"id": {"id": "pkg-x"}}),
    ):
        result = runner.invoke(
            app, ["ota", "upload", str(fw), "-T", "fw", "-v", "1.0", "-p", PROFILE_UUID]
        )

    assert result.exit_code != 0
    assert "400" in result.stderr
    mock_api.delete_ota_package.assert_called_once_with(ota_package_id="pkg-x")


def test_upload_error_shows_server_message_not_raw_json(tmp_path):
    from tb_client.exceptions import ApiException

    fw = tmp_path / "firmware.bin"
    fw.write_bytes(b"data")
    body = (
        '{"status":400,"message":"OtaPackage with such title and version already '
        'exists!","errorCode":31}'
    )
    mock_api = MagicMock()

    with (
        patch("tbctl.commands.ota._get_api", return_value=mock_api),
        patch(
            "tbctl.commands.ota.raw_post",
            side_effect=ApiException(status=400, body=body),
        ),
    ):
        result = runner.invoke(
            app, ["ota", "upload", str(fw), "-T", "fw", "-v", "1.0", "-p", PROFILE_UUID]
        )

    assert result.exit_code != 0
    assert "OtaPackage with such title and version already exists!" in result.stderr
    assert "errorCode" not in result.stderr
    assert "{" not in result.stderr


def test_upload_body_serialises_all_fields():
    """Regression: the generated model dropped every field, sending an empty body."""
    from tb_client.api_client import ApiClient
    from tbctl.commands.ota import _info_body

    body = _info_body(
        title="application-ox_label_legacy@13.2.0/nrf9151/ns",
        version="0.12.3-debug",
        pkg_type="FIRMWARE",
        profile_id=PROFILE_UUID,
        content_type=None,
        url=None,
    )
    sanitised = ApiClient().sanitize_for_serialization(body)
    assert sanitised["title"] == "application-ox_label_legacy@13.2.0/nrf9151/ns"
    assert sanitised["version"] == "0.12.3-debug"
    assert sanitised["type"] == "FIRMWARE"
    assert sanitised["deviceProfileId"]["id"] == PROFILE_UUID


# --- list --version (client-side version filter) ---


def _page(data, total=None):
    page = MagicMock()
    page.data = data
    page.total_elements = total if total is not None else len(data)
    return page


def test_list_version_filters_client_side():
    mock_api = MagicMock()
    pkgs = [
        _mock_package("id-1", "FW", "1.0"),
        _mock_package("id-2", "FW", "0.12.3-debug"),
        _mock_package("id-3", "FW", "2.0"),
    ]
    mock_api.get_ota_packages.return_value = _page(pkgs, total=3)

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list", "--version", "0.12"])

    assert result.exit_code == 0, result.output
    assert "id-2" in result.output
    assert "id-1" not in result.output
    assert "id-3" not in result.output


def test_list_version_case_insensitive():
    mock_api = MagicMock()
    pkgs = [_mock_package("id-2", "FW", "0.12.3-debug")]
    mock_api.get_ota_packages.return_value = _page(pkgs, total=1)

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list", "--version", "DEBUG"])

    assert result.exit_code == 0, result.output
    assert "id-2" in result.output


def test_list_version_paginates_all_pages():
    mock_api = MagicMock()
    page0 = _page(
        [_mock_package("id-1", "FW", "1.0"), _mock_package("id-2", "FW", "0.12.3")], total=3
    )
    page1 = _page([_mock_package("id-3", "FW", "0.12.9")], total=3)
    mock_api.get_ota_packages.side_effect = [page0, page1]

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list", "--version", "0.12"])

    assert result.exit_code == 0, result.output
    assert "id-2" in result.output
    assert "id-3" in result.output
    assert "id-1" not in result.output
    calls = mock_api.get_ota_packages.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["page"] == 0
    assert calls[1].kwargs["page"] == 1


def test_list_version_combines_with_search():
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value = _page(
        [_mock_package("id-2", "app-fw", "0.12.3")], total=1
    )

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list", "--search", "app-fw", "--version", "0.12"])

    assert result.exit_code == 0, result.output
    assert mock_api.get_ota_packages.call_args.kwargs["text_search"] == "app-fw"
    assert "id-2" in result.output


def test_list_version_no_match():
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value = _page([_mock_package("id-1", "FW", "1.0")], total=1)

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list", "--version", "9.9"])

    assert result.exit_code == 0
    assert "No OTA packages found" in result.output


def test_list_version_json():
    mock_api = MagicMock()
    keep = _mock_package("id-2", "FW", "0.12.3-debug")
    keep.model_dump.return_value = {"id": {"id": "id-2"}, "version": "0.12.3-debug"}
    drop = _mock_package("id-1", "FW", "1.0")
    drop.model_dump.return_value = {"id": {"id": "id-1"}, "version": "1.0"}
    mock_api.get_ota_packages.return_value = _page([keep, drop], total=2)

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list", "--version", "0.12", "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert [p["version"] for p in data] == ["0.12.3-debug"]


def test_list_version_device_profile_path_paginates():
    mock_api = MagicMock()
    page0 = _page([_mock_package("id-1", "FW", "0.12.1")], total=2)
    page1 = _page([_mock_package("id-2", "FW", "9.9")], total=2)
    mock_api.get_ota_packages1.side_effect = [page0, page1]

    with patch("tbctl.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(
            app,
            [
                "ota",
                "list",
                "--device-profile",
                _LIST_PROFILE_UUID,
                "--type",
                "FIRMWARE",
                "--version",
                "0.12",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "id-1" in result.output
    assert "id-2" not in result.output
    assert mock_api.get_ota_packages1.call_count == 2
    mock_api.get_ota_packages.assert_not_called()
