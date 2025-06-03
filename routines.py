import configparser
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES=True
import cv2
import numpy as np
import threading
import time
import easyocr
import roa2
import re
import smartcv_core.core as core
from smartcv_core.matching import findBestMatch
from datetime import datetime
client_name = "smartcv-roa2"
payload_lock = threading.Lock()
config = configparser.ConfigParser()
config.read('config.ini')
previous_states = [None] # list of previous states to be used for state change detection
reader = easyocr.Reader(['en'])

payload = {
    "state": None,
    "stage": None,
    "players": [
        {
            "name": None,
            "character": None,
            "stocks": None,
            "damage": None
        },
        {
            "name": None,
            "character": None,
            "stocks": None,
            "damage": None
        }
    ]
}

def detect_stage_select_screen(payload:dict):
    img, scale_x, scale_y = core.capture_screen()
    if not img: return
    pixel = img.getpixel((int(75 * scale_x), int(540 * scale_y)))  # white stage width icon
    
    # Define the target colors and deviation
    target_color = (252, 250, 255)  # white stage width icon
    deviation = 0.1
    
    if core.is_within_deviation(pixel, target_color, deviation):
        print("Stage select screen detected")
        payload['state'] = "stage_select"
        if payload['state'] != previous_states[-1]:
            previous_states.append(payload['state'])
            # reset payload to original values
            payload['stage'] = None
        if payload['players'][0]['character'] == None: detect_characters_and_tags()



def detect_character_select_screen(payload:dict):    
    img, scale_x, scale_y = core.capture_screen()
    if not img: return
    pixel = img.getpixel((int(875 * scale_x), int(23 * scale_y))) #white tournament mode icon
    pixel2 = img.getpixel((int(320 * scale_x), int(10 * scale_y))) #back button area
    
    # Define the target color and deviation
    target_color = (252, 250, 255)  #(white tournament mode icon)
    target_color2 = (60, 47, 101)  #back button area
    deviation = 0.1
    
    if core.is_within_deviation(pixel, target_color, deviation) and core.is_within_deviation(pixel2, target_color2, deviation):
        payload['state'] = "character_select"
        print("Character select screen detected")
        if payload['state'] != previous_states[-1]:
            previous_states.append(payload['state'])
            #clean up some more player information
            for player in payload['players']:
                player['stocks'] = None
                player['damage'] = None
                player['character'] = None
                player['name'] = None

    return

def detect_characters_and_tags(payload:dict):
    img, scale_x, scale_y = core.capture_screen()
    if not img: return
    
    #set initial game data, both players have 3 stocks
    for player in payload['players']:
        player['stocks'] = 3
    def read_characters_and_names(payload):
        # signal to the main loop that character and tag detection is in progress
        if payload['state'] != "stage_select": return
        payload['players'][0]['character'] = False
        payload['players'][1]['character'] = False
        # Initialize the reader
        tags = core.read_text(img, (0, int(990 * scale_y), int(1920 * scale_x), int(25 * scale_y)))
        characters = core.read_text(img, (0, int(1020 * scale_y), int(1920 * scale_x), int(20 * scale_y)))
        #this will yield a number of 2 characters separated by spaces. they must be assigned for each player. 
        #it will also yield a number of 2 tags separated by spaces. an exception to this is if the player does not have a tag, in which case they will show up as Player 1, Player 2, Player 3 or Player 4.
        #the regex will handle these exceptions.
        if tags is not None:
            tags = re.split(r' (?=\D)', tags)
            if len(tags) == 2:
                t1, t2 = tags[0], tags[1]
            else:
                return detect_characters_and_tags(payload) # re-attempt detection
        else:
            return detect_characters_and_tags(payload) # re-attempt detection
        if characters is not None:
            characters = characters.split(" ")
            if len(characters) == 2:
                c1, c2 = findBestMatch(characters[0], roa2.characters), findBestMatch(characters[1], roa2.characters)
            else:
                return detect_characters_and_tags(payload) # re-attempt detection
        else:
            return detect_characters_and_tags(payload)
        payload['players'][0]['character'], payload['players'][1]['character'], payload['players'][0]['name'], payload['players'][1]['name'] = c1, c2, t1, t2
        print("Player 1 character:", c1)
        print("Player 2 character:", c2)
        print("Player 1 tag:", t1)
        print("Player 2 tag:", t2)

    threading.Thread(target=read_characters_and_names, args=(payload,)).start()
    return img

