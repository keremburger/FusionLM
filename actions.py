"""
actions.py — FusionLM'in sohbet sırasında tetikleyebileceği yerel eylemler.

AI, bir eylem çağırmak istediğinde cevabının TAMAMI tek satırlık bir JSON
olur: {"action": "<isim>", "parameters": {...}}. chat_window.py bunu
yakalar, run_action() ile çalıştırır, sonucu tekrar modele vererek doğal
bir cümleyle kullanıcıya sunar. Normal sohbette bu JSON hiç görünmez.
"""
import json
import platform
import re
import shutil
import subprocess
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import psutil

_SYSTEM = platform.system()

ACTIONS_SYSTEM_PROMPT = """
You can also perform actions on the user's computer. When the user's
request clearly matches one of the actions below, respond with ONLY a
single-line JSON object — nothing else, no markdown fences, no extra text:
{"action": "<name>", "parameters": {...}}

Available actions:
- open_app(app_name): opens a desktop application (e.g. chrome, spotify, vscode)
- get_weather(city, time): opens a weather search for a city ("today"/"tomorrow")
- web_search(query, mode): mode is "search" or "news"
- play_youtube(query): plays the first matching YouTube video
- set_reminder(date, time, message): date "YYYY-MM-DD", time "HH:MM" (24h)
- send_message(receiver, message_text, platform): platform e.g. "whatsapp","telegram","discord"
- get_system_status(): CPU/RAM/uptime
- get_time(): current date and time

If the user is just chatting, asking a question, or wants code/explanations,
answer normally — do NOT use the JSON format.

IMPORTANT: There is currently NO action for controlling Spotify or any music
app directly (playing a specific song, resuming/skipping/pausing playback,
or fetching song lyrics) beyond simply opening the app with open_app. If the
user asks for any of these, say honestly that this isn't supported yet —
never claim you played, resumed, or found something you did not actually do.
"""

_ACTION_JSON_RE = re.compile(r'^\s*\{.*"action"\s*:\s*".+?"\s*.*\}\s*$', re.S)


