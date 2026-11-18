#!/usr/bin/env python3
import curses, html, json, locale, os, platform, plistlib, random, re, shutil, signal, subprocess, sys, textwrap, threading, time
import urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

import om_backups as backups
import om_chat
import om_screensavers as screensavers

OLLAMA_DEFAULT_HOST = "http://localhost:11434"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST") or OLLAMA_DEFAULT_HOST
API = OLLAMA_HOST if "://" in OLLAMA_HOST else f"http://{OLLAMA_HOST}"
LIBRARY = "https://ollama.com/library"  # no JSON API for the full catalog, so the marketplace parses this page
REGISTRY = "https://registry.ollama.ai/v2"
CUSTOM = "cc-longwork"
SUITE = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "om"
MODELFILE = CONFIG / f"{CUSTOM}.Modelfile"
NVIM_MODEL = CONFIG / "nvim.model"
MODEL_LIBRARY = CONFIG / "model_library.txt"
OLLAMA_SETTINGS = CONFIG / "ollama_settings.env"
OM_SETTINGS = CONFIG / "om_settings.json"
LAUNCH_AGENTS = Path.home() / "Library/LaunchAgents"
CLAUDE_TOKEN = "ollama"
CLAUDE_TIERS = ("OPUS", "SONNET", "HAIKU")
MACOS_GPU_SHARE = 0.75
OM_OPTIONS = {
    "screensaver": (screensavers.SCENES + ["random"], "what z shows: warp-speed stars, a rainy day, growing pipes, "
                    "or a muncher eating its way through the bytes. Each one speeds up with the download"),
    "progress style": (screensavers.PROGRESS_STYLES, "how the screensaver shows the percentage: big blocks, "
                       "a seven-segment display, a smooth bar, or just the number"),
    "walker": (list(screensavers.WALKERS), "who walks the screensaver's progress track to the flag"),
    "accent colour": (["cyan", "magenta", "green", "yellow", "blue", "red"], "the highlight colour for selections, keys and bars"),
}
OM_TEXT_SETTINGS = {"backup folder": "~/Documents"}
STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "om"
DOWNLOADS = STATE / "downloads"
CHATS = STATE / "chats"
CLAUDE_BACKUP = SUITE / "claude-backup"
CLAUDE_PROMPT = Path.home() / ".claude" / "CLAUDE.md"
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
ENTER = (10, 13, curses.KEY_ENTER)
GROUPS = [
    ("ollama", [("llms", "models"), ("market", "marketplace"), ("settings", "ollama")]),
    ("local", [("configs", "configs"), ("files", "files"), ("system", "system"), ("chats", "chats"), ("backups", "backups")]),
    ("om", [("settings", "om")]),
]
PAGES = [page for _, pages in GROUPS for _, page in pages]
ROW_PAGES = ["configs", "files", "system", "chats", "backups"]
CHORD_SECONDS = 1.5
BLINKS_PER_SECOND = 4
MODELFILE_BASE = r"^FROM (\S+)"
MODELFILE_CONTEXT = r"^PARAMETER num_ctx (\d+)"
SORTS = ["popular", "newest", "updated", "name"]
FOOTER = {
    "models": [("⏎", "load/unload"), ("p", "pull"), ("x", "pause/resume"), ("a", "save"), ("u", "update"), ("o", "chat"),
               ("n", "nvim"), ("c", "claude here"), ("b", "claude base"), ("d", "delete"), ("z", "screensaver"),
               ("h", "help"), ("q", "quit")],
    "marketplace": [("⏎", "pick a size"), ("/", "search"), ("t", "tools only"), ("s", "sort"), ("r", "reload"),
                    ("z", "screensaver"), ("h", "help"), ("q", "quit")],
    "ollama": [("⏎", "edit"), ("a", "apply & restart ollama"), ("r", "reload"), ("h", "help"), ("q", "quit")],
    "configs": [("⏎", "change"), ("r", "refresh"), ("h", "help"), ("q", "quit")],
    "files": [("⏎", "open"), ("f", "show in Finder"), ("r", "refresh"), ("h", "help"), ("q", "quit")],
    "chats": [("⏎", "open"), ("d", "delete"), ("r", "refresh"), ("h", "help"), ("q", "quit")],
    "backups": [("⏎", "back up / restore"), ("b", "back up everything"), ("f", "show in Finder"), ("r", "refresh"),
                ("h", "help"), ("q", "quit")],
    "system": [("⏎", "change"), ("r", "refresh"), ("h", "help"), ("q", "quit")],
    "om": [("⏎", "next choice"), ("z", "try the screensaver"), ("h", "help"), ("q", "quit")],
}
HELP = {
    "models": [("⏎  space", "load into memory or unload; on a saved model, start / pause / resume its download"),
               ("p", "pull a model by name"), ("x", "pause or resume the selected model's download"),
               ("a", "save a model to your library without downloading it"),
               ("u", "update the selected model (cc-longwork: rebuild it)"), ("U", "update every installed model, then rebuild cc-longwork"),
               ("o", "chat with this model inside om; the whole conversation scrolls and stays until om quits"),
               ("n", "make nvim (codecompanion) use this model; restart nvim after"),
               ("c", "start Claude Code on this model in a directory (om claude)"), ("b", "rebuild cc-longwork on top of this model"),
               ("d", "delete from disk (it stays in your library); on a saved model, cancel its download and forget it"),
               ("r", "refresh now (it also refreshes every 2s)"), ("S", "start the Ollama service")],
    "marketplace": [("⏎", "list a model's tags with download sizes, then pull or save one"),
                    ("/", "search names and descriptions"), ("t", "only models that can use tools (om claude needs this)"),
                    ("s", "sort: popular, newest, recently updated, name"), ("r", "reload the library from ollama.com")],
    "ollama": [("⏎", "edit the selected server setting (empty resets it)"),
               ("a", "apply: restart ollama with these settings (unloads models)"), ("r", "re-read what ollama documents")],
    "configs": [("⏎", "change the selected config: nvim's model, om claude's base model, its context size, "
                      "or the backup folder"),
                ("r", "re-read the configs")],
    "chats": [("⏎", "reopen the selected ollama-local chat"), ("d", "delete it"), ("r", "refresh")],
    "backups": [("⏎", "run the selected backup, or restore the selected archive (adds what's missing, never overwrites)"),
                ("b", "back up claude-local and ollama-local now"), ("f", "show the archive in Finder"), ("r", "refresh")],
    "files": [("⏎", "open the file in $EDITOR, the log in less, or the folder in Finder"), ("f", "show it in Finder"),
              ("r", "refresh sizes")],
    "system": [("⏎", "change the GPU memory limit"), ("r", "refresh")],
    "om": [("⏎  space", "switch the selected setting to its next choice (saved right away)")],
    "every page": [("↑ ↓  j k  g G", "move the selection"), ("1  2  3", "switch group: ollama, local, om"),
                   ("two numbers", "jump to a page: 1 1 llms, 1 2 market, 2 2 files…; the group blinks until the second, 0 goes back"),
                   ("tab  shift+tab", "next / previous page"), ("m  esc", "market / back to your llms"), ("z", "screensaver: watch the downloads (any key returns)"),
                   ("h  ?", "show this help"), ("q  ctrl+c", "quit; downloads keep going and om picks them up next time")],
}
C = {}


def api(path, body=None, method=None, stream=False, timeout=5):
    req = urllib.request.Request(API + path, method=method, headers={"Content-Type": "application/json"},
                                 data=None if body is None else json.dumps(body).encode())
    resp = urllib.request.urlopen(req, timeout=timeout)
    return (json.loads(line) for line in resp) if stream else json.loads(resp.read() or b"{}")


def fetch(url, **headers):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "om", **headers}), timeout=15).read().decode()


def err_text(e):
    if isinstance(e, urllib.error.HTTPError):
        try:
            return json.loads(e.read())["error"]
        except Exception:
            pass
    return str(e)


def size_text(n):
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{n / 1e3:.1f} KB"


def size_bytes(s):
    m = re.match(r"([\d.]+)\s*([KMGT])B", s or "")
    return m and float(m.group(1)) * 10 ** (3 * "KMGT".index(m.group(2)) + 3)


def sysctl(key):
    if not shutil.which("sysctl"):
        return ""
    return subprocess.run(["sysctl", "-n", key], capture_output=True, text=True).stdout.strip()


def memory_bytes():
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


def gpu_limit_mb():
    return int(sysctl("iogpu.wired_limit_mb") or 0) if sys.platform == "darwin" else 0


def gpu_budget():  # memory macOS lets the GPU wire: the iogpu override if set, else ~75% of RAM
    return gpu_limit_mb() * 2 ** 20 or memory_bytes() * MACOS_GPU_SHARE


def config_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def when(iso):
    t = datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", iso))
    s = (datetime.now(timezone.utc) - t).total_seconds()
    if s < -86400 * 365:
        return "indefinitely"
    v = next((f"{int(abs(s) // n)}{u}" for u, n in (("d", 86400), ("h", 3600), ("m", 60)) if abs(s) >= n), f"{int(abs(s))}s")
    return f"in {v}" if s < 0 else f"{v} ago"


def age_seconds(text):
    m = re.match(r"(\d+|an?) (minute|hour|day|week|month|year)s? ago", text)
    units = dict(minute=60, hour=3600, day=86400, week=604800, month=2629800, year=31557600)
    return (1 if m.group(1) in ("a", "an") else int(m.group(1))) * units[m.group(2)] if m else float("inf")


def is_custom(name):
    return name.split(":")[0] == CUSTOM


def is_installed(entry):
    return "digest" in entry


def tagged(name):
    return name if ":" in name else name + ":latest"


