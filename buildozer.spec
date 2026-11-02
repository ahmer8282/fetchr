[app]
title = Fetchr
package.name = fetchr
package.domain = io.github.fetchrapp
source.dir = .
source.include_exts = py,png,jpg,kv,xml
source.exclude_dirs = bin,.buildozer,.github,build,dist
version = 1.0.0

# charset_normalizer is pinned to its pure-Python wheel: python-for-android picks the
# Android-only wheel from PyPI otherwise, then fails to install it.
requirements = python3,kivy,yt-dlp,certifi,openssl,pyjnius,android,charset_normalizer@https://files.pythonhosted.org/packages/fc/ad/d07d7862a62ffa6d79d68074d14823243dd235a77c45262acbf6adeb28bf/charset_normalizer-3.5.2-py3-none-any.whl

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 34
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True

# Lets Instagram / TikTok / YouTube "Share" links straight into the app
android.manifest.intent_filters = intent_filters.xml
android.manifest.launch_mode = singleTask

# Pinned, tested python-for-android release (Python 3.14, Kivy 2.3.1)
p4a.branch = v2026.05.09

[buildozer]
log_level = 2
warn_on_root = 0
