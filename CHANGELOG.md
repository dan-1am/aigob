# aigob changelog

## 2024.03.19

- Rename from talk2kobold to aigob

## 2024.03.10

- Fix /set and conf.setpath(): convert input to previous value type
    to prevent float becoming str

- Add some error handling in char.load()

## 2024.03.03

- Move all output code to separate ChatView classes

## 2024.02.25

- Use new kobold api to get max_context_length, old is wrong.

## 2024.02.25

- Refactor display code from chat to new ChatView class
- Add patches field to the end of memory to patch char
    without context reprocessing

## 2024.02.19

- Move context-shifting and response iteration to engine class
- Use "with requests.Session" to do clean-up on exceptions
- Rename chat.stop_parsed to chat.stop_sequence
- Check LLM max_context_length to cap conf.engine value
- Enhance history saving/loading
- Store stop_sequence in conf as string instead of array
- Add story/chat profiles

## 2024.02.17

- Move global var engine to Conversation class
- Corrected assistant char creation
- Move global var conf to chat.conf

## 2024.02.14

- New Engine class for LLM engine interface

## 2024.02.12

- Make deep_compare() able to handle None's in config
- Presets and /preset chat command

## 2024.01.24

- Move conf variables from attributes to separate .data dict

## 2024.01.22

- Extract char functions into separate class Character
- Loading assistant with /load without parameters
- Add /save command to save char file
- Changed --char to --load, added --conf options

## 2024.01.13

- Add gen_until_end mode and option.
    In this mode generation call repeats until eos / stop word encountered.

## 2024.01.11

- Command @: use external editor

## 2024.01.06

- Randomize conf.engine['genkey']
- Reformat text for display

## 2024.01.02

- Configuration nested names support: /set name1.name2 = value
- Add conf.textmode - story/chat, chat prepends message with "user >"
- Add conf.username

## 2024.01.02

- Extract history save/load from Conversation.

## 2024.01.01

- Separate engine functions from Conversation.

## 2023.12.31

- Remove prompt from Conversation, keep current vars in settings
    and generate prompt dynamically.
- Configuration loader now checks keys for existance (recursive).

## 2023.12.30

- Settings smart save
- Disable settings autosave for now (except if .conf is missing)
- New settings: engine, stop_sequence
- New command: /saveconf

## 2023.12.27

- Integrate Settings class fully.
- Add time measurement to input, discard too fast input
    (helps with pasted text unexpected newlines).
- Add engine-generated text to readline history.

## 2023.12.23

- Got puzzled with llm in wrong format not working with koboldcpp
    context shifting for a long time, but eventually did it right.
- Streamline line endings in stream_response() and add_message()
- Configuration class (not fully integrated yet) and file.
- Tune char load/save.
- Implement /ls chat command.

## 2023.12.20

- Context shifting fully works!
      (added "\n" before char_greeting, cut prompt just before "\n")
- Removed char message stripping.

## 2023.12.19

- Changed char/bot variable names to more descriptive.
- Prompt commands for char loading, history clearing
- History files with char name.
- Context shifting from previous version working, except the first shift.

## 2023.12.19

- Try to repair context shifting with memory-prompt separator "##"
    - Not working (mostly).
- Extended stop_reason use in response handling.
- Prompt commands: delete line, add newline, set engine variable.
- Remove engine auto-abort on start.

## 2023.12.18

- Response sse streaming.
- Ctrl+c streaming interruption.
- Try to repair context shifting with prompt cut to next token start.
    - Not working.

## 2023.12.16

- Add extended kobold api.
- Prepare token counting.
- Get stop_reason from kobold engine.
- Single history variable and history file with cutoff.

## 2023.12.16

- Development version with a lot of garbage.
- Prompt file with stored cutoff.
- Embedded assistant bot.

## 2023.12.13

Basic implementation.
