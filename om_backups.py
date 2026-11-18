import getpass, re, shutil, socket, subprocess, time, zipfile
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*m")
KINDS = {"ClaudeBackups": "claude-local", "OllamaBackups": "ollama-local"}


def backup_name():
    return f"{socket.gethostname().split('.')[0]}_{getpass.getuser()}_{time.strftime('%Y%m%d-%H%M%S')}.zip"


def claude_backup_available(folder):
    return (folder / "Makefile").exists() or bool(shutil.which("claude-backup"))


def claude_backup_binary(folder):
    binary = folder / "claude-backup"
    if not (folder / "Makefile").exists():
        return Path(shutil.which("claude-backup"))
    if not binary.exists():
        built = subprocess.run(["make", "-C", str(folder)], capture_output=True, text=True)
        if built.returncode:
            raise RuntimeError((built.stderr.strip().splitlines() or ["make failed"])[-1])
    return binary


def claude_local_backup(folder, destination):
    result = subprocess.run([str(claude_backup_binary(folder)), "--yes", "backup", "-p", str(destination)], capture_output=True, text=True)
    output = ANSI.sub("", result.stdout + result.stderr)
    archive = re.search(r"Backup -> (.+\.zip)", output)
    if result.returncode or not archive:
        raise RuntimeError((output.strip().splitlines() or ["claude-backup failed"])[-1])
    return Path(archive.group(1))


def ollama_local_backup(sources, destination):
    archive = destination / "OllamaBackups" / backup_name()
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for name, source in sources.items():
            files = sorted(p for p in source.rglob("*") if p.is_file()) if source.is_dir() else [source] if source.exists() else []
            for file in files:
                zipped.write(file, name if file == source else f"{name}/{file.relative_to(source)}")
    return archive


def ollama_local_restore(archive, targets):
    restored = []
    with zipfile.ZipFile(archive) as zipped:
        for entry in zipped.namelist():
            top, _, rest = entry.partition("/")
            if top not in targets:
                continue
            target = targets[top] / rest if rest else targets[top]
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zipped.read(entry))
                restored.append(entry)
    return restored


def backups_list(destination):
    found = [(KINDS[folder], path) for folder in KINDS for path in (destination / folder).glob("*.zip")]
    return sorted(found, key=lambda item: item[1].stat().st_mtime, reverse=True)
