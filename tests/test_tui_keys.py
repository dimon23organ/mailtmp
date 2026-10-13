#!/usr/bin/env python3
"""Тесты логики клиента — без терминала.

Проверять curses через псевдотерминал оказалось ненадёжно: нажатие то
доходит, то нет, в зависимости от таймингов отрисовки, и результат
зависит от скорости машины, а не от кода. Здесь терминала нет вообще —
подменяется только addstr, а handle() вызывается напрямую.

Запуск:
    python3 tests/test_tui_keys.py
"""

import curses
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "tests"))

import fake_tui as ft                                  # noqa: E402


class FakeScr:
    """Минимальная замена окна curses: только размер и addstr."""

    def __init__(self, h=34, w=150):
        self.h, self.w = h, w
        self.drawn = []

    def getmaxyx(self):
        return self.h, self.w

    def addstr(self, y, x, text, attr=0):
        self.drawn.append((y, x, text, attr))
        return len(text)

    def erase(self):
        self.drawn = []

    def noutrefresh(self):
        pass

    def refresh(self):
        pass

    def keypad(self, value):
        pass

    def getch(self):
        return -1


def load_tui():
    loader = importlib.machinery.SourceFileLoader("tui_under_test", str(HERE / "mailtmp-tui"))
    spec = importlib.util.spec_from_loader("tui_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    mod.core.api = ft.fake_api
    mod.core.load_state = lambda: {"address": "demo@maxxspace.com",
                                   "token": "t", "password": "x"}
    return mod


STATE = Path(tempfile.gettempdir()) / "mailtmp-tui-test-state.json"


def make_app(mod, h=34, w=150, items=None):
    scr = FakeScr(h, w)
    app = mod.App.__new__(mod.App)
    app.scr = scr
    app.p = mod.Panel(scr)
    app.ui = {"starred": [], "read": []}
    app.items = list(items if items is not None else ft.MESSAGES)
    app.cursor = 0
    app.top = 0
    app.focus = "list"
    app.status = ""
    app.status_kind = "info"
    app.search = ""
    app.searching = False
    app.folder = "inbox"
    app.side_cursor = 0
    app.screen = "mail"
    app.narrow_page = "list"
    app.read_id = None
    app.read_scroll = 0
    app.read_msg = None
    app.wait_until = 0.0
    app.auto = False
    app.poll = 5.0
    app.last_poll = 0.0
    app.quit = False
    return app


class Navigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_tui()
        cls.mod.UI_STATE = STATE

    def setUp(self):
        if STATE.exists():
            STATE.unlink()
        self.app = make_app(self.mod)

    def test_letters_move_cursor(self):
        for expected in (1, 2, 3):
            self.app.handle(ord("j"))
            self.assertEqual(self.app.cursor, expected)
        for expected in (2, 1, 0):
            self.app.handle(ord("k"))
            self.assertEqual(self.app.cursor, expected)

    def test_arrow_keys_move_cursor(self):
        self.app.handle(curses.KEY_DOWN)
        self.assertEqual(self.app.cursor, 1)
        self.app.handle(curses.KEY_DOWN)
        self.assertEqual(self.app.cursor, 2)
        self.app.handle(curses.KEY_UP)
        self.assertEqual(self.app.cursor, 1)

    def test_cursor_stops_at_edges(self):
        self.app.handle(ord("k"))
        self.assertEqual(self.app.cursor, 0)
        for _ in range(len(ft.MESSAGES) + 5):
            self.app.handle(ord("j"))
        self.assertEqual(self.app.cursor, len(ft.MESSAGES) - 1)

    def test_g_and_shift_g_jump(self):
        self.app.handle(ord("G"))
        self.assertEqual(self.app.cursor, len(ft.MESSAGES) - 1)
        self.app.handle(ord("g"))
        self.assertEqual(self.app.cursor, 0)

    def test_page_keys(self):
        self.app.handle(curses.KEY_NPAGE)
        self.assertGreater(self.app.cursor, 0)
        before = self.app.cursor
        self.app.handle(curses.KEY_PPAGE)
        self.assertLess(self.app.cursor, before)

    def test_enter_opens_selected(self):
        self.app.handle(ord("j"))
        self.app.handle(ord("j"))
        self.app.handle(10)
        expected = ft.MESSAGES[2]["id"]        # список отсортирован по дате
        self.assertEqual(self.app.read_id, expected)
        self.assertEqual(self.app.focus, "read")

    def test_u_returns_to_list(self):
        self.app.handle(10)
        self.app.focus = "read"
        self.app.handle(ord("u"))
        self.assertEqual(self.app.focus, "list")
        self.assertIsNone(self.app.read_id)

    def test_opening_marks_read(self):
        mid = ft.MESSAGES[0]["id"]
        self.app.handle(10)
        self.assertIn(mid, self.app.ui["read"])


class Star(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_tui()
        cls.mod.UI_STATE = STATE

    def setUp(self):
        if STATE.exists():
            STATE.unlink()
        self.app = make_app(self.mod)

    def test_star_toggles_and_persists(self):
        mid = ft.MESSAGES[0]["id"]
        self.assertFalse(self.app.is_starred(mid))
        self.app.handle(ord("s"))
        self.assertTrue(self.app.is_starred(mid))
        self.assertTrue(STATE.exists(), "звезда должна сохраниться на диск")
        self.app.handle(ord("s"))
        self.assertFalse(self.app.is_starred(mid))

    def test_starred_folder_reachable(self):
        """Папка «Отмеченные» обязана открываться — раньше было недостижимо."""
        self.app.handle(ord("s"))
        self.app.focus = "side"
        self.app.side_cursor = 1
        self.app.handle(10)
        self.assertEqual(self.app.folder, "starred")
        self.assertEqual(len(self.app.rows), 1)

    def test_sidebar_arrows_move_folder_cursor(self):
        self.app.focus = "side"
        self.app.handle(ord("j"))
        self.assertEqual(self.app.side_cursor, 1)
        self.app.handle(ord("j"))
        self.assertEqual(self.app.side_cursor, 1, "не должен уходить за последнюю папку")
        self.app.handle(ord("k"))
        self.assertEqual(self.app.side_cursor, 0)
        self.app.handle(ord("k"))
        self.assertEqual(self.app.side_cursor, 0)


class Search(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_tui()
        cls.mod.UI_STATE = STATE

    def setUp(self):
        if STATE.exists():
            STATE.unlink()
        self.app = make_app(self.mod)

    def test_search_by_sender_and_subject(self):
        self.app.handle(ord("/"))
        self.assertTrue(self.app.searching)
        for ch in "yandex":
            self.app.handle(ord(ch))
        self.app.handle(10)
        self.assertEqual(self.app.search, "yandex")
        self.assertEqual(len(self.app.rows), 1)

    def test_search_escape_cancels(self):
        self.app.handle(ord("/"))
        for ch in "vk":
            self.app.handle(ord(ch))
        self.app.handle(27)
        self.assertFalse(self.app.searching)
        self.assertEqual(self.app.search, "")
        self.assertEqual(len(self.app.rows), len(ft.MESSAGES))

    def test_search_no_hits(self):
        self.app.handle(ord("/"))
        for ch in "zzzzz":
            self.app.handle(ord(ch))
        self.app.handle(10)
        self.assertEqual(self.app.rows, [])

    def test_backspace(self):
        self.app.handle(ord("/"))
        for ch in "vk":
            self.app.handle(ord(ch))
        self.app.handle(curses.KEY_BACKSPACE)
        self.assertEqual(self.app.search, "v")


class Layout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_tui()

    def test_wide_terminal_has_three_panes(self):
        p = self.mod.Panel(FakeScr(34, 150))
        self.assertFalse(p.narrow)
        self.assertIsNotNone(p.side)
        self.assertIsNotNone(p.read)
        self.assertLess(p.list[0], p.read[0])

    def test_narrow_terminal_keeps_reader_area(self):
        """Раньше в узком окне Enter не показывал письмо: p.read был None."""
        p = self.mod.Panel(FakeScr(20, 70))
        self.assertTrue(p.narrow)
        self.assertIsNotNone(p.read, "в узком режиме область чтения обязана быть")

    def test_put_respects_right_edge(self):
        app = make_app(self.mod, 34, 60)
        app.put(1, 55, "очень длинный текст который не влезет")
        for y, x, text, _ in app.scr.drawn:
            self.assertLessEqual(x + len(text), 59, "строка вылезла за правый край")

    def test_put_writes_at_all_x_positions(self):
        """Регрессия: width вычитался вместе с x, и всё правее 22 было пусто."""
        app = make_app(self.mod, 34, 150)
        for x in (2, 25, 60, 100):
            app.scr.drawn = []
            app.put(3, x, "маркер")
            self.assertTrue(app.scr.drawn, "put() молча ничего не написал на x=%d" % x)

    def test_cyrillic_is_not_double_counted(self):
        app = make_app(self.mod)
        self.assertEqual(self.mod.visible_len("abc"), 3)
        self.assertEqual(self.mod.clip("Входящие", 20), "Входящие")
        self.assertLessEqual(len(self.mod.clip("длинный текст", 5)), 5)


class Help(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_tui()

    def test_help_opens_and_closes(self):
        app = make_app(self.mod)
        app.handle(ord("?"))
        self.assertEqual(app.screen, "help")
        app.handle(27)
        self.assertEqual(app.screen, "mail")

    def test_help_lists_commands_from_core(self):
        cmds = self.mod.cli_commands()
        names = [c for c, _ in cmds]
        self.assertIn("new", names)
        self.assertIn("wait", names)
        self.assertIn("tui", names, "команда tui есть в ядре и должна попадать в справку")
        # Справка берётся из докстринга ядра, поэтому строки-заголовки
        # вроде «mailtmp — временная почта…» командами быть не должны.
        self.assertNotIn("—", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)