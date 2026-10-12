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


class TestApiShapes(unittest.TestCase):
    """Реальный ответ mail.tm, а не предположение о нём.

    На живом письме выяснилось: `text` приходит СТРОКОЙ, а `html` —
    списком строк. Ранняя версия кода ждала список словарей с ключом
    'value' и падала с AttributeError. Формат неоднороден, поэтому
    покрыты все три варианта.
    """

    def test_text_as_plain_string(self):
        # Ровно то, что вернул api.mail.tm на живом письме:
        # subject="12312", text — строка, html — список строк.
        # Ответ 12312, а НЕ 312312312315: тема разбирается первой,
        # а 12 цифр подряд не подходят под \d{4,8} из-за границ слова.
        expect_code(self, {"subject": "12312", "text": "312312312315",
                           "html": ["<div dir=\"ltr\">312312312315</div>"]}, "12312")

    def test_long_digit_run_is_not_a_code(self):
        # 12 цифр подряд — это не код, ловить нечего.
        code, url = extract({"subject": "тест", "text": "312312312315"})
        self.assertIsNone(code)
        self.assertIsNone(url)

    def test_html_as_list_of_strings(self):
        expect_link(self, {"subject": "Go",
                           "html": ["<a href=\"https://ex.com/x\">go</a>"]},
                    "https://ex.com/x")

    def test_sections_as_list_of_dicts(self):
        # другой вариант того же ответа
        expect_code(self, {"subject": "", "text": [{"value": "код 4455"}]}, "4455")

    def test_mixed_shapes(self):
        expect_code(self, {"subject": "Code 7788",
                           "text": "ignored",
                           "html": [{"value": "<p>ignored</p>"}]}, "7788")

    def test_non_string_subject_ignored(self):
        code, url = extract({"subject": ["x"], "text": "abc"})
        self.assertIsNone(code)
        self.assertIsNone(url)


if __name__ == "__main__":
    unittest.main(verbosity=2)