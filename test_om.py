import curses, tempfile
from pathlib import Path

import om

with tempfile.TemporaryDirectory() as folder:
    om.MODEL_LIBRARY, om.OLLAMA_SETTINGS = Path(folder, "library.txt"), Path(folder, "settings.env")
    assert om.model_library_read() == []
    om.MODEL_LIBRARY.write_text("qwen3-coder\nqwen3-coder:latest\n\ngemma3:4b\n")
    assert om.model_library_read() == ["qwen3-coder:latest", "gemma3:4b"]
    om.model_library_write(om.model_library_read() + ["gemma3:4b", "a:b"])
    assert om.MODEL_LIBRARY.read_text() == "qwen3-coder:latest\ngemma3:4b\na:b\n"

    om.OM_SETTINGS = Path(folder, "om.json")
    assert om.om_settings_read() == {"controls": "classic", "screensaver": "warp", "progress style": "blocks", "walker": "llama",
                                 "accent colour": "cyan", "backup folder": "~/Documents"}
    om.OM_SETTINGS.write_text('{"screensaver": "rain", "accent colour": "plaid", "gone": 1}')
    assert om.om_settings_read()["screensaver"] == "rain" and om.om_settings_read()["accent colour"] == "cyan"

    om.ollama_settings_write({"OLLAMA_KEEP_ALIVE": "10m", "OLLAMA_ORIGINS": "a=b,c"})
    assert om.ollama_settings_read() == {"OLLAMA_KEEP_ALIVE": "10m", "OLLAMA_ORIGINS": "a=b,c"}

assert om.selection_move(ord("j"), 0, 3) == 1 and om.selection_move(ord("G"), 0, 3) == 2
assert om.selection_move(ord("k"), 0, 3) == 0 and om.selection_move(ord("x"), 0, 3) is None
assert om.selection_move(curses.KEY_DOWN, 0, 0) == 0
assert om.size_text(18.6e9) == "18.6 GB" and om.size_text(6.2e6) == "6.2 MB" and om.size_text(2048) == "2.0 KB"
assert om.age_seconds("3 weeks ago") < om.age_seconds("1 month ago") < om.age_seconds("2 years ago") < om.age_seconds("?")
print("ok")

import om_chat
chat = om_chat.Chat(None, None, dict(accent=1, err=2, tag=4, dim=8, warn=16), "", "m", Path("missing.json"))
rows = chat.message_lines(dict(role="assistant", content="hello world\n```py\n    x = 1\n```\nafter"), 40)
assert [r for r, _ in rows] == ["m", "  hello world", "  ```py", "      x = 1", "  ```", "  after", ""]
assert [a for _, a in rows][2:5] == [16, 16, 16] and rows[5][1] == 0
print("chat ok")

last = ["models", "configs", "om"]
assert om.page_jump(last, None, 1, 10.0, "models") == ("configs", (1, 10.0, "models"))
assert om.page_jump(last, (1, 10.0, "models"), 1, 10.5, "configs") == ("files", None)
assert om.page_jump(last, (1, 10.0, "models"), 1, 12.0, "configs") == ("configs", (1, 12.0, "configs"))
assert om.page_jump(last, (2, 10.0, "models"), 1, 10.5, "om") == ("configs", (1, 10.5, "om"))
assert om.page_jump(last, None, 5, 10.0, "models") == (None, None)
assert om.page_jump(last, (1, 10.0, "models"), -1, 10.5, "configs") == ("models", None)
assert om.page_jump(last, (1, 10.0, "models"), -1, 12.0, "configs") == (None, None)
assert [om.page_group(p) for p in ("models", "marketplace", "files", "om")] == [0, 0, 1, 2]
assert om.fuzzy_score("pl", "pull") == 1 and om.fuzzy_score("lp", "pull") is None and om.fuzzy_score("", "x") == 0
commands = [dict(name="pull", group="ollama"), dict(name="backup", group="local"), dict(name="backups", group="local"),
            dict(name="pause", group="ollama")]
assert [c["name"] for c in om.command_matches(commands, "pu")] == ["pull", "pause"]
assert [c["name"] for c in om.command_matches(commands, "back")] == ["backup", "backups"]
assert [c["name"] for c in om.command_matches(commands, "local ba")] == ["backup", "backups"]
assert om.command_matches(commands, "zzz") == []
assert om.palette_parse("pull qwen3") == ("pull", "qwen3") and om.palette_parse("local sys") == ("local sys", "")
assert om.palette_parse("ollama pull qwen3 x") == ("ollama pull", "qwen3 x") and om.palette_parse("local") == ("local", "")
import socket, urllib.error
assert om.ollama_timed_out(TimeoutError()) and om.ollama_timed_out(urllib.error.URLError(socket.timeout("timed out")))
assert not om.ollama_timed_out(urllib.error.URLError(ConnectionRefusedError(61, "Connection refused")))
assert om.page_label("chats") == "2 4 chats" and om.page_label("models") == "1 1 llms" and om.page_label("om") == "3 1 settings"
print("pages ok")

import om_backups, zipfile
with tempfile.TemporaryDirectory() as folder:
    folder = Path(folder)
    chats = folder / "chats"
    first, second = chats / "20261118-100000_a@1.json", chats / "20261118-110000_b@1.json"
    om_chat.chat_write(first, "a:1", [dict(role="user", content="  hello\n there "), dict(role="assistant", content="hi")])
    om_chat.chat_write(second, "b:1", [])
    assert not second.exists() and om_chat.chat_read(first)["model"] == "a:1"
    assert om_chat.chat_latest(chats, "a:1") == first and om_chat.chat_latest(chats, "b:1") is None
    assert om_chat.chat_title(om_chat.chat_read(first)) == "hello there"

    library = folder / "library.txt"
    library.write_text("x:1\n")
    archive = om_backups.ollama_local_backup({"chats": chats, "library.txt": library}, folder / "out")
    assert sorted(zipfile.ZipFile(archive).namelist()) == ["chats/20261118-100000_a@1.json", "library.txt"]
    library.write_text("changed\n")
    first.unlink()
    restored = om_backups.ollama_local_restore(archive, {"chats": chats, "library.txt": library})
    assert restored == ["chats/20261118-100000_a@1.json"] and library.read_text() == "changed\n" and first.exists()
    assert om_backups.backups_list(folder / "out") == [("ollama-local", archive)]
print("backups ok")
