import base64
import io
import json
import os
import random
import re

import requests


def tolog(txt):
    with open("aiclient_debug.log","a") as f:
        f.write(txt)


default_prompt = {
    "memory": "",
    "prompt": "",
    "stop_sequence": ["You:", "\nYou "], #+
    "use_story": False,  #?
    "use_memory": True,  #?
    "use_default_badwordsids": False,
    "use_authors_note": False,  #?
    "use_world_info": False,  #?
    "quiet": True,
    "max_context_length": 2048,
    "max_length": 10,
    "singleline": False,  #?
    "n": 1,
    "temperature": 0.7,
    "mirostat": 2,
    "mirostat_tau": 5.0,
    "mirostat_eta": 0.1,
    "rep_pen": 1.1,
    "rep_pen_range": 320,
    "rep_pen_slope": 0.7,
    "tfs": 1,
    "top_a": 0,
    "top_k": 100,
    "top_p": 0.92,
    "typical": 1,
    "min_p": 0,
    "genkey": "KCPP1912",
    "sampler_order": [6, 0, 1, 3, 4, 2, 5],
    #"sampler_seed": 69420,   #set the seed
    #"sampler_full_determinism": False,     #set it so the seed determines generation content
    "frmttriminc": False,  #?
    "frmtrmblln": False,  #?
}


def eval_template(template, context):
    return re.sub(r'\{\{(.*?)\}\}',
        lambda m: str( eval(m[1], context) ), template)


class Conversation:

    endpoint = "http://127.0.0.1:5001"

    def __init__(self, user, bot=None):
        self.user = user
        self.prompt_data = default_prompt
        self.stop_sequence = ["{{user}}:"]
#        self.stop_sequence = ["\n{{user}}:", "\n{{user}} ", "\n{{char}}"]
        if bot is not None:
            self.set_bot(bot)

    def set_bot(self, bot):
        self.botname = bot["name"]
        self.bot = bot
        memory = "\n".join((bot["persona"], bot["scenario"], bot["example"]))
        self.prompt_data["memory"] = self.parse_vars(memory)
        self.prompt_file = f"aiclient.log"
        self.log = f"aiclient_full.log"
        self.prompt = ""
        self.load_prompt()

    def parse_vars(self, text):
        context = dict(user=self.user, char=self.botname)
        return eval_template(text, context)

    def load_prompt(self):
        with open(self.prompt_file, 'a+') as file:
            file.seek(0)
            self.prompt = file.read()
        if self.prompt == "":
            self.to_prompt( self.parse_vars(self.bot["first_mes"]) )
        print(self.prompt,"\n", sep="")

    def to_history(self, text):
        if text != "":
            with open(self.log, "a") as f:
                f.write(text)

    def check_saved(self):
        with open(self.prompt_file, "r") as f:
            saved = f.read()
        if self.prompt != saved:
            tolog(f'save corruption:\nsaved=[{saved}]\norig=[{self.prompt}]\n')

    def load_history(self):
        with open(self.log) as f:
            text = f.read()
        self.cutoff = int(text[-8:])
        self.history = text[:-8]

    def save_message(self, msg):
        with open(self.log, "r+") as f:
            f.seek(-8, os.SEEK_END)
            f.write(msg)
            f.write(f"{self.cutoff:8}")

    def to_prompt(self, message):
        self.to_history(message)
        self.prompt += message
        now = len(self.prompt)
        max = (self.prompt_data['max_context_length']*3
            - len(self.prompt_data["memory"]))
        tolog(f'{now} < {max} = {self.prompt_data["max_context_length"]*28//10}-{len(self.prompt_data["memory"])}\n')
        if now > max:
            pos = now-max
            for end in ('\n\n', '.\n', '"\n', '\n'):
                pos2 = self.prompt.find(end, pos)
                if pos2 < 120 or end == '\n':
                    pos = pos2
                    break
            tolog(f'cut=[{self.prompt[:pos+len(end)]}]\nnew_start=[{self.prompt[pos+len(end):pos+200]}]\n')
            self.prompt = self.prompt[pos+len(end):]
            with open(self.prompt_file, "w") as f:
                f.write(self.prompt)
            self.check_saved()
        elif message != "":
            with open(self.prompt_file, "a") as f:
                f.write(message)
            self.check_saved()

    def get_json_prompt(self):
        context = dict(user=self.user, char=self.botname)
        stop = [eval_template(s, context) for s in self.stop_sequence]
        self.prompt_data["stop_sequence"] = stop
        self.prompt_data["prompt"] = self.prompt
        return self.prompt_data

    def send_to_ai(self):
        jprompt = self.get_json_prompt()
        response_data = requests.post(f"{self.endpoint}/api/v1/generate", json=jprompt)
        if response_data.status_code != 200:
            raise IOError  #!!!todo add text
        results = response_data.json()['results']
        response = results[0]['text']
        return response

    def collect_response(self, message):
        self.to_prompt(message)
        generated = 0
        done = False
        while True:
            response = self.send_to_ai()
            generated += len(response)
            for suffix in self.prompt_data['stop_sequence']:
                if response.endswith(suffix):
                    response = response.removesuffix(suffix).rstrip()
                    if response != "":
                        response += "\n"
                    done = True
            if not done:
                if ( len(response) < 1*self.prompt_data["max_length"] or
                        response.rstrip()[-2:] in ('."', '!"', '?"', ',"') ):
                    response = response.rstrip()+"\n"
                    done = True
                elif generated > 240:
                    pos = response.rfind("\n")
                    letter = response[pos-1:pos]
                    if pos >= 0 and letter in '.!?"':
                        response = response[:pos+1]
                        done = True
            self.to_prompt(response)
            print(response, end="", flush=True)
            if done:
                print()
                break

    def post(self, message):
        message = message.strip()
        if message[0:1] == '"':
            message = f"{self.user}: {message}"
        if len(message):
            message = f"\n{message}\n\n"
        try:
            self.collect_response(message)
        except IOError:
            print("Error: can not send message.")


def format_bot(bot):
    for k in bot:
        bot[k] = bot[k].strip()


def talk(bot):
    format_bot(bot)
    chat = Conversation("You", bot)
    while True:
        user_message = input(f"{chat.user}> ")
        print()
        chat.post(user_message)


assistant=dict(name="Assistant",
    persona="""Try to help.""",
    example="",
    scenario="",
    first_mes="How can I help?"
)


talk(assistant)
