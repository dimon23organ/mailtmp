#!/usr/bin/env python3
"""Гоняет TUI в псевдотерминале и снимает текстовый кадр.

Зачем это нужно: curses.require_window() нельзя вызвать без настоящего
терминала, а `shot`-подобного способа снять экран TUI нет. Поэтому
поднимаем pty, кормим программе клавиши, читаем что она нарисовала.

    python3 tools/tui_probe.py 'q'
    python3 tools/tui_probe.py '?' q

Каждый аргумент — одна последовательность клавиш, между ними программа
успевает отрисовать кадр. Кадры печатаются в stdout, ошибки curses
(которые он пишет в stderr) собираются отдельно.
"""

import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import fcntl

CMD = sys.argv[1] if len(sys.argv) > 1 else "q"
KEYS = sys.argv[2:] or ["q"]
ROWS, COLS = 34, 150


def strip_ansi(data):
    """Убирает управляющие последовательности, но сохраняет позиционирование.

    feed() разбирает позиционирование сам, поэтому здесь режем только то,
    что не несёт смысла для сетки: цвета, режимы, частные коды терминала.
    """
    # Цвета и атрибуты: \x1b[...m — выкидываем целиком
    data = re.sub(rb"\x1b\[[0-9;?]*m", b"", data)
    # Выбор кодировки: \x1b(B, \x1b)0 и подобные
    data = re.sub(rb"\x1b[\(\)][B0]", b"", data)
    # Частные режимы терминала: \x1b[?...h/l, \x1b[...t, \x1b[...r
    data = re.sub(rb"\x1b\[\?[0-9;]*[hl]", b"", data)
    data = re.sub(rb"\x1b\[[0-9;]*t", b"", data)
    data = re.sub(rb"\x1b\[[0-9;]*r", b"", data)
    # Включение/выключение режимов, сохранение курсора
    data = re.sub(rb"\x1b[=>78]", b"", data)
    data = re.sub(rb"\x1b[78]", b"", data)
    return data


def feed(data, grid, cursor):
    """Разбирает поток в сетку. Сетка накапливается между кадрами.

    Кириллица приходит многобайтовой: читаем UTF-8 по символам, а не
    по байтам, иначе каждая буква распадётся на «замены».
    """
    row, col = cursor
    text = data.decode("utf-8", "replace")
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\x1b":
            m = re.match(r"\x1b\[([0-9;?]*)([a-zA-Z])", text[i:])
            if m:
                params, cmd = m.group(1), m.group(2)
                nums = [int(x) for x in params.split(";") if x.isdigit()]
                # Позиционирование: curses мешает CUP, VPA, CHA и курсорные
                # сдвиги. Без их учёта кадр рассыпается на строки.
                if cmd == "H":
                    row = (nums[0] - 1) if nums else 0
                    col = (nums[1] - 1) if len(nums) > 1 else 0
                elif cmd == "d":
                    row = (nums[0] - 1) if nums else 0
                elif cmd == "G":
                    col = (nums[0] - 1) if nums else 0
                elif cmd == "C":
                    col += nums[0] if nums else 1
                elif cmd == "D":
                    col = max(0, col - (nums[0] if nums else 1))
                elif cmd == "A":
                    row = max(0, row - (nums[0] if nums else 1))
                elif cmd == "B":
                    row += nums[0] if nums else 1
                elif cmd == "J" and params in ("2", ""):
                    for r in grid:
                        for c in range(COLS):
                            r[c] = " "
                    row = col = 0
                elif cmd == "J" and params == "0":
                    for c in range(col, COLS):
                        grid[row][c] = " "
                elif cmd == "J" and params == "1":
                    for c in range(0, min(col + 1, COLS)):
                        grid[row][c] = " "
                elif cmd == "K":
                    # ncurses чистит остаток строки через EL — без этой
                    # ветки затираемые хвосты остаются в сетке.
                    mode = params or "0"
                    if mode == "0":
                        rng = range(col, COLS)
                    elif mode == "1":
                        rng = range(0, min(col + 1, COLS))
                    else:
                        rng = range(0, COLS)
                    for c in rng:
                        if 0 <= row < ROWS and c < COLS:
                            grid[row][c] = " "
                elif cmd == "X":
                    # ECH: затереть N символов, курсор не двигается.
                    times = nums[0] if nums else 1
                    for k in range(times):
                        if 0 <= row < ROWS and col + k < COLS:
                            grid[row][col + k] = " "
                elif cmd == "S":
                    for _ in range(nums[0] if nums else 1):
                        grid.pop(0)
                        grid.append([" "] * COLS)
                elif cmd == "T":
                    for _ in range(nums[0] if nums else 1):
                        grid.insert(0, [" "] * COLS)
                        grid.pop()
                elif cmd == "b":
                    # REP: повторяет предыдущий символ N раз. ncurses
                    # так затирает хвосты строк пробелами — без этой
                    # ветки затирка молча теряется и старый текст
                    # остаётся на экране.
                    times = nums[0] if nums else 1
                    last = grid[row][col - 1] if col > 0 else " "
                    for _ in range(times):
                        if 0 <= row < ROWS and 0 <= col < COLS:
                            grid[row][col] = last
                        col += 1
                i += m.end()
                continue
            # Прочие escape: CSI-последовательности с ';' и прочее
            # пропускаем целиком, чтобы не печатать мусор.
            m2 = re.match(r"\x1b[\(\)][B0]", text[i:])
            if m2:
                i += m2.end()
                continue
            m3 = re.match(r"\x1b[=>78Mc]", text[i:])
            if m3:
                i += m3.end()
                continue
            i += 1
            continue
            i += 1
            continue
        if ch == "\r":
            col = 0
        elif ch == "\n":
            row += 1
            col = 0
            if row >= ROWS:
                # ncurses при записи на последнюю строку прокручивает
                # экран вверх. Без этого нижняя строка (подсказка)
                # уезжает за сетку и теряется.
                grid.pop(0)
                grid.append([" "] * COLS)
                row = ROWS - 1
        elif ch == "\b":
            col = max(0, col - 1)
        elif ch >= " ":
            if row >= ROWS:
                grid.pop(0)
                grid.append([" "] * COLS)
                row = ROWS - 1
            if 0 <= row < ROWS and 0 <= col < COLS:
                grid[row][col] = ch
            col += 1
        i += 1
    cursor[0], cursor[1] = row, col


