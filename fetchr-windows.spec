# PyInstaller recipe for the Windows .exe (used by GitHub Actions)
from kivy_deps import sdl2, glew
from PyInstaller.utils.hooks import collect_submodules, collect_all

ff_datas, ff_bins, ff_hidden = collect_all("imageio_ffmpeg")

a = Analysis(
    ["main.py"],
    datas=ff_datas,
    binaries=ff_bins,
    hiddenimports=collect_submodules("yt_dlp") + ff_hidden + ["certifi"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],
    name="Fetchr",
    console=False,
    upx=False,
)
