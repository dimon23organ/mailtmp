#!/usr/bin/env python3
"""
Тесты логики извлечения кода и ссылки. Без сети, без API.
Запуск:  python3 tests/test_extract.py
"""

import os
import re
import sys
import unittest

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "mailtmp")
SRC = os.path.normpath(SRC)

# Вытаскиваем только функцию extract(), не выполняя блок __main__ и
# не делая сетевых запросов при импорте.
with open(SRC) as f:
    source = f.read()
source = source.replace('if __name__ == "__main__":', 'if False:')

ns = {}
exec(compile(source, "mailtmp", "exec"), ns)
extract = ns["extract"]


def text(*parts):
    return {"subject": "", "text": [{"value": p} for p in parts]}


def subject(sub, *parts):
    return {"subject": sub, "text": [{"value": p} for p in parts]}


def html(sub, *parts):
    return {"subject": sub, "html": [{"value": p} for p in parts]}


def expect_code(test, msg, want):
    """В письме должен найтись код, и НЕ должна находиться ссылка."""
    code, url = extract(msg)
    test.assertIsNone(url, "ссылка не ожидалась, но была найдена")
    test.assertEqual(code, want)


def expect_link(test, msg, want):
    """В письме должна найтись ссылка, и НЕ должен находиться код."""
    code, url = extract(msg)
    test.assertIsNone(code, "код не ожидался, но был найден")
    test.assertEqual(url, want)


class TestCodeExtraction(unittest.TestCase):
    def test_code_in_subject(self):
        expect_code(self, subject("Your verification code is: 482913", "ignore me"), "482913")

    def test_code_labelled_english(self):
        expect_code(self, subject("Sign in", "Your code is 7391."), "7391")

    def test_code_labelled_russian(self):
        expect_code(self, subject("Вход", "Ваш код: 7391. Не сообщайте его."), "7391")

    def test_code_otp(self):
        expect_code(self, subject("Sign in", "Your OTP is 552014"), "552014")

    def test_code_in_html_body(self):
        expect_code(self, html("Verify", "<p>Enter <b>118642</b> below</p>"), "118642")

    def test_any_digits_fallback(self):
        expect_code(self, text("Order 99201 shipped"), "99201")

    def test_no_code(self):
        code, url = extract(text("welcome aboard"))
        self.assertIsNone(code)
        self.assertIsNone(url)


class TestLinkExtraction(unittest.TestCase):
    def test_link_in_html_attribute(self):
        # Регрессия: тег <a href="..."> содержит URL в атрибуте,
        # и вырезание тегов регуляркой раньше его уничтожало.
        expect_link(
            self,
            html("Activate", '<a href="https://ex.com/v/abc?x=1">click</a>'),
            "https://ex.com/v/abc?x=1",
        )

    def test_link_in_plain_text(self):
        expect_link(self, text("Open https://ex.com/confirm?t=99 now"),
                    "https://ex.com/confirm?t=99")

    def test_code_wins_over_link(self):
        code, url = extract(
            {"subject": "Code 4471", "html": [{"value": '<a href="https://ex.com/a">x</a>'}]}
        )
        self.assertEqual(code, "4471")
        self.assertIsNone(url)


class TestRobustness(unittest.TestCase):
    def test_missing_sections(self):
        code, url = extract({})
        self.assertIsNone(code)
        self.assertIsNone(url)

    def test_none_sections(self):
        code, url = extract({"subject": None, "text": None, "html": None})
        self.assertIsNone(code)
        self.assertIsNone(url)

    def test_known_false_positive_documented(self):
        # Известное ограничение, зафиксировано в README:
        # посторонние числа в обычном письме считаются кодом.
        expect_code(self, text("Order 99201 shipped"), "99201")


if __name__ == "__main__":
    unittest.main(verbosity=2)