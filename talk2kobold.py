import base64
import io
import json
import os
from pathlib import Path
import string
import random
import re
import readline
import sys
import time

import requests



################ Misc

def tolog(txt):
    with open("aiclient_debug.log","a") as f:
        f.write(txt)


def random_string(length, charset=None):
    if charset == None:
        charset = string.ascii_uppercase+string.digits
    return "".join(random.choices(charset, k=length))


def print_nested(store):
    if hasattr(store, "items"):
        for k,v in store.items():
            print(f"{k}={v}")
    else:
        empty = True
        for name in dir(store):
            if ( not name.startswith("_")
                    and not callable(value := getattr(store, name)) ):
                empty = False
                print(f"{name}={value}")
        if empty:
            print(store)


def get_nested(store, name):
    """For name=name1.name2... get store.name1[name2]..."""
    start,_,end = name.partition(".")
    old = getattr(store, start, None)
    if old is None:
        # try store[start]
        if hasattr(store, "__getitem__"):
            old = store.get(start, None)
            if old is None:
                print("Var not exists.")
            elif end == "":
                return old
            else:
                return get_nested(old, end)
        else:
            print("Var not exists.")
    # store.start
    elif end == "":
        return old
    else:
        return get_nested(old, end)


def set_nested(store, name, value):
    """For name=name1.name2... set store.name1[name2]... to value."""
    start,_,end = name.partition(".")
    old = getattr(store, start, None)
    if old is None:
        # try store[start]
        if hasattr(store, "__getitem__"):
            old = store.get(start, None)
            if old is None:
                print("Var not exists.")
            elif end == "":
                store[start] = value
            else:
                set_nested(old, end, value)
        else:
            print("Var not exists.")
    # store.start
    elif end == "":
        setattr(store, start, value)
    else:
        set_nested(old, end, value)


def eval_template(template, context):
    return re.sub(r'\{\{(.*?)\}\}',
        lambda m: str( eval(m[1], context) ), template)


def count_newlines(text):
    i = len(text)
    while text[i-1] == "\n":
        i -= 1
    return len(text)-i


def split_to_paragraphs(text):
    """Generator, split text maintaining its length."""
    while True:
        pos = text.find("\n\n")
        if pos < 0:
            yield text
            break
        cr_pos = pos+2
        while text[cr_pos:cr_pos+1] == "\n":
            cr_pos += 1
        extra = cr_pos-pos-2
        yield text[:pos]+" "*extra
        text = text[cr_pos:]


def wrap_text(text, width=None):
    """Wrap text to lines not exceeding width. Keep text length."""
    if width is None:
        width = conf.wrap_at
    text = text.replace("\n", " ")
#    text = re.sub("\s{2,}", " ", text)
    result = []
    while True:
        if len(text) <= width:
            result.append(text)
            break
        pos = width+1
        pos2 = text.rfind(" ", 0, pos)
        if pos2 < 0:
            pos2 = text.find(" ", pos)
            if pos2 < 0:
                result.append(text)
                break
        pos = pos2
        result.append(text[:pos])
        text = text[pos+1:]
    return "\n".join(result)


def reformat(text, width=None, keep_nl=True):
    parts = split_to_paragraphs(text)
    newtext = "\n\n".join(wrap_text(para, width) for para in parts)
    # needed for \n before input() and for del_line
    # ugly, to be reworked:
    if keep_nl and text.endswith("\n") and not newtext.endswith("\n"):
        newtext = newtext[:-1] + "\n"
    return newtext

################



################ Settings

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


def deep_update(storage, data):
    for name,value in data.items():
        old = storage.get(name, None)
        if old is None:
            raise KeyError(f"Wrong key {name} = {value} in options.")
        if getattr(old, "keys", None):
            deep_update(old, value)
        else:
            storage[name] = value


class Settings:
    _conffile = "talk2kobold.conf"
    save_on_exit = True
    chardir = "chars"
    logdir = "log"
    endpoint = "http://127.0.0.1:5001"
    username = "You"
    textmode = "chat"
    wrap_at = 72
    lastchar = ""
    stop_sequence = ["{{user}}:", "\n{{user}} ", "<START>"]
#    stop_sequence = ["\n{{user}}:", "\n{{user}} ", "\n{{char}}"]
    engine = engine_settings

    def set(self, var, value):
        setattr(self, var, value)
