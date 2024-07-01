#!/usr/bin/env python3
import asyncio
from functools import partial
import json
import nats
from uuid import uuid4
from pprint import pprint
from decouple import config

from modules.nats_listener import NatsListener
from modules.tmux_manager import Tmux_manager
from modules.pipe_listener import PipeListener
from modules.text_processor import TextProcessor
from modules.dbus_interface import DbusInterface


async def main():
    env = {
            "MINDWM_BACK_NATS_HOST": config("MINDWM_BACK_NATS_HOST", default="127.0.0.1"),
            "MINDWM_BACK_NATS_PORT": config("MINDWM_BACK_NATS_PORT", default=4222, cast=int),
            "MINDWM_BACK_NATS_USER": config("MINDWM_BACK_NATS_USER", default="root"),
            "MINDWM_BACK_NATS_PASS": config("MINDWM_BACK_NATS_PASS", default="r00tpass"),
            "MINDWM_BACK_NATS_SUBJECT_PREFIX": config("MINDWM_BACK_NATS_SUBJECT_PREFIX"),

            "MINDWM_ASCIINEMA_REC_PIPE": config("MINDWM_ASCIINEMA_REC_PIPE"),
            }
#
#    # TODO: need to validate MINDWM_TMUX value and describe what's wrong
#    tmux_socket = env['MINDWM_TMUX'].split(',')[0]
    nats_url = f"nats://{env['MINDWM_BACK_NATS_USER']}:{env['MINDWM_BACK_NATS_PASS']}@{env['MINDWM_BACK_NATS_HOST']}:{env['MINDWM_BACK_NATS_PORT']}"
    nc = await nats.connect(nats_url)

    loop = asyncio.get_event_loop()

    text_processor = TextProcessor()
    #ai_processor = AiProcessor(env)
    await text_processor.init()
    #await ai_processor.init()

    dbus_interface = DbusInterface()
    loop.create_task(dbus_interface.init())

    async def nats_message_callback(msg):
        print(f"Nats feedback received: {msg}")
        await dbus_interface.feedback_message(json.dumps(msg))

    nats_feedback_topic = "{}.feedback".format(env['MINDWM_BACK_NATS_SUBJECT_PREFIX'])
    nats_listener = NatsListener(nats_url, nats_feedback_topic, message_callback=nats_message_callback)
    loop.create_task(nats_listener.init())


    async def nats_pub(topic, t, msg):
        subject = f"{env['MINDWM_BACK_NATS_SUBJECT_PREFIX']}.{topic}"
        payload = {
            "knativebrokerttl": "255",
            "specversion": "1.0",
            "type": t,
            "source": f"{subject}",
            "subject": f"{subject}",
            "datacontenttype": "application/json",
            "data": {
                t: msg,
            },
            "id": str(uuid4()),
        }
        await nc.publish(subject, bytes(json.dumps(payload), encoding='utf-8'))

    nats_pub_word = partial(nats_pub, "words", "word")
    nats_pub_line = partial(nats_pub, "lines", "line")
    nats_pub_summary = partial(nats_pub, "summary", "summary")
    nats_pub_iodoc = partial(nats_pub, "iodocument", "iodocument")
    nats_pub_ai_answer = partial(nats_pub, "ai_answer", "ai_answer")

    async def cb_print(payload):
        data = json.loads(payload)
        inp = data['input']
        full_cmd = inp
        #summary = None

        if len(inp) > 3 and not inp.startswith('#'):
            # try to expand short commands to it full form
            # TODO: disabled temporary
            full_cmd = inp #await ai_processor.cmd_short_to_full(data['input'].strip())

        # send message to ai
        if inp.startswith('#mw'):
            answer = await ai_processor.query(data['input'][3:])
            print(f"answer: {answer}")
            await nats_pub_ai_answer(answer)

        result = json.loads(payload)
        try:
            res_ = await text_processor.parse(cmd=full_cmd, output=data['output'])
            result['textfsm'] = json.loads(res_)
        except NotImplementedError:
            pass

        result['full_cmd'] = full_cmd
        #result['summary'] = summary
        #pprint(res, width=200)
        #print(f"full_cmd: {full_cmd}")
        #print(f"type: {type(res)}")
        await nats_pub_iodoc(result)
        print(f"result: {result}")

    print(f"pipe_path: {env['MINDWM_ASCIINEMA_REC_PIPE']}")
    #pipe_listener = PipeListener(env['MINDWM_ASCIINEMA_REC_PIPE'], cb=cb_print, cb_word=nats_pub_word, cb_line=nats_pub_line)
    pipe_listener = PipeListener(env['MINDWM_ASCIINEMA_REC_PIPE'], cb=cb_print, cb_line=nats_pub_line)

    await pipe_listener.init()
    await pipe_listener.loop()

    while True:
        print("tick")
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
