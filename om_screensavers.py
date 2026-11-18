import curses, random, time

SCENES = ["warp", "rain", "pipes", "chomp"]
PROGRESS_STYLES = ["blocks", "segments", "bar", "minimal"]
FULL_SPEED = 500e6


def speed(d):
    return min(d["rate"], FULL_SPEED) / FULL_SPEED if d and d["state"] == "downloading" else 0


def moving(d):
    return bool(d) and d["state"] == "downloading"


# ---- walkers: [walk frame, walk frame], resting frame ----
WALKERS = {
    "llama": ([["      ,^ ", "     (o> ", " ____/|  ", "(     |  ", " /\\  /\\ "],
               ["      ,^ ", "     (o> ", " ____/|  ", "(     |  ", " |\\  |\\ "]],
              ["      ,^  z", "     (-> z ", " ____/|    ", "(_____|    ", "           "]),
    "cat": ([["     /\\_/\\ ", "~~~( o.o ) ", "  (  ___ ) ", "   /\\   /\\ "],
             ["     /\\_/\\ ", " ~~( o.o ) ", "  (  ___ ) ", "   |\\   |\\ "]],
            ["     /\\_/\\ z", "~~~( -.- )  ", "  (_______) ", "            "]),
    "robot": ([["  .-.  ", " [o_o] ", " /|=|\\ ", "  / \\  "],
               ["  .-.  ", " [o_o] ", " \\|=|/ ", "  | |  "]],
              ["  .-.  z", " [-_-]  ", " /|=|\\  ", "  |_|   "]),
    "snail": ([["   .--.   o o ", "  ( @  )__/_/ ", "~~~~~~~~~~~   "],
               ["   .--.  o o  ", "  ( @  )_/_/  ", " ~~~~~~~~~~   "]],
              ["   .--.     z ", "  ( @  )      ", "~~~~~~~~      "]),
}


def walker_draw(put, C, name, x, ground, walking, umbrella=False):
    frames, resting = WALKERS[name]
    sprite = frames[int(time.time() * 4) % 2] if walking else resting
    for i, row in enumerate(sprite):
        put(ground - len(sprite) + i, x, row, curses.A_BOLD)
    if umbrella:
        middle = x + max(len(row) for row in sprite) // 2 - 4
        put(ground - len(sprite) - 2, middle, " .-'^'-. ", C["accent"] | curses.A_BOLD)
        put(ground - len(sprite) - 1, middle, "'---|---'", C["accent"] | curses.A_BOLD)


def walker_width(name):
    return max(len(row) for frame in WALKERS[name][0] for row in frame)


# ---- percentage styles ----
BLOCKS = {
    "0": ["███", "█ █", "█ █", "█ █", "███"], "1": [" █ ", "██ ", " █ ", " █ ", "███"],
    "2": ["███", "  █", "███", "█  ", "███"], "3": ["███", "  █", "███", "  █", "███"],
    "4": ["█ █", "█ █", "███", "  █", "  █"], "5": ["███", "█  ", "███", "  █", "███"],
    "6": ["███", "█  ", "███", "█ █", "███"], "7": ["███", "  █", "  █", "  █", "  █"],
    "8": ["███", "█ █", "███", "█ █", "███"], "9": ["███", "█ █", "███", "  █", "███"],
    "%": ["█ █", "  █", " █ ", "█  ", "█ █"], "-": ["   ", "   ", "███", "   ", "   "],
}
SEGMENTS = {
    "0": ["┏━┓", "┃ ┃", "┗━┛"], "1": ["  ╻", "  ┃", "  ╹"], "2": ["╺━┓", "┏━┛", "┗━╸"], "3": ["╺━┓", " ━┫", "╺━┛"],
    "4": ["╻ ╻", "┗━┫", "  ╹"], "5": ["┏━╸", "┗━┓", "╺━┛"], "6": ["┏━╸", "┣━┓", "┗━┛"], "7": ["╺━┓", "  ┃", "  ╹"],
    "8": ["┏━┓", "┣━┫", "┗━┛"], "9": ["┏━┓", "┗━┫", "╺━┛"], "%": ["o ╱", " ╱ ", "╱ o"], "-": ["   ", "╺━╸", "   "],
    ".": ["   ", "   ", " • "],
}
EIGHTHS = " ▏▎▍▌▋▊▉"


def font_rows(text, font, wide):
    cells = [font[c] for c in text if c in font]
    widen = (lambda row: row.replace("█", "██").replace(" ", "  ")) if wide else (lambda row: row)
    return [("  " if wide else " ").join(widen(cell[row]) for cell in cells) for row in range(len(cells[0]))] if cells else []


def bar_rows(frac, width):
    cells = frac * width
    fill = "█" * int(cells) + (EIGHTHS[int(cells % 1 * 8)] if int(cells) < width else "")
    bar = "▕" + fill.ljust(width, "░") + "▏"
    return [bar, bar, f"{frac:.1%}".center(len(bar))]