def detect_versus_screen(payload:dict):
    img, scale_x, scale_y = core.capture_screen()
    if not img: return
    pixel1 = img.getpixel((int(1075 * scale_x), int(69 * scale_y))) #(white rupture between characters on VS screen)
    pixel2 = img.getpixel((int(855 * scale_x), int(985 * scale_y))) #(white rupture between characters on VS screen)
    pixel3 = img.getpixel((int(942 * scale_x), int(85 * scale_y))) #backup pixel to detect game has started: semicolon from ingame timer
    
    # Define the target color and deviation
    target_color = (252, 250, 255)  #(white rupture between characters on VS screen)
    deviation = 0.1
    
    if (core.is_within_deviation(pixel1, target_color, deviation) and core.is_within_deviation(pixel2, target_color, deviation)) or core.is_within_deviation(pixel3, target_color, deviation):
        payload['state'] = "in_game"
        if payload['state'] != previous_states[-1]:
            previous_states.append(payload['state'])
        # read stage name
        if core.is_within_deviation(pixel1, target_color, deviation) and core.is_within_deviation(pixel2, target_color, deviation):
            stage = core.read_text(img, (int(1120 * scale_x), int(25 * scale_y), int(750 * scale_x), int(75 * scale_y)))
            if stage is not None:
                payload['stage'] = findBestMatch(stage, roa2.stages)
                print("Match has started on stage: ", payload['stage'])
            else:
                print("Match has started!")
            time.sleep(10) # wait for the game to start
        else:
            print("Match has started!")

    return

def detect_game_end(payload:dict):
    img, scale_x, scale_y = core.capture_screen()
    if not img: return
    pixel1 = img.getpixel((0, int(90 * scale_y))) #(black letterbox that shows up when game ends)
    pixel2 = img.getpixel((0, int(980 * scale_y))) #(black letterbox that shows up when game ends)
            
    target_color = (0, 0, 0)  #(black letterbox that shows up when game ends)
    deviation = 0.1
        
    if (core.is_within_deviation(pixel1, target_color, deviation) and core.is_within_deviation(pixel2, target_color, deviation)):
        print("Game end detected")
        if (process_game_end_data(payload, img, (int(541 * scale_x), int(754 * scale_y), int(731 * scale_x), int(197 * scale_y)), (int(187 * scale_x), int(238 * scale_x), int(535 * scale_x), int(580 * scale_x)))):
            payload['state'] = "game_end"
            if payload['state'] != previous_states[-1]:
                previous_states.append(payload['state'])

    
def process_game_end_data(payload:dict, img, region: tuple[int, int, int, int], crop_area: tuple[int, int, int, int]):
    # Define the area to read
    x, y, w, h = region
    img_array = np.array(img)
    full_data = img_array[int(y):int(y+h), int(x):int(x+w)]
    full_data = cv2.cvtColor(full_data, cv2.COLOR_RGB2GRAY)
    # Increase contrast of the image
    full_data = cv2.convertScaleAbs(full_data, alpha=2, beta=0)
    # black out character icons regions
    full_data[:, crop_area[0]:crop_area[1]] = 0  # first icon
    full_data[:, crop_area[2]:crop_area[3]] = 0  # second icon
    
    # Use OCR to read the text from the grayscale image
    result = reader.readtext(full_data, paragraph=False, allowlist='0123456789%', text_threshold=0.3, low_text=0.2)
    # print(result)

    # what this text will extract are for excerpts of numbers. the first is the number of stocks for player 1, the second is the damage received by player 1, the third is the number of stocks for player 2, and the fourth is the damage received by player 2.
    if result:
        # remove results that have less than 0.25 confidence (might not be numbers)
        result = [res for res in result if res[2] >= 0.25]

        # remove % sign
        result = ([int(res[1].replace('%', '') or 0) for res in result])

        # do some cleanup
        if len(result) == 4:
            stocks1, damage1, stocks2, damage2 = result[0], result[1], result[2], result[3]
            payload['players'][0]['stocks'] = stocks1
            payload['players'][1]['stocks'] = stocks2
            payload['players'][0]['damage'] = damage1
            payload['players'][1]['damage'] = damage2

            print(f"{payload['players'][0]['name']}'s end state: {stocks1} stocks at {damage1}%")
            print(f"{payload['players'][1]['name']}'s end state: {stocks2} stocks at {damage2}%")
            
            #validate stock counts
            if not (0 <= stocks1 <= 3) or not (0 <= stocks2 <= 3): return False
            #print out the winner of the match based on two conditions: if one player has 0 stcks the other player wins. if both players have the same amount of stocks, the player with the least amount of damage wins.
            if stocks1 == 0 or stocks1 < stocks2:
                print(f"{payload['players'][1]['name']} wins!")
            elif stocks2 == 0 or stocks2 < stocks1:
                print(f"{payload['players'][0]['name']} wins!")
            elif stocks1 == stocks2:
                # in this case, we need to be more scrumptuous with the damage values as they can be read wrong
                if damage1 > 270 or damage2 > 270:
                    print("Damage values considered too high")
                    return False
                if damage1 < damage2:
                    print(f"{payload['players'][0]['name']} wins!")
                elif damage1 > damage2:
                    print(f"{payload['players'][1]['name']} wins!")
            else: print("Draw game")
            return True
        else:
            print("Could not read game end data. Trying again...")
    return False

states_to_functions = {
    None: [detect_character_select_screen],
    "character_select": [detect_stage_select_screen],
    "stage_select": [detect_character_select_screen, detect_versus_screen],
    "in_game": [detect_character_select_screen, detect_game_end],
    "game_end": [detect_character_select_screen, detect_stage_select_screen],
}