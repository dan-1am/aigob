import base64
import io
import json
import os
from pathlib import Path
import random
import re
import readline
import sys
import time

import requests


engine_settings = {
#    "stop_sequence": ["You:", "\nYou ", "\n\n"],
    "use_story": False,
    "use_memory": True,
    "use_default_badwordsids": False,
    "use_authors_note": False,
    "use_world_info": False,
    "quiet": True,
    "singleline": False,

    "genkey": "KCPP1912",
    "max_context_length": 4096,
    "max_length": 16,
    "n": 1,
    #"sampler_seed": 69420,   #set the seed
    #"sampler_full_determinism": False,     #set it so the seed determines generation content

#    "temperature": 0.7,
    "temperature": 0.8,
    "mirostat": 2,
    "mirostat_tau": 5.0,
    "mirostat_eta": 0.1,

    "sampler_order": [6, 0, 1, 3, 4, 2, 5],
    "rep_pen": 1.1,
    "rep_pen_range": 320,
    "rep_pen_slope": 0.7,
    "tfs": 1,
    "top_a": 0,
    "top_k": 100,
    "top_p": 0.92,
    "typical": 1,
    "min_p": 0,
    "frmttriminc": False,
    "frmtrmblln": False,
}


class Settings:
    _conffile = "talk2kobold.conf"
    chardir = "chars"
    logdir = "log"
    endpoint = "http://127.0.0.1:5001"
    lastchar = ""
    stop_sequence = ["{{user}}:", "\n{{user}} ", "<START>"]
#    stop_sequence = ["\n{{user}}:", "\n{{user}} ", "\n{{char}}"]
    engine = engine_settings

    def set(self, var, value):
        setattr(self, var, value)
#        self.save()

    def save(self):
        opts = {name: value
            for name in dir(self)
            if not name.startswith("_")
            if not callable(value := getattr(self, name))
        }
        opts['engine'] = self.engine.copy()
        for name in ("history", "prompt", "stop_sequence"):
            opts['engine'].pop(name, None)
        with open(self._conffile, "w") as f:
            json.dump(opts, f, indent=4)

    def load(self):
        if Path(self._conffile).is_file():
            with open(self._conffile, "r") as f:
                self.__dict__ = json.load(f)
        else:
            self.save()


conf = Settings()


def tolog(txt):
    with open("aiclient_debug.log","a") as f:
        f.write(txt)


def eval_template(template, context):
    return re.sub(r'\{\{(.*?)\}\}',
        lambda m: str( eval(m[1], context) ), template)


def count_newlines(text):
    i = len(text)
    while text[i-1] == "\n":
        i -= 1
    return len(text)-i


def wrap_text(txt, width=72):
    txt = txt.replace("\n", " ")
    txt = re.sub("\s{2,}", " ", txt)
    result = []
    while len(txt):
        pos = width
        if len(txt) <= pos:
            result.append(txt.rstrip())
            break
        pos2 = txt.rfind(" ", 0, pos+1)
        if pos2 >= 0:
            pos = pos2+1
        result.append(txt[:pos].rstrip())
        txt = txt[pos:]
    return "\n".join(result)


assistant=dict(
    name="Assistant",
    description="",
    example_dialogue="",
    scenario="",
    char_greeting="How can I help?",
)


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


def load_char(name, dir=None):
    if dir == None:
        dir = conf.chardir
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
def char_to_json(char, file, dir=None):
    if dir == None:
        dir = conf.chardir
    if not file.endswith(".json"):
        file += ".json"
    with open(f"{dir}/{file}", "w") as f:
        json.dump(char, f, indent=3)


def char_to_pch(char, file, dir=None):
    if dir == None:
        dir = conf.chardir
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