def percent_rows(style, frac, width, known):
    text = f"{frac:.0%}" if known else "--"
    if style == "segments":
        return font_rows(f"{frac:.1%}" if known else "--", SEGMENTS, False)
    if style == "bar":
        return bar_rows(frac, max(10, min(60, width - 10))) if known else ["--"]
    if style == "minimal":
        return [f"{frac:.1%}" if known else "--"]
    return font_rows(text, BLOCKS, True)


# ---- scenes ----
def warp(put, C, state, d, h, w):
    stars = state.setdefault("stars", [[random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(0.2, 1)] for _ in range(90)])
    step = 0.004 + speed(d) * 0.05
    for star in stars:
        star[2] -= step
        x, y = int(w / 2 + star[0] / star[2] * w / 4), int(h / 2 + star[1] / star[2] * h / 4)
        if star[2] <= 0.05 or not (0 <= x < w and 0 <= y < h - 1):
            star[:] = [random.uniform(-1, 1), random.uniform(-1, 1), 1.0]
            continue
        near = 1 - star[2]
        put(y, x, "*" if near > 0.75 else "+" if near > 0.45 else ".",
            C["accent"] | curses.A_BOLD if near > 0.75 else C["accent"] if near > 0.45 else C["dim"])


def rain(put, C, state, d, h, w):
    drops = state.setdefault("drops", [])
    wanted, ground = int(w * h / 12 * (0.25 + speed(d) * 0.75)), h - 3
    while len(drops) < wanted:  # [x, y, fall speed]
        drops.append([random.randrange(w), random.uniform(-h, 0), random.uniform(0.6, 1.6)])
    del drops[wanted:]
    for drop in drops:
        drop[1] += drop[2]
        if drop[1] >= ground:
            put(ground - 1, drop[0], random.choice(".,`'"), C["rain"])
            drop[:] = [random.randrange(w), random.uniform(-3, 0), random.uniform(0.6, 1.6)]
        elif drop[1] >= 0:
            put(int(drop[1]), drop[0], "|" if drop[2] > 1.2 else "'" if drop[2] < 0.8 else "¦",
                C["rain"] | (curses.A_BOLD if drop[2] > 1.2 else 0))


PIPE_STEPS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
PIPE_OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}
PIPE_JOINTS = {frozenset(("left", "right")): "━", frozenset(("up", "down")): "┃", frozenset(("down", "right")): "┏",
               frozenset(("down", "left")): "┓", frozenset(("up", "right")): "┗", frozenset(("up", "left")): "┛"}


def pipes(put, C, state, d, h, w):
    cells, heads = state.setdefault("cells", {}), state.setdefault("heads", [])
    colours = ["accent", "ok", "tag", "warn", "rain", "err"]
    if len(cells) > w * h * 0.45 or not heads:
        cells.clear()
        heads[:] = [dict(y=random.randrange(h - 1), x=random.randrange(w), way=random.choice(list(PIPE_STEPS)),
                         colour=random.choice(colours)) for _ in range(3)]
    for _ in range(1 + int(speed(d) * 6)):
        for head in heads:
            came = head["way"]
            if random.random() < 0.15:
                head["way"] = random.choice([way for way in PIPE_STEPS if way not in (came, PIPE_OPPOSITE[came])])
            cells[(head["y"], head["x"])] = (PIPE_JOINTS[frozenset((PIPE_OPPOSITE[came], head["way"]))], head["colour"])
            dy, dx = PIPE_STEPS[head["way"]]
            head["y"], head["x"] = (head["y"] + dy) % (h - 1), (head["x"] + dx) % w
    for (y, x), (glyph, colour) in cells.items():
        put(y, x, glyph, C[colour])


MUNCHER = ([["╭────╮", "│ ◉ ╱ ", "│   ╲ ", "╰────╯"], ["╭────╮", "│ ◉  │", "│ ▾▾▾│", "╰────╯"]],
           ["╭────╮ z", "│ -  │  ", "│ ▾▾▾│  ", "╰────╯  "])


def chomp(put, C, state, d, h, w):
    frac = d["done"] / d["total"] if d and d.get("total") else 0
    top, lane = h - 10, h - 8
    put(top, 1, "═" * (w - 2), C["rain"] | curses.A_BOLD)
    put(top + 5, 1, "═" * (w - 2), C["rain"] | curses.A_BOLD)
    x = 2 + int(frac * (w - 12))
    for dot in range(x + 7, w - 2, 2):
        pellet = (dot - 2) * 10 // (w - 4) != (dot - 4) * 10 // (w - 4)  # a big one every tenth of the way
        put(lane, dot, "●" if pellet else "·", C["warn"] | curses.A_BOLD if pellet else C["warn"])
    frames, resting = MUNCHER
    chewing = int(time.time() * (3 + speed(d) * 9)) % 2
    for i, row in enumerate(frames[chewing] if moving(d) else resting):
        put(top + 1 + i, x, row, C["accent"] | curses.A_BOLD)
