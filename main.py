"""
Fetchr - video downloader for YouTube, Instagram, TikTok, Facebook, X and 1000+ sites.
One codebase: runs on Android (built by GitHub Actions) and on Windows/Mac/Linux.
Engine: yt-dlp (https://github.com/yt-dlp/yt-dlp)
"""
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
        text: 'YouTube - Instagram - TikTok - Facebook - X and 1000+ sites'
        color: .6, .6, .65, 1
        font_size: '13sp'
        size_hint_y: None
        height: dp(20)
        text_size: self.size
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
            width: dp(84)
            background_normal: ''
            background_color: .22, .22, .27, 1
            on_release: app.paste()

    Spinner:
        id: quality
        text: 'Best'
        values: app.qualities
        size_hint_y: None
        height: dp(46)
        background_normal: ''
        background_color: .15, .15, .18, 1

    Button:
        text: 'Downloading...' if app.busy else 'Download'
        disabled: app.busy
        size_hint_y: None
        height: dp(54)
        font_size: '17sp'
        bold: True
        background_normal: ''
        background_disabled_normal: ''
        background_color: (.4, .4, .45, 1) if app.busy else (.86, .15, .30, 1)
        on_release: app.start_download()

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
        height: dp(44)
        text_size: self.width, None
        halign: 'left'
        valign: 'top'
    Label:
        text: 'Saving to: ' + app.save_dir
        color: .5, .5, .55, 1
        font_size: '11sp'
        size_hint_y: None
        height: dp(28)
        text_size: self.width, None
        halign: 'left'
        shorten: True

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


def friendly_error(msg):
    msg = ANSI_RE.sub("", msg).replace("ERROR:", "").strip()
    low = msg.lower()
    if "login" in low or "sign in" in low or "private" in low:
        return "This post is private or needs a login, so it can't be downloaded."
    if "unsupported url" in low:
        return "That site or link isn't supported."
    if "unable to download webpage" in low or "network" in low or "timed out" in low:
        return "Network problem - check your connection and try again."
    return msg[:220]


class FetchrApp(App):
    status = StringProperty("Paste a link and tap Download.")
    progress = NumericProperty(0)
    busy = BooleanProperty(False)
    save_dir = StringProperty("")
    qualities = ListProperty(QUALITIES)

    # ---------- setup ----------
    def build(self):
        self.title = "Fetchr"
        self.ffmpeg = self._find_ffmpeg()  # desktop only; enables HD merge + MP3
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

    def _find_save_dir(self):
        candidates = []
        if platform == "android":
            try:
                from android.storage import primary_external_storage_path
                candidates.append(os.path.join(primary_external_storage_path(), "Download", "Fetchr"))
            except Exception:
                pass
        else:
            candidates.append(os.path.join(os.path.expanduser("~"), "Downloads", "Fetchr"))
        candidates.append(os.path.join(self.user_data_dir, "downloads"))
        for d in candidates:
            try:
                os.makedirs(d, exist_ok=True)
                probe = os.path.join(d, ".probe")
                open(probe, "w").close()
                os.remove(probe)
                return d
            except Exception:
                continue
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

    def start_download(self):
        if self.busy:
            return
        m = URL_RE.search(self.root.ids.url.text.strip())
        if not m:
            self.status = "Please paste a valid link first."
            return
        self.busy = True
        self.progress = 0
        self.status = "Fetching video info..."
        quality = self.root.ids.quality.text
        threading.Thread(target=self._worker, args=(m.group(0), quality), daemon=True).start()

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

    def _hook(self, d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            pct = (done * 100 / total) if total else 0
            parts = [f"{pct:.0f}%" if total else human_bytes(done)]
            if d.get("speed"):
                parts.append(f"{human_bytes(d['speed'])}/s")
            if d.get("eta") is not None:
                parts.append(f"{int(d['eta'])}s left")
            self._update(pct, "Downloading - " + " - ".join(parts))
        elif d.get("status") == "finished":
            self._update(100, "Finishing up...")

    @mainthread
    def _update(self, pct, text):
        self.progress = pct
        self.status = text

    def _worker(self, url, quality):
        try:
            with yt_dlp.YoutubeDL(self._build_opts(quality)) as ydl:
                info = ydl.extract_info(url, download=True)
                if info.get("entries"):
                    info = info["entries"][0]
                title = info.get("title") or "video"
                path = (info.get("requested_downloads") or [{}])[0].get("filepath")
            self._finish(True, title, path)
        except Exception as e:
            self._finish(False, friendly_error(str(e)), None)

    @mainthread
    def _finish(self, ok, text, path):
        self.busy = False
        if ok:
            self.progress = 100
            self.status = f"Saved: {text}"
            self.root.ids.url.text = ""
            self._scan_media(path)
        else:
            self.progress = 0
            self.status = f"Failed: {text}"
        row = Label(
            text=("Done:  " if ok else "Failed:  ") + text,
            color=(.55, .9, .6, 1) if ok else (1, .5, .5, 1),
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