class Conversation:

    cutoff_digits = 8

    def __init__(self, user, bot=""):
        self.user = user
        self.prompt_data = conf.engine
        self.set_bot(bot)

    def set_bot(self, bot=""):
        if bot == "":
            bot = assistant
        self.botname = bot["name"]
        self.bot = bot
        memory = "\n".join((bot["description"], bot["scenario"], bot["example_dialogue"])) + "\n" #!!!
        memory = self.parse_vars(memory)
        self.prompt_data["memory"] = memory
        self.memory_tokens = self.count_tokens(memory)
        self.log = f"{conf.logdir}/aiclient_{self.botname}.log"
        print("\n\n", "#"*32, sep="")
        print(f"Started character: {self.botname}")
        self.load_history()

    def parse_vars(self, text):
        context = dict(user=self.user, char=self.botname)
        return eval_template(text, context)

    def abort(self):
        requests.post(f"{conf.endpoint}/api/extra/abort")

    def status(self):
        """ Get status of KoboldCpp
        Result: last_process, last_eval, last_token_count, total_gens, queue, idle,
        stop_reason (INVALID=-1, OUT_OF_TOKENS=0, EOS_TOKEN=1, CUSTOM_STOPPER=2)
        """
        response = requests.get(f"{conf.endpoint}/api/extra/perf")
        if response.status_code != 200:
            raise IOError("Can not get status from engine")
        return response.json()

    def count_tokens(self, text):
        response = requests.post(f"{conf.endpoint}/api/extra/tokencount",
            json={"prompt": text})
        if response.status_code != 200:
            raise IOError("Can not get get token count from engine")
        return response.json()['value']

    def find_token(self, text, pos):
        if pos == 0:
            n = 0
        else:
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
            # "\n" for avoid failing first context shift:
            first = "\n"+self.parse_vars( self.bot['char_greeting'] )+"\n\n"
            self.to_prompt(first)
        else:
            print(f"History loaded: {self.log}\n")
            self.to_prompt("")  # shift context, if log was extended manually
        print(self.prompt, sep="", end="", flush=True)

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
                pos = pos2+len(end)-1  #!!!
                break
        else:
            pos = pos + self.find_token(self.prompt[pos:], 0)
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
        max_ctx = self.prompt_data['max_context_length'] - self.memory_tokens
        now = self.count_tokens(self.prompt[self.cutoff:])
        extra = now-(max_ctx-10-self.prompt_data['max_length'])
