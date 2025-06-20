import configparser
import numpy as np
import threading
import time
import roa2
import re
import core.core as core
from core.matching import findBestMatch
client_name = "smartcv-roa2"
payload_lock = threading.Lock()
config = configparser.ConfigParser()
config.read('config.ini')
previous_states = [None] # list of previous states to be used for state change detection

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

def detect_stage_select_screen(payload:dict, img, scale_x:float, scale_y:float):
    pixel = img.getpixel((int(75 * scale_x), int(540 * scale_y)))  # white stage width icon
    
    # Define the target colors and deviation
    target_color = (252, 250, 255)  # white stage width icon
    deviation = 0.1
    
    if core.is_within_deviation(pixel, target_color, deviation):
        core.print_with_time("Stage select screen detected")
        payload['state'] = "stage_select"
        if payload['state'] != previous_states[-1]:
            previous_states.append(payload['state'])
            # reset payload to original values
            payload['stage'] = None
            for player in payload['players']:
                player['stocks'] = None
                player['damage'] = None
                player['character'] = None
                player['name'] = None
        detect_characters_and_tags(payload, img, scale_x, scale_y)



def detect_character_select_screen(payload:dict, img, scale_x:float, scale_y:float):    
    pixel = img.getpixel((int(875 * scale_x), int(23 * scale_y))) #white tournament mode icon
    pixel2 = img.getpixel((int(320 * scale_x), int(10 * scale_y))) #back button area
    
    # Define the target color and deviation
    target_color = (252, 250, 255)  #(white tournament mode icon)
    target_color2 = (60, 47, 101)  #back button area
    deviation = 0.1
    
    if core.is_within_deviation(pixel, target_color, deviation) and core.is_within_deviation(pixel2, target_color2, deviation):
        payload['state'] = "character_select"
        core.print_with_time("Character select screen detected")
        if payload['state'] != previous_states[-1]:
            previous_states.append(payload['state'])
            #clean up some more player information
            for player in payload['players']:
                player['stocks'] = None
                player['damage'] = None
                player['character'] = None
                player['name'] = None

def detect_characters_and_tags(payload:dict, img, scale_x:float, scale_y:float):
    if payload['players'][0]['character'] != None: return 
    
    #set initial game data, both players have 3 stocks
    for player in payload['players']:
        player['stocks'] = 3
    def read_characters_and_names(payload, img, scale_x, scale_y):
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
            if len(tags) == 2:
                t1, t2 = tags[0], tags[1]
            else:
                return
        else:
            return
        if characters is not None:
            if len(characters) == 2:
                c1, _ = findBestMatch(characters[0], roa2.characters)
                c2, _ = findBestMatch(characters[1], roa2.characters)
            else:
                return
        else:
            return
        payload['players'][0]['character'], payload['players'][1]['character'], payload['players'][0]['name'], payload['players'][1]['name'] = c1, c2, t1, t2
        core.print_with_time("Player 1 character:", c1)
        core.print_with_time("Player 2 character:", c2)
        core.print_with_time("Player 1 tag:", t1)
        core.print_with_time("Player 2 tag:", t2)

    threading.Thread(target=read_characters_and_names, args=(payload, img, scale_x, scale_y)).start()

def detect_versus_screen(payload:dict, img, scale_x:float, scale_y:float):
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
            stage = core.read_text(img, (int(1120 * scale_x), int(25 * scale_y), int(755 * scale_x), int(75 * scale_y)))
            if stage is not None:
                stage = '. '.join(stage)
                payload['stage'], _ = findBestMatch(stage, roa2.stages)
                core.print_with_time("Match has started on stage:", payload['stage'])
            else:
                core.print_with_time("Match has started!")
            time.sleep(10) # wait for the game to start
        else:
            core.print_with_time("Match has started!")
    return

