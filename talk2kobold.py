import base64
import io
import json
import os
import random
import re

import requests



ENDPOINT = "http://127.0.0.1:5001"

def split_text(text):
    parts = re.split(r'\n[a-zA-Z]', text)
    return parts


username =  "User"
botname = "Assistant"


def get_prompt(conversation_history, username, text): # For KoboldAI Generation
    return {
        "prompt": conversation_history + f"{username}: {text}\n{botname}:",
        "use_story": False,
        "use_memory": True,
        "use_authors_note": False,
        "use_world_info": False,
        "max_context_length": 2048,
        "max_length": 120,
        "rep_pen": 1.0,
        "rep_pen_range": 2048,
        "rep_pen_slope": 0.7,
        "temperature": 0.8,
        "tfs": 0.97,
        "top_a": 0.8,
        "top_k": 0,
        "top_p": 0.5,
        "typical": 0.19,
        "sampler_order": [6, 0, 1, 3, 4, 2, 5],
        "singleline": False,
        #"sampler_seed": 69420,   #set the seed
        #"sampler_full_determinism": False,     #set it so the seed determines generation content
        "frmttriminc": False,
        "frmtrmblln": False
    }


num_lines_to_keep = 20
global conversation_history
with open(f'conv_history_{botname}_terminal.txt', 'a+') as file:
    file.seek(0)
    chathistory = file.read()
    print(chathistory)
conversation_history = f"{chathistory}"


def handle_message(user_message):
    global conversation_history
    prompt = get_prompt(conversation_history, username, user_message) # Generate a prompt using the conversation history and user message
    response = requests.post(f"{ENDPOINT}/api/v1/generate", json=prompt) # Send the prompt to KoboldAI and get the response
    if response.status_code == 200:
        results = response.json()['results']
        text = results[0]['text'] # Parse the response and get the generated text
        response_text = split_text(text)[0]
        response_text = response_text.replace("  ", " ")
        conversation_history += f"{username}: {user_message}\n{botname}: {response_text}\n" # Update the conversation history with the user message and bot response
        with open(f'conv_history_{botname}_terminal.txt', "a") as f:
            f.write(f"{username}: {user_message}\n{botname}: {response_text}\n") # Append conversation to text file
        response_text = response_text.replace("\n", "")
        print(f"{botname}: {response_text}") # Send the response back to the user


while True: # Start the conversation
    user_message = input(f"{username}: ")  # Get user input from the console
    handle_message(user_message)  # Handle the user's input and get the bot's response
