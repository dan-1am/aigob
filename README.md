# aigob - AI gray on black

Console client for KoboldCpp AI text generation engine.

Features: character loading, history editing.

With SSH and Screen: multi-user chat and computer switching.

## Installation

This app is intentionally single-file, possible to be downloaded
directly, or be git-cloned.

The only dependencity is requests library.

On the first run aigob will create a configuration file. You can edit it
directly (be sure to close aigob first, or the file will be overwritten) or
with `/set variable value` command.

`endpoint` option is configured to the default koboldcpp address
`http://127.0.0.1:5001)`.

## Usage

You can type `/help` to list available commands.

By default built-in assistant character is loaded. You can load
different character with `/load path-to-charfile.json`. Then just start
writing. To stop the AI prematurely you can use Ctrl-C.

Simple history editing could be done with commands:

1. '+some text' - append text to previous line
2. 'Some text+' - allow AI to continue this text
3. '-' - delete last line
4. '=' - add a newline

Advanced editing could be done in external editor with `@` command.

You can set your favorite console (or even windowed) editor with
`/set editor nano` command.

## Presets

You can use presets to set several related options at once and
be able to see at a glance how is the app configured.

`/preset` lists available presets, activated presets and manually
changed options.

`/preset creative,chat` activates 'creative' and 'chat' presets once
and records them as the only activated presets.
