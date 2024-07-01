#!/usr/bin/env python3
import aiofiles
import asyncio
from decouple import config
import os
import requests
import sys
import json

class AiProcessor:
    prompts = {
        "cmd_short_to_full": "data/prompts/cmd_short_to_full",
        "summarize_output": "data/prompts/summarize_output",
        "query": "./prompts/query",
    }
    def __init__(self, config):
        self.openai_api_key = config["OPENAI_API_KEY"]
        self.openai_api_base = config["OPENAI_API_BASE"]
        self.path = os.path.dirname(sys.modules[self.__class__.__module__].__file__)

    async def init(self):
        pass

    async def load_template(self, name):
        prompt_path = self.path + '/' + self.prompts[name]
        async with aiofiles.open(prompt_path, mode='rt') as f:
            prompt_ = await f.read()

        return prompt_

    async def cmd_short_to_full(self, cmd):
        prompt_ = await self.load_template('cmd_short_to_full')
        prompt = prompt_.replace("%%USER%%", cmd)
        #print(f"prompt: {prompt}")
        answer = await self.ask_ai(prompt)
        return answer

    async def summarize(self, cmd, output):
        prompt_ = await self.load_template('summarize_output')
        prompt = prompt_.replace("%%INPUT%%", cmd).replace("%%OUTPUT%%", output)
        print(f"prompt: {prompt}")
        answer = await self.ask_ai(prompt)
        return answer

    async def query(self, query):
        prompt_ = await self.load_template('query')
        prompt = prompt_.replace("%%QUERY%%", query)
        print(f"prompt: {prompt}")
        answer = await self.ask_ai(prompt)
        return answer

    async def ask_ai(self, prompt):
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.openai_api_key}"}
    
        kobold_data = {
            "n": 1,
            "max_context_length": 1600,
            "max_length": 512,
            "rep_pen": 1.1,
            "temperature": 0.4,
            "top_p": 0.92,
            "top_k": 100,
            "top_a": 0,
            "typical": 1,
            "tfs": 1,
            "rep_pen_range": 320,
            "rep_pen_slope": 0.7,
            "sampler_order": [6, 0, 1, 3, 4, 2, 5],
            "memory": "",
#            "genkey": "KCPP9898",
            "min_p": 0,
            "dynatemp_range": 0,
            "dynatemp_exponent": 1,
            "smoothing_factor": 0,
            "presence_penalty": 0,
            "logit_bias": {},
            "prompt": prompt,
            "quiet": False,
            "stop_sequence": ["### Instruction:", "### Response:"],
            "use_default_badwordsids": False
        }
        data = {
            "model": "chatgpt-3.5-turbo",
            "prompt": prompt,
            "temperature": 0.5,
            "max_tokens": 512,
            "top_p": 1.0,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0
        }
    
        #response = requests.post(f"{self.openai_api_base}/completions", json=data, headers=headers)
        #response = requests.post(f"{self.openai_api_base}/generate", json=json.dumps(kobold_data), headers=headers)
        response = requests.post(f"{self.openai_api_base}/generate", json=kobold_data, headers=headers)
    
        #print(f"rest: {response.json()}\n\n\n")
        #return response.json()["choices"][0]["text"].strip()
        return response.json()["results"][0]["text"].strip()

#
# Example usage:
async def main(cmd):
    env = {
        "OPENAI_API_KEY": config("OPENAI_API_KEY"),
        "OPENAI_API_BASE": config("OPENAI_API_BASE")
    }
    ai = AiProcessor(config=env)
    await ai.init()
    response = await ai.cmd_short_to_full(cmd)
    print(response)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <input short command>")
        exit(1)

    cmd = ' '.join(sys.argv[1:])
    asyncio.run(main(cmd))
