from libtmux import Server
from time import sleep

class Tmux_manager:
    envs = {}

    def __init__(self, config, socket_path=None, socket_name=None):
        def wrap(**kwargs):
            return Server(**{k:v for k,v in kwargs.items() if v is not None})
        self.config = config
        self.tmux = wrap(socket_path=socket_path, socket_name=socket_name)
        self.envs['services'] =  {
                "MINDWM_BACK_NATS_HOST": self.config['MINDWM_BACK_NATS_HOST'],
                "MINDWM_BACK_NATS_PORT": self.config['MINDWM_BACK_NATS_PORT'],
                "MINDWM_BACK_NATS_USER": self.config['MINDWM_BACK_NATS_USER'],
                "MINDWM_BACK_NATS_PASS": self.config['MINDWM_BACK_NATS_PASS'],
                "MINDWM_BACK_NATS_SUBJECT_WORDS_IN": self.config['MINDWM_BACK_NATS_SUBJECT_WORDS_IN']
         }
        self.envs['term'] = {
                "MINDWM_VECTOR_UDP_HOST": self.config['MINDWM_VECTOR_UDP_HOST'],
                "MINDWM_VECTOR_UDP_PORT": self.config['MINDWM_VECTOR_UDP_PORT'],
                }
        self.envs['feedback'] = {
                "MINDWM_NATS_URL": "nats://{user}:{password}@{host}:{port}".format(
                    host = self.config['MINDWM_NATS_HOST'],
                    port = self.config['MINDWM_NATS_PORT'],
                    user = self.config['MINDWM_NATS_USER'],
                    password = self.config['MINDWM_NATS_PASS']),
                "MINDWM_NATS_SUBJECT_FEEDBACK": self.config['MINDWM_NATS_SUBJECT_FEEDBACK'],
                }


    async def init(self):
        print(f"Tmux reset: {self.tmux}")
        self.session = self.tmux.sessions[0]
        self.session.rename_session("MindWM")
        await self.reset()
        await self.mk_layout()
        print(f"Tmux sessions: {self.tmux.sessions}")

        self.nats_pane.send_keys("operable-nats-client")
        self.vector_pane.send_keys("operable-vector-client")

        # FIXME: I have no ideas why this don't works. When the same command copy-pasted into the same
        # terminal then pipe-pane works as expected
        self.terminal_pane.send_keys(f"tmux pipe-pane -O 'nc -u {self.envs['term']['MINDWM_VECTOR_UDP_HOST']} {self.envs['term']['MINDWM_VECTOR_UDP_PORT']}'")

        self.feedback_pane.send_keys(f"nats -s {self.envs['feedback']['MINDWM_NATS_URL']} sub {self.envs['feedback']['MINDWM_NATS_SUBJECT_FEEDBACK']}")


    async def set_pane_title(self, pane, title):
        # FIXME: without switching the active window
        # keys will be sent into current pane instead of target pane
        # but this is true only when external variable used in string template
        # i.e. `pane.send_keys("echo hello")` works as expected
        old_window = self.session.active_window
        old_pane = old_window.active_pane
        pane.window.select()
        pane.select()
        pane.send_keys(r"printf '\033]2;%s\033\\' '" + title + "'")
        old_window.select()
        old_pane.select()


    async def mk_layout(self):
        self.ui_window = self.session.new_window(environment=self.envs['term'])
        self.ui_window.rename_window("Terminal")
        self.service_window = self.session.new_window(environment=self.envs['services'])
        self.service_window.rename_window("Service")

        self.terminal_pane = self.ui_window.panes[0]
        # FIXME: panes do not inherit window environment variables
        self.feedback_pane = self.terminal_pane.split_window(environment=self.envs['feedback'])
        await self.set_pane_title(self.terminal_pane, "Term")
        await self.set_pane_title(self.feedback_pane, "Feedback")

        self.vector_pane = self.service_window.panes[0]
        self.nats_pane = self.vector_pane.split_window()
        await self.set_pane_title(self.vector_pane, "Vector")
        await self.set_pane_title(self.nats_pane, "NATS")

        self.terminal_pane.clear()
        self.feedback_pane.clear()
        self.vector_pane.clear()
        self.nats_pane.clear()


    async def reset(self):
        windows = self.session.windows
        windows[0].rename_window("Manager")
        panes = windows[0].panes
        for p in panes[1:]:
            p.kill()

        for w in windows[1:]:
            w.kill()


    async def session_by_name(self, name):
        pass