#        tolog(f'tokens: {extra=}, {now} < {max_ctx}, memory={self.memory_tokens}\n')
        if extra > 0:
            self.shift_context(max(extra, len(message)//5+1)) #!!! testing max()
        elif message == "":
            return
        self.to_history(message)

    def get_json_prompt(self):
        context = dict(user=self.user, char=self.botname)
        stop = [eval_template(s, context) for s in conf.stop_sequence]
        self.prompt_data["stop_sequence"] = stop
        self.prompt_data["prompt"] = self.prompt[self.cutoff:]
        return self.prompt_data

    def get_stream(self):
        jprompt = self.get_json_prompt()
        response = requests.post(f"{conf.endpoint}/api/extra/generate/stream",
            json=jprompt, stream=True)
        if response.status_code != 200:
            raise IOError("Can not get response stream from engine")
        if response.encoding is None:
            response.encoding = 'utf-8'
        return response.iter_lines(chunk_size=20, decode_unicode=True)

    def read_stream(self):
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
        stop_reason = self.status()['stop_reason']
        return response, stop_reason

    def to_readline(self, response):
        if len(self.prompt) and self.prompt[-1] != "\n":
            pos = self.prompt.rfind("\n")  # -1 is ok
            text = self.prompt[pos+1:] + response
        else:
            text = response
        for line in text.splitlines():
            if line != "":
                readline.add_history(line)
        readline.add_history(text.replace("\n", " "))

    def stream_response(self, message):
        self.to_prompt(message)
        response, stop_reason = self.read_stream()
        if stop_reason == 2:  # custom stopper == stop word?
            for suffix in self.prompt_data['stop_sequence']:
                if response.endswith(suffix):
                    response = response.removesuffix(suffix)
                    if suffix.startswith("\n") or suffix.endswith("\n"):
                        response += "\n"
                    break
        #else:  # 0=out of tokens, 1=eos token, -1=invalid
#        response = response.rstrip()+"\n"
        self.to_readline(response)
        self.to_prompt(response)

    def post(self, message):
        try:
#            if not self.status()['idle']:
#                self.abort()
            self.stream_response(message)
        except IOError:
            print("Error: can not send message.")
        except KeyboardInterrupt:
            print()

    def refresh_screen(self, end="", chars=2000):
        print("\n"*3, self.prompt[-chars:], end, sep="", end="")

    def help(self):
        print("""Help:
/saveconf  - save configuration
/ls        - list all chars
/load char - load new char
/clear     - clear history
"=" - add new line
/h /help   - this help message
/del [n] /d [n]  - delete n lines / last line
/r         - refresh screen
/stop      - stop answering llm engine
Ctrl+c     - while receiving llm answer: cancel
Ctrl-z     - exit
/set var value - set engine variable
/set       - list engine variables
"""     )

    def command_message(self, message):
        if message == "/stop":
            self.abort()
        elif message.startswith( ("/h", "/help") ):
            self.help()
        elif message == "/test":
            mem = self.prompt_data["memory"]
            prompt = self.prompt[self.cutoff:]
            memtm = self.count_tokens(mem[:-1])
            memt0 = self.count_tokens(mem)
#            memt1 = self.count_tokens(mem+prompt[:1])
            memt1 = self.count_tokens(mem+"\n")
            memt2 = self.count_tokens(mem+"\n\n")
            memt3 = self.count_tokens(mem+"\n\n\n")
            print(f"tokens: {memtm=} {memt0=} {memt1=} {memt2=} {memt3=}")
        elif message == "/saveconf":
            conf.save()
        elif message == "/ls":
            for f in Path(conf.chardir).iterdir():
                if f.suffix in (".json", ".pch"):
                    print(f.name)
        elif message.startswith("/load"):
            name = message.partition(" ")[2].strip()
            conf.set("lastchar", name)
            char = load_char(name)
            self.set_bot(char)
        elif message.startswith("/clear"):
            self.clear_bot()
        elif message.startswith( ("/del", "/d") ):
            count = message.partition(" ")[2].strip()
            count = int(count) if count.isdigit() else 1
            self.del_prompt_lines(count)
            self.refresh_screen()
        elif message.startswith("/r"):
            self.refresh_screen(chars=4000)
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
            print("Unknown command.")

    def add_message(self, message):
#        unfinished = len(self.prompt) and self.prompt[-1:] != "\n"
        if message.startswith("/"):
            self.command_message(message)
        elif message == "":
            self.refresh_screen(end="")
            self.post("")
        elif message == "=":
            self.to_prompt("\n")
            self.refresh_screen()
        elif message == "-":
            self.del_prompt_lines()
            self.refresh_screen()
        elif message[0] == "+":
            parts = message[1:].split("\\n")
            message = "\n".join(wrap_text(t) for t in parts)
            self.to_prompt(message)
            self.refresh_screen()
        else:
            newlines = count_newlines(self.prompt)
            prefix = ""
            if newlines > 2:
                self.prompt = self.prompt[:2-newlines]
                # need optimization: extra file write
                self.truncate_history()
            elif newlines < 2:
                prefix = "\n"*(2-newlines)
# test if User:/Char: tags mess llm logic
#            if message.startswith('"'):
#                message = f"{self.user}: {message}"
            message = prefix + wrap_text(message)
            if message.endswith("+"):
                message = message[:-1]
            else:
                message = f"{message}\n\n"
            self.refresh_screen(end="")
            print(message, end="", flush=True)
            self.post(message)


def talk(bot):
    chat = Conversation("You", bot)
    while True:
        if chat.prompt == "" or chat.prompt.endswith("\n"):
            mode = ""
            print("\r", " "*20, "\r", sep="", end="")
        else:
            mode = "+"
            print()
        try:
            start = time.time()
            while True:
                message = input(f"{chat.user} {mode}> ")
                if time.time()-start > 0.5:
                    break
            chat.add_message(message)
        except KeyboardInterrupt:
            input("\nEnter to continue, Ctrl+C second time to exit.")
        except EOFError:
            print("End of input, exiting...")
            break


conf.load()
char = conf.lastchar
if char != "":
    char = load_char(char)

args = sys.argv[1:]
while args:
    arg = args.pop(0)
    if arg in ("-c", "--char"):
        conf.set("lastchar", args.pop(0))
        char = load_char(conf.lastchar)
    elif arg in ("-j", "--json"):
        char_to_json(char, args.pop(0))
        sys.exit()
    elif arg in ("-p", "--py"):
        char_to_pch(char, args.pop(0))
        sys.exit()
    else:
        raise NameError(f"Error: unknown option {arg}")

talk(char)

#conf.save()
