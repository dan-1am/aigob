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




def tolog(txt):
    with open("aiclient_debug.log","a") as f:
        f.write(txt)


def warn(txt):
    print("Warning! "+txt, file=sys.stderr)


def error(txt):
    print("Error! "+txt, file=sys.stderr)


def safeinput(prompt):
    start = time.time()
    while True:
        message = input(prompt)
        if time.time()-start > 0.1:
            return message


def random_string(length, charset=None):
    if charset == None:
        charset = string.ascii_uppercase+string.digits
    return "".join(random.choices(charset, k=length))


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


def wrap_text(text, width):
    """Wrap text to lines not exceeding width. Keep text length."""
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


def reformat(text, width, keep_nl=True):
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

conf_presets = dict(
    strict = dict(
        engine = {
            "temperature": 0.7,
            "mirostat": 0,
        },
    ),
    creative = dict(
        engine = {
            "temperature": 0.8,
            "mirostat": 2,
            "mirostat_tau": 5.0,
            "mirostat_eta": 0.1,
        },
    ),
    norepeat = dict(
        engine = {
            "rep_pen": 1.15,
            "rep_pen_range": 2000,
            "rep_pen_slope": 0.0,
        },
    ),
    stdrepeat = dict(
        engine = {
            "rep_pen": 1.1,
            "rep_pen_range": 320,
            "rep_pen_slope": 0.7,
        },
    ),
)


def deep_update(storage, data):
    for name,value in data.items():
        if name not in storage:
            raise KeyError(f"Wrong key {name} = {value} in options.")
        old = storage[name]
        if hasattr(old, "items"):
            deep_update(old, value)
        else:
            storage[name] = value


def deep_diff(storage, data, prefix="", changed=None):
    if changed is None:
        changed = []
    for name,value in data.items():
        loop_prefix = prefix+"."+name if prefix else name
        if name not in storage:
            changed.append(loop_prefix)
        else:
            old = storage[name]
            if hasattr(old, "items"):
                deep_diff(old, value, loop_prefix, changed)
            elif old != value:
                changed.append(loop_prefix)
    return changed


class Settings:
    conffile = "talk2kobold.conf"

    default = dict(
        save_on_exit = True,
        chardir = "chars",
        logdir = "log",
        endpoint = "http://127.0.0.1:5001",
        username = "You",
        textmode = "chat",
        wrap_at = 72,
        gen_until_end = True,
        lastchar = "",
        stop_sequence = ["{{user}}:", "\n{{user}} ", "<START>"],
#        stop_sequence = ["\n{{user}}:", "\n{{user}} ", "\n{{char}}"],
        engine = engine_settings,
        presets = conf_presets,
        active_presets = "strict,stdrepeat",
    )

    def __init__(self):
        self.data = dict(self.default)
        self.generate_key()

    def updated(self):
        pass

    def set(self, var, value):
        self.data[var] = value
        self.updated()

    def __getattr__(self, var):
        return self.data[var]

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.updated()

    def update(self, new):
        deep_update(self.data, new)

    def generate_key(self):
        self.data["engine"]["genkey"] = random_string(8)

    def print(self, path=""):
        branch = self.getpath(path)
        if hasattr(branch, "__getitem__"):
            for k,v in self.getpath(path).items():
                print(f"{k}={v}")
        else:
            print(f"{path}={branch}")

    def getpath(self, name):
        """For name="name1.name2..." get data[name1][name2]..."""
        store = self.data
        try:
            if len(name):
                for part in name.split("."):
                    store = store[part]
            return store
        except (KeyError,TypeError):
            print(f"Variable {name} not exists.")

    def setpath(self, name, value):
        """For name="name1.name2..." set data[name1][name2]... to value"""
        store = self.data
        try:
            *path,last = name.split(".")
            if len(name):
                for var in path:
                    store = store[var]
            store[last] = value
            self.updated()
        except (KeyError,TypeError):
            print(f"Variable {name} not exists.")

    def use_presets(self, names):
        presets = self.data["presets"]
        used = []
        for name in names.split(","):
            if name in presets:
                self.update(presets[name])
                used.append(name)
            else:
                print(f"Preset [$name] not found.")
        self.data["active_presets"] = ",".join(used)

    def presets_status(self):
        ans = []
        presets = self.data["presets"]
        for name in self.data["active_presets"].split(","):
            if name in presets:
                diff = deep_diff(self.data, presets[name])
                if diff:
                    ans.append("\n  *".join((name, *diff)))
                else:
                    ans.append(name)
            else:
                ans.append(name+" - missing preset")
        return "\n".join(ans)

    def save(self):
        with open(self.conffile, "w") as f:
            json.dump(self.data, f, indent=4)

    def load(self, path=None):
        if path is None:
            path = self.conffile
        else:
            self.conffile = path
        if Path(path).is_file():
            with open(path, "r") as f:
                loaded = json.load(f)
            self.update(loaded)
        else:
            warn(f"Configuration file not exist: {path}")

################



################ Characters

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
    def load(cls, name, dir=""):
        if name in ("", "assistant"):
            return assistant
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

    def to_json(self, file, dir=""):
        save = list(self.data)
        for key1,key2 in self.dupkeys:
            save[key2] = save[key1]
        file = Path(dir, file)
        if file.suffix.lower() != ".json":
            file.with_suffix(file.suffix + ".json")
        with open(file, "w") as f:
            json.dump(save, f, indent=3)

    def to_pch(self, file, dir=""):
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
        file = Path(dir, file)
        if file.suffix.lower() != ".pch":
            file.with_suffix(file.suffix + ".pch")
        with open(file, "w") as f:
            f.write(text)


assistant=Character(dict(
    name="Assistant",
    description="",
    example_dialogue="",
    scenario="",
    char_greeting="How can I help?",
))

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
    path = Path(file_name).expanduser()
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        open(path, "w").close()
    with open(path, "r+", errors="replace") as file:
        text, cutoff = get_cutoff(file.read())
        if cutoff is None:
            cutoff = 0
            # add cutoff to history file
            store_cutoff(file, cutoff)
            file.write(text)
    return text, cutoff


def update_history(file_name, text, cutoff):
    path = Path(file_name).expanduser()
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        open(path, "w").close()
    with open(path, "r+", errors="replace") as f:
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



################ llm api

class Engine:

    def __init__(self, conf):
        self.conf = conf

    def stop(self):
        requests.post(f"{self.conf.endpoint}/api/extra/abort")

    def status(self):
        """ Get status of KoboldCpp
        Result: last_process, last_eval, last_token_count, total_gens, queue, idle,
        stop_reason (INVALID=-1, OUT_OF_TOKENS=0, EOS_TOKEN=1, CUSTOM_STOPPER=2)
        """
        response = requests.get(f"{self.conf.endpoint}/api/extra/perf")
        if response.status_code != 200:
            raise IOError("Can not get status from engine")
        return response.json()

    def idle(self):
        return self.status()['idle']

    def stop_reason(self):
        return self.status()['stop_reason']

    def get_max_context(self):
        response = requests.get(f"{self.conf.endpoint}/api/v1/config/max_context_length")
        if response.status_code != 200:
            return None
        return response.json()['value']

    def count_tokens(self, text):
        response = requests.post(f"{self.conf.endpoint}/api/extra/tokencount",
            json={"prompt": text})
        if response.status_code != 200:
            raise IOError("Can not get get token count from engine")
        return response.json()['value']

    def next_token(self, text, pos):
        if pos == 0:
            n = 0
        else:
            n = engine.count_tokens(text[:pos])
        while n == engine.count_tokens(text[:pos+1]):
            pos += 1
        return pos

    def get_stream(self, request, session=None):
        if session is None:
            session = requests
        response = session.post(f"{self.conf.endpoint}/api/extra/generate/stream",
            json=request, stream=True)
        if response.status_code != 200:
            raise IOError("Can not get response stream from engine")
        if response.encoding is None:
            response.encoding = 'utf-8'
        return response.iter_lines(chunk_size=20, decode_unicode=True)


    def set_memory(self, memory):
        if getattr(self, "last_memory", None) != memory:
            self.last_mempory = memory
            self.memory_tokens = self.count_tokens(memory)

    def safe_cut(self, pos):
        for end in ('\n\n', '.\n', '"\n', '\n', ' '):
            pos2 = self.prompt.find(end, pos, pos+200)
            if pos2 >= 0:
                # keep single space-like token, it prevents
                # triggering context-shifting bug in koboldcpp
                pos = pos2+len(end)-1
                break
        else:
            pos = pos + self.engine.next_token(self.prompt[pos:], 0)
        return pos

    # for reference, up to 300 tokens shifts were observed in koboldcpp
    def shift_context(self):
        max_ctx = (self.max_context
            - self.conf.engine["max_length"] - self.memory_tokens - 10)
        pos = self.cutoff
        while True:
            text = self.prompt[pos:]
            tokens = self.count_tokens(text)
            extra_tokens = tokens-max_ctx
            if extra_tokens <= 0:
                break
            pos += extra_tokens*len(text)//tokens
        if pos <= self.cutoff:
            return
        self.cutoff = self.safe_cut(pos)

    def prepare(self, data):
        self.max_context = min(
            self.conf.engine["max_context_length"],
            self.get_max_context())
        self.prompt = data.prompt
        self.set_memory(getattr(data, "memory", ""))
        self.cutoff = getattr(data, "cutoff", 0)
        self.shift_context()
        data.cutoff = self.cutoff
        request = dict(self.conf.engine)
        request.update(
            stop_sequence=data.stop_sequence,
            memory=data.memory,
            prompt=data.prompt[self.cutoff:],
        )
        return request

    def run(self, data):
        request = self.prepare(data)
        is_message = False
        with requests.Session() as session:
            for line in self.get_stream(request, session):
                if line:    # filter out keep-alive new lines
                    if is_message:
                        if line.startswith("data:"):
                            jresponse = json.loads(line.removeprefix("data: "))
                            yield jresponse['token']
                            is_message = False
                    else:
                        if line == "event: message":
                            is_message = True

################



class Conversation:

    def __init__(self, char, conf, engine=None):
        self.conf = conf
        if engine is None:
            engine = Engine(conf)
        self.engine = engine
        self.username = conf.username
        self.stop_reason = 0
        self.set_char(char)

    def parse_vars(self, text):
        context = dict(user=self.username, char=self.char['name'])
        return eval_template(text, context)

    def parse_vars_batch(self, parts):
        context = dict(user=self.username, char=self.char['name'])
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

    def set_char(self, char):
        self.char = char
        self.memory = self.char.memory()
        self.memory = self.parse_vars(self.memory)
        self.log = f"{self.conf.logdir}/{self.char['name']}.log"
        print("\n\n", "#"*32, sep="")
        print(f"Started character: {self.char['name']}")
        self.init_dialogue()

    def clear_char(self):
        self.prompt = ""
        self.cutoff = 0
        update_history(self.log, self.prompt, self.cutoff)
        self.set_char(self.char)

    def del_prompt_lines(self, count=1):
        text = self.prompt[self.cutoff:]
        text = reformat(text, self.conf.wrap_at)
        pos = len(text)
        while count > 0:
            count -= 1
            pos = text.rfind("\n", 0, pos)
        if pos < 0:
            pos = 0
        self.prompt = self.prompt[:self.cutoff+pos]
        update_history(self.log, self.prompt, self.cutoff)

    def to_prompt(self, message):
        if not message:
            return
        self.prompt += message
        update_history(self.log, self.prompt, self.cutoff)

    def read_stream(self):
        response = ""
        self.stop_sequence = self.parse_vars_batch(self.conf.stop_sequence)
        #todo: try-except to keep accumulated response on ctrl+c / errors.
        for token in self.engine.run(self):
            response += token
            print(token, end="", flush=True)
        self.stop_reason = self.engine.stop_reason()
        self.cutoff = self.engine.cutoff
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
                for suffix in self.stop_sequence:
                    if response.endswith(suffix):
                        response = response.removesuffix(suffix)
                        if suffix.startswith("\n") or suffix.endswith("\n"):
                            response += "\n"
                        break
        #else:  # 0=out of tokens, 1=eos token, -1=invalid
#        response = response.rstrip()+"\n"
            self.to_readline(response)
            self.to_prompt(response)
            if not( self.conf.gen_until_end and self.stop_reason == 0 ):
                break

    def post(self, message):
        try:
            #todo: maybe an option for this? May interrupt multi-user engine.
            if not self.engine.idle():
                self.engine.stop()
            self.stream_response(message)
        except IOError:
            print("Error: can not send message.")
        except KeyboardInterrupt:
            print()
            #todo: maybe an option for this? May interrupt multi-user engine.
            if not self.engine.idle():
                self.engine.stop()

    def refresh_screen(self, end="", chars=2000):
        text = self.prompt[-chars:]
        text = reformat(text, self.conf.wrap_at)
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
/load  -load Assistant character
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
        self.engine.stop()

    @chat_cmd
    def cmd_test(self, params):
        """cmd  -debug."""
        print(f"test")

    @chat_cmd
    def cmd_saveconf(self, params):
        """cmd -save configuration to file."""
        self.conf.save()

    @chat_cmd
    def cmd_ls(self, params):
        """cmd  -list available characters."""
        for f in Path(self.conf.chardir).iterdir():
            if f.suffix in (".json", ".pch"):
                print(f.name)

    @chat_cmd
    def cmd_load(self, params):
        """cmd charname  -load character."""
        name = params.strip()
        self.conf.set("lastchar", name)
        char = Character.load(name, self.conf.chardir)
        self.set_char(char)

    @chat_cmd
    def cmd_save(self, params):
        """cmd filename  -save character to json/pch file."""
        name = params.strip()
        if not name.endswith((".pch",".json")):
            name += ".json"
        if name.endswith(".json"):
            self.char.to_json(name, self.conf.chardir)
        else:
            self.char.to_pch(name, self.conf.chardir)

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
            self.conf.print()
        elif len(args) == 1:
            var = args[0]
            self.conf.print(var)
        elif len(args) == 2:
            var,value = args
            if value.isdigit():
                value = int(value)
            self.conf.setpath(var, value)
        else:
            print("Error: set need at most 2 parameters.")

    @chat_cmd
    def cmd_preset(self, params):
        """cmd name1,name2,... -use presets."""
        if not params:
            for name in self.conf.presets:
                print(name)
            print("\nActive:\n" + self.conf.presets_status())
        else:
            self.conf.use_presets(params)

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
        text = reformat(self.prompt[self.cutoff:], self.conf.wrap_at)
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

    def append_message(self, message):
        text = reformat(self.prompt[self.cutoff:].rstrip(), self.conf.wrap_at)
        pos = text.rfind("\n")
        message = wrap_text(text[pos+1:] + message[1:], self.conf.wrap_at)
        # unsaved prompt, update_history() needed later
        self.prompt = self.prompt[:pos+1]
        self.to_prompt(message)
        self.refresh_screen()

    def add_message(self, message):
        newlines = count_newlines(self.prompt)
        prefix = ""
        if newlines > 2:
            # unsaved prompt, update_history() needed later
            self.prompt = self.prompt[:2-newlines]
        elif newlines < 2:
            prefix = "\n"*(2-newlines)
        if self.conf.textmode == "chat":
            message = f"{self.username}: {message}"
        message = prefix + wrap_text(message, self.conf.wrap_at)
        if message.endswith("+"):
            message = message[:-1]
        else:
            message = f"{message}\n\n"
        self.refresh_screen(end="")
        print(message, end="", flush=True)
        self.post(message)
        self.refresh_screen(end="")

    def user_message(self, message):
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
            self.append_message(message)
        else:
            self.add_message(message)

    def run(self):
        while True:
            if self.prompt == "" or self.prompt.endswith("\n"):
                mode = ""
                print("\r", " "*20, "\r", sep="", end="")
            else:
                mode = "+"
                print()
            try:
                if self.conf.textmode == "chat":
                    prefix = f"{self.username} "
                else:
                    prefix = ""
                message = safeinput(f"{prefix}{mode}> ")
                self.user_message(message)
            except KeyboardInterrupt:
                input("\nEnter to continue, Ctrl+C second time to exit.")
            except EOFError:
                print("End of input, exiting...")
                break
            except SystemExit:
                break



################ Main

conf = Settings()
conf.load()
char = Character.load(conf.lastchar, conf.chardir)

args = sys.argv[1:]
while args:
    arg = args.pop(0)
    if arg in ("-c", "--conf"):
        conf.load(args.pop(0))
    elif arg in ("-l", "--load"):
        conf.set("lastchar", args.pop(0))
        char = Character.load(conf.lastchar, conf.chardir)
    elif arg in ("-j", "--json"):
        char.to_json(args.pop(0), conf.chardir)
        sys.exit()
    elif arg in ("-p", "--py"):
        char.to_pch(args.pop(0), conf.chardir)
        sys.exit()
    else:
        raise NameError(f"Error: unknown option {arg}")

chat = Conversation(char, conf)
chat.run()

if conf.save_on_exit:
    conf.save()