#        self.save()

    def update(self, new):
        for name,value in new.items():
            old = getattr(self, name, None)
            if old is None:
                raise KeyError(f"Wrong key {name} = {value} in options.")
            if getattr(old, "keys", None):
                deep_update(old, value)
            else:
                setattr(self, name, value)

    def generate_key(self):
        self.engine["genkey"] = random_string(8)

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
#                self.__dict__ = json.load(f)
                loaded = json.load(f)
            self.update(loaded)
        else:
            self.generate_key()
            self.save()


conf = Settings()

################



################ llm api

def engine_abort():
    requests.post(f"{conf.endpoint}/api/extra/abort")


def engine_status():
    """ Get status of KoboldCpp
    Result: last_process, last_eval, last_token_count, total_gens, queue, idle,
    stop_reason (INVALID=-1, OUT_OF_TOKENS=0, EOS_TOKEN=1, CUSTOM_STOPPER=2)
    """
    response = requests.get(f"{conf.endpoint}/api/extra/perf")
    if response.status_code != 200:
        raise IOError("Can not get status from engine")
    return response.json()


def engine_stop_reason():
    return engine_status()['stop_reason']


def count_tokens(text):
    response = requests.post(f"{conf.endpoint}/api/extra/tokencount",
        json={"prompt": text})
    if response.status_code != 200:
        raise IOError("Can not get get token count from engine")
    return response.json()['value']


def find_token_start(text, pos):
    if pos == 0:
        n = 0
    else:
        n = count_tokens(text[:pos])
    while n == count_tokens(text[:pos+1]):
        pos += 1
    return pos


def get_stream(json_prompt):
#    jprompt = self.get_json_prompt()
    response = requests.post(f"{conf.endpoint}/api/extra/generate/stream",
        json=json_prompt, stream=True)
    if response.status_code != 200:
        raise IOError("Can not get response stream from engine")
    if response.encoding is None:
        response.encoding = 'utf-8'
    return response.iter_lines(chunk_size=20, decode_unicode=True)


def engine_query_stream(json_prompt):
    is_message = False
    for line in get_stream(json_prompt):
        if line:  #filter out keep-alive new lines
            if is_message:
                if line.startswith("data:"):
                    jresponse = json.loads(line.removeprefix("data: "))
                    token = jresponse['token']
                    yield token
                    is_message = False
            else:
                if line == "event: message":
                    is_message = True

################



################ char

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

################



################ history

cutoff_digits = 8

def store_cutoff(file, cutoff):
    file.write(f"\n{cutoff:0{cutoff_digits}}")


def load_history(file_name):
    with open(file_name, "a+") as file:
        file.seek(0)
        text = file.read()
        field = text[-cutoff_digits:]
        if field.isdecimal():
            cutoff = int(field)
            history = text[:-cutoff_digits-1]
        else:
            cutoff = 0
            history = text
            store_cutoff(file, cutoff)
    return history, cutoff


def to_history(file_name, msg, cutoff):
    with open(file_name, "r+") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        if end > cutoff_digits:
            f.seek(end-cutoff_digits-1)
        f.write(msg)
        store_cutoff(f, cutoff)


def truncate_history(file_name, size, cutoff):
    with open(file_name, "r+") as f:
        f.seek(size)
        store_cutoff(f, cutoff)
        f.truncate()

################



