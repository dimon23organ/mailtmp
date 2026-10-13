#!/usr/bin/env python3
"""Запускает mailtmp-tui на подставных данных, без сети.

Нужно, чтобы проверить интерфейс на непустом inbox: живой адрес пуст,
а панель чтения, список, поиск и звезды иначе не увидеть.

    python3 tests/fake_tui.py
    python3 tools/tui_probe.py tests/fake_tui.py

Сеть не трогается вообще: core.api подменяется заглушкой, которая
отдаёт заранее заданные ответы.
"""

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

# Грузим ядро так же, как это делает mailtmp-tui, и подменяем api.
loader = importlib.machinery.SourceFileLoader("mailtmp_core", str(HERE / "mailtmp"))
core_spec = importlib.util.spec_from_loader("mailtmp_core", loader)
core = importlib.util.module_from_spec(core_spec)
loader.exec_module(core)

MESSAGES = [
    {
        "id": "aaaaaaaa-1111-2222-3333-444444444444",
        "from": {"address": "noreply@github.com"},
        "subject": "Your GitHub verification code",
        "createdAt": "2026-10-13T09:14:00Z",
    },
    {
        "id": "bbbbbbbb-1111-2222-3333-444444444444",
        "from": {"address": "no-reply@yandex.ru"},
        "subject": "Код подтверждения: 482913",
        "createdAt": "2026-10-13T08:02:31Z",
    },
    {
        "id": "cccccccc-1111-2222-3333-444444444444",
        "from": {"address": "billing@steamcommunity.com"},
        "subject": "Order 99201 shipped",
        "createdAt": "2026-10-12T22:41:09Z",
    },
    {
        "id": "dddddddd-1111-2222-3333-444444444444",
        "from": {"address": "support@tg.org"},
        "subject": "Activate your account",
        "createdAt": "2026-10-12T19:20:55Z",
    },
    {
        "id": "eeeeeeee-1111-2222-3333-444444444444",
        "from": {"address": "hello@vk.com"},
        "subject": "Письмо без кода",
        "createdAt": "2026-10-11T11:03:00Z",
    },
]

FULL = {
    "id": "aaaaaaaa-1111-2222-3333-444444444444",
    "from": {"address": "noreply@github.com"},
    "subject": "Your GitHub verification code",
    "createdAt": "2026-10-13T09:14:00Z",
    "text": ["Hi there,\n\nYour verification code is 731294.\n\n"
             "It expires in 10 minutes. If you did not request it, ignore this.\n"],
    "html": ["<p>Your verification code is <b>731294</b>.</p>"],
}


def fake_api(method, path, body=None, token=None, timeout=30):
    if path == "/domains":
        return {"hydra:member": [{"domain": "maxxspace.com", "isActive": True},
                                 {"domain": "dead.example", "isActive": False}]}
    if path == "/messages":
        return {"hydra:member": MESSAGES}
    if path.startswith("/messages/"):
        return FULL
    return {}


def main():
    import os
    os.environ.setdefault("HOME", os.path.expanduser("~"))
    core.api = fake_api
    core.load_state = lambda: {"address": "demo7f3k9x@maxxspace.com",
                              "password": "x", "token": "t"}

    loader2 = importlib.machinery.SourceFileLoader("mailtmp_tui_fake", str(HERE / "mailtmp-tui"))
    spec = importlib.util.spec_from_loader("mailtmp_tui_fake", loader2)
    tui = importlib.util.module_from_spec(spec)
    loader2.exec_module(tui)
    # Клиент загружает свой экземпляр ядра — подменяем api и у него тоже.
    tui.core.api = fake_api
    tui.core.load_state = lambda: {"address": "demo7f3k9x@maxxspace.com",
                                   "password": "x", "token": "t"}
    tui.UI_STATE = Path(os.path.expanduser("~/.local/state/mailtmp-tui-fake.json"))
    tui.main()


if __name__ == "__main__":
    main()