from __future__ import annotations

import json

import urwid
from mindwm.model.objects import ShowMessage


def exit_on_q(key: str) -> None:
    if key in {"q", "Q"}:
        raise urwid.ExitMainLoop()


def show_message(title: str, msg: str):
    txt = urwid.Text(f"{title}:\n\n{msg}\n\nPress Q to exit.")
    fill = urwid.ScrollBar(urwid.Scrollable(urwid.Filler(txt, "top")))
    #fill = urwid.ScrollBar(txt)
    #loop = urwid.MainLoop(fill, unhandled_input=exit_on_q, handle_mouse=True, screen=urwid.display.curses.Screen())
    #loop = urwid.MainLoop(fill, unhandled_input=exit_on_q, handle_mouse=True, screen=urwid.display.raw.Screen())
    loop = urwid.MainLoop(fill,
                          unhandled_input=exit_on_q,
                          handle_mouse=False,
                          screen=urwid.display.raw.Screen())
    loop.run()


if __name__ == "__main__":
    with open('/home/pion/work/dev/mindwm/mindwm-manager/.state/message.json',
              'r') as f:
        j = dict(json.load(f))
        msg = ShowMessage.model_validate(j)
        show_message(msg.title, msg.message)
