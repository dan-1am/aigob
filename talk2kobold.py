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
    "max_length": 16,
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
    cutoff_digits = 8

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
        self.memory_tokens = self.count_tokens(memory)
        self.log = f"aiclient.log"
        self.load_history()

    def parse_vars(self, text):
        context = dict(user=self.user, char=self.botname)
        return eval_template(text, context)

    def load_history(self):
        with open(self.log, "a+") as file:
            file.seek(0)
            text = file.read()
            field = text[-self.cutoff_digits:]
            if field.isdecimal():
                self.cutoff = int(field)
                self.prompt = text[:-self.cutoff_digits-1]
            else:
                tolog("\n#### Warning: no cutoff in log! ####\n\n")
                self.cutoff = 0
                self.prompt = text
                file.write(f"\n{self.cutoff:0{self.cutoff_digits}}")
        self.to_prompt("")  # shift context, if log was extended manually
        print(self.prompt,"\n", sep="")

    def to_history(self, msg):
        with open(self.log, "r+") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            if end > self.cutoff_digits:
                f.seek(end-self.cutoff_digits-1)
            f.write(msg)
            f.write(f"\n{self.cutoff:0{self.cutoff_digits}}")

    # up to 300 tokens shifts were observed, we can assume no small limit there
    def shift_context(self, shift):
        pos = self.cutoff+shift*5+100
#        for end in ('\n\n', '.\n', '"\n', '\n', ' '):
#            pos2 = self.prompt.find(end, pos, pos+400)
#            if pos2 >= 0:
#                pos = pos2+len(end)
#                break
        tolog(f'{shift=} cutting={pos-self.cutoff}\n\ncut=[{self.prompt[self.cutoff:pos]}]\n\nnew_start=[{self.prompt[pos:pos+60]}]...\n')
        self.cutoff = pos

    """
    def to_prompt(self, message):
        self.prompt += message
        now = len(self.prompt) - self.cutoff
        #!!! if 30//10 will work, try 29//10. 30//10 with 4k context may overflow.
        max_context = self.prompt_data['max_context_length']
        max = (max_context-self.memory_tokens)*30//10
        add = self.count_tokens(self.prompt)
        # - len(self.prompt_data["memory"])
        tolog(f'{now} < {max} = {len(self.prompt_data["memory"])}\n')
        if now > max:
            tolog(f'message {len(message)}=[{message}]\n')
            self.shift_context(now-max)
        elif message == "":
            return
        self.to_history(message)
    """

    def to_prompt(self, message):
        self.prompt += message
        max = self.prompt_data['max_context_length'] - self.memory_tokens
        now = self.count_tokens(self.prompt[self.cutoff:])
        extra = now-max+10+self.prompt_data['max_length']
        tolog(f'tokens: {extra=}, {now} < {max}, memory={self.memory_tokens}\n')
        if extra > 0:
            tolog(f'message {len(message)}=[{message}]\n')
            self.shift_context(extra)
        elif message == "":
            return
        self.to_history(message)

    def get_json_prompt(self):
        context = dict(user=self.user, char=self.botname)
        stop = [eval_template(s, context) for s in self.stop_sequence]
        self.prompt_data["stop_sequence"] = stop
        self.prompt_data["prompt"] = self.prompt[self.cutoff:]
        return self.prompt_data

    def send_to_ai(self):
        jprompt = self.get_json_prompt()
        response_data = requests.post(f"{self.endpoint}/api/v1/generate", json=jprompt)
        if response_data.status_code != 200:
            raise IOError  #!!!todo add text
        results = response_data.json()['results']
        response = results[0]['text']
        status = self.status()
        return response, status['stop_reason']

    def collect_response(self, message):
        self.to_prompt(message)
        generated = 0
        done = False
        while True:
            response, stop_reason = self.send_to_ai()
            generated += len(response)
            for suffix in self.prompt_data['stop_sequence']:
                if response.endswith(suffix):
                    response = response.removesuffix(suffix).rstrip()
                    if response != "":
                        response += "\n"
                    done = True
            if not done:
                if stop_reason == 1:
                    response = response.rstrip()+"\n"
                    done = True
                elif ( len(response) < 1*self.prompt_data["max_length"] or
                        response.rstrip()[-2:] in ('."', '!"', '?"', ',"') ):
                    response = response.rstrip()+"\n"
                    done = True
                elif generated > 240:
                    pos = response.rfind(".")
                    if pos >= 0:
                        response = response[:pos+1]
                        done = True
                elif generated > 160:
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

    def abort(self):
        requests.post(f"{self.endpoint}/api/extra/abort")

    def status(self):
        """ Get status of KoboldCpp
        Result: last_process, last_eval, last_token_count, total_gens, queue, idle,
        stop_reason (INVALID=-1, OUT_OF_TOKENS=0, EOS_TOKEN=1, CUSTOM_STOPPER=2)
        """
        response = requests.get(f"{self.endpoint}/api/extra/perf")
        if response.status_code != 200:
            raise IOError  #!!!todo add text
        return response.json()

    def count_tokens(self, text):
        response = requests.post(f"{self.endpoint}/api/extra/tokencount",
            json={"prompt": text})
        if response.status_code != 200:
            tolog(f"count_tokens: err={response.status_code}\n")
            raise IOError  #!!!todo add text
        return response.json()['value']


def format_bot(bot):
    for k in bot:
        bot[k] = bot[k].strip()


def talk(bot):
    format_bot(bot)
    chat = Conversation("You", bot)
    chat.abort()
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
