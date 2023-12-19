import base64
import io
import json
import os
from pathlib import Path
import random
import re
import readline

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
#    "max_context_length": 4096,
    "max_context_length": 2048,
    "max_length": 30,
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
        self.stop_sequence = ["{{user}}:", "\n{{user}} "]
#        self.stop_sequence = ["\n{{user}}:", "\n{{user}} ", "\n{{char}}"]
        if bot is not None:
            self.set_bot(bot)

    def set_bot(self, bot):
        self.botname = bot["name"]
        self.bot = bot
        memory = "\n".join((bot["description"], bot["scenario"], bot["example_dialogue"]))+"##"
        memory = self.parse_vars(memory)
        self.prompt_data["memory"] = memory
        self.memory_tokens = self.count_tokens(memory)
        self.log = f"log/aiclient_{self.botname}.log"
        print("\n\n", "#"*32, sep="")
        print(f"Started character: {self.botname}")
        self.load_history()

    def parse_vars(self, text):
        context = dict(user=self.user, char=self.botname)
        return eval_template(text, context)

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
            raise IOError  #!!!todo add text
        return response.json()['value']

    def find_token(self, text, pos):
        n = self.count_tokens(text[:pos])
        while n == self.count_tokens(text[:pos+1]):
            pos += 1
        return pos

    def store_cutoff(self, file):
        file.write(f"\n{self.cutoff:0{self.cutoff_digits}}")

    def load_history(self):
        with open(self.log, "a+") as file:
            file.seek(0)
            text = file.read()
            field = text[-self.cutoff_digits:]
            if field.isdecimal():
                self.cutoff = int(field)
                self.prompt = text[:-self.cutoff_digits-1]
            else:
                self.cutoff = 0
                self.prompt = text
                self.store_cutoff(file)
        if self.prompt == "":
            print("History is empty, starting new conversation.\n")
            # trying to avoid failed first context shift
            first = "\n"+self.parse_vars( self.bot['char_greeting'] )
            self.to_prompt(first)
        else:
            print(f"History loaded: {self.log}\n")
            self.to_prompt("")  # shift context, if log was extended manually
        print(self.prompt,"\n", sep="")

    def to_history(self, msg):
        with open(self.log, "r+") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            if end > self.cutoff_digits:
                f.seek(end-self.cutoff_digits-1)
            f.write(msg)
            self.store_cutoff(f)

    def truncate_history(self):
        with open(self.log, "r+") as f:
            pos = len(self.prompt)
            f.seek(pos)
            self.store_cutoff(f)
            f.truncate()

    def clear_bot(self):
        self.prompt = ""
        self.cutoff = 0
        self.truncate_history()
        self.set_bot(self.bot)

    # up to 300 tokens shifts were observed, we can assume no small limit there
    def shift_context(self, shift):
        pos = self.cutoff+shift*5+10
        for end in ('\n\n', '.\n', '"\n', '\n', ' '):
            pos2 = self.prompt.find(end, pos, pos+200)
            if pos2 >= 0:
                pos = pos2+len(end)-1
                break
        pos = self.find_token(self.prompt, pos)
#        tolog(f'{shift=} cutting={pos-self.cutoff}\n\ncut=[{self.prompt[self.cutoff:pos]}]\n\nnew_start=[{self.prompt[pos:pos+60]}]...\n')
        self.cutoff = pos

    def del_prompt_lines(self, count=1):
        pos = len(self.prompt)
        while count > 0:
            count -= 1
            pos = self.prompt.rfind("\n", 0, pos)
        self.prompt = self.prompt[:pos]
        self.truncate_history()

    def to_prompt(self, message):
        self.prompt += message
        max = self.prompt_data['max_context_length'] - self.memory_tokens
        now = self.count_tokens(self.prompt[self.cutoff:])
        extra = now-max+10+self.prompt_data['max_length']
#        tolog(f'tokens: {extra=}, {now} < {max}, memory={self.memory_tokens}\n')
        if extra > 0:
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

    def get_stream(self):
        jprompt = self.get_json_prompt()
        response = requests.post(f"{self.endpoint}/api/extra/generate/stream",
            json=jprompt, stream=True)
        if response.status_code != 200:
            raise IOError  #!!!todo add text
        if response.encoding is None:
            response.encoding = 'utf-8'
        return response.iter_lines(chunk_size=20, decode_unicode=True)

    def stream_response(self, message):
        self.to_prompt(message)
        response = ""
        mode = None
        for line in self.get_stream():
            if line:  #filter out keep-alive new lines
                if mode is None:
                    if line == "event: message":
                        mode = "message"
                elif mode == "message":
                    if line.startswith("data:"):
                        jresponse = json.loads(line.removeprefix("data: "))
                        token = jresponse['token']
                        response += token
                        print(token, end="", flush=True)
                        mode = None
        done = False
        stop_reason = self.status()['stop_reason']
        if stop_reason == 2:  # custom stopper
            for suffix in self.prompt_data['stop_sequence']:
                if response.endswith(suffix):
                    response = response.removesuffix(suffix).rstrip()
                    if response != "":
                        response += "\n"
                    print("\r", " "*20, "\r", sep="")
                    done = True
                    break
        elif stop_reason == 0:  # out of tokens
            response = response.rstrip()
            if len(response) > 2 and response[:-2] in ('."', '!"', '?"'):
                response += "\n"
        else:  # eos token/invalid
            response = response.rstrip()+"\n"
        print("\n")
        self.to_prompt(response)

    def post(self, message):
        message = message.strip()
        if len(message):
            message = f"\n{message}\n\n"
        try:
#            if not self.status()['idle']:
#                self.abort()
            self.stream_response(message)
        except IOError:
            print("Error: can not send message.")
        except KeyboardInterrupt:
            print()

    def help(self):
        print("""Help:
/ls        - list all chars
/load char - load new char
/clear     - clear history
"=" - add new line
/h /help   - this help message
/d [n] /del [n] - delete n lines / last line
/r         - refresh screen
/stop      - stop answering llm engine
Ctrl+c     - while receiving llm answer: cancel
Ctrl-z     - exit
/set var value - set engine variable
/set       - list engine variables
"""     )

    def refresh_screen(self, chars=2000):
        print("\n"*3, self.prompt[-chars:], "\n", sep="")

    def add_message(self, message):
        if message == "/stop":
            self.abort()
        elif message.startswith( ("/h", "/help") ):
            self.help()
        elif message == "/ls":
            pass  #!!! todo
        elif message.startswith("/load"):
            name = message.partition(" ")[2].strip()
            char = load_char(name)
            self.set_bot(char)
        elif message.startswith("/clear"):
            self.clear_bot()
        elif message.startswith( ("/d", "/del") ):
            count = message.partition(" ")[2].strip()
            count = int(count) if count.isdigit() else 1
            self.del_prompt_lines(count)
            self.refresh_screen()
        elif message.startswith("/r"):
            self.refresh_screen(4000)
        elif message.startswith("/set"):
            args = message.split()
            if len(args) == 1:
                for k,v in self.prompt_data.items():
                    print(f"{k}={v}\n")
            else:
                if len(args) != 3:
                    print("Error: set need 2 parameters.")
                else:
                    _,var,value = args
                    if value.isdigit():
                        value = int(value)
                    if self.prompt_data.get(var, None) is not None:
                        self.prompt_data[var] = value
                    else:
                        print("Var not exists.")
        else:
            if message == "":
                self.refresh_screen()
                self.post("")
            elif message == "=":
                self.to_prompt("\n")
                self.refresh_screen()
            else:
                if message[0:1] == '"':
                    message = f"{self.user}: {message}"
                self.to_prompt(message+"\n")


def format_bot(bot):
    for k in bot:
        bot[k] = bot[k].strip()


def talk(bot):
    format_bot(bot)
    chat = Conversation("You", bot)
    while True:
        try:
            if chat.prompt == "" or chat.prompt.endswith("\n"):
                mode = "="
            else:
                mode = "+"
            message = input(f"{chat.user} {mode}> ")
            chat.add_message(message)
        except KeyboardInterrupt:
            input("\nEnter to continue, Ctrl+C second time to exit.")
        except EOFError:
            print("End of input, exiting...")
            break


def strip_char(char):
    dupkeys = (
        ("name", "char_name"),
        ("description", "char_persona"),
        ("scenario", "world_scenario"),
        ("example_dialogue", "mes_example"),
        ("char_greeting", "first_mes"),
    )
    for key1,key2 in dupkeys:
        if char.get(key1, None) is None:
            char[key1] = char[key2]
        char.pop(key2, None)
        char[key1] = char[key1].strip()


def load_char(name, dir="chars"):
    names = (name, name+".pch", name+".json")
    for testname in names:
        path = Path(dir, testname)
        if path.is_file():
            with path.open() as f:
                if testname.endswith(".pch"):
                    char = eval(f.read(), {"__builtins__": {"dict": dict}})
                else:
                    char = json.load(f)
                strip_char(char)
                return char


#!!! todo: fill alternative tags from pair
def save_char(char, file, dir="chars"):
    if not file.endswith(".json"):
        file += ".json"
    with open(f"{dir}/{file}", "w") as f:
        json.dump(char, f, indent=3)


def char_to_py(char, file, dir="chars"):
    longkeys = (
        "description", "char_persona",
        "scenario", "world_scenario",
        "example_dialogue", "mes_example",
        "char_greeting", "first_mes",
    )
    parts = ["dict(\n"]
    for k,v in char.items():
        if isinstance(v, str):
            if v == "" or k not in longkeys:
                parts.append(f'{k} = """{v}""",\n')
            else:
                parts.append(f'{k} = """\n\n{v}\n\n""",\n')
        else:
            parts.append(f'{k} = {v},\n')
    parts.append(")\n")
    text = "\n".join(parts)
    if not file.endswith(".pch"):
        file += ".pch"
    with open(f"{dir}/{file}", "w") as f:
        f.write(text)


assistant=dict(
    name="Assistant",
    description="",
    example_dialogue="",
    scenario="",
    char_greeting="How can I help?",
)


char = assistant

args = sys.argv[1:]
while args:
    arg = args.pop(0)
    if arg in ("-c", "--char"):
        char = load_char(args.pop(0))
    elif arg in ("-j", "--json"):
        save_char(char, args.pop(0))
        sys.exit()
    elif arg in ("-p", "--py"):
        char_to_py(char, args.pop(0))
        sys.exit()
    else:
        raise NameError(f"Error: unknown option {arg}")

talk(char)
