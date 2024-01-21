import base64
import io
import json
import os
from pathlib import Path
import string
import subprocess
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


def find_diff(old, new):
    min_len = min(len(old), len(new))
    for i in range(min_len):
        if old[i] != new[i]:
            return i
    if len(old) != len(new):
        return min_len
    return -1


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
    "use_default_badwordsids": False,
    "genkey": "0I3IVC7D",
    "max_context_length": 4096,
    "max_length": 16,
    #"sampler_seed": 69420,   #set the seed
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
    gen_until_end = True
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



################ history

cutoff_digits = 8

def get_cutoff(text):
    digits = text[:cutoff_digits]
    if len(text) < cutoff_digits or not digits.isdecimal():
        return text, None
    cutoff = int(digits)
    text = text[cutoff_digits:]
    return text, cutoff


def store_cutoff(file, cutoff):
    file.seek(0)
    file.write(f"{cutoff:0{cutoff_digits}}")


def load_history(file_name):
    if not Path(file_name).is_file():
        open(file_name, "w").close()
    with open(file_name, "r+", errors="replace") as file:
        text, cutoff = get_cutoff(file.read())
        if cutoff is None:
            cutoff = 0
            # add cutoff to history file
            store_cutoff(file, cutoff)
            file.write(text)
    return text, cutoff


def update_history(file_name, text, cutoff):
    if not Path(file_name).is_file():
        open(file_name, "w").close()
    with open(file_name, "r+", errors="replace") as f:
        history, old_cutoff = get_cutoff( f.read() )
        if old_cutoff is None:
            store_cutoff(f, 0)
            f.write(text)
            f.truncate()
            return
        if cutoff != old_cutoff:
            store_cutoff(f, cutoff)
        pos = find_diff(history, text)
        if pos >= 0:
            filepos = cutoff_digits + len( text[:pos].encode('utf-8') )
            # todo: not working for os.linesep > 1
            f.seek(filepos)
            f.write(text[pos:])
            f.truncate()

################



################ chat commands

chat_commands = dict()


def chat_cmd(f):
    chat_commands[f.__name__[4:]] = f


def chat_cmd_alias(name):
    last = list( chat_commands.keys() )[-1]
    chat_commands[name] = chat_commands[last]


def chat_cmd_get(name):
    return chat_commands.get(name, None)


def chat_cmd_help():
    parts = []
    for name,f in chat_commands.items():
        parts.append(f"/{name}{f.__doc__[3:]}\n")
    return "".join(parts)

################



class Character:

    dupkeys = (
        ("name", "char_name"),
        ("description", "char_persona"),
        ("scenario", "world_scenario"),
        ("example_dialogue", "mes_example"),
        ("char_greeting", "first_mes"),
    )

    def __init__(self, data):
        self.data = data

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def memory(self):
        parts = []
        for variable,template in (
            ('system_prompt', "{}"),
            ('description', "Persona:\n{}"),
            ('scenario', "[Scenario: {}]"),
            ('post_history_instructions', "{}"),
            ('example_dialogue', "{}"),
        ):
            text = self.data.get(variable, "")
            if len(text):
                parts.append(template.format(text))
        parts.append("***\n")
        return "\n".join(parts)

    def strip(self):
        for key1,key2 in self.dupkeys:
            if self.data.get(key1, None) is None:
                self[key1] = self.data.get(key2, "")
            self.data.pop(key2, None)
            self[key1] = self[key1].strip()

    @classmethod
    def load(cls, name, dir=None):
        if dir == None:
            dir = conf.chardir
        names = (name, name+".pch", name+".json")
        for testname in names:
            path = Path(dir, testname)
            if path.is_file():
                with path.open() as f:
                    if testname.endswith(".pch"):
                        data = eval(f.read(), {"__builtins__": {"dict": dict}})
                    else:
                        data = json.load(f)
                    char = cls(data)
                    char.strip()
                    return char

    def to_json(self, file, dir=None):
        save = list(self.data)
        for key1,key2 in self.dupkeys:
            save[key2] = save[key1]
        if dir == None:
            dir = conf.chardir
        if not file.endswith(".json"):
            file += ".json"
        with open(f"{dir}/{file}", "w") as f:
            json.dump(save, f, indent=3)

    def to_pch(self, file, dir=None):
        if dir == None:
            dir = conf.chardir
        longkeys = (
            "description",
            "scenario",
            "example_dialogue",
            "char_greeting",
        )
        parts = ["dict(\n"]
        for k,v in self.data.items():
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