class Conversation:

    def __init__(self, bot=""):
        self.username = conf.username
        self.set_bot(bot)

    def parse_vars(self, text):
        context = dict(user=self.username, char=self.botname)
        return eval_template(text, context)

    def parse_vars_batch(self, parts):
        context = dict(user=self.username, char=self.botname)
        return [eval_template(text, context) for text in parts]

    def init_dialogue(self):
        self.prompt, self.cutoff = load_history(self.log)
        if self.prompt == "":
            print("History is empty, starting new conversation.\n")
            # first "\n" to avoid failing first context shift:
            first = "\n"+self.parse_vars( self.bot['char_greeting'] )+"\n\n"
            self.to_prompt(first)
        else:
            print(f"History loaded: {self.log}\n")
            self.to_prompt("")  # shift context, if log was extended manually
        print(self.prompt, sep="", end="", flush=True)

    def set_bot(self, bot=""):
        if bot == "":
            bot = assistant
        self.botname = bot["name"]
        self.bot = bot
        memory = "\n".join((bot["description"], bot["scenario"], bot["example_dialogue"])) + "\n" #!!!
        memory = self.parse_vars(memory)
        self.memory = memory
        self.memory_tokens = count_tokens(memory)
        self.log = f"{conf.logdir}/aiclient_{self.botname}.log"
        print("\n\n", "#"*32, sep="")
        print(f"Started character: {self.botname}")
        self.init_dialogue()

    def clear_bot(self):
        self.prompt = ""
        self.cutoff = 0
        truncate_history(self.log, len(self.prompt), self.cutoff)
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
            pos = pos + find_token_start(self.prompt[pos:], 0)
        self.cutoff = pos

    def del_prompt_lines(self, count=1):
        text = self.prompt[self.cutoff:]
        text = reformat(text)
        pos = len(text)
        while count > 0:
            count -= 1
            pos = text.rfind("\n", 0, pos)
        if pos < 0:
            pos = 0
        self.prompt = self.prompt[:self.cutoff+pos]
        truncate_history(self.log, len(self.prompt), self.cutoff)

    def to_prompt(self, message):
        self.prompt += message
        max_ctx = conf.engine["max_context_length"] - self.memory_tokens
        now = count_tokens(self.prompt[self.cutoff:])
        extra = now-(max_ctx-10-conf.engine["max_length"])
        if extra > 0:
            self.shift_context(max(extra, len(message)//5+1)) #!!! testing max()
        elif message == "":
            return
        to_history(self.log, message, self.cutoff)

    def get_json_prompt(self):
        self.stop_parsed = self.parse_vars_batch(conf.stop_sequence)
        prompt_data = dict(conf.engine)
        prompt_data.update(
            stop_sequence=self.stop_parsed,
            memory=self.memory,
            prompt=self.prompt[self.cutoff:],
        )
        return prompt_data

    def read_stream(self):
        response = ""
        for token in engine_query_stream( self.get_json_prompt() ):
            response += token
            print(token, end="", flush=True)
        return response, engine_stop_reason()

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
        if stop_reason == 2:  # custom stopper == stop word
            for suffix in self.stop_parsed:
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
            #todo: maybe an option for this? May interrupt multi-user engine.
            if not engine_status()['idle']:
                engine_abort()
            self.stream_response(message)
        except IOError:
            print("Error: can not send message.")
        except KeyboardInterrupt:
            print()
            #todo: maybe an option for this? May interrupt multi-user engine.
            if not engine_status()['idle']:
                engine_abort()

    def refresh_screen(self, end="", chars=2000):
        text = self.prompt[-chars:]
        text = reformat(text)
        print("\n"*3, text, end, sep="", end="")

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
/set textmode chat/text - mode of conversation
"""     )

    def command_message(self, message):
        if message == "/stop":
            engine_abort()
        elif message.startswith( ("/h", "/help") ):
            self.help()
        elif message == "/test":
            print(f"test")
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
                print_nested(conf)
            elif len(args) == 2:
                name = args[1]
                value = get_nested(conf, name)
                print_nested(value)
            else:
                if len(args) != 3:
                    print("Error: set need 2 parameters.")
                else:
                    _,var,value = args
                    if value.isdigit():
                        value = int(value)
                    set_nested(conf, var, value)
        else:
            print("Unknown command.")

    def add_message(self, message):
#        unfinished = len(self.prompt) and self.prompt[-1:] != "\n"
        if message.startswith("/"):
            self.command_message(message)
        elif message == "":
            self.refresh_screen(end="")
            self.post("")
            self.refresh_screen(end="")
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
                truncate_history(self.log, len(self.prompt), self.cutoff)
            elif newlines < 2:
                prefix = "\n"*(2-newlines)
# test if User:/Char: tags mess llm logic
            if conf.textmode == "chat":
                message = f"{self.username}: {message}"
            message = prefix + wrap_text(message)
            if message.endswith("+"):
                message = message[:-1]
            else:
                message = f"{message}\n\n"
            self.refresh_screen(end="")
            print(message, end="", flush=True)
            self.post(message)
            self.refresh_screen(end="")


def talk(bot):
    chat = Conversation(bot)
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
                if conf.textmode == "chat":
                    prefix = f"{chat.username} "
                else:
                    prefix = ""
                message = input(f"{prefix}{mode}> ")
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

if conf.save_on_exit:
    conf.save()
