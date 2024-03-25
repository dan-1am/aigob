# AiGob - AI Gray On Black

Console client for the KoboldCpp AI text generation engine.

Features: character loading, history editing, chat/story modes,
autoformat text.

With SSH and Screen: multi-user chat and computer switching.

## Installation

This app is intentionally made as single file an can be downloaded
directly.

The only dependencity is required: the Python Requests library.

Upon its initial launch AiGob creates a configuration file. You can edit
the file directly (be sure to close AiGob first, or the file will be
overwritten) or with chat command `/set variable value`.

By default the `endpoint` option is configured to the standard KoboldCpp
address: http://127.0.0.1:5001

## Usage

Typing "/help" will display a list of available commands.

Initially, the built-in assistant character is loaded during startup.
You can load alternative characters with `/load path-to-charfile.json`.
Pressing Ctrl-C stops the AI prematurely.

Simple history editing includes:

1. '+some text' - Append text to previous line.
2. 'Some text+' - Allows AI to continue this line.
3. '-' - Delete the last line.
4. '=' - Add a newline.

Advanced editing can be performed in external editor with `@` command.

You can set your favorite console (or even windowed) editor using the
`/set editor path-to-editor` command.

## Presets

Presets allow you change multiple related settings simultaneously. They
also provide a convenient way to observe the current state of the
program.

`/preset` lists available presets, activated presets and manually
changed options.

`/preset creative,chat` activates 'creative' and 'chat' presets once
and records them as the only activated presets.
