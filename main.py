import chess
import random
import mss
import cv2
import pyautogui
import sys
import numpy as np
from PIL import Image
from chessboard_finder import get_chessboard_corners
from recognize import predict_chessboard

#TODO: fix datarace type issues.. either slow down the loop, or ensure we only move when fen changes
#this would allow us to use engine moves sometimes if we want, since it would fix the premove issues

def main(): #sys args?

    #region helpers
    companion = chess.Board() #logical representation of the game being player to assist with generating legal moves
    move_count = 0 #helper to make sure we stay on pace in testing
    we_are_white = None #true if we are white, else false
    current_board_state_screenshot = None #reference to current board state for passing to predict_board
    current_board_fen = None #track the fen for the current board state
    found_board = False
    sct = mss.mss()
    #basic location and dimensions of board
    top_left = None
    cell_size = None
    w, h = pyautogui.size()
    monitor = {
        "top": 0,
        "left": 0,
        "width": w,
        "height": h,
    }
    #endregion helpers

    #finding the board location on startup -- chessboard should be lichess and on screen when program runs
    while found_board == False:
        ss = sct.grab(monitor=monitor)
        arr_ss = np.array(ss)
        gray = cv2.cvtColor(np.array(ss), cv2.COLOR_BGR2GRAY)
        corn, err = get_chessboard_corners(gray, detect_corners=True) #corn: x1, y1, x2, y2 : TL | BR

        if corn is not None:
            y_start = corn[1]
            y_end = corn[3]
            x_start = corn[0]
            x_end = corn[2]
            current_board_state_screenshot = arr_ss[y_start:y_end, x_start:x_end].copy() #cropped grayscale of the board from fullscreen screenshot
            
            #populate globals for board positoin
            top_left = [x_start, y_start]
            bottom_right = [x_end, y_end]
            width = x_end - x_start
            height = y_end - y_start
            cell_size = ((width//8),(height//8))
            buffer_x = cell_size[0] // 2
            buffer_y = cell_size[1] // 2
            
            found_board = True
        
    print("DEBUG: found board")

    #generate fen of starting position, find our color for later logic on when to generate fen
    img_data = Image.fromarray(current_board_state_screenshot).convert('RGB')
    img_data = img_data.resize([256, 256], Image.BILINEAR)
    fen, predictions = predict_chessboard(img_data)

    #if the first character in the fen array is uppercase letter, we are black
    if fen[0].isupper():
        we_are_white = False
    else:
        we_are_white = True

    #set the current board fen
    current_board_fen = fen

    #main event loop
    while True: #later while chess.game is not over

        #find our legal moves in the position
        r_move = str(get_random_legal_move(current_board_fen, companion, we_are_white))

        #calculate the screen postions required to execute r_move
        to_from = convert_uci_to_pixel_location(r_move, cell_size, top_left, we_are_white)

        #attempt to make a move, regardless if it is actually our move or not
        attempt_to_move(to_from[0], to_from[1])

        #whenever we detect a move has happened, try to resolve the fen for the position
        invalid_fen = True
        while invalid_fen == True:

            #try to resolve the fen of the position with high confidence
            try:
                img_data = Image.fromarray(current_board_state_screenshot).convert('RGB')
                img_data = img_data.resize([256, 256], Image.BILINEAR)
                fen, predictions = predict_chessboard(img_data)
                for confidence in predictions:
                    if confidence[1] > 0.999: 
                        continue
                    else: 
                        print("DEBUG: Low Confidence")
                        raise Exception('Low Confidence') #likely in animation where piece is overlapping squares
                        # break

                #update the fen now once confident
                current_board_fen = fen       
                invalid_fen = False
            
            #take a new screenshot and try again, must have been in animation
            except:
                ss = sct.grab(monitor=monitor)
                arr_ss = np.array(ss)
                current_board_state_screenshot = arr_ss[y_start:y_end, x_start:x_end].copy()
                
        #get a new screenshot and repeat the loop
        ss = sct.grab(monitor=monitor)
        arr_ss = np.array(ss)
        current_board_state_screenshot = arr_ss[y_start:y_end, x_start:x_end].copy()

        #game over checks
        if companion.legal_moves.count() == 0: #if we have no legal moves
            print("Game is over... exiting")
            sys.exit()

        if companion.is_game_over() == True: #if game state == game over state
            print("Game is over... exiting")
            sys.exit()

#TODO: move these to another file
#generate the legal moves and the position, choose one at random
def get_random_legal_move(fenny, boardy: chess.Board, we_are_white: bool) -> str:
    if we_are_white:
        boardy.turn = chess.WHITE
    else:
        boardy.turn = chess.BLACK
        fenny = fenny[::-1] #TODO: EXTREMELY IMPORTANT, THE LIB OUTPUTS FENS IN REVERSE COMPARED TO CHESS ENGINE

    boardy.set_board_fen(fenny)
    legals = list(boardy.generate_legal_moves())
    r = random.randint(0, len(legals) - 1)
    return legals[r]
    
#attempt to make a move, regardless if it is actually our move or not
def attempt_to_move(start: tuple, end: tuple) -> None: #consider bool response
    pyautogui.moveTo(start[0], start[1]) #set our cursor on the location start
    pyautogui.dragTo(end[0], end[1]) #drag lmb to point x, y from our current position

#takes in a move uci from chess library (e.g. e2e4) and translates it to screen coordinates for pyautogui to click
#TODO: handle edge cases: e1g1 (white short castling); e7e8q (for promotion)
#TODO: clean and refactor because this is gross
def convert_uci_to_pixel_location(move: str, cell_size: tuple, top_left: tuple, we_are_white: bool) -> tuple:
    #calculate buffers
    buffer_x = cell_size[0] // 2
    buffer_y = cell_size[1] // 2

    #split string into 4 parts
    letter1 = move[:1] #e
    number1 = int(move[1:2]) #2
    letter2 = move[2:3] #e
    number2 = int(move[3:4]) #4

    #NOTE: the moves need to be flipped if we are black in terms of what is legal, but the pixel math works
    if we_are_white:
        #temp flipping numbers 
        number1 = 9 - number1
        number2 = 9 - number2

        #convert letters to int grid postions (0 indexed)
        letter1_int = ord(letter1) - 97
        number1_reduced = number1 - 1
        letter2_int = ord(letter2) - 97
        number2_reduced = number2 - 1

    else: #we are black
        #temp flipping letters
        switch = {
            "a":"h",
            "b":"g",
            "c":"f",
            "d":"e",
            "e":"d",
            "f":"c",
            "g":"b",
            "h":"a"
        }
        letter1 = switch[letter1]
        letter2 = switch[letter2]
        
        #convert letters to int grid postions (0 indexed)
        letter1_int = ord(letter1) - 97
        number1_reduced = number1 - 1
        letter2_int = ord(letter2) - 97
        number2_reduced = number2 - 1

    #calculate logical pixel location using cell size
    _x1 = letter1_int * cell_size[0] + top_left[0] + buffer_x
    _y1 = number1_reduced * cell_size[1] + top_left[1] + buffer_y
    _x2 = letter2_int * cell_size[0] + top_left[0] + buffer_x
    _y2 = number2_reduced * cell_size[1] + top_left[1] + buffer_y

    return ((_x1, _y1), (_x2, _y2))

if __name__ == "__main__":
    main()
    