"""
Fetchr - video downloader for YouTube, Instagram, TikTok, Facebook, X and 1000+ sites.
One codebase: runs on Android (built by GitHub Actions) and on Windows/Mac/Linux.
Engine: yt-dlp (https://github.com/yt-dlp/yt-dlp)
"""
import json
import os
import re
import shutil
import sys
import threading

# The Windows .exe has no console: give Python real (silent) output streams
# so nothing crashes trying to print.
for _name in ("stdout", "stderr"):
    if not hasattr(getattr(sys, _name, None), "write"):
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))

os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.utils import platform

if platform not in ("android", "ios"):
    from kivy.config import Config
    Config.set("graphics", "width", "420")
    Config.set("graphics", "height", "760")

from kivy.app import App
from kivy.lang import Builder
from kivy.clock import Clock, mainthread
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ListProperty

# HTTPS certificates (needed on Android)
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:
    pass

import yt_dlp

URL_RE = re.compile(r"https?://\S+")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
QUALITIES = ["Best", "1080p", "720p", "480p", "360p", "Audio only"]

KV = """
#:import dp kivy.metrics.dp
BoxLayout:
    orientation: 'vertical'
    padding: dp(16)
    spacing: dp(10)
    canvas.before:
        Color:
            rgba: 0.07, 0.07, 0.09, 1
        Rectangle:
            pos: self.pos
            size: self.size

    Label:
        text: '[b]Fetchr[/b]'
        markup: True
        font_size: '28sp'
        size_hint_y: None
        height: dp(44)
        text_size: self.size
        halign: 'left'
        valign: 'middle'
    Label:
        text: 'YouTube, Instagram, TikTok, Facebook, X and 1000+ sites'
        color: .6, .6, .65, 1
        font_size: '13sp'
        size_hint_y: None
        height: self.texture_size[1]
        text_size: self.width, None
        halign: 'left'

    BoxLayout:
        size_hint_y: None
        height: dp(50)
        spacing: dp(8)
        TextInput:
            id: url
            hint_text: 'Paste a video link'
            multiline: False
            write_tab: False
            font_size: '15sp'
            padding: [dp(12), dp(14)]
            background_color: .15, .15, .18, 1
            foreground_color: 1, 1, 1, 1
            cursor_color: 1, 1, 1, 1
            hint_text_color: .5, .5, .55, 1
            on_text_validate: app.start_download()
        Button:
            text: 'Paste'
            size_hint_x: None
            width: dp(76)
            background_normal: ''
            background_color: .22, .22, .27, 1
            on_release: app.paste()
        Button:
            text: '\u00d7'
            font_size: '24sp'
            size_hint_x: None
            width: dp(50)
            background_normal: ''
            background_color: .22, .22, .27, 1
            on_release: app.clear_link()

    Spinner:
        id: quality
        text: 'Best'
        values: app.qualities
        size_hint_y: None
        height: dp(46)
        background_normal: ''
        background_color: .15, .15, .18, 1

    Button:
        text: ('Stopping...' if app.stopping else 'Stop') if app.busy else 'Download'
        disabled: app.stopping
        size_hint_y: None
        height: dp(54)
        font_size: '17sp'
        bold: True
        background_normal: ''
        background_disabled_normal: ''
        background_color: (.35, .35, .4, 1) if app.busy else (.86, .15, .30, 1)
        on_release: app.stop_download() if app.busy else app.start_download()

    ProgressBar:
        max: 100
        value: app.progress
        size_hint_y: None
        height: dp(14)

    Label:
        text: app.status
        color: .88, .88, .92, 1
        font_size: '13sp'
        size_hint_y: None
        height: max(dp(24), self.texture_size[1])
        text_size: self.width, None
        halign: 'left'
        valign: 'top'
    BoxLayout:
        size_hint_y: None
        height: dp(34)
        spacing: dp(8)
        Label:
            text: 'Saving to:'
            color: .55, .55, .6, 1
            font_size: '12sp'
            size_hint_x: None
            width: self.texture_size[0]
        Label:
            text: app.save_dir
            color: .75, .75, .8, 1
            font_size: '12sp'
            text_size: self.size
            halign: 'left'
            valign: 'middle'
            shorten: True
            shorten_from: 'left'
        Button:
            text: 'Change'
            font_size: '13sp'
            size_hint_x: None
            width: dp(76)
            disabled: app.busy
            background_normal: ''
            background_color: .22, .22, .27, 1
            on_release: app.change_folder()

    Label:
        text: '[b]Recent[/b]'
        markup: True
        font_size: '15sp'
        size_hint_y: None
        height: dp(26)
        text_size: self.size
        halign: 'left'
    ScrollView:
        BoxLayout:
            id: history
            orientation: 'vertical'
            size_hint_y: None
            height: self.minimum_height
            spacing: dp(6)
"""