def detect_game_end(payload:dict, img, scale_x:float, scale_y:float):

    target_color = (0, 0, 0)  #(black letterbox that shows up when game ends)
    deviation = 0.05
    if (core.get_color_match_in_region(img, (0, int(5 * scale_y), int(1920 * scale_x), int(10 + 1 * scale_y)), target_color, deviation) >= 0.9
    and core.get_color_match_in_region(img, (0, int(1075 * scale_y), int(1920 * scale_x), int(10 + 1 * scale_y)), target_color, deviation) >= 0.9):
        core.print_with_time("Game end detected")
        region = (int(540 * scale_x), int(825 * scale_y), int(731 * scale_x), int(175 * scale_y))
        if (process_game_end_data(payload, img, scale_y, region)):
            payload['state'] = "game_end"
            if payload['state'] != previous_states[-1]:
                previous_states.append(payload['state'])

def unstick_result(data):
    result = []
    for item in data:
        if len(item) > 1 and item.startswith('0'):
            result.append('0')
            result.append(item[1:])
        elif len(item) > 4:
            result.append(item[0])
            result.append(item[1:])
        else:
            result.append(item)
    return result
    
def process_game_end_data(payload:dict, img, scale_y:int, region: tuple[int, int, int, int]):
    x, y, w, h = region
    img = np.array(img)
    img = img[int(y):int(y+h), int(x):int(x+w)]
    img = core.stitch_text_regions(img, int(56 * scale_y), (255,255,255), margin=10, deviation=0.2)
    if not len(img) or not img.any(): 
        core.print_with_time("Could not read game end data. Trying again...")
        return False
    read_data = core.read_text(img, colored=False, contrast=2, allowlist="DO0I12345678A9x%")

    # what this text will extract are for excerpts of numbers. the first is the number of stocks for player 1, the second is the damage received by player 1, the third is the number of stocks for player 2, and the fourth is the damage received by player 2.
    if read_data:
        # this is to separa the stock count from the damage count as easyocr usually reads it as one big string
        # example: '214%084%'
        read_data = ' '.join(read_data)
        read_data = read_data.replace('O','0').replace('D','0').replace('I','1').replace('A','9')
        read_data = re.split(r"[ x%]", read_data)
        read_data = [data for data in read_data if data]
        print(read_data)
        result = []
        for i, data in enumerate(read_data):
            if not data.isdigit(): del read_data[i]
            if len(result) >= 4: break
            result.extend([data[0], data[1:]]) if len(data) > 1 and len(read_data[i-1]) > 1  else result.append(data)

        print(result)
        if len(result) == 4:
            stocks1, damage1, stocks2, damage2 = int(result[0]), int(result[1]), int(result[2]), int(result[3])
            payload['players'][0]['stocks'] = stocks1
            payload['players'][1]['stocks'] = stocks2
            payload['players'][0]['damage'] = damage1
            payload['players'][1]['damage'] = damage2
            
            #validate stock counts
            if not (0 <= stocks1 <= 3) and stocks2 > 0: stocks1, stocks2 = 0, 1
            if not (0 <= stocks2 <= 3) and stocks1 > 0: stocks2, stocks1 = 0, 1


            core.print_with_time(f"{payload['players'][0]['name']}'s end state: {stocks1} stocks at {damage1}%")
            core.print_with_time(f"{payload['players'][1]['name']}'s end state: {stocks2} stocks at {damage2}%")
            
            #print out the winner of the match based on two conditions: if one player has 0 stcks the other player wins. if both players have the same amount of stocks, the player with the least amount of damage wins.
            if stocks1 == 0 or stocks1 < stocks2:
                core.print_with_time(f"{payload['players'][1]['name']} wins!")
            elif stocks2 == 0 or stocks2 < stocks1:
                core.print_with_time(f"{payload['players'][0]['name']} wins!")
            elif stocks1 == stocks2:
                # in this case, we need to be more scrumptuous with the damage values as they can be read wrong
                if damage1 < damage2:
                    core.print_with_time(f"{payload['players'][0]['name']} wins!")
                elif damage1 > damage2:
                    core.print_with_time(f"{payload['players'][1]['name']} wins!")
            return True
    core.print_with_time("Could not read game end data. Trying again...")
    return False

states_to_functions = {
    None: [detect_character_select_screen],
    "character_select": [detect_stage_select_screen],
    "stage_select": [detect_characters_and_tags, detect_character_select_screen, detect_versus_screen],
    "in_game": [detect_character_select_screen, detect_game_end],
    "game_end": [detect_character_select_screen, detect_stage_select_screen],
}