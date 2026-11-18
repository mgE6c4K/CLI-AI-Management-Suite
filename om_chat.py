import curses, json, os, signal, textwrap, threading, time, urllib.request

SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
HINT = "⏎ send · esc stops a reply / returns to om · ↑↓ pgup pgdn home end scroll · /new starts a new chat"


def chat_new_path(folder, model):
    return folder / f"{time.strftime('%Y%m%d-%H%M%S')}_{model.replace('/', '_').replace(':', '@')}.json"


def chat_read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def chat_write(path, model, messages):
    if not messages:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(dict(model=model, messages=messages), indent=1))
    os.replace(temporary, path)


def chat_list(folder):
    return [(path, chat) for path in sorted(folder.glob("*.json"), reverse=True) if (chat := chat_read(path)).get("model")]


def chat_latest(folder, model):
    return next((path for path, chat in chat_list(folder) if chat["model"] == model), None)


def cc_record_write(folder, session, cwd, model):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{session}.json").write_text(json.dumps(dict(session=session, cwd=str(cwd), model=model, started=time.time())))


def cc_transcript(projects, session):
    return next(iter(projects.glob(f"*/{session}.jsonl")), None)


def cc_summary(transcript):
    title, first, messages = None, None, 0
    for line in transcript.read_text(errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        kind = entry.get("type")
        if kind == "custom-title":
            title = entry.get("customTitle") or title
        elif kind in ("user", "assistant") and not entry.get("isMeta"):
            content = entry.get("message", {}).get("content")
            text = content if isinstance(content, str) else " ".join(
                block.get("text", "") for block in content or [] if isinstance(block, dict) and block.get("type") == "text")
            messages += bool(text.strip())
            first = first or (text.strip() if kind == "user" else None)
    return dict(title=" ".join((title or first or "empty session").split()), messages=messages)


def cc_sessions(folder, projects):
    sessions = []
    for path in folder.glob("*.json"):
        record = chat_read(path)
        if record.get("session"):
            transcript = cc_transcript(projects, record["session"])
            summary = cc_summary(transcript) if transcript else dict(title="no messages yet", messages=0)
            sessions.append(dict(record, **summary, path=path, transcript=transcript,
                                 updated=transcript.stat().st_mtime if transcript else record.get("started", 0)))
    return sorted(sessions, key=lambda s: s["updated"], reverse=True)


def nvim_chats(index_path):
    index = chat_read(index_path)
    return sorted(index.values(), key=lambda chat: chat.get("updated_at") or 0, reverse=True) if isinstance(index, dict) else []


def chat_title(chat):
    first = next((m["content"] for m in chat.get("messages", []) if m["role"] == "user"), "")
    return " ".join(first.split()) or "empty chat"


class Chat:
    def __init__(self, scr, put, C, api_url, model, path):
        self.scr, self.put, self.C, self.api_url, self.model, self.path = scr, put, C, api_url, model, path
        self.messages = chat_read(path).get("messages", [])
        self.text, self.scroll, self.status = "", 0, ""
        self.generation, self.busy = 0, False  # a reply belongs to one generation; esc bumps it to drop the rest
        self.wrapped = {}

    # ---- talking to ollama ----
    def send(self, text):
        self.messages.append(dict(role="user", content=text))
        self.generation += 1
        self.busy, self.scroll, self.status = True, 0, "loading the model…"
        self.save()
        threading.Thread(target=self.stream, args=(self.generation,), daemon=True).start()

    def save(self):
        chat_write(self.path, self.model, self.messages)

    def stream(self, generation):
        history = [dict(role=m["role"], content=m["content"]) for m in self.messages if m["role"] in ("user", "assistant")]
        reply = dict(role="assistant", content="", thinking="")
        request = urllib.request.Request(f"{self.api_url}/api/chat", data=json.dumps(dict(model=self.model, messages=history)).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=None) as response:
                for line in response:
                    if generation != self.generation:
                        return  # stopped with esc; closing the stream makes ollama stop generating
                    if not reply["content"] and not reply["thinking"] and reply not in self.messages[-1:]:
                        self.messages.append(reply)
                    event = json.loads(line)
                    if "error" in event:
                        raise RuntimeError(event["error"])
                    reply["thinking"] += event.get("message", {}).get("thinking", "")
                    reply["content"] += event.get("message", {}).get("content", "")
                    self.status = "thinking…" if reply["thinking"] and not reply["content"] else "writing…"
                    if event.get("done") and event.get("eval_duration"):
                        self.status = f"{event['eval_count'] / event['eval_duration'] * 1e9:.0f} tokens/s"
        except Exception as e:
            if generation == self.generation:
                self.messages.append(dict(role="error", content=str(e)))
                self.status = ""
        finally:
            if generation == self.generation:
                self.busy = False
                self.save()

    def stop(self):
        self.generation += 1
        self.busy, self.status = False, "stopped"
        self.save()

    # ---- drawing ----
    def lines(self, width):
        out = []
        for i, m in enumerate(self.messages):
            key = (i, len(m["content"]), len(m.get("thinking", "")), width)
            if key not in self.wrapped:
                self.wrapped[key] = self.message_lines(m, width)
            out += self.wrapped[key]
        return out

    def message_lines(self, m, width):
        C = self.C
        label, attr = {"user": ("you", C["accent"]), "error": ("error", C["err"])}.get(m["role"], (self.model, C["tag"]))
        out, code = [(label, attr | curses.A_BOLD)], False
        for line in m.get("thinking", "").splitlines():
            out += [(f"  {row}", C["dim"]) for row in textwrap.wrap(line, width - 2) or [""]]
        for line in m["content"].splitlines():
            fence = line.lstrip().startswith("```")
            as_code = code or fence
            colour = C["warn"] if as_code else C["err"] if m["role"] == "error" else 0
            rows = ([line[i:i + width - 2] for i in range(0, max(len(line), 1), width - 2)] if as_code
                    else textwrap.wrap(line, width - 2) or [""])
            out += [(f"  {row}", colour) for row in rows]
            code = code != fence  # a fence opens or closes a block
        return out + [("", 0)]

    def draw(self):
        h, w = self.scr.getmaxyx()
        C = self.C
        self.scr.erase()
        self.put(0, 0, " " * w, C["bar"])
        self.put(0, 1, " om ", C["sel"] | curses.A_BOLD)
        self.put(0, 6, f" chat · {self.model} ", C["bar"] | curses.A_BOLD)
        lines, area = self.lines(w - 2), h - 4
        self.scroll = max(0, min(self.scroll, len(lines) - area))
        end = len(lines) - self.scroll
        for y, (text, attr) in enumerate(lines[max(0, end - area):end], 1):
            self.put(y, 1, text, attr)
        if self.scroll:
            self.put(h - 4, w - 22, f" ↓ {self.scroll} more lines ", C["sel"])
        spin = SPIN[int(time.time() * 10) % len(SPIN)] + " " if self.busy else ""
        self.put(h - 3, 0, "─" * w, C["dim"])
        self.put(h - 3, 2, f" {spin}{self.status} " if spin or self.status else "", C["dim"])
        shown = self.text[-(w - 4):]
        self.put(h - 2, 0, "› ", C["accent"] | curses.A_BOLD)
        self.put(h - 2, 2, shown)
        self.put(h - 1, 1, HINT, C["dim"])
        self.scr.move(h - 2, 2 + len(shown))
        self.scr.refresh()

    # ---- keys ----
    def run(self):
        old = signal.signal(signal.SIGINT, lambda *_: self.stop())
        curses.curs_set(1)
        self.scr.timeout(50)
        try:
            while True:
                self.draw()
                try:
                    k = self.scr.get_wch()
                except curses.error:
                    continue  # no key this frame
                if self.handle(k) is False:
                    return
        finally:
            signal.signal(signal.SIGINT, old)
            curses.curs_set(0)
            self.scr.timeout(150)

    def handle(self, k):
        page = self.scr.getmaxyx()[0] - 5
        moves = {curses.KEY_UP: 1, curses.KEY_DOWN: -1, curses.KEY_PPAGE: page, curses.KEY_NPAGE: -page,
                 curses.KEY_HOME: 10 ** 9, curses.KEY_END: -10 ** 9}
        if k in moves:
            self.scroll = max(0, self.scroll + moves[k])
        elif k == "\x1b":
            if not self.busy:
                return False
            self.stop()
        elif k in ("\n", "\r", curses.KEY_ENTER):
            return self.submit()
        elif k in ("\x7f", "\b", curses.KEY_BACKSPACE):
            self.text = self.text[:-1]
        elif k == "\x15":
            self.text = ""
        elif isinstance(k, str) and k.isprintable():
            self.text += k

    def submit(self):
        text, self.text = self.text.strip(), ""
        if text in ("/bye", "/exit"):
            return False
        if text in ("/new", "/clear"):
            self.stop()
            self.path, self.messages = chat_new_path(self.path.parent, self.model), []
            self.wrapped.clear()
            self.status = "new chat; the last one stays saved"
        elif text and not self.busy:
            self.send(text)
        elif text:
            self.text, self.status = text, "still replying: esc stops it"
