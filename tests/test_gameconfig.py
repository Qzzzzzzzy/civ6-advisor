"""游戏配置改写测试。"""

from pathlib import Path

from civ6_advisor import gameconfig as gc

SAMPLE = (
    ";; Civilization VI app options\r\n"
    "; Run in fullscreen mode\r\n"
    "FullScreen 1\r\n"
    "; Borderless window\r\n"
    "WindowedBorderless 0\r\n"
    "RenderWidth 2560\r\n"
    "RenderHeight 1440\r\n"
    "EnableTuner 0\r\n"
    ";EnableTuner 1\r\n"
)


def test_read_options_skips_comments():
    o = gc.read_options(SAMPLE)
    assert o["FullScreen"] == "1" and o["EnableTuner"] == "0" and o["RenderWidth"] == "2560"
    assert gc.describe_mode(o) == "独占全屏"


def test_patch_to_borderless_and_tuner():
    r = gc.patch_options(SAMPLE)
    o = gc.read_options(r.text)
    assert o["FullScreen"] == "0" and o["WindowedBorderless"] == "1" and o["EnableTuner"] == "1"
    assert r.borderless_key == "WindowedBorderless"
    assert gc.describe_mode(o) == "无边框全屏"
    assert ";EnableTuner 1\r\n" in r.text  # 注释原样保留
    assert r.text.count("\r\n") == SAMPLE.count("\r\n")  # 行尾风格不变
    assert not r.warnings


def test_patch_is_idempotent():
    once = gc.patch_options(SAMPLE).text
    again = gc.patch_options(once)
    assert not again.changed and again.text == once


def test_missing_keys_append_tuner_and_warn():
    r = gc.patch_options("FullScreen 1\nRenderWidth 1920")
    o = gc.read_options(r.text)
    assert o["EnableTuner"] == "1" and o["FullScreen"] == "0"
    assert r.warnings and "无边框" in r.warnings[0]
    assert r.text.endswith("EnableTuner 1\n")


def test_tuner_only_keeps_fullscreen():
    r = gc.patch_options(SAMPLE, borderless=False)
    assert gc.read_options(r.text)["FullScreen"] == "1"


def test_apply_and_restore(tmp_path: Path):
    p = tmp_path / "AppOptions.txt"
    p.write_bytes(SAMPLE.encode())
    r = gc.apply(p)
    assert r.changed and gc.has_backup(p)
    gc.apply(p)  # 第二次不覆盖最原始的备份
    assert gc.read_options(p.read_text())["EnableTuner"] == "1"
    assert gc.restore(p)
    assert p.read_bytes() == SAMPLE.encode() and not gc.has_backup(p)
    assert not gc.restore(p)


def test_find_sdk_from_library_list(tmp_path: Path):
    lib = tmp_path / "lib"
    (lib / "steamapps/common" / gc.SDK_DIR_NAME).mkdir(parents=True)
    assert gc.find_sdk([tmp_path / "none", lib]) == lib / "steamapps/common" / gc.SDK_DIR_NAME
    assert gc.find_sdk([tmp_path / "none"]) is None


def test_steam_libraries_parses_vdf(tmp_path: Path):
    (tmp_path / "steamapps").mkdir()
    (tmp_path / "steamapps/libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n "0" { "path" "C:\\\\Steam" }\n "1" { "path" "D:\\\\SteamLibrary" }\n}\n'
    )
    libs = gc.steam_libraries(tmp_path)
    assert Path("D:\\SteamLibrary") in libs and libs[0] == tmp_path
