#!/usr/bin/env bash
dbus-send \
  --session \
  --dest=org.mindwm.client.manager \
  --type=method_call \
  /service \
  org.mindwm.client.manager.tmux_join \
  string:"$TMUX,$TMUX_PANE"
