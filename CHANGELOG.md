# talk2kobold changelog

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