def snapshot(grid):
    return "\n".join("".join(r).rstrip() for r in grid)


def main():
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm-256color"
        os.environ["LINES"] = str(ROWS)
        os.environ["COLUMNS"] = str(COLS)
        os.execvp("python3", ["python3", CMD])
        os._exit(1)

    fcntl.ioctl(fd, termios.TIOCSWINSZ,
                struct.pack("HHHH", ROWS, COLS, 0, 0))

    # Сетка одна на весь прогон: curses рисует ДИФФЕРЕНЦИАЛЬНО, шлёт
    # только изменившиеся клетки. Если обнулять сетку перед каждым
    # кадром, в нём будут только последние изменённые символы.
    grid = [[" "] * COLS for _ in range(ROWS)]
    cursor = [0, 0]
    frames = []

    def drain(seconds, idle=0.35):
        """Читает вывод, пока он идёт, и жмёт наглухо паузу idle секунд.

        Фиксированный sleep ненадёжен: если программа успела отрисовать
        раньше, кадр терялся, и нажатия выглядели неработающими. Теперь
        ждём реальных данных.
        """
        deadline = time.monotonic() + seconds
        chunk = b""
        last = time.monotonic()
        while time.monotonic() < deadline:
            r, _, _ = select.select([fd], [], [], 0.05)
            if fd in r:
                try:
                    part = os.read(fd, 65536)
                except OSError:
                    break
                if not part:
                    break
                chunk += part
                last = time.monotonic()
            elif chunk and time.monotonic() - last >= idle:
                break
        return chunk

    # ncurses с keypad(True) высылает smkx и ждёт прикладную форму
    # стрелок: ESC O A/B/C/D, а не ESC [ A/B/C/D. Настоящий терминал
    # переключается сам, псевдотерминал — нет. Поэтому probe держит флаг
    # прикладного режима и сам переписывает CSI в SS3, иначе стрелки
    # выглядят сломанными, хотя в живом терминале работают.
    app_mode = {"on": False}

    def send(key):
        data = key.encode()
        if app_mode["on"] and len(data) == 3 and data[:2] == b"\x1b[":
            if data[2:3] in (b"A", b"B", b"C", b"D", b"H", b"F"):
                data = b"\x1bO" + data[2:3]
        try:
            os.write(fd, data)
        except OSError:
            pass

    chunks = []
    first = drain(2.5)  # запуск, первый кадр
    # smkx = ESC [ ? 1 h — терминал переведён в прикладной режим.
    if b"\x1b[?1h" in first:
        app_mode["on"] = True
    feed(strip_ansi(first), grid, cursor)
    chunks.append(first)
    frames.append(("старт", snapshot(grid)))

    for key in KEYS:
        send(key)
        chunk = drain(3.0)
        if not chunk:
            continue
        chunks.append(chunk)
        feed(strip_ansi(chunk), grid, cursor)
        frames.append(("после %r" % key, snapshot(grid)))

    try:
        os.write(fd, b"q")
    except OSError:
        pass
    chunks.append(drain(0.8))
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    os.waitpid(pid, os.WNOHANG)

    # stdout здесь может быть в cp866 (терминал Void), а текст — UTF-8.
    # Перекодируем в utf-8 с заменой, иначе кириллица рассыпается.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    text = strip_ansi(b"".join(chunks)).decode("utf-8", "replace")

    print("=" * 100)
    for label, frame in frames:
        print("--- %s ---" % label)
        print(frame)
    noise = [ln for ln in text.splitlines()
             if "curses" in ln.lower() or "Traceback" in ln or ln.strip().startswith("Error")]
    if noise:
        print("--- CURSES/ОШИБКИ ---")
        for line in noise:
            print(line)
    if not frames:
        print("!! ни одного кадра — программа не отрисовала ничего")


if __name__ == "__main__":
    main()