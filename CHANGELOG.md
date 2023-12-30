# talk2kobold changelog

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