class QuietLogger:
    """Sends yt-dlp's messages nowhere instead of to a console window."""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def human_bytes(n):
    if not n:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


TRACKING_PARAMS = ("igsh", "igshid", "utm_", "_r", "_t", "is_from_webapp", "sender_device", "si", "mibextid", "rdid", "share_")


def clean_url(url):
    """Remove share-tracking junk (igsh=, utm_=, ...) that some sites choke on."""
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    try:
        parts = urlsplit(url.strip())
        keep = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                if not k.lower().startswith(TRACKING_PARAMS)]
        return urlunsplit(parts._replace(query=urlencode(keep)))
    except Exception:
        return url


def friendly_error(msg):
    msg = ANSI_RE.sub("", msg).replace("ERROR:", "").strip()
    low = msg.lower()
    if "empty media response" in low or "rate-limit" in low or "rate limit" in low:
        return ("Instagram refused this download (it often blocks requests without a login, "
                "especially on mobile data). Try again later, on Wi-Fi, or on the Windows app.")
    if "login" in low or "logged-in" in low or "sign in" in low or "private" in low:
        return "This post is private or needs a login, so it can't be downloaded."
    if "requested format is not available" in low or "no downloadable video format" in low:
        return "No downloadable version of this video was found. Try another quality, or 'Audio only'."
    if "unsupported url" in low:
        return "That site or link isn't supported."
    if "unable to download webpage" in low or "network" in low or "timed out" in low:
        return "Network problem - check your connection and try again."
    return msg[:220]


def android_merge(video_path, audio_path, out_path):
    """Combine a video-only MP4 and an audio-only M4A into one MP4 using Android's MediaMuxer."""
    from jnius import autoclass

    MediaExtractor = autoclass("android.media.MediaExtractor")
    MediaMuxer = autoclass("android.media.MediaMuxer")
    OutputFormat = autoclass("android.media.MediaMuxer$OutputFormat")
    BufferInfo = autoclass("android.media.MediaCodec$BufferInfo")
    ByteBuffer = autoclass("java.nio.ByteBuffer")

    muxer = MediaMuxer(out_path, OutputFormat.MUXER_OUTPUT_MPEG_4)
    tracks = []
    try:
        for path in (video_path, audio_path):
            ex = MediaExtractor()
            ex.setDataSource(path)
            ex.selectTrack(0)
            tracks.append((ex, muxer.addTrack(ex.getTrackFormat(0))))
        muxer.start()
        buf = ByteBuffer.allocateDirect(8 * 1024 * 1024)
        info = BufferInfo()
        for ex, track in tracks:
            while True:
                size = ex.readSampleData(buf, 0)
                if size < 0:
                    break
                info.set(0, size, ex.getSampleTime(), ex.getSampleFlags())
                muxer.writeSampleData(track, buf, info)
                ex.advance()
        muxer.stop()
    finally:
        for ex, _ in tracks:
            ex.release()
        muxer.release()


