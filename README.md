# Fetchr — video downloader

Download videos and audio from YouTube, Instagram, TikTok, Facebook, X and 1000+ other sites.
One codebase runs on **Android** and **Windows/Mac/Linux**. Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Features
- Paste a link, or **share straight from Instagram / TikTok / YouTube → Fetchr** (Android)
- Quality: Best, 1080p, 720p, 480p, 360p, Audio only
- Live progress, speed and time left
- Saves to `Download/Fetchr` on the phone (shows in Gallery) or your `Downloads` folder on PC — change it any time with **Change**
- **Stop** cancels a download (and deletes the unfinished file); **×** clears the link box

## Get the apps from GitHub (no coding needed)
1. Create a new repository on GitHub and upload **all** these files, including the hidden `.github` folder
   (easiest: GitHub Desktop, or drag the unzipped folder into "Add file → Upload files").
2. Open the **Actions** tab. The "Build Fetchr" workflow starts on every push (or click **Run workflow**).
3. When it finishes (Android ~30–40 min the first time, faster after), open the run and download:
   - **Fetchr-Android-APK** → unzip, copy the `.apk` to your phone, tap to install (allow "Install unknown apps").
   - **Fetchr-Windows-EXE** → unzip and run `Fetchr.exe`.

The workflow also rebuilds on the 1st of every month, so you always get a fresh yt-dlp —
when a site changes and downloads start failing, just reinstall the latest build.

## Run on a computer from source
```
pip install -r requirements.txt
python main.py
```
Install [ffmpeg](https://ffmpeg.org) (or `pip install imageio-ffmpeg`) for full HD and MP3.

## Notes
- On Android, videos come as a single file that already contains audio (usually up to 720p on YouTube);
  1080p+ YouTube and MP3 conversion need ffmpeg, which the Windows build includes.
- Private posts or anything behind a login can't be downloaded.
- Only download content you own or have permission to save; respect each platform's terms.

## License
Free and open source under the MIT License — anyone can use, copy or modify it.