def _extract_action_json(text: str) -> str | None:
    """Metnin İÇİNDE herhangi bir yerde bir action JSON'u varsa bulur — model
    "İşte:" gibi ekstra kelimeler eklese ya da JSON'dan önce/sonra açıklama
    yazsa bile süslü parantezleri dengeleyerek doğru JSON bloğunu çıkarır.
    Eskiden tam string '^...$' eşleşmesi arandığı için modelin en ufak fazla
    kelimesi, action'ın hiç çalışmadan olduğu gibi sesli okunmasına yol
    açıyordu."""
    t = _strip_code_fence(text or "")
    start = t.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(t)):
            if t[i] == "{":
                depth += 1
            elif t[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = t[start:i + 1]
                    if '"action"' in candidate:
                        try:
                            json.loads(candidate)
                            return candidate
                        except Exception:
                            pass
                    break
        start = t.find("{", start + 1)
    return None


def _strip_code_fence(text: str) -> str:
    """Bazı modeller "sadece JSON" talimatına rağmen ```json ... ``` bloğu
    ekleyebiliyor — kontrol etmeden önce bunu temizle."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"```\s*$", "", t)
        t = t.strip()
    return t


# ---------------------------------------------------------------------------
# open_app
# ---------------------------------------------------------------------------
_APP_ALIASES = {
    "chrome":     {"Windows": "chrome",       "Darwin": "Google Chrome",      "Linux": "google-chrome"},
    "firefox":    {"Windows": "firefox",      "Darwin": "Firefox",            "Linux": "firefox"},
    "edge":       {"Windows": "msedge",       "Darwin": "Microsoft Edge",     "Linux": "microsoft-edge"},
    "spotify":    {"Windows": "Spotify",      "Darwin": "Spotify",            "Linux": "spotify"},
    "vlc":        {"Windows": "vlc",          "Darwin": "VLC",                "Linux": "vlc"},
    "vscode":     {"Windows": "code",         "Darwin": "Visual Studio Code", "Linux": "code"},
    "terminal":   {"Windows": "wt",           "Darwin": "Terminal",           "Linux": "x-terminal-emulator"},
    "notepad":    {"Windows": "notepad.exe",  "Darwin": "TextEdit",           "Linux": "gedit"},
    "explorer":   {"Windows": "explorer.exe", "Darwin": "Finder",             "Linux": "nautilus"},
    "calculator": {"Windows": "calc.exe",     "Darwin": "Calculator",         "Linux": "gnome-calculator"},
    "discord":    {"Windows": "Discord",      "Darwin": "Discord",            "Linux": "discord"},
    "whatsapp":   {"Windows": "WhatsApp",     "Darwin": "WhatsApp",           "Linux": "whatsapp"},
    "telegram":   {"Windows": "Telegram",     "Darwin": "Telegram",           "Linux": "telegram"},
    "steam":      {"Windows": "steam",        "Darwin": "Steam",              "Linux": "steam"},
    "word":       {"Windows": "winword",      "Darwin": "Microsoft Word",     "Linux": "libreoffice --writer"},
    "excel":      {"Windows": "excel",        "Darwin": "Microsoft Excel",    "Linux": "libreoffice --calc"},
}


def _normalize_app(raw: str) -> str:
    key = raw.lower().strip()
    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)
    for alias, os_map in _APP_ALIASES.items():
        if alias in key or key in alias:
            return os_map.get(_SYSTEM, raw)
    return raw


def _launch(app_name: str) -> bool:
    try:
        if _SYSTEM == "Windows":
            if shutil.which(app_name) or shutil.which(app_name.split(".")[0]):
                subprocess.Popen(app_name, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            import pyautogui
            pyautogui.press("win"); time.sleep(0.6)
            pyautogui.write(app_name, interval=0.04); time.sleep(0.8)
            pyautogui.press("enter"); time.sleep(2.0)
            return True
        elif _SYSTEM == "Darwin":
            for args in (["open", "-a", app_name], ["open", "-a", f"{app_name}.app"]):
                r = subprocess.run(args, capture_output=True, timeout=8)
                if r.returncode == 0:
                    return True
            return False
        else:
            binary = shutil.which(app_name) or shutil.which(app_name.lower())
            if binary:
                subprocess.Popen([binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            subprocess.run(["xdg-open", app_name], capture_output=True, timeout=5)
            return True
    except Exception:
        return False


def open_app(params: dict) -> str:
    app_name = (params or {}).get("app_name", "").strip()
    if not app_name:
        return "No application name provided."
    normalized = _normalize_app(app_name)
    ok = _launch(normalized) or (normalized.lower() != app_name.lower() and _launch(app_name))
    return f"Opened {app_name}." if ok else f"Could not open {app_name}."


# ---------------------------------------------------------------------------
# weather
# ---------------------------------------------------------------------------
def get_weather(params: dict) -> str:
    city = (params or {}).get("city", "").strip()
    when = (params or {}).get("time", "today").strip() or "today"
    if not city:
        return "Please provide a city."
    query = f"weather in {city} {when}"
    webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
    return f"Showing the weather for {city}, {when}."


# ---------------------------------------------------------------------------
# web_search (DDG öncelikli, Google News RSS yedekli — API key gerekmez)
# ---------------------------------------------------------------------------
def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    last_err = None
    for _ in range(2):  # geçici DNS/bağlantı hatalarına karşı bir kez tekrar dene
        try:
            with DDGS() as ddgs:
                return [
                    {"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")}
                    for r in ddgs.text(query, max_results=max_results)
                ]
        except Exception as e:
            last_err = e
            time.sleep(0.8)
    raise last_err


def _google_news_rss(query: str, max_results: int = 8) -> list[dict]:
    """DDG haber uç noktası çalışmadığında yedek: Google News RSS.
    Ekstra bağımlılık gerektirmez (requests + stdlib xml)."""
    import requests
    from xml.etree import ElementTree

    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=tr&gl=TR&ceid=TR:tr"
    resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    items = root.findall(".//item")[:max_results]
    return [
        {"title": (it.findtext("title") or ""),
         "snippet": (it.findtext("description") or ""),
         "url": (it.findtext("link") or ""),
         "source": (it.findtext("source") or "")}
        for it in items
    ]


def _ddg_news(query: str, max_results: int = 8) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    try:
        with DDGS() as ddgs:
            results = [
                {"title": r.get("title", ""), "snippet": r.get("body", ""),
                 "url": r.get("url", ""), "source": r.get("source", "")}
                for r in ddgs.news(query, max_results=max_results)
            ]
            if results:
                return results
    except Exception:
        pass
    try:
        results = _google_news_rss(query, max_results=max_results)
        if results:
            return results
    except Exception:
        pass
    return _ddg_search(query, max_results=max_results)


def web_search(params: dict) -> str:
    query = (params or {}).get("query", "").strip()
    mode = (params or {}).get("mode", "search").lower().strip()
    if not query:
        return "Please provide a search query."
    try:
        results = _ddg_news(query) if mode == "news" else _ddg_search(query)
        if not results:
            return f"No results found for: {query}"
        lines = [f"{'News' if mode == 'news' else 'Search results'} for: {query}\n"]
        for i, r in enumerate(results, 1):
            if r.get("title"):
                lines.append(f"{i}. {r['title']}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet'][:180]}")
            if r.get("url"):
                lines.append(f"   {r['url']}")
        return "\n".join(lines)
    except Exception as e:
        return (f"Search failed — could not reach any search backend "
                f"(possible internet/DNS issue on this machine): {e}")


# ---------------------------------------------------------------------------
# youtube
# ---------------------------------------------------------------------------
def _open_url(url: str) -> None:
    try:
        if _SYSTEM == "Darwin":
            subprocess.Popen(["open", url])
        elif _SYSTEM == "Linux":
            subprocess.Popen(["xdg-open", url])
        else:
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
    except Exception:
        webbrowser.open(url)


def play_youtube(params: dict) -> str:
    query = (params or {}).get("query", "").strip()
    if not query:
        return "Please say what you'd like to watch."
    try:
        import requests
        headers = {"User-Agent": "Mozilla/5.0"}
        search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp=EgIQAQ%3D%3D"
        r = requests.get(search_url, headers=headers, timeout=10)
        video_ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', r.text)
        for vid in video_ids:
            if f"/shorts/{vid}" not in r.text:
                _open_url(f"https://www.youtube.com/watch?v={vid}")
                return f"Playing: {query}"
    except Exception:
        pass
    _open_url(f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp=EgIQAQ%3D%3D")
    return f"Opened YouTube search for: {query}"


# ---------------------------------------------------------------------------
# reminder (basit: OS bildirim zamanlayıcısı yerine hafif dosya + thread bekletme)
# ---------------------------------------------------------------------------
def set_reminder(params: dict) -> str:
    date_str = (params or {}).get("date", "").strip()
    time_str = (params or {}).get("time", "").strip()
    message = (params or {}).get("message", "Reminder").strip()

    if not date_str or not time_str:
        return "I need both a date and a time to set a reminder."
    try:
        target_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        return "I couldn't parse that date or time. Use YYYY-MM-DD and HH:MM."
    if target_dt <= datetime.now():
        return "That time has already passed."

    delay = (target_dt - datetime.now()).total_seconds()

    def _fire():
        time.sleep(delay)
        try:
            if _SYSTEM == "Windows":
                subprocess.run(["msg", "*", "/TIME:30", message], check=False)
            elif _SYSTEM == "Darwin":
                script = f'display notification "{message}" with title "Reminder"'
                subprocess.run(["osascript", "-e", script], check=False)
            else:
                subprocess.run(["notify-send", "Reminder", message], check=False)
        except Exception:
            pass

    import threading
    threading.Thread(target=_fire, daemon=True).start()
    friendly_time = target_dt.strftime("%B %d at %I:%M %p")
    return f"Reminder set for {friendly_time}. (Keep the app running for it to fire.)"


# ---------------------------------------------------------------------------
# send_message (pyautogui ile masaüstü uygulaması taklidi)
# ---------------------------------------------------------------------------
def send_message(params: dict) -> str:
    receiver = (params or {}).get("receiver", "").strip()
    message_text = (params or {}).get("message_text", "").strip()
    platform_name = (params or {}).get("platform", "whatsapp").strip().title()

    if not receiver:
        return "Please specify a recipient."
    if not message_text:
        return "Please specify the message content."

    try:
        import pyautogui
        import pyperclip
    except ImportError:
        return "pyautogui/pyperclip not installed — cannot send messages."

    if not _launch(_normalize_app(platform_name)):
        return f"Could not open {platform_name}."
    time.sleep(1.2)

    hotkey = ("command", "f") if _SYSTEM == "Darwin" else ("ctrl", "f")
    pyautogui.hotkey(*hotkey)
    time.sleep(0.5)
    pyperclip.copy(receiver)
    pyautogui.hotkey(*(("command", "v") if _SYSTEM == "Darwin" else ("ctrl", "v")))
    time.sleep(1.0)
    pyautogui.press("enter")
    time.sleep(0.8)
    pyperclip.copy(message_text)
    pyautogui.hotkey(*(("command", "v") if _SYSTEM == "Darwin" else ("ctrl", "v")))
    time.sleep(0.2)
    pyautogui.press("enter")

    return f"Message sent to {receiver} via {platform_name}."


# ---------------------------------------------------------------------------
# system / time
# ---------------------------------------------------------------------------
def get_system_status(params: dict = None) -> str:
    cpu = psutil.cpu_percent(interval=0.3)
    ram = psutil.virtual_memory()
    uptime = time.time() - psutil.boot_time()
    h, m = int(uptime // 3600), int((uptime % 3600) // 60)
    return (f"CPU: {cpu:.0f}%. RAM: {ram.percent:.0f}% "
            f"({ram.used/1024**3:.1f}/{ram.total/1024**3:.1f} GB). Uptime: {h}h {m}m.")


def get_time(params: dict = None) -> str:
    return datetime.now().strftime("It's %H:%M on %A, %B %d, %Y.")


ACTIONS = {
    "open_app": open_app,
    "get_weather": get_weather,
    "web_search": web_search,
    "play_youtube": play_youtube,
    "set_reminder": set_reminder,
    "send_message": send_message,
    "get_system_status": get_system_status,
    "get_time": get_time,
}


def is_action_json(text: str) -> bool:
    return _extract_action_json(text) is not None


def run_action(text: str) -> str | None:
    """text içinde bir eylem JSON'u varsa çalıştırır ve sonucu döner; yoksa None döner."""
    candidate = _extract_action_json(text)
    if candidate is None:
        return None
    try:
        payload = json.loads(candidate)
    except Exception:
        return None
    name = payload.get("action")
    params = payload.get("parameters", {})
    fn = ACTIONS.get(name)
    if fn is None:
        return f"Unknown action: {name}"
    try:
        return fn(params)
    except Exception as e:
        return f"Action '{name}' failed: {e}"