def windows_pick_folder(title):
    """Native Windows 'Browse for folder' dialog (no extra libraries needed)."""
    import ctypes
    from ctypes import wintypes

    class BROWSEINFOW(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", wintypes.HWND), ("pidlRoot", ctypes.c_void_p),
            ("pszDisplayName", wintypes.LPWSTR), ("lpszTitle", wintypes.LPCWSTR),
            ("ulFlags", wintypes.UINT), ("lpfn", ctypes.c_void_p),
            ("lParam", wintypes.LPARAM), ("iImage", ctypes.c_int),
        ]

    shell32, ole32, user32 = ctypes.windll.shell32, ctypes.windll.ole32, ctypes.windll.user32
    shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFOW)]
    shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
    shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
    shell32.SHGetPathFromIDListW.restype = wintypes.BOOL
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    user32.GetActiveWindow.restype = wintypes.HWND
    ole32.CoInitialize(None)

    name = ctypes.create_unicode_buffer(260)
    info = BROWSEINFOW()
    info.hwndOwner = user32.GetActiveWindow()
    info.pszDisplayName = ctypes.cast(name, wintypes.LPWSTR)
    info.lpszTitle = title
    info.ulFlags = 0x0001 | 0x0040  # only real folders + modern resizable dialog with "New Folder"
    pidl = shell32.SHBrowseForFolderW(ctypes.byref(info))
    if not pidl:
        return None
    path = ctypes.create_unicode_buffer(1024)
    ok = shell32.SHGetPathFromIDListW(pidl, path)
    ole32.CoTaskMemFree(pidl)
    return path.value if ok and path.value else None


