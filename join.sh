#!/usr/bin/env bash
if `env | rg -q ASCIINEMA_REC`; then
  echo "asciinema already running." >&2
  exit 1
fi

dbus-send \
  --session \
  --dest=org.mindwm.client.manager \
  --type=method_call \
  /service \
  org.mindwm.client.manager.tmux_join \
  string:"$TMUX,$TMUX_PANE"
