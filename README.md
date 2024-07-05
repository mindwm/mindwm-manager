# Quick start


source environment and start mindwm-manager
```sh
direnv reload
set -a && source ./.env.sample && set +a
python ./src/mindwm/manager.py
```

Start new tmux session
```sh
tmux -Lmindwm new
```

Inside the tmux session send join command to the manager via DBus
```sh
dbus-send --session \
  --dest=org.mindwm.client.manager \
  --type=method_call \
  /service \
  org.mindwm.client.manager.tmux_join \
  string:"$TMUX,$TMUX_PANE"
```

You should see that the `asciinema` is recording on socket
```
asciinema: appending to asciicast at /tmp/mindwm-asciinema-f61eb911-c792-b130-e9ba-bde9196433b0.socket
asciinema: press <ctrl-d> or type "exit" when you're done
```