class FetchrApp(App):
    status = StringProperty("Paste a link and tap Download.")
    progress = NumericProperty(0)
    busy = BooleanProperty(False)
    stopping = BooleanProperty(False)
    save_dir = StringProperty("")
    qualities = ListProperty(QUALITIES)

    # ---------- setup ----------
    def build(self):
        self.title = "Fetchr"
        self.ffmpeg = self._find_ffmpeg()  # desktop only; enables HD merge + MP3
        self.cancel = threading.Event()
        self.job_files = set()
        self.stage = "Downloading"
        self.save_dir = self._find_save_dir()
        return Builder.load_string(KV)

    def on_start(self):
        if platform == "android":
            self._android_setup()

    def _find_ffmpeg(self):
        found = shutil.which("ffmpeg")
        if found:
            return found
        try:  # bundled inside the Windows .exe
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None

    # ---------- settings (remembered save folder) ----------
    def _settings_file(self):
        return os.path.join(self.user_data_dir, "fetchr_settings.json")

    def _load_settings(self):
        try:
            with open(self._settings_file(), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_settings(self, **changes):
        data = self._load_settings()
        data.update(changes)
        try:
            os.makedirs(self.user_data_dir, exist_ok=True)
            with open(self._settings_file(), "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass

    @staticmethod
    def _writable(d):
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".fetchr_probe")
            open(probe, "w").close()
            os.remove(probe)
            return True
        except Exception:
            return False

    def _find_save_dir(self):
        saved = self._load_settings().get("save_dir")
        if saved and self._writable(saved):
            return saved
        candidates = []
        if platform == "android":
            try:
                from android.storage import primary_external_storage_path
                candidates.append(os.path.join(primary_external_storage_path(), "Download", "Fetchr"))
            except Exception:
                pass
        else:
            candidates.append(os.path.join(os.path.expanduser("~"), "Downloads"))
        candidates.append(os.path.join(self.user_data_dir, "downloads"))
        for d in candidates:
            if self._writable(d):
                return d
        return self.user_data_dir

    def _android_setup(self):
        try:
            from android.permissions import request_permissions, Permission

            def on_perms(perms, grants):
                Clock.schedule_once(lambda dt: setattr(self, "save_dir", self._find_save_dir()))

            request_permissions(
                [Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE], on_perms
            )
        except Exception:
            pass
        # Receive links shared from Instagram / TikTok / YouTube ("Share -> Fetchr")
        try:
            from android import activity
            from jnius import autoclass
            activity.bind(on_new_intent=self._on_new_intent)
            self._on_new_intent(autoclass("org.kivy.android.PythonActivity").mActivity.getIntent())
        except Exception:
            pass

    def _on_new_intent(self, intent):
        try:
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            if intent is not None and intent.getAction() == Intent.ACTION_SEND:
                text = intent.getStringExtra(Intent.EXTRA_TEXT)
                if text:
                    Clock.schedule_once(lambda dt: self._set_url(text, shared=True))
        except Exception:
            pass

    # ---------- UI actions ----------
    def _set_url(self, text, shared=False):
        m = URL_RE.search(text or "")
        if m:
            self.root.ids.url.text = m.group(0)
            self.status = "Link received - choose quality and tap Download." if shared else "Link pasted."
        else:
            self.status = "No link found in that text."

    def paste(self):
        self._set_url(Clipboard.paste())

    def clear_link(self):
        self.root.ids.url.text = ""
        if not self.busy:
            self.status = "Paste a link and tap Download."
            self.progress = 0

    def stop_download(self):
        if self.busy and not self.stopping:
            self.stopping = True
            self.cancel.set()
            self.status = "Stopping..."

    # ---------- save folder ----------
    def change_folder(self):
        if self.busy:
            return
        if platform == "android":
            self._android_folder_popup()
            return
        chosen = None
        if platform == "win":
            try:
                chosen = windows_pick_folder("Choose where Fetchr saves downloads")
            except Exception:
                chosen = None
        else:
            try:
                import tkinter
                from tkinter import filedialog
                root = tkinter.Tk()
                root.withdraw()
                chosen = filedialog.askdirectory(initialdir=self.save_dir) or None
                root.destroy()
            except Exception:
                chosen = None
        if chosen:
            self._use_folder(chosen)

    def _use_folder(self, folder):
        if self._writable(folder):
            self.save_dir = folder
            self._save_settings(save_dir=folder)
            self.status = "Downloads will be saved to: " + folder
        else:
            self.status = "Can't save to that folder - please choose another one."

    def _android_folder_popup(self):
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.popup import Popup
        try:
            from android.storage import primary_external_storage_path
            base = primary_external_storage_path()
        except Exception:
            base = "/storage/emulated/0"
        choices = [
            ("Download / Fetchr", os.path.join(base, "Download", "Fetchr")),
            ("Download", os.path.join(base, "Download")),
            ("Movies / Fetchr", os.path.join(base, "Movies", "Fetchr")),
            ("Pictures / Fetchr", os.path.join(base, "Pictures", "Fetchr")),
            ("Music / Fetchr", os.path.join(base, "Music", "Fetchr")),
        ]
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        popup = Popup(title="Save downloads to", content=box, size_hint=(.9, None),
                      height=dp(80 + 56 * len(choices)))
        for label, path in choices:
            current = os.path.normpath(path) == os.path.normpath(self.save_dir)
            btn = Button(text=("> " if current else "") + label, size_hint_y=None, height=dp(48),
                         background_normal="", background_color=(.22, .22, .27, 1))
            btn.bind(on_release=lambda _b, p=path: (popup.dismiss(), self._use_folder(p)))
            box.add_widget(btn)
        popup.open()

    def start_download(self):
        if self.busy:
            return
        m = URL_RE.search(self.root.ids.url.text.strip())
        if not m:
            self.status = "Please paste a valid link first."
            return
        url = clean_url(m.group(0))
        self.cancel.clear()
        self.job_files = set()
        self.stopping = False
        self.busy = True
        self.progress = 0
        self.status = "Fetching video info..."
        quality = self.root.ids.quality.text
        threading.Thread(target=self._worker, args=(url, quality), daemon=True).start()

    # ---------- download engine ----------
    def _build_opts(self, quality):
        opts = {
            "outtmpl": os.path.join(self.save_dir, "%(title).80s [%(id)s].%(ext)s"),
            "noplaylist": True,
            "windowsfilenames": True,
            "progress_hooks": [self._hook],
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": QuietLogger(),
            "retries": 5,
            "fragment_retries": 5,
            "concurrent_fragment_downloads": 4,
        }
        if self.ffmpeg:
            opts["ffmpeg_location"] = self.ffmpeg

        if quality == "Audio only":
            if self.ffmpeg:
                opts["format"] = "ba/b"
                opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                ]
            else:
                opts["format"] = "ba[ext=m4a]/ba/b"
            return opts

        lim = "" if quality == "Best" else f"[height<={int(quality[:-1])}]"
        if self.ffmpeg:
            # separate HD video + audio streams, merged into one MP4
            opts["format"] = f"bv*{lim}+ba/b{lim}/b"
            opts["merge_output_format"] = "mp4"
        else:
            # single file that already contains video + audio (no merging needed)
            opts["format"] = f"b{lim}[ext=mp4]/b{lim}/b"
        return opts

    def _check_cancel(self):
        if self.cancel.is_set():
            raise yt_dlp.utils.DownloadCancelled("Stopped by user")

    def _hook(self, d):
        for key in ("tmpfilename", "filename"):
            if d.get(key):
                self.job_files.add(d[key])
        self._check_cancel()
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            pct = (done * 100 / total) if total else 0
            parts = [f"{pct:.0f}%" if total else human_bytes(done)]
            if d.get("speed"):
                parts.append(f"{human_bytes(d['speed'])}/s")
            if d.get("eta") is not None:
                parts.append(f"{int(d['eta'])}s left")
            self._update(pct, self.stage + " - " + " - ".join(parts))
        elif d.get("status") == "finished":
            self._update(100, "Finishing up...")

    @mainthread
    def _update(self, pct, text):
        self.progress = pct
        self.status = text

    def _worker(self, url, quality):
        self.stage = "Downloading"
        try:
            if platform == "android" and not self.ffmpeg and quality != "Audio only":
                title, path = self._android_video(url, quality)
                self._finish(True, title, path)
                return
            with yt_dlp.YoutubeDL(self._build_opts(quality)) as ydl:
                info = ydl.extract_info(url, download=True)
                if info.get("entries"):
                    info = info["entries"][0]
                title = info.get("title") or "video"
                path = (info.get("requested_downloads") or [{}])[0].get("filepath")
            self._finish(True, title, path)
        except Exception as e:
            if self.cancel.is_set():
                self._remove_partial_files()
                self._finish(None, "Download cancelled", None)
            else:
                self._finish(False, friendly_error(str(e)), None)

    def _remove_partial_files(self):
        for f in list(self.job_files):
            for path in (f, f + ".part", f + ".ytdl"):
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                except Exception:
                    pass

    # ---------- Android: separate video + audio, merged with Android's own MediaMuxer ----------
    def _android_video(self, url, quality):
        """YouTube (and some other sites) now mostly serve video and audio as separate
        streams. Desktop merges them with ffmpeg; Android has no ffmpeg, so we download
        both and merge them with the phone's built-in MediaMuxer."""
        import copy

        lim = None if quality == "Best" else int(quality[:-1])
        base = self._build_opts(quality)
        base.pop("format", None)

        self._update(0, "Fetching video info...")
        with yt_dlp.YoutubeDL(base) as ydl:
            info = ydl.extract_info(url, download=False)
        self._check_cancel()
        if info.get("entries"):
            info = info["entries"][0]
        title = info.get("title") or "video"
        fmts = info.get("formats") or [info]

        def fits(f):
            return lim is None or (f.get("height") or 0) <= lim

        def plain_http(f):
            return (f.get("protocol") or "https") in ("http", "https")

        def rank(f):
            return (f.get("height") or 0, f.get("tbr") or f.get("abr") or 0)

        combined = [f for f in fmts if f.get("vcodec") != "none" and f.get("acodec") != "none" and fits(f)]
        videos = [f for f in fmts if f.get("acodec") == "none" and f.get("ext") == "mp4"
                  and (f.get("vcodec") or "").startswith(("avc1", "h264")) and fits(f) and plain_http(f)]
        audios = [f for f in fmts if f.get("vcodec") == "none" and f.get("ext") in ("m4a", "mp4")
                  and (f.get("acodec") or "").startswith("mp4a") and plain_http(f)]

        best_c = max(combined, key=rank) if combined else None
        best_v = max(videos, key=rank) if videos else None
        best_a = max(audios, key=lambda f: f.get("abr") or f.get("tbr") or 0) if audios else None

        def grab(fmt_id, outtmpl):
            fresh = copy.deepcopy(info)
            for key in ("requested_formats", "requested_downloads", "url", "format_id",
                        "format", "protocol", "ext", "vcodec", "acodec", "filepath", "_filename"):
                fresh.pop(key, None)
            self._check_cancel()
            opts = dict(base, format=fmt_id, outtmpl=outtmpl)
            with yt_dlp.YoutubeDL(opts) as ydl:
                done = ydl.process_ie_result(fresh, download=True)
            return (done.get("requested_downloads") or [{}])[0].get("filepath")

        split_better = best_v and best_a and (not best_c or rank(best_v)[0] > rank(best_c)[0])
        if not split_better:
            if not best_c:
                raise RuntimeError("No downloadable video format was found for this link.")
            return title, grab(best_c["format_id"], base["outtmpl"])

        part = os.path.join(self.save_dir, "%(title).80s [%(id)s].part-%(format_id)s.%(ext)s")
        self.stage = "Downloading video (1/2)"
        vpath = grab(best_v["format_id"], part)
        self.stage = "Downloading audio (2/2)"
        apath = grab(best_a["format_id"], part)

        self._check_cancel()
        self._update(100, "Merging video and audio...")
        final = re.sub(r"\.part-[^.]+\.[^.]+$", ".mp4", vpath)
        try:
            android_merge(vpath, apath, final)
        finally:
            for p in (vpath, apath):
                try:
                    os.remove(p)
                except Exception:
                    pass
        return title, final

    @mainthread
    def _finish(self, ok, text, path):
        self.busy = False
        self.stopping = False
        if ok:
            self.progress = 100
            self.status = f"Saved: {text}"
            self.root.ids.url.text = ""
            self._scan_media(path)
        elif ok is None:
            self.progress = 0
            self.status = "Stopped - the unfinished file was deleted."
        else:
            self.progress = 0
            self.status = f"Failed: {text}"
        prefix = "Done:  " if ok else ("Stopped:  " if ok is None else "Failed:  ")
        color = (.55, .9, .6, 1) if ok else ((.75, .75, .8, 1) if ok is None else (1, .5, .5, 1))
        row = Label(
            text=prefix + text,
            color=color,
            font_size="13sp",
            size_hint_y=None,
            height=dp(36),
            halign="left",
            valign="middle",
            shorten=True,
        )
        row.bind(size=lambda w, s: setattr(w, "text_size", s))
        history = self.root.ids.history
        history.add_widget(row, index=len(history.children))

    def _scan_media(self, path):
        """Make the file show up in the phone's Gallery / Music apps."""
        if platform != "android" or not path:
            return
        try:
            from jnius import autoclass
            ctx = autoclass("org.kivy.android.PythonActivity").mActivity
            autoclass("android.media.MediaScannerConnection").scanFile(ctx, [path], None, None)
        except Exception:
            pass


if __name__ == "__main__":
    FetchrApp().run()