assistant=Character(dict(
    name="Assistant",
    description="",
    example_dialogue="",
    scenario="",
    char_greeting="How can I help?",
))


class Conversation:

    def __init__(self, char=""):
        self.username = conf.username
        self.stop_reason = 0
        self.set_char(char)

    def parse_vars(self, text):
        context = dict(user=self.username, char=self.charname)
        return eval_template(text, context)

    def parse_vars_batch(self, parts):
        context = dict(user=self.username, char=self.charname)
        return [eval_template(text, context) for text in parts]

    def init_dialogue(self):
        self.prompt, self.cutoff = load_history(self.log)
        if self.prompt == "":
            print("History is empty, starting new conversation.\n")
            # first "\n" to avoid failing first context shift:
            first = "\n"+self.parse_vars( self.char['char_greeting'] )+"\n\n"
            self.to_prompt(first)
        else:
            print(f"History loaded: {self.log}\n")
        self.refresh_screen(chars=8000)

    def set_char(self, char=""):
        if char == "":
            char = assistant
        self.charname = char["name"]
        self.char = char
        self.memory = self.char.memory()
        self.memory = self.parse_vars(self.memory)
        self.memory_tokens = count_tokens(self.memory)
        self.log = f"{conf.logdir}/aiclient_{self.charname}.log"
        print("\n\n", "#"*32, sep="")
        print(f"Started character: {self.charname}")
        self.init_dialogue()

    def clear_char(self):
        self.prompt = ""
        self.cutoff = 0
        update_history(self.log, self.prompt, self.cutoff)
        self.set_char(self.char)

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
        update_history(self.log, self.prompt, self.cutoff)

    def to_prompt(self, message):
        self.prompt += message
        max_ctx = conf.engine["max_context_length"] - self.memory_tokens
        now = count_tokens(self.prompt[self.cutoff:])
        extra = now-(max_ctx-10-conf.engine["max_length"])
        if extra > 0:
            self.shift_context(max(extra, len(message)//5+1)) #!!! testing max()
        elif message == "":
            return
        update_history(self.log, self.prompt, self.cutoff)

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
        self.stop_reason = engine_stop_reason()
        return response

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
        while True:
            response = self.read_stream()
            if self.stop_reason == 2:  # custom stopper == stop word
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
            if not( conf.gen_until_end and self.stop_reason == 0 ):
                break

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
        head = """Help:
Ctrl+c  -while receiving llm answer: cancel
Ctrl-z  -exit
"="  -add new line
"+text"  -append text to last line
"text+"  -let llm to continue text
"@"  -edit in external editor
/set textmode chat/text - mode of conversation
"""
        print(head, chat_cmd_help(), sep="", end="")

    @chat_cmd
    def cmd_help(self, params):
        """cmd  -display help page."""
        self.help()

    chat_cmd_alias("h")

    @chat_cmd
    def cmd_stop(self, params):
        """cmd  -command llm to stop generation."""
        engine_abort()

    @chat_cmd
    def cmd_test(self, params):
        """cmd  -debug."""
        print(f"test")

    @chat_cmd
    def cmd_saveconf(self, params):
        """cmd -save configuration to file."""
        conf.save()

    @chat_cmd
    def cmd_ls(self, params):
        """cmd  -list available characters."""
        for f in Path(conf.chardir).iterdir():
            if f.suffix in (".json", ".pch"):
                print(f.name)

    @chat_cmd
    def cmd_load(self, params):
        """cmd charname  -load character."""
        name = params.strip()
        conf.set("lastchar", name)
        char = Character.load(name)
        self.set_char(char)

    @chat_cmd
    def cmd_clear(self, params):
        """cmd  -clear current character history."""
        self.clear_char()

    @chat_cmd
    def cmd_del(self, params):
        """cmd count  -delete count history lines."""
        count = params.strip()
        count = int(count) if count.isdigit() else 1
        self.del_prompt_lines(count)
        self.refresh_screen()

    chat_cmd_alias("d")

    @chat_cmd
    def cmd_r(self, params):
        """cmd  -refresh screen."""
        self.refresh_screen(chars=4000)

    @chat_cmd
    def cmd_set(self, params):
        """cmd [name] [value] -display or set variable."""
        args = params.split()
        if len(params) == 0:
            print_nested(conf)
        elif len(args) == 1:
            name = args[0]
            value = get_nested(conf, name)
            print_nested(value)
        elif len(args) == 2:
            var,value = args
            if value.isdigit():
                value = int(value)
            set_nested(conf, var, value)
        else:
            print("Error: set need at most 2 parameters.")

    @chat_cmd
    def cmd_exit(self, params):
        """cmd -exit program."""
        raise SystemExit

    def command_message(self, message):
        params = message.split(maxsplit=1)
        cmd = params[0][1:]
        params = params[1] if len(params) > 1 else ""
        f = chat_cmd_get(cmd)
        if f:
            f(self, params)
        else:
            print("Unknown command.")

    def use_editor(self):
        text = reformat( self.prompt[self.cutoff:] )
        file_to_edit = "/tmp/t2k"+random_string(8)
        with open(file_to_edit, "w") as f:
            f.write(text)
        subprocess.run(['mcedit', file_to_edit+":99999"])
        with open(file_to_edit) as f:
            new = f.read()
        Path(file_to_edit).unlink(missing_ok=True)
        diff = find_diff(text, new)
        if diff >= 0:
            if self.cutoff+diff < len(self.prompt):
                # unsaved prompt cut, need update_history later
                self.prompt = self.prompt[:self.cutoff+diff]
            add = new[diff:]
            if add.strip().startswith("/"):
                self.command_message(add.strip())
            else:
                self.to_prompt(add)

    def add_message(self, message):
#        unfinished = len(self.prompt) and self.prompt[-1:] != "\n"
        if message.startswith("/"):
            self.command_message(message)
        elif message == "@":
            self.use_editor()
            update_history(self.log, self.prompt, self.cutoff)
            self.refresh_screen(end="")
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
            text = reformat( self.prompt[self.cutoff:].rstrip() )
            pos = text.rfind("\n")
            message = wrap_text( text[pos+1:] + message[1:] )
            # unsaved prompt, update_history() needed later
            self.prompt = self.prompt[:pos+1]
            self.to_prompt(message)
            self.refresh_screen()
        else:
            newlines = count_newlines(self.prompt)
            prefix = ""
            if newlines > 2:
                # unsaved prompt, update_history() needed later
                self.prompt = self.prompt[:2-newlines]
            elif newlines < 2:
                prefix = "\n"*(2-newlines)
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


def talk(char):
    chat = Conversation(char)
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
        except SystemExit:
            break


conf.load()
char = conf.lastchar
if char != "":
    char = Character.load(char)

args = sys.argv[1:]
while args:
    arg = args.pop(0)
    if arg in ("-c", "--char"):
        conf.set("lastchar", args.pop(0))
        char = Character.load(conf.lastchar)
    elif arg in ("-j", "--json"):
        char.to_json(args.pop(0))
        sys.exit()
    elif arg in ("-p", "--py"):
        char.to_pch(args.pop(0))
        sys.exit()
    else:
        raise NameError(f"Error: unknown option {arg}")

talk(char)

if conf.save_on_exit:
    conf.save()