def duration_text(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600}h {seconds % 3600 // 60}m" if seconds >= 3600 else f"{seconds // 60}m {seconds % 60}s"


def home_short(path):
    return str(path).replace(str(Path.home()), "~", 1)


def modelfile_field(pattern):
    try:
        m = re.search(pattern, MODELFILE.read_text(), re.M)
    except OSError:
        return None
    return m and m.group(1)


def modelfile_field_write(pattern, line):
    text = MODELFILE.read_text() if MODELFILE.exists() else ""
    if re.search(pattern, text, re.M):
        text = re.sub(pattern, line, text, flags=re.M)
    else:
        text = f"{line}\n{text}" if line.startswith("FROM") else f"{text}{line}\n"
    config_write(MODELFILE, text)


def modelfile_rebuild():
    if not base():
        raise RuntimeError(f"pick a base model for {CUSTOM} first: om use <model>")
    r = subprocess.run(["ollama", "create", CUSTOM, "-f", str(MODELFILE)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError((r.stderr.strip().splitlines() or ["ollama create failed"])[-1])
    return f"rebuilt {CUSTOM} on {base()}"


def modelfile_base_set(name):
    modelfile_field_write(MODELFILE_BASE, f"FROM {name}")
    return modelfile_rebuild()


def modelfile_context_set(tokens):
    modelfile_field_write(MODELFILE_CONTEXT, f"PARAMETER num_ctx {tokens}")
    return modelfile_rebuild()


def nvim_model_set(name, pull_offer=None):
    name = tagged(name)
    try:
        api("/api/show", {"model": name})
    except urllib.error.HTTPError:
        if not (pull_offer and pull_offer(name)):
            raise RuntimeError(f"{name} isn't installed")
        subprocess.run(["ollama", "pull", name], check=True)
    config_write(NVIM_MODEL, f"{name}\n")
    return f"nvim model is now {name}. Restart nvim to use it; new shells export it through `om env`."


def base():
    name = modelfile_field(MODELFILE_BASE)
    return name and tagged(name)


def backup_folder():
    return Path(os.path.expanduser(om_settings_read()["backup folder"]))


def ollama_local_sources():
    return {"chats": CHATS, "config": CONFIG}


def backup_everything():
    made = [backups.claude_local_backup(CLAUDE_BACKUP, backup_folder())] if backups.claude_backup_available(CLAUDE_BACKUP) else []
    return made + [backups.ollama_local_backup(ollama_local_sources(), backup_folder())]


def page_group(page):
    return next(i for i, (_, pages) in enumerate(GROUPS) if page in [p for _, p in pages])


def chord_pending(chord, now):
    return bool(chord) and now - chord[1] < CHORD_SECONDS


def page_jump(group_last, chord, digit, now, current):
    if digit < 0:
        return (chord[2], None) if chord_pending(chord, now) else (None, None)
    if chord_pending(chord, now) and digit < len(GROUPS[chord[0]][1]):
        return GROUPS[chord[0]][1][digit][1], None
    if digit < len(GROUPS):
        return group_last[digit], (digit, now, current)
    return None, None


def nvim_model():
    try:
        return tagged(NVIM_MODEL.read_text().strip())
    except OSError:
        return None


# ---- model library ----
def model_library_read():
    try:
        return list(dict.fromkeys(tagged(line.strip()) for line in MODEL_LIBRARY.read_text().splitlines() if line.strip()))
    except OSError:
        return []


def model_library_write(names):
    config_write(MODEL_LIBRARY, "".join(f"{name}\n" for name in dict.fromkeys(names)))


def registry_repository(name):
    repository, tag = tagged(name).rsplit(":", 1)
    return f"{REGISTRY}/{repository if '/' in repository else 'library/' + repository}", tag


def registry_manifest(name):
    repository, tag = registry_repository(name)
    try:
        return json.loads(fetch(f"{repository}/manifests/{tag}", Accept="application/vnd.docker.distribution.manifest.v2+json"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def registry_stats(name):
    manifest = registry_manifest(name)
    if manifest is None:
        return dict(missing=True)
    config = json.loads(fetch(f"{registry_repository(name)[0]}/blobs/{manifest['config']['digest']}"))
    tag = tagged(name).rsplit(":", 1)[1]  # safetensors models leave params/quant blank; their tags usually spell them out
    tag_hint = lambda pattern: (m := re.search(pattern, tag, re.I)) and m.group(1) or ""
    return dict(size=manifest["config"]["size"] + sum(layer["size"] for layer in manifest["layers"]), requires=config.get("requires"),
                caps=config.get("capabilities") or [],
                details=dict(family=config.get("model_family", ""),
                             parameter_size=config.get("model_type") or tag_hint(r"\b(\d+(?:\.\d+)?[bm])\b"),
                             quantization_level=config.get("file_type") or tag_hint(r"((?:nv|mx)fp\d+|bf16|f16|q\d\w*)$")))


# ---- downloads ----
def ollama_pull(name, report):
    # closing the stream stops ollama's download; pulling again resumes from its partial blobs
    layers = {}
    for ev in api("/api/pull", {"model": name}, stream=True, timeout=None):
        if "error" in ev:
            raise RuntimeError(ev["error"])
        if ev.get("total"):
            layers[ev["digest"]] = (ev.get("completed", 0), ev["total"])
        report(sum(done for done, _ in layers.values()), sum(total for _, total in layers.values()), ev.get("status", ""))


def rate_tracker(window=5):
    samples = []

    def rate(done):
        now = time.time()
        samples.append((now, done))
        while len(samples) > 2 and now - samples[0][0] > window:
            samples.pop(0)
        return (done - samples[0][1]) / max(now - samples[0][0], 1e-3)
    return rate


def download_path(name):
    return DOWNLOADS / (tagged(name).replace("/", "_").replace(":", "@") + ".json")


def download_read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def download_write(state):  # atomic, since om reads these files while workers write them
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    path = download_path(state["name"])
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state))
    os.replace(temporary, path)


def process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, TypeError):
        return pid is not None


def download_states():
    states = [download_read(path) for path in sorted(DOWNLOADS.glob("*.json"))]
    for state in states:
        if state.get("state") == "downloading" and not process_alive(state.get("pid")):
            state["state"] = "paused"
    return [state for state in states if state.get("name")]


def download_start(name):
    previous = download_read(download_path(name))
    if previous.get("state") == "downloading" and process_alive(previous.get("pid")):
        return
    worker = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "_download", tagged(name)], start_new_session=True,
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    download_write(dict(name=tagged(name), pid=worker.pid, state="downloading", done=previous.get("done", 0),
                        total=previous.get("total", 0), rate=0, status="starting", error=""))


def download_pause(name):
    state = download_read(download_path(name))
    if state.get("state") == "downloading" and process_alive(state.get("pid")):
        os.kill(state["pid"], signal.SIGTERM)  # the worker writes "paused" on its way out


def download_cancel(name):
    download_pause(name)
    for _ in range(30):  # wait for the worker's last "paused" write, or it would recreate the file after we delete it
        if download_read(download_path(name)).get("state") != "downloading":
            break
        time.sleep(0.1)
    download_path(name).unlink(missing_ok=True)


def download_worker(name):
    state = download_read(download_path(name)) or dict(name=name, done=0, total=0)
    state.update(pid=os.getpid(), state="downloading", rate=0, error="")
    rate, last_write = rate_tracker(), 0

    def report(done, total, status):
        nonlocal last_write
        speed = rate(done)
        if time.time() - last_write > 0.5:
            state.update(done=done, total=total, rate=speed, status=status)
            download_write(state)
            last_write = time.time()

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    download_write(state)
    try:
        ollama_pull(name, report)
        state.update(state="done", done=state["total"], rate=0)
    except SystemExit:
        state.update(state="paused", rate=0)
    except Exception as e:
        state.update(state="failed", error=err_text(e), rate=0)
    download_write(state)


# ---- ollama server settings ----
def ollama_settings_options():
    if not shutil.which("ollama"):
        return []
    out = subprocess.run(["ollama", "serve", "-h"], capture_output=True, text=True).stdout
    return re.findall(r"^\s+([A-Z][A-Z_]+)\s{2,}(.+)$", out.split("Environment Variables:")[-1], re.M)


def om_settings_read():
    try:
        saved = json.loads(OM_SETTINGS.read_text())
    except (OSError, ValueError):
        saved = {}
    chosen = {name: saved.get(name) if saved.get(name) in choices else choices[0] for name, (choices, _) in OM_OPTIONS.items()}
    typed = {name: saved.get(name) if isinstance(saved.get(name), str) and saved.get(name) else default
             for name, default in OM_TEXT_SETTINGS.items()}
    return {**chosen, **typed}


def om_settings_write(settings):
    config_write(OM_SETTINGS, json.dumps(settings, indent=2) + "\n")


def ollama_settings_read():
    try:
        lines = OLLAMA_SETTINGS.read_text().splitlines()
    except OSError:
        return {}
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def ollama_settings_write(settings):
    config_write(OLLAMA_SETTINGS, "".join(f"{name}={value}\n" for name, value in sorted(settings.items())))


def plist_read(path):
    return plistlib.loads(path.read_bytes()) if path and path.exists() else {}


def ollama_service_template():
    binary = shutil.which("ollama")
    return binary and next(Path(binary).resolve().parents[1].glob("*ollama.plist"), None)


def ollama_service_agent():
    return next(LAUNCH_AGENTS.glob("*ollama.plist"), None)


def ollama_service_environment_wanted():
    return {**plist_read(ollama_service_template()).get("EnvironmentVariables", {}), **ollama_settings_read()}


def ollama_service_environment_applied():
    return plist_read(ollama_service_agent()).get("EnvironmentVariables", {})


def ollama_service_apply():
    template = ollama_service_template()
    if not template:
        raise RuntimeError("no brew launch agent for ollama; is it installed with brew?")
    agent = plistlib.loads(template.read_bytes())
    agent["EnvironmentVariables"] = ollama_service_environment_wanted()
    target, domain = LAUNCH_AGENTS / template.name, f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{agent['Label']}"], capture_output=True)
    target.write_bytes(plistlib.dumps(agent))
    for _ in range(20):  # bootstrap fails with EIO while launchd is still tearing the old job down
        if subprocess.run(["launchctl", "bootstrap", domain, str(target)], capture_output=True).returncode == 0:
            return "ollama restarted with your settings"
        time.sleep(0.5)
    raise RuntimeError("launchctl couldn't start ollama; try `brew services restart ollama`")


def ollama_service_pid():
    label = plist_read(ollama_service_agent()).get("Label", "")
    status = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{label}"], capture_output=True, text=True).stdout
    m = re.search(r"^\s*pid = (\d+)", status, re.M)
    return m and m.group(1)


# ---- ollama.com scraping ----
def strip_tags(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def parse_library(page):
    out = []
    for block in page.split('<li  class="flex items-baseline')[1:]:
        name = re.search(r'href="/library/([^"]+)"', block)
        if not name:
            continue
        desc = re.search(r'<p class="max-w-lg[^"]*">(.*?)</p>', block, re.S)
        chips = lambda cls: [strip_tags(x) for x in re.findall(rf'<span\s+class="[^"]*{re.escape(cls)}[^"]*">(.*?)</span>', block, re.S)]
        stat = lambda label: (m := re.search(rf'<span\s*>([^<]+)</span>\s*<span class="hidden sm:flex">&nbsp;{label}', block)) and m.group(1).strip()
        upd = re.search(r'Updated&nbsp;</span>\s*<span\s*>([^<]+)</span>', block)
        out.append(dict(name=name.group(1), desc=strip_tags(desc.group(1)) if desc else "",
                        caps=chips("bg-indigo-50") + chips("bg-cyan-50"), sizes=chips("bg-[#ddf4ff]"),
                        pulls=stat("Pulls") or "", tags=stat("Tags") or "", updated=upd.group(1).strip() if upd else ""))
    return out


def parse_tags(page, model):
    out = []
    for tag, body in re.findall(rf'<a href="/library/({re.escape(model)}:[^"]+)" class="md:hidden[^"]*">(.*?)</a>', page, re.S):
        parts = [p.strip() for p in strip_tags(body).split("•")] + ["", "", ""]
        out.append(dict(tag=tag, latest="latest" in parts[0].split(), size=parts[1],
                        ctx=parts[2].replace(" context window", ""), input=parts[3]))
    return out


def setup_colors():
    curses.start_color()
    curses.use_default_colors()
    grey = 244 if curses.COLORS >= 256 else curses.COLOR_WHITE
    accent = getattr(curses, f"COLOR_{om_settings_read()['accent colour'].upper()}")
    pairs = dict(accent=(accent, -1), ok=(curses.COLOR_GREEN, -1), tag=(curses.COLOR_MAGENTA, -1),
                 warn=(curses.COLOR_YELLOW, -1), err=(curses.COLOR_RED, -1), dim=(grey, -1),
                 sel=(curses.COLOR_BLACK, accent), bar=(curses.COLOR_BLACK, curses.COLOR_WHITE), rain=(curses.COLOR_BLUE, -1))
    for i, (k, (fg, bg)) in enumerate(pairs.items(), 1):
        curses.init_pair(i, fg, bg)
        C[k] = curses.color_pair(i)


def selection_move(k, sel, count):
    step = {curses.KEY_DOWN: 1, ord("j"): 1, curses.KEY_UP: -1, ord("k"): -1, curses.KEY_NPAGE: 10,
            curses.KEY_PPAGE: -10, ord("g"): -10 ** 9, ord("G"): 10 ** 9}.get(k)
    return None if step is None else max(0, min(sel + step, count - 1))


class App:
    def __init__(self, scr):
        self.scr, self.models, self.entries, self.loaded, self.info = scr, [], [], {}, {}
        self.page, self.sel = "models", dict.fromkeys(PAGES, 0)
        self.group_last, self.chord, self.page_rows = [pages[0][1] for _, pages in GROUPS], None, {}
        self.last, self.down, self.version = 0, False, "?"
        self.job, self.prog, self.msg = None, None, ("", 0)
        self.lib, self.lib_err, self.lib_loading = None, None, False
        self.query, self.tools_only, self.sort = "", False, "popular"
        self.settings_options = None
        self.budget, self.body_h = gpu_budget(), 0
        self.newest_rank, self.remote = {}, {}
        self.downloads = {}
        self.load_library()

    # ---- data -------------------------------------------------------------
    def refresh(self):
        try:
            self.models = sorted(api("/api/tags")["models"], key=lambda m: (not is_custom(m["name"]), m["name"]))
            self.loaded = {m["name"]: m for m in api("/api/ps")["models"]}
            self.version, self.down = api("/api/version")["version"], False
        except OSError:
            self.models, self.loaded, self.down = [], {}, True
        # while ollama is down nothing looks installed, so don't offer every model as saved-only
        saved = [] if self.down else sorted(self.model_library_sync())
        self.entries = self.models + [dict(name=name, **(self.remote.get(name) or {})) for name in saved]
        self.registry_stats_load([name for name in saved if name not in self.remote])
        self.sel["models"] = max(0, min(self.sel["models"], len(self.entries) - 1))
        self.last = time.time()

    def model_library_sync(self):
        library, installed = model_library_read(), [m["name"] for m in self.models]
        if set(installed) - set(library):
            model_library_write(library + installed)
        return [name for name in library if name not in installed]

    def registry_stats_load(self, names):
        def work(name):
            try:
                self.remote[name] = registry_stats(name)
            except Exception:
                self.remote.pop(name, None)
        for name in names:
            self.remote[name] = {}  # pending, so the next refresh doesn't start a second fetch
            threading.Thread(target=work, args=(name,), daemon=True).start()

    def details(self, name):
        if name not in self.info:
            try:
                s = api("/api/show", {"model": name})
                ctx = next((v for k, v in s.get("model_info", {}).items() if k.endswith(".context_length")), None)
                num = re.search(r"num_ctx\s+(\d+)", s.get("parameters") or "")
                self.info[name] = dict(ctx=ctx, num_ctx=num and int(num.group(1)), caps=s.get("capabilities", []))
            except OSError:
                self.info[name] = {}
        return self.info[name]

    def load_library(self):
        if self.lib_loading:
            return
        self.lib_loading = True

        def work():
            try:
                newest = parse_library(fetch(LIBRARY + "?sort=newest"))
                self.newest_rank = {m["name"]: i for i, m in enumerate(newest)}
                self.lib, self.lib_err = parse_library(fetch(LIBRARY)), None  # ollama.com's default order is popularity
            except Exception as e:
                self.lib_err = f"couldn't load the library from ollama.com: {err_text(e)}"
            finally:
                self.lib_loading = False

        threading.Thread(target=work, daemon=True).start()

    def market(self):
        q = self.query.lower()
        shown = [m for m in self.lib or [] if (not q or q in m["name"].lower() or q in m["desc"].lower())
                 and (not self.tools_only or "tools" in m["caps"])]
        order = {"newest": lambda m: self.newest_rank.get(m["name"], len(self.newest_rank)),
                 "updated": lambda m: age_seconds(m["updated"]), "name": lambda m: m["name"]}.get(self.sort)
        return sorted(shown, key=order) if order else shown  # stable, so ties keep popularity order

    def library_caps(self, name):  # gguf configs on the registry don't list capabilities
        caps = next((m["caps"] for m in self.lib or [] if m["name"] == name.split(":")[0]), [])
        return [cap for cap in caps if cap != "cloud"]  # "cloud" means some other tag runs remotely

    def ollama_setting_rows(self):
        if self.settings_options is None:
            self.settings_options = ollama_settings_options()
        mine, wanted, applied = ollama_settings_read(), ollama_service_environment_wanted(), ollama_service_environment_applied()
        return [dict(name=name, desc=desc, value=wanted.get(name), applied=applied.get(name),
                     source="set by you" if name in mine else "brew default" if name in wanted else "")
                for name, desc in self.settings_options]

    def system_rows_collect(self):
        limit, pid = gpu_limit_mb(), ollama_service_pid()
        return [
            dict(label="chip", value=sysctl("machdep.cpu.brand_string") or platform.processor() or platform.machine()),
            dict(label="memory", value=size_text(memory_bytes())),
            dict(label="system", value=platform.platform(terse=True)),
        ] + ([dict(label="GPU memory limit", value=size_text(limit * 2 ** 20) if limit else f"macOS default ({size_text(self.budget)})",
                   note="How much RAM the GPU may hold for models. ⏎ changes it with sudo; it resets at reboot.",
                   action=self.gpu_limit_edit)] if sys.platform == "darwin" else []) + [
            dict(label="ollama", value=f"{self.version} · {API} · " + (f"running, pid {pid}" if pid else "service not found")),
        ]

    def files_rows_collect(self):
        agent = ollama_service_agent()
        log = Path(plist_read(agent).get("StandardErrorPath", "/opt/homebrew/var/log/ollama.log"))
        models_dir = Path(os.path.expanduser(ollama_service_environment_wanted().get("OLLAMA_MODELS", "~/.ollama/models")))
        used = subprocess.run(["du", "-sk", str(models_dir)], capture_output=True, text=True).stdout.split() or ["0"]
        free = shutil.disk_usage(models_dir if models_dir.exists() else Path.home()).free
        om_files = [("model library", MODEL_LIBRARY, "Every model you saved or had installed."),
                    ("nvim model", NVIM_MODEL, "The model codecompanion uses; `om nvim` writes it and `om env` exports it."),
                    ("claude Modelfile", MODELFILE, f"What {CUSTOM} is built from."),
                    ("om settings", OM_SETTINGS, "om's look: screensaver, progress style, walker, accent colour."),
                    ("ollama settings", OLLAMA_SETTINGS, "Server settings om applies to the launch agent.")]
        claude_prompt = self.file_row("global CLAUDE.md", CLAUDE_PROMPT.resolve(), (
            f"{home_short(CLAUDE_PROMPT)} links here." if CLAUDE_PROMPT.is_symlink() else
            "A plain file: keep it in a repo and symlink it here to track changes."), self.editor_open)
        return [claude_prompt] + [self.file_row(label, path, note, self.editor_open) for label, path, note in om_files] + [
            self.file_row("ollama-local chats", CHATS, "Every saved chat with a local model.", self.finder_show),
            self.file_row("downloads", DOWNLOADS, "Progress files for background pulls.", self.finder_show),
            self.file_row("launch agent", agent, "Where launchd reads ollama's settings.", self.editor_open),
            dict(self.file_row("models folder", models_dir, "Every model ollama has on disk.", self.finder_show),
                 value=f"{home_short(models_dir)} · {size_text(int(used[0]) * 1024)} used · {size_text(free)} free on disk"),
            self.file_row("server log", log, "ollama's log, opened at the end.", lambda path: self.terminal_run(["less", "+G", str(path)])),
        ]

    def file_row(self, label, path, note, opener):
        exists = bool(path) and Path(path).exists()
        size = f" · {size_text(Path(path).stat().st_size)}" if exists and Path(path).is_file() else ""
        shown = Path(path).name if path and Path(path).parent == MODELFILE.parent else home_short(path or "none")
        return dict(label=label, value=shown + size if exists else f"{shown} · not created yet", note=note,
                    path=path if exists else None, location=path and home_short(path), action=exists and (lambda: opener(path)))

    def editor_open(self, path):
        self.terminal_run([os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi", str(path)])
        self.page_rows.clear()

    def finder_show(self, path):
        path = Path(path)
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(path)])
        else:
            subprocess.run(["xdg-open", str(path if path.is_dir() else path.parent)])

    def configs_rows_collect(self):
        context = modelfile_field(MODELFILE_CONTEXT)
        return [
            dict(label="nvim model", value=nvim_model() or "not set", action=self.config_nvim_edit,
                 note="What codecompanion uses: `om env` exports it as OLLAMA_MODEL. Restart nvim after changing it."),
            dict(label="claude base", value=base() or "not set", action=self.config_base_edit,
                 note=f"The model {CUSTOM} is built on; changing it rebuilds {CUSTOM}."),
            dict(label="claude context", value=f"{int(context):,} tokens" if context else "model default",
                 action=self.config_context_edit, note=f"num_ctx in {MODELFILE.name}; bigger needs more memory. Rebuilds {CUSTOM}."),
            dict(label="backup folder", value=home_short(backup_folder()), action=self.config_backup_folder_edit,
                 note="Backups land in ClaudeBackups/ and OllamaBackups/ inside it."),
        ]

    def chats_rows_collect(self):
        rows = [dict(label=chat["model"], value=f"{om_chat.chat_title(chat)} · {len(chat['messages'])} messages · "
                                                f"{when(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())}",
                     note=f"Saved in {home_short(path)}", path=path, action=lambda path=path, chat=chat: self.chat_open(chat["model"], path),
                     delete=lambda path=path: path.unlink(missing_ok=True))
                for path, chat in om_chat.chat_list(CHATS)]
        return rows or [dict(label="no chats yet", value="press o on a model in 1 1 llms to start one")]

    def backups_rows_collect(self):
        folder = backup_folder()
        actions = ([dict(label="back up claude-local", value=f"~/.claude, ~/.claude.json and the Claude app's sessions → "
                                                             f"{home_short(folder / 'ClaudeBackups')}",
                         note="Runs claude-backup; chats, memory, settings and the global CLAUDE.md.",
                         action=lambda: self.run("backing up claude-local", self.backup_claude_local))]
                   if backups.claude_backup_available(CLAUDE_BACKUP) else [])
        actions.append(dict(label="back up ollama-local", value=f"om's chats, library and settings → {home_short(folder / 'OllamaBackups')}",
                            note="Models aren't included; the library lists them so they can be pulled again.",
                            action=lambda: self.run("backing up ollama-local", self.backup_ollama_local)))
        archives = [dict(label=kind, value=f"{path.name} · {size_text(path.stat().st_size)} · "
                                           f"{when(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())}",
                         note="⏎ restores it: adds what's missing, never overwrites.", path=path,
                         action=lambda kind=kind, path=path: self.backup_restore(kind, path))
                    for kind, path in backups.backups_list(folder)
                    if kind == "ollama-local" or backups.claude_backup_available(CLAUDE_BACKUP)]
        return actions + archives

    # ---- background jobs ---------------------------------------------------
    def run(self, label, fn):
        if self.job:
            self.msg = (f"busy: {self.job}", C["warn"])
            return
        self.job, self.msg = label, (label, C["dim"])

        def work():
            try:
                self.msg = (fn() or f"{label}: done", C["ok"])
            except Exception as e:
                self.msg = (f"{label} failed: {err_text(e)}", C["err"])
            finally:
                self.job = self.prog = None
                self.last = 0
                self.info.clear()
                self.page_rows.clear()

        threading.Thread(target=work, daemon=True).start()

    def pull(self, name):
        rate = rate_tracker()
        ollama_pull(name, lambda done, total, status: setattr(
            self, "prog", dict(name=name, done=done, total=total, rate=rate(done), state="downloading") if total else None))
        return f"pulled {name}"

    def update_all(self):
        skipped = []
        for name in [m["name"] for m in self.models if not is_custom(m["name"])]:
            try:
                self.pull(name)
            except RuntimeError:
                skipped.append(name)
        modelfile_rebuild()
        return "all models updated" + (f", skipped {', '.join(skipped)}" if skipped else "")

    def toggle(self, name):
        if name in self.loaded:
            api("/api/generate", {"model": name, "keep_alive": 0}, timeout=60)
            return f"unloaded {name}"
        api("/api/generate", {"model": name}, timeout=600)
        return f"loaded {name}"

    def downloads_collect(self):
        self.downloads = {}
        for state in download_states():
            if state["state"] == "done":
                download_path(state["name"]).unlink(missing_ok=True)
                self.msg, self.last = (f"pulled {state['name']}", C["ok"]), 0
            else:
                self.downloads[state["name"]] = state

    def download_featured(self):
        entry = self.entries[self.sel["models"]]["name"] if self.entries else None
        running = [d for d in self.downloads.values() if d["state"] == "downloading"]
        return self.downloads.get(entry) or (running or list(self.downloads.values()) or [None])[0]

    def download_toggle(self, name, size=None):
        state = self.downloads.get(name, {}).get("state")
        if state == "downloading":
            download_pause(name)
            self.msg = (f"paused {name}", C["warn"])
        elif state in ("paused", "failed"):
            download_start(name)
            self.msg = (f"resuming {name}", C["dim"])
        else:
            self.pull_checked(name, size)

    def delete(self, name):
        api("/api/delete", {"model": name}, method="DELETE")
        return f"deleted {name}; it stays in your library (d again forgets it)"

    def model_library_add(self, name):
        name = tagged(name)
        if registry_manifest(name) is None:
            raise RuntimeError(f"{name} isn't in the ollama registry")
        model_library_write(model_library_read() + [name])
        return f"saved {name} to your library (not downloaded)"

    def model_library_forget(self, name):
        model_library_write([n for n in model_library_read() if n != name])
        return f"forgot {name}"

    # ---- terminal handover -------------------------------------------------
    def terminal_run(self, command):
        curses.endwin()  # this also leaves the alternate screen; go straight back to it, cleared
        os.write(1, (curses.tigetstr("smcup") or b"") + (curses.tigetstr("clear") or b""))
        # ctrl+c in the command (e.g. stopping ollama's reply) mustn't also quit om; exec resets the handler for the child
        old = signal.signal(signal.SIGINT, lambda *_: None)
        try:
            return subprocess.run(command).returncode
        finally:
            signal.signal(signal.SIGINT, old)
            self.scr.clear()
            self.scr.refresh()
            self.last = 0

    # ---- drawing -----------------------------------------------------------
    def put(self, y, x, s, a=0):
        h, w = self.scr.getmaxyx()
        if 0 <= y < h and 0 <= x < w:
            try:
                self.scr.addnstr(y, x, s, w - x - (y == h - 1), a)
            except curses.error:
                pass

    def pane(self, y, w, title):
        self.put(y, 1, "─" * (w - 2), C["dim"])
        self.put(y, 3, f" {title} ", C["accent"] | curses.A_BOLD)

    def pane_lines(self, y, w, lines):
        rows = [(row, a) for text, a in lines for row in textwrap.wrap(text, max(20, w - 6))[:2]]
        for i, (row, a) in enumerate(rows[:5]):
            self.put(y + 1 + i, 3, row, a)

    def table(self, cols, rows, sel):
        h, w = self.body_h, self.scr.getmaxyx()[1]
        x = 4
        for title, cw in cols:
            self.put(2, x, title, C["dim"] | curses.A_BOLD)
            x += cw
        top = max(0, sel - (h - 14))
        for i, (dot, dot_a, cells, extra, extra_a) in enumerate(rows[top:top + h - 13], top):
            y, on = 3 + i - top, i == sel
            pick = (lambda a: C["sel"] | (a & curses.A_BOLD)) if on else (lambda a: a)
            if on:
                self.put(y, 0, " " * w, C["sel"])
                self.put(y, 1, "▸", C["sel"] | curses.A_BOLD)
            self.put(y, 2, dot, pick(dot_a))
            x = 4
            for (title, cw), (text, a) in zip(cols, cells):
                self.put(y, x, text if len(text) < cw else text[:cw - 2] + "…", pick(a))
                x += cw
            self.put(y, x, extra, pick(extra_a))

    def draw(self):
        s = self.scr
        s.erase()
        h, w = s.getmaxyx()
        self.put(0, 0, " " * w, C["bar"])
        self.put(0, 1, " om ", C["sel"] | curses.A_BOLD)
        group, pending = page_group(self.page), chord_pending(self.chord, time.time())
        blink_off = pending and int(time.time() * BLINKS_PER_SECOND) % 2
        x = self.draw_tabs(0, 6, [name for name, _ in GROUPS], -1 if blink_off else group, C["bar"])
        pages = GROUPS[group][1]
        hint_x = self.draw_tabs(1, 2, [name for name, _ in pages], [page for _, page in pages].index(self.page), C["dim"])
        if pending:
            self.put(1, hint_x + 1, f"← {GROUPS[group][0]}: press 1-{len(pages)} for a page, 0 to go back", C["accent"] | curses.A_BOLD)
        self.downloads_collect()
        footer = self.footer_rows(w)
        self.body_h = h - len(footer) + 1  # pages lay out as if the footer were one row
        right = getattr(self, f"draw_{self.page}")(self.body_h, w)
        self.put(0, max(x + 1, w - len(right)), right, C["bar"])
        self.draw_status(self.body_h - 3, w)
        for y, row in enumerate(footer, h - len(footer)):
            for k, label, x in row:
                self.put(y, x, k, C["accent"] | curses.A_BOLD)
                self.put(y, x + len(k) + 1, label, C["dim"])
        s.refresh()

    def draw_tabs(self, y, x, names, current, attr):
        for i, name in enumerate(names, 1):
            label = f" {i} {name} "
            self.put(y, x, label, C["sel"] | curses.A_BOLD if i - 1 == current else attr)
            x += len(label) + 1
        return x

    def footer_rows(self, w):
        rows, x = [[]], 1
        for k, label in FOOTER[self.page]:
            width = len(k) + len(label) + 4
            if x + width - 3 > w and rows[-1]:
                rows.append([])
                x = 1
            rows[-1].append((k, label, x))
            x += width
        return rows

    def draw_models(self, h, w):
        mem = sum(m.get("size_vram", 0) for m in self.loaded.values())
        saved = len(self.entries) - len(self.models)
        right = f"{size_text(mem)} in memory · {size_text(sum(m['size'] for m in self.models))} on disk · {saved} saved "
        if self.down:
            self.put(2, 2, "Ollama isn't running.", C["err"] | curses.A_BOLD)
            self.put(3, 2, "Press S to start it with your settings.", C["dim"])
            return right
        b, nv = base(), nvim_model()
        nw = max([len(m["name"]) for m in self.entries] + [10]) + 2
        rows = []
        for m in self.entries:
            name, d, on, have = m["name"], m.get("details", {}), m["name"] in self.loaded, is_installed(m)
            roles = (("om claude", is_custom(name)), ("base", name == b), ("nvim", name == nv), ("saved", not have))
            size = size_text(m["size"]) if "size" in m else "…" if name in self.remote and not m.get("missing") else "—"
            cells = [(name, curses.A_BOLD if have else C["dim"]), (d.get("parameter_size", ""), 0 if have else C["dim"]),
                     (d.get("quantization_level", ""), 0 if have else C["dim"]), (size, 0 if have else C["dim"]),
                     (when(m["modified_at"]), C["dim"]) if have else ("not installed", C["dim"])]
            if name in self.downloads:
                cells[4] = self.download_cell(self.downloads[name])
            rows.append(("●" if on else "○" if have else "◌", C["ok"] if on else C["dim"], cells,
                         " ".join(role for role, yes in roles if yes), C["tag"]))
        self.table([("MODEL", nw), ("PARAMS", 9), ("QUANT", 9), ("SIZE", 10), ("MODIFIED", 15)], rows, self.sel["models"])
        if self.entries:
            self.draw_details(h - 9, w, self.entries[self.sel["models"]], b)
        return right

    def draw_marketplace(self, h, w):
        shown = self.market()
        spin = SPIN[int(time.time() * 10) % len(SPIN)] + " " if self.lib_loading else ""
        right = (f"{spin}{self.sort}" + (f" · “{self.query}”" if self.query else "") + (" · tools only" if self.tools_only else "")
                 + (f" · {len(shown)} of {len(self.lib)} models " if self.lib else " "))
        if self.lib is None:
            msg = self.lib_err or f"{SPIN[int(time.time() * 10) % len(SPIN)]} loading the library from ollama.com…"
            self.put(2, 2, msg, C["err"] if self.lib_err else C["dim"])
            if self.lib_err:
                self.put(3, 2, "Press r to try again.", C["dim"])
            return right
        if not shown:
            self.put(3, 4, "No models match. / to change the search, t to toggle tools only.", C["dim"])
            return right
        sel = self.sel["marketplace"] = max(0, min(self.sel["marketplace"], len(shown) - 1))
        have = {m["name"].split(":")[0] for m in self.models}
        saved = {m["name"].split(":")[0] for m in self.entries}
        rows = [("●" if m["name"] in have else "○" if m["name"] in saved else " ", C["ok"] if m["name"] in have else C["dim"],
                 [(m["name"], curses.A_BOLD), (" ".join(m["sizes"]) or "—", 0), (m["pulls"], 0), (m["updated"], C["dim"])],
                 " ".join(m["caps"]), C["tag"]) for m in shown]
        nw = min(28, max(len(m["name"]) for m in shown) + 2)
        self.table([("MODEL", nw), ("SIZES", 24), ("PULLS", 9), ("UPDATED", 15)], rows, sel)
        m, y = shown[sel], h - 9
        self.pane(y, w, m["name"])
        for i, line in enumerate(textwrap.wrap(m["desc"], max(20, w - 6))[:2]):
            self.put(y + 1 + i, 3, line)
        self.put(y + 3, 3, " · ".join(f for f in [", ".join(m["caps"]), f"{m['pulls']} pulls", f"{m['tags']} tags",
                                                   f"updated {m['updated']}"] if f.strip()), C["dim"])
        if "cloud" in m["caps"] and not m["sizes"]:
            self.put(y + 4, 3, "cloud-only: runs on ollama.com and needs `ollama signin`", C["warn"])
        else:
            self.put(y + 4, 3, "⏎ to see each tag's download size, then pull or save one", C["dim"])
        return right

    def draw_ollama(self, h, w):
        rows = self.ollama_setting_rows()
        pending = ollama_service_environment_wanted() != ollama_service_environment_applied()
        right = "not applied yet: a restarts ollama with them " if pending else f"{OLLAMA_SETTINGS.name} "
        if not rows:
            self.put(2, 2, "Couldn't read the settings from `ollama serve -h`. Is ollama installed?", C["err"])
            return right
        sel = self.sel["ollama"] = max(0, min(self.sel["ollama"], len(rows) - 1))
        mine = lambda r: r["source"] == "set by you"
        stale = lambda r: r["value"] != r["applied"]
        self.table([("VARIABLE", max(len(r["name"]) for r in rows) + 2), ("VALUE", 26)],
                   [("●" if mine(r) else "○", C["accent"] if mine(r) else C["dim"],
                     [(r["name"], curses.A_BOLD), (r["value"] or "default", 0 if r["value"] else C["dim"])],
                     r["source"] + (" · not applied" if stale(r) else ""), C["warn"] if stale(r) else C["tag"]) for r in rows], sel)
        r = rows[sel]
        self.pane(h - 9, w, r["name"])
        source = {"set by you": f"set by you in {OLLAMA_SETTINGS.name}", "brew default": "brew's launch agent sets this"}
        self.pane_lines(h - 9, w, [(r["desc"], 0), (source.get(r["source"], "not set: ollama uses its own default"), C["dim"])]
                        + ([(f"ollama runs with {r['applied'] or 'the default'}; a applies {r['value'] or 'the default'}", C["warn"])]
                           if stale(r) else []))
        return right

    def rows(self):
        if self.page not in self.page_rows:
            self.page_rows[self.page] = getattr(self, f"{self.page}_rows_collect")()
        return self.page_rows[self.page]

    def draw_rows(self, h, w):
        rows = self.rows()
        sel = self.sel[self.page] = max(0, min(self.sel[self.page], len(rows) - 1))
        label_width = max(len(r["label"]) for r in rows) + 3
        self.table([("NAME", label_width), ("VALUE", max(20, w - label_width - 6))],
                   [("›" if r.get("action") else " ", C["accent"], [(r["label"], curses.A_BOLD), (r["value"], 0)], "", 0)
                    for r in rows], sel)
        row = rows[sel]
        self.pane(h - 9, w, row["label"])
        self.pane_lines(h - 9, w, [(row["value"], 0)] + ([(row["location"], C["dim"])] if row.get("location") else [])
                        + [(row.get("note", ""), C["dim"])])
        return f"{platform.node()} " if self.page == "system" else ""

    draw_configs = draw_files = draw_system = draw_chats = draw_backups = draw_rows

    def draw_om(self, h, w):
        settings = om_settings_read()
        names = list(OM_OPTIONS)
        sel = self.sel["om"] = max(0, min(self.sel["om"], len(names) - 1))
        self.table([("SETTING", 18), ("VALUE", 16)],
                   [("●" if settings[n] != OM_OPTIONS[n][0][0] else "○", C["accent"], [(n, curses.A_BOLD), (settings[n], 0)],
                     "default" if settings[n] == OM_OPTIONS[n][0][0] else "", C["dim"]) for n in names], sel)
        choices, about = OM_OPTIONS[names[sel]]
        self.pane(h - 9, w, names[sel])
        self.pane_lines(h - 9, w, [(about, 0), ("choices: " + " · ".join(f"[{c}]" if c == settings[names[sel]] else c for c in choices), C["dim"])])
        return f"{OM_SETTINGS.name} "

    def draw_details(self, y, w, m, b):
        name, d = m["name"], m.get("details", {})
        self.pane(y, w, name)
        if not is_installed(m):
            self.draw_details_saved(y, w, m)
            return
        info = self.details(name)
        facts = [d.get("family", ""), d.get("parameter_size", ""), d.get("quantization_level", "")]
        if info.get("ctx"):
            facts.append(f"context {info['ctx'] // 1024}K max" + (f", {info['num_ctx'] // 1024}K set" if info.get("num_ctx") else ""))
        self.put(y + 1, 3, " · ".join(f for f in facts if f))
        self.put(y + 2, 3, "can: " + ", ".join(info.get("caps", [])), C["dim"])
        if name in self.loaded:
            p = self.loaded[name]
            self.put(y + 3, 3, f"● loaded · {size_text(p.get('size_vram', 0))} in memory · unloads {when(p['expires_at'])}", C["ok"])
        else:
            self.put(y + 3, 3, "○ not loaded", C["dim"])
        if is_custom(name):
            self.put(y + 4, 3, f"what om claude runs · built from {b} via {MODELFILE.name}", C["tag"])

    def draw_details_saved(self, y, w, m):
        d = m.get("details", {})
        if m.get("missing"):
            facts = [("not in ollama's registry anymore, so it can't be pulled", C["warn"])]
        elif "size" in m:
            stats = [d.get("family"), d.get("parameter_size"), d.get("quantization_level"), f"{size_text(m['size'])} download",
                     m.get("requires") and f"needs ollama {m['requires']}+"]
            big = m["size"] > self.budget
            caps = m["caps"] or self.library_caps(m["name"])
            facts = [(" · ".join(f for f in stats if f), 0)] + ([("can: " + ", ".join(caps), C["dim"])] if caps else []) + (
                [(f"over the {size_text(self.budget)} the GPU can use", C["warn"])] if big else [])
        else:
            facts = [("loading its size from ollama's registry…", C["dim"])]
        download = self.downloads.get(m["name"], {})
        hint = {"downloading": "downloading · ⏎ or x pauses · z screensaver · d cancels",
                "paused": "paused · ⏎ or x resumes · d cancels and forgets it",
                "failed": f"download failed: {download.get('error')} · ⏎ retries"}.get(download.get("state"),
                                                                                       "in your library, not installed · ⏎ pulls it · d forgets it")
        self.pane_lines(y, w, facts + [(hint, C["err"] if download.get("state") == "failed" else C["dim"])])

    def download_cell(self, d):
        frac = d["done"] / d["total"] if d.get("total") else 0
        if d["state"] == "failed":
            return "download failed", C["err"]
        if d["state"] == "paused":
            return f"⏸ paused {frac:.0%}", C["warn"]
        return "█" * round(frac * 8) + "░" * (8 - round(frac * 8)) + f" {frac:.0%}", C["accent"]

    def draw_status(self, y, w):
        p = self.prog or self.download_featured()
        if self.msg[0] and p and p.get("total"):
            self.put(y + 1, 1, self.msg[0], self.msg[1])
        if p and p.get("total"):
            frac = p["done"] / p["total"]
            speed = {"paused": "paused", "failed": "failed"}.get(p["state"], f"{p['rate'] / 1e6:.0f} MB/s")
            others = len(self.downloads) - (p["name"] in self.downloads)
            head = f"{p['name']} "
            tail = f" {frac:4.0%}  {size_text(p['done'])} / {size_text(p['total'])}  {speed}" + (f"  +{others} more" if others > 0 else "")
            bw = max(10, w - len(head) - len(tail) - 2)
            self.put(y, 1, head, curses.A_BOLD)
            self.put(y, 1 + len(head), "█" * int(bw * frac), C["accent"])
            self.put(y, 1 + len(head) + int(bw * frac), "░" * (bw - int(bw * frac)), C["dim"])
            self.put(y, 1 + len(head) + bw, tail)
        elif self.msg[0]:
            spin = SPIN[int(time.time() * 10) % len(SPIN)] + " " if self.job else ""
            self.put(y, 1, spin + self.msg[0], self.msg[1])

    # ---- screensaver ---------------------------------------------------------
    def screensaver(self):
        settings = om_settings_read()
        scene = random.choice(screensavers.SCENES) if settings["screensaver"] == "random" else settings["screensaver"]
        state = {}
        self.scr.timeout(50)
        try:
            while self.scr.getch() == -1:
                self.downloads_collect()
                d = self.prog or self.download_featured()
                h, w = self.scr.getmaxyx()
                self.scr.erase()
                getattr(screensavers, scene)(self.put, C, state, d, h, w)
                self.screensaver_progress(d, scene, settings)
                self.scr.refresh()
        finally:
            self.scr.timeout(150)
            self.scr.clear()

    def screensaver_progress(self, d, scene, settings):
        h, w = self.scr.getmaxyx()
        frac = d["done"] / d["total"] if d and d.get("total") else 0
        top = max(1, h // 2 - 9)
        title = d["name"] if d else "nothing is downloading"
        self.put(top, (w - len(title)) // 2 - 1, f" {title} ", C["tag"] | curses.A_BOLD)
        rows = screensavers.percent_rows(settings["progress style"], frac, w, bool(d and d.get("total")))
        for i, row in enumerate(rows):
            self.put(top + 2 + i, (w - len(row)) // 2 - 1, f" {row} ", C["ok"] if screensavers.moving(d) else C["warn"])
        if d and d.get("total"):
            stats = f" {self.screensaver_stats(d)} "
            self.put(top + 3 + len(rows), (w - len(stats)) // 2, stats, C["dim"])
        if scene != "chomp":
            ground, finish, walker = h - 3, w - 4, settings["walker"]
            x = 2 + int(frac * max(0, finish - 2 - screensavers.walker_width(walker)))
            middle = x + screensavers.walker_width(walker) // 2
            self.put(ground, 2, "═" * max(0, middle - 2), C["accent"])
            self.put(ground, middle, "─" * max(0, finish - middle), C["dim"])
            self.put(ground - 1, finish, "⚑", C["tag"] | curses.A_BOLD)
            screensavers.walker_draw(self.put, C, walker, x, ground, screensavers.moving(d), umbrella=scene == "rain")
        hint = "any key returns · quitting om leaves downloads running"
        self.put(h - 1, (w - len(hint)) // 2, hint, C["dim"])

    def screensaver_stats(self, d):
        state = {"paused": "paused · x on the models page resumes it", "failed": f"failed: {d.get('error')}"}.get(d["state"])
        left = (d["total"] - d["done"]) / d["rate"] if d["rate"] > 0 else 0
        stats = f"{size_text(d['done'])} / {size_text(d['total'])} · " + (
            state or f"{d['rate'] / 1e6:.0f} MB/s" + (f" · {duration_text(left)} left" if left else ""))
        others = len(self.downloads) - (d["name"] in self.downloads)
        return stats + (f" · +{others} more downloading" if others > 0 else "")

    # ---- modals ------------------------------------------------------------
    def box(self, lines, width):
        h, w = self.scr.getmaxyx()
        lines = lines[:max(1, h - 2)]
        bw = min(w - 2, max(width, *map(len, lines)) + 4)
        win = curses.newwin(len(lines) + 2, bw, (h - len(lines)) // 2 - 1, (w - bw) // 2)
        win.keypad(True)
        win.box()
        for i, line in enumerate(lines):
            win.addnstr(i + 1, 2, line, bw - 4)
        return win

    def help(self):
        entries = [(self.page, "")] + HELP[self.page] + [("", ""), ("every page", "")] + HELP["every page"]
        w = max(len(k) for k, _ in entries) + 3
        win = self.box([k.ljust(w) + d for k, d in entries] + ["", "any key closes"], 40)
        try:
            for i, (k, d) in enumerate(entries, 1):
                win.addstr(i, 2, k, C["tag"] | curses.A_BOLD if not d else C["accent"] | curses.A_BOLD)
            win.addstr(len(entries) + 2, 2, "any key closes", C["dim"])
        except curses.error:  # window clipped on a small terminal
            pass
        win.getch()
        self.scr.touchwin()

    def wrapped(self, text):
        return textwrap.wrap(text, max(20, self.scr.getmaxyx()[1] - 8)) or [""]

    def confirm(self, text):
        win = self.box(self.wrapped(text) + ["", "y  yes      n  no"], 30)
        win.refresh()
        while (k := win.getch()) not in (ord("y"), ord("n"), 27):
            pass
        self.scr.touchwin()
        return k == ord("y")

    def ask(self, prompt, text=""):
        curses.curs_set(1)
        while True:
            prompt_lines = self.wrapped(prompt)
            win = self.box(prompt_lines + ["> " + text, "", "⏎ ok      esc cancel"], 44)
            win.move(len(prompt_lines) + 1, 4 + len(text))
            k = win.get_wch()
            if k in ("\n", "\r", curses.KEY_ENTER):
                break
            if k == "\x1b":
                text = None
                break
            if k in ("\x7f", "\b", curses.KEY_BACKSPACE):
                text = text[:-1]
            elif isinstance(k, str) and k.isprintable():
                text += k
        curses.curs_set(0)
        self.scr.touchwin()
        return None if text is None else text.strip()

    def choose(self, title, options, current=None):
        if not options:
            self.msg = (f"nothing to choose for {title}", C["warn"])
            return None
        i = options.index(current) if current in options else 0
        while True:
            n = max(1, min(len(options), self.scr.getmaxyx()[0] - 8))
            top = min(max(0, i - n // 2), len(options) - n)
            lines = [f"{'●' if o == current else ' '} {o}" for o in options[top:top + n]]
            win = self.box([title] + lines + ["", "⏎ pick   esc cancel   ● current"], 40)
            width = win.getmaxyx()[1] - 4
            try:
                win.addnstr(1, 2, title, width, C["accent"] | curses.A_BOLD)
                win.addnstr(2 + i - top, 2, lines[i - top].ljust(width), width, C["sel"])
            except curses.error:
                pass
            k = win.getch()
            s = selection_move(k, i, len(options))
            if s is not None:
                i = s
            elif k in (*ENTER, 27, ord("q")):
                self.scr.touchwin()
                return options[i] if k in ENTER else None

    def pick_tag(self, model):
        self.msg = (f"loading {model}'s tags from ollama.com…", C["dim"])
        self.draw()
        try:
            tags = parse_tags(fetch(f"{LIBRARY}/{model}/tags"), model)
        except Exception as e:
            self.msg = (f"couldn't load {model}'s tags: {err_text(e)}", C["err"])
            return None
        self.msg = ("", 0)
        if not tags:
            self.msg = (f"no tags found for {model}", C["warn"])
            return None
        have, saved = {m["name"] for m in self.models}, {m["name"] for m in self.entries}
        tw = max(len(t["tag"]) for t in tags) + 2
        lines = [f"{'●' if t['tag'] in have else '○' if t['tag'] in saved else ' '} {t['tag']:<{tw}}{t['size']:>7}  {t['ctx']:>5}  "
                 f"{'latest' if t['latest'] else ''}" for t in tags]
        i = next((j for j, t in enumerate(tags) if t["latest"]), 0)
        while True:
            n = max(1, min(len(tags), self.scr.getmaxyx()[0] - 8))
            top = min(max(0, i - n // 2), len(tags) - n)
            foot = f"⏎ pull   a save   esc cancel   ● installed  ○ saved   red: over the {size_text(self.budget)} GPU limit"
            win = self.box([f"{model}: pick a tag ({len(tags)})", f"  {'TAG':<{tw}}{'SIZE':>7}  {'CTX':>5}"] + lines[top:top + n] + ["", foot], 50)
            bw = win.getmaxyx()[1]
            try:
                win.addnstr(1, 2, model, bw - 4, C["accent"] | curses.A_BOLD)
                win.addnstr(2, 2, f"  {'TAG':<{tw}}{'SIZE':>7}  {'CTX':>5}", bw - 4, C["dim"] | curses.A_BOLD)
                for r, j in enumerate(range(top, top + n)):
                    big = (size_bytes(tags[j]["size"]) or 0) > self.budget
                    win.addnstr(3 + r, 2, lines[j].ljust(bw - 4), bw - 4, C["sel"] if j == i else C["err"] if big else 0)
                win.addnstr(4 + n, 2, foot, bw - 4, C["dim"])
            except curses.error:
                pass
            k = win.getch()
            if k in (curses.KEY_DOWN, ord("j")):
                i = min(i + 1, len(tags) - 1)
            elif k in (curses.KEY_UP, ord("k")):
                i = max(i - 1, 0)
            elif k in (*ENTER, ord("a"), 27, ord("q")):
                self.scr.touchwin()
                return {ord("a"): ("save", tags[i]), 27: None, ord("q"): None}.get(k, ("pull", tags[i]))

    # ---- keys --------------------------------------------------------------
    def handle(self, k):
        if k == ord("q"):
            return False
        if k in (ord("h"), ord("?")):
            return self.help()
        if k == ord("z"):
            return self.screensaver()
        page = self.page_for_key(k)
        if page is None:
            return getattr(self, f"handle_{self.page}")(k)
        self.page = page
        self.group_last[page_group(page)] = page
        if page == "marketplace" and self.lib is None:
            self.load_library()

    def page_for_key(self, k):
        i = PAGES.index(self.page)
        if k == 9:
            return PAGES[(i + 1) % len(PAGES)]
        if k == curses.KEY_BTAB:
            return PAGES[i - 1]
        if ord("0") <= k <= ord("9"):
            page, self.chord = page_jump(self.group_last, self.chord, k - ord("1"), time.time(), self.page)
            return page
        if k == ord("m"):
            return "models" if self.page == "marketplace" else "marketplace"
        if k == 27 and self.page != "models":
            return "models"
        return None

    def handle_models(self, k):
        s = selection_move(k, self.sel["models"], len(self.entries))
        if s is not None:
            self.sel["models"] = s
        elif k == ord("r"):
            self.last = 0
            self.info.clear()
        elif k == ord("S"):
            self.run("starting ollama", ollama_service_apply)
        elif k == ord("p"):
            name = self.ask("Pull which model? (e.g. qwen3-coder-next)")
            if name:
                self.pull_checked(tagged(name), None)
        elif k == ord("a"):
            name = self.ask("Save which model to your library? (no download, e.g. gpt-oss:120b)")
            if name:
                self.run(f"checking {name}", lambda: self.model_library_add(name))
        elif k == ord("U") and self.models:
            self.run("updating all models", self.update_all)
        elif self.entries and k == ord("x"):
            name = self.entries[self.sel["models"]]["name"]
            if name in self.downloads:
                self.download_toggle(name)
            else:
                self.msg = (f"{name} isn't downloading", C["dim"])
        elif self.entries:
            entry = self.entries[self.sel["models"]]
            return (self.handle_installed if is_installed(entry) else self.handle_saved)(k, entry["name"])

    def handle_saved(self, k, name):
        if k in (*ENTER, ord(" "), ord("u")):
            self.download_toggle(name, self.entries[self.sel["models"]].get("size"))
        elif k == ord("d") and self.confirm(f"Forget {name}? It's not installed, so this only drops it from your library"
                                            + (" and cancels its download." if name in self.downloads else ".")):
            download_cancel(name)
            self.msg = (self.model_library_forget(name), C["ok"])
            self.last = 0
        elif k in map(ord, "oncb"):
            self.msg = (f"{name} isn't installed: ⏎ pulls it", C["warn"])

    def handle_installed(self, k, name):
        if k in (*ENTER, ord(" ")):
            self.run(("unloading " if name in self.loaded else "loading ") + name, lambda: self.toggle(name))
        elif k == ord("u"):
            self.pull_checked(name, None)
        elif k == ord("o"):
            self.chat_open(name, om_chat.chat_latest(CHATS, name) or om_chat.chat_new_path(CHATS, name))
        elif k == ord("n"):
            self.run(f"setting the nvim model to {name}", lambda: nvim_model_set(name))
        elif k == ord("c"):
            where = self.ask(f"Start Claude Code on {name} in:", os.getcwd())
            where = where and os.path.expanduser(where)
            if where and os.path.isdir(where):
                return where, name
            if where:
                self.msg = (f"not a directory: {where}", C["err"])
        elif k == ord("b"):
            if is_custom(name):
                self.msg = (f"{CUSTOM} can't be built from itself; pick another model", C["warn"])
            elif self.confirm(f"Rebuild {CUSTOM} on top of {name}?"):
                self.run(f"rebuilding {CUSTOM} on {name}", lambda: modelfile_base_set(name))
        elif k == ord("d"):
            warn = " om claude uses it!" if is_custom(name) else ""
            if self.confirm(f"Delete {name} ({size_text(self.entries[self.sel['models']]['size'])})?{warn}"):
                self.run(f"deleting {name}", lambda: self.delete(name))

    def handle_marketplace(self, k):
        shown = self.market()
        s = selection_move(k, self.sel["marketplace"], len(shown))
        if s is not None:
            self.sel["marketplace"] = s
        elif k == ord("/"):
            query = self.ask("Search the library (empty clears):", self.query)
            if query is not None:
                self.query, self.sel["marketplace"] = query, 0
        elif k == ord("t"):
            self.tools_only, self.sel["marketplace"] = not self.tools_only, 0
        elif k == ord("s"):
            self.sort, self.sel["marketplace"] = SORTS[(SORTS.index(self.sort) + 1) % len(SORTS)], 0
        elif k == ord("r"):
            self.load_library()
        elif k in ENTER and shown:
            self.marketplace_pick(shown[self.sel["marketplace"]]["name"])

    def marketplace_pick(self, model):
        picked = self.pick_tag(model)
        if not picked:
            return
        action, t = picked
        if action == "save":
            self.run(f"saving {t['tag']}", lambda: self.model_library_add(t["tag"]))
            return
        self.pull_checked(t["tag"], size_bytes(t["size"]))

    def pull_checked(self, name, size):
        if size and size > self.budget and not self.confirm(
                f"{name} is {size_text(size)}, over the {size_text(self.budget)} the GPU can use. Pull anyway?"):
            return
        if is_custom(name):
            self.run(f"rebuilding {name}", modelfile_rebuild)
            return
        model_library_write(model_library_read() + [tagged(name)])
        download_start(name)
        self.msg, self.last = (f"downloading {name} in the background · x pauses · z screensaver", C["dim"]), 0

    def handle_ollama(self, k):
        options = self.settings_options or []
        s = selection_move(k, self.sel["ollama"], len(options))
        if s is not None:
            self.sel["ollama"] = s
        elif k == ord("r"):
            self.settings_options = None
        elif k == ord("a") and self.confirm("Restart ollama with these settings? Loaded models will unload."):
            self.run("restarting ollama", ollama_service_apply)
        elif k in ENTER and options:
            self.ollama_setting_edit(options[self.sel["ollama"]][0])

    def ollama_setting_edit(self, name):
        settings, current = ollama_settings_read(), ollama_service_environment_wanted().get(name, "")
        value = self.ask(f"{name} (empty resets it):", current)
        if value is None or value == current:
            return
        if value:
            settings[name] = value
        else:
            settings.pop(name, None)
        ollama_settings_write(settings)
        self.msg = (f"saved {name}. a applies it (restarts ollama)", C["warn"])

    def handle_om(self, k):
        names = list(OM_OPTIONS)
        s = selection_move(k, self.sel["om"], len(names))
        if s is not None:
            self.sel["om"] = s
        elif k in (*ENTER, ord(" ")):
            settings, name = om_settings_read(), names[self.sel["om"]]
            choices = OM_OPTIONS[name][0]
            settings[name] = choices[(choices.index(settings[name]) + 1) % len(choices)]
            om_settings_write(settings)
            setup_colors()
            self.msg = (f"{name}: {settings[name]}", C["ok"])

    def handle_rows(self, k):
        rows = self.rows()
        row = rows[self.sel[self.page]]
        s = selection_move(k, self.sel[self.page], len(rows))
        if s is not None:
            self.sel[self.page] = s
        elif k == ord("r"):
            self.page_rows.pop(self.page, None)
        elif k in ENTER and row.get("action"):
            row["action"]()
            self.page_rows.pop(self.page, None)
        elif k == ord("f") and row.get("path"):
            self.finder_show(row["path"])
        elif k == ord("d") and row.get("delete") and self.confirm(f"Delete {row['label']}: {row['value']}?"):
            row["delete"]()
            self.page_rows.pop(self.page, None)
        elif k == ord("b") and self.page == "backups":
            self.run("backing up everything", lambda: ", ".join(home_short(path) for path in backup_everything()))

    handle_configs = handle_files = handle_system = handle_chats = handle_backups = handle_rows

    def chat_open(self, model, path):
        om_chat.Chat(self.scr, self.put, C, API, model, path).run()
        self.scr.clear()
        self.page_rows.pop("chats", None)

    def backup_claude_local(self):
        return f"saved {home_short(backups.claude_local_backup(CLAUDE_BACKUP, backup_folder()))}"

    def backup_ollama_local(self):
        return f"saved {home_short(backups.ollama_local_backup(ollama_local_sources(), backup_folder()))}"

    def backup_restore(self, kind, path):
        if not self.confirm(f"Restore {kind} from {path.name}? It adds what's missing and never overwrites."):
            return
        if kind == "claude-local":
            self.terminal_run([str(backups.claude_backup_binary(CLAUDE_BACKUP)), "restore", "-p", str(path)])
            return
        restored = backups.ollama_local_restore(path, ollama_local_sources())
        self.msg = (f"restored {len(restored)} files from {path.name}" if restored else "nothing missing; restored nothing", C["ok"])

    def config_backup_folder_edit(self):
        answer = self.ask("Backup folder (ClaudeBackups/ and OllamaBackups/ go inside it):", om_settings_read()["backup folder"])
        if not answer:
            return
        if not Path(os.path.expanduser(answer)).is_dir():
            self.msg = (f"not a folder: {answer}", C["err"])
            return
        settings = om_settings_read()
        settings["backup folder"] = answer
        om_settings_write(settings)

    def config_nvim_edit(self):
        name = self.choose("nvim model", [m["name"] for m in self.models], nvim_model())
        if name:
            self.run(f"setting the nvim model to {name}", lambda: nvim_model_set(name))

    def config_base_edit(self):
        name = self.choose(f"{CUSTOM} base model", [m["name"] for m in self.models if not is_custom(m["name"])], base())
        if name and name != base() and self.confirm(f"Rebuild {CUSTOM} on top of {name}?"):
            self.run(f"rebuilding {CUSTOM} on {name}", lambda: modelfile_base_set(name))

    def config_context_edit(self):
        limit = self.details(base() or "").get("ctx")
        answer = self.ask(f"Context size in tokens for {CUSTOM}" + (f" (the model allows up to {limit:,})" if limit else "") + ":",
                          modelfile_field(MODELFILE_CONTEXT) or "")
        if not answer:
            return
        if not answer.isdigit() or int(answer) <= 0 or (limit and int(answer) > limit):
            self.msg = (f"not a context size {base()} supports: {answer}", C["err"])
            return
        self.run(f"rebuilding {CUSTOM} with a {int(answer):,} token context", lambda: modelfile_context_set(int(answer)))

    def gpu_limit_edit(self):
        memory = memory_bytes()
        answer = self.ask(f"GPU memory limit in GB, 0 for the macOS default (RAM is {size_text(memory)}). Asks for sudo:")
        if answer is None:
            return
        if not answer.replace(".", "", 1).isdigit() or float(answer) * 1e9 >= memory:
            self.msg = (f"not a size under {size_text(memory)}: {answer}", C["err"])
            return
        mb = round(float(answer) * 1e9 / 2 ** 20)
        code = self.terminal_run(["sudo", "sysctl", f"iogpu.wired_limit_mb={mb}"])
        self.budget = gpu_budget()
        self.page_rows.clear()
        self.msg = ("GPU memory limit changed (until reboot)", C["ok"]) if code == 0 else ("sudo sysctl failed", C["err"])


def main(scr):
    setup_colors()
    curses.curs_set(0)
    scr.timeout(150)
    app = App(scr)
    while True:
        if time.time() - app.last > 2:
            app.refresh()
        app.draw()
        k = scr.getch()
        r = app.handle(k) if k != -1 else None
        if r is False or isinstance(r, tuple):
            return r


HELP_TEXT = """om                         interactive model manager (TUI)
om ls                      installed and loaded models
om pull <model>...         download models
om rm <model>...           delete models (they stay in the library)
om stop [model]...         unload models from memory (all if none given)
om up                      re-pull every installed model, then rebuild cc-longwork
om base                    the model cc-longwork is built from
om use <model>             rebuild cc-longwork on top of <model>
om nvim [model]            show or set the model nvim's codecompanion uses
om env                     shell exports for nvim: add eval "$(om env)" to your shell rc
om claude [-m model] [dir] [claude args]   Claude Code on local Ollama (cc-longwork unless -m)
om backup                  back up claude-local (with the claude-backup add-on) and ollama-local
om apply                   restart ollama with om's server settings (brew on macOS)
om upgrade                 brew upgrade ollama, then apply"""


def claude_exec(model, folder=None, args=()):
    if not shutil.which("claude"):
        raise RuntimeError("om claude needs Claude Code's `claude` command on your PATH")
    if folder:
        os.chdir(folder)
    env = {**os.environ, "ANTHROPIC_BASE_URL": API, "ANTHROPIC_AUTH_TOKEN": CLAUDE_TOKEN, "ANTHROPIC_API_KEY": "",
           "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", **{f"ANTHROPIC_DEFAULT_{tier}_MODEL": model for tier in CLAUDE_TIERS}}
    os.execvpe("claude", ["claude", *args], env)


def ask_yes(question):
    return sys.stdin.isatty() and input(f"{question} [y/N] ").strip().lower() == "y"


def cli_claude(args):
    args, model = list(args), CUSTOM
    if args[:1] == ["-m"] and len(args) > 1:
        model, args = args[1], args[2:]
    folder = args.pop(0) if args and os.path.isdir(os.path.expanduser(args[0])) else None
    claude_exec(model, folder and os.path.expanduser(folder), args)


def cli_rm(args):
    for name in args:
        if subprocess.run(["ollama", "rm", name]).returncode == 0:
            model_library_write(model_library_read() + [tagged(name)])


def cli_stop(args):
    for name in args or [m["name"] for m in api("/api/ps")["models"]]:
        if subprocess.run(["ollama", "stop", name]).returncode == 0:
            print(f"unloaded {name}")


def cli_up(args):
    for name in [m["name"] for m in api("/api/tags")["models"] if not is_custom(m["name"])]:
        print(f"== {name}")
        if subprocess.run(["ollama", "pull", name]).returncode:
            print(f"skipped {name} (not in the registry)")
    print(modelfile_rebuild())


def cli_use(args):
    if len(args) != 1:
        raise RuntimeError("usage: om use <model>")
    subprocess.run(["ollama", "pull", args[0]], check=True)
    print(modelfile_base_set(args[0]))


def cli_env(args):
    print(f'export OLLAMA_HOST="{API}"')
    if nvim_model():
        print(f'export OLLAMA_MODEL="{nvim_model()}"')


def cli_upgrade(args):
    if shutil.which("brew"):
        subprocess.run(["brew", "upgrade", "ollama"], check=True)
    print(ollama_service_apply())


COMMANDS = {
    "ls": lambda args: [subprocess.run(["ollama", "list"]), print(), subprocess.run(["ollama", "ps"])],
    "pull": lambda args: [subprocess.run(["ollama", "pull", name]) for name in args],
    "rm": cli_rm,
    "stop": cli_stop,
    "up": cli_up,
    "base": lambda args: print(base() or "not set"),
    "use": cli_use,
    "nvim": lambda args: print(nvim_model_set(args[0], ask_yes) if args else nvim_model() or "not set"),
    "env": cli_env,
    "claude": cli_claude,
    "backup": lambda args: print("\n".join(f"saved {path}" for path in backup_everything())),
    "apply": lambda args: print(ollama_service_apply()),
    "upgrade": cli_upgrade,
    "_download": lambda args: download_worker(args[0]),
}


def tui():
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    try:
        launch = curses.wrapper(main)
    except KeyboardInterrupt:
        launch = None
    running = [d["name"] for d in download_states() if d["state"] == "downloading"]
    if running:
        print(f"still downloading in the background: {', '.join(running)}. Run om to watch or pause them.")
    if launch:
        where, model = launch
        claude_exec(model, where)


def cli(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return tui()
    command = COMMANDS.get(argv[0])
    if command is None:
        print(HELP_TEXT)
        return
    try:
        command(argv[1:])
    except (RuntimeError, OSError, subprocess.CalledProcessError) as e:
        sys.exit(f"om {argv[0]}: {err_text(e)}")


if __name__ == "__main__":
    cli()
