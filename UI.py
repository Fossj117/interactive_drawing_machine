#! /usr/bin/env python3
# This file has the user interface code

import board
import RPi.GPIO as GPIO
import os
import threading
import time
from adafruit_seesaw.seesaw import Seesaw 
from adafruit_seesaw.analoginput import AnalogInput
from adafruit_seesaw import neopixel

import pygame 

from art import ArtproofDrawing, intialize_pygame
import stream

plot_lock = threading.Lock()
plotfile = None
def plot_thread(plotter_port):
    global plotfile, plot_lock
    if plotter_port:
        plot = stream.open_port_and_home(plotter_port, verbose=False)
    while True:
        plot_lock.acquire()
        f = plotfile
        plot_lock.release()
        if f:
            if plotter_port:
                stream.stream_gcode(plot, open(f), verbose=False)
            else:
                #fake serial sending by just sleeping
                time.sleep(20)
            plot_lock.acquire()
            plotfile = None
            plot_lock.release()
        else:
            time.sleep(0.1)

def initialize_GPIO(btnL_pin, btnR_pin):
    GPIO.setwarnings(False) # Ignore warning for now
    #GPIO.setmode(GPIO.BOARD) # Use physical pin numbering
    GPIO.setup(btnR_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) # Set pin 10 to be an input pin and set initial value to be pulled low (off)
    GPIO.setup(btnL_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) # Set pin 10 to be an input pin and set initial value to be pulled low (off)

def initialize_pots(addresses):
    '''
    This sets up the potentiometers
    '''

    i2c = board.I2C()
    sliders = [Seesaw(i2c, addr) for addr in addresses]

    return sliders, [AnalogInput(slider, 18) for slider in sliders]

def initialize_pixels(pots): 
    '''
    This sets up the LEDs
    '''
    return [neopixel.NeoPixel(pot, 14, 4, pixel_order=neopixel.RGB) for pot in pots]

def potentiometer_to_color(value): 
    return value/1023 * 255

def main(pots, screen, pixels, drawing, btnL_pin, btnR_pin, seedstart=0):
    global plotfile, plot_lock
    '''
    This what runs the event loop

    Args:
        pots: a list of AnalogInput objects (potentiometers)
        screen: the pygame screen object
        pixels: a list of NeoPixel objects (LEDs)
        drawing: the art object
        btnL_pin: the input pin for save button
        btnR_pinL the input pin for print button
    '''

    BACKGROUND_COLOR = pygame.Color('white')
    FPS = 5

    seed = seedstart

    curr_values = [pot.value for pot in pots]
    last_printed_values = curr_values
    drawing.update(curr_values)

    clock = pygame.time.Clock()

    current_state = "DRAWING" # can be DRAWING or MESSAGE

    font = pygame.font.Font('freesansbold.ttf', 32)

    while True:
        plot_lock.acquire()
        plot_busy = (plotfile != None)
        plot_name = plotfile
        plot_lock.release()

        screen.fill(BACKGROUND_COLOR)

        if plot_busy:
            #text = font.render("Saved for printing! Number:{seed}".format(seed=seed), True, (0, 0, 0), (255, 255, 255))
            text = font.render("BUSY Plotting: %s"%(plot_name), True, (0, 0, 0), (128, 128, 0))
        else:
            text = font.render("Ready!", True, (255, 255, 255), (0, 128, 0))
        textRect = text.get_rect()
        textRect.center = (300,900)
        screen.blit(text, textRect)

        #READ INPUTS
        values = [pot.value for pot in pots]
        if values != curr_values:
            drawing.update(values, seed)
            curr_values = values

        #TODO show input hash

        #GENERATE ART
        drawing.draw()
        pygame.display.flip()
        
        if (not plot_busy) and GPIO.input(btnR_pin) == GPIO.HIGH: #PRINTING
            fname = "drawing_{seed}".format(seed=seed)
            fname_svg = fname+".svg"
            fname_gcode = fname+".gcode"

            #put up processing message
            screen.fill((120,128,0))
            text = font.render("Processing: %s..."%(fname), True, (0, 0, 0), (128, 128, 0))
            textRect = text.get_rect()
            textRect.center = (300,512)
            screen.blit(text, textRect)
            pygame.display.flip()

            #block while generating GCODE
            drawing.to_svg(fname_svg)
            os.system("vpype read {filename} scaleto 4.5in 4.5in layout -m .5in -v top 5.5x7in linesimplify -t 0.05mm write {filename}".format(filename=fname_svg)) #format the created svg to a 5x7 layout
            os.system("vpype read party_signature.svg scaleto 4.05in 1.05in layout -h center -v bottom 5.5x6.5in read {filename} write {filename}".format(filename=fname_svg)) #add the signature svg
            os.system("vpype -c test_party_config.cfg read {svg} linemerge linesort gwrite -p test_party_config {gcode}".format(svg=fname_svg, gcode=fname_gcode)) #create gcode from merged file

            #signal to serial thread new gcode is available
            plot_lock.acquire()
            plotfile = fname_gcode
            plot_lock.release()

            seed += 1
            last_printed_values = values

        #SAVE BUTTON - essentially the same as GENERATE ART but can be done while busy as well and does not signal to serial
        if GPIO.input(btnL_pin) == GPIO.HIGH: # press again to go back
            fname = "drawing_{seed}".format(seed=seed)
            fname_svg = fname+".svg"
            fname_gcode = fname+".gcode"

            #put up saving message
            screen.fill((120,128,0))
            text = font.render("Saving: %s..."%(fname), True, (0, 0, 0), (128, 128, 0))
            textRect = text.get_rect()
            textRect.center = (300,512)
            screen.blit(text, textRect)
            pygame.display.flip()

            #block while generating SVG (and gcode as a time delay for legibility
            drawing.to_svg(fname_svg)
            os.system("vpype read {filename} scaleto 4.5in 4.5in layout -m .5in -v top 5.5x7in linesimplify -t 0.05mm write {filename}".format(filename=fname_svg)) #format the created svg to a 5x7 layout
            os.system("vpype read party_signature.svg scaleto 4.05in 1.05in layout -h center -v bottom 5.5x6.5in read {filename} write {filename}".format(filename=fname_svg)) #add the signature svg
            os.system("vpype -c test_party_config.cfg read {svg} linemerge linesort gwrite -p test_party_config {gcode}".format(svg=fname_svg, gcode=fname_gcode)) #create gcode from merged file
 
            seed += 1
            last_printed_values = values

        # UPDATE LEDS
        for i, pixel in enumerate(pixels):
            pixel.fill(
                (0, 0, min(255, max(potentiometer_to_color(values[i]), 0)))
                )

        #UPDATE SCREEN
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
        
        clock.tick(FPS)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="run the Pl0tb0t")
    parser.add_argument('-n', '--no-plotter', default=False, action="store_true", dest="noplotter", help="don't actually talk to Pl0tb0t, just fake plotting with a timeer")
    parser.add_argument('-p', '--port', default='/dev/ttyUSB0', action="store", help="use PORT for Pl0tb0t connection", metavar='PORT')
    parser.add_argument('-s', '--seed', default=0, action="store", type=int, help="set seed value start position to avoid file overwrites")
    args = parser.parse_args()


    POT_ADDRESSES = [0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39] # the addresses of the potentiometers
    SCREEN_DIMENSIONS = (600,1024)
    DRAW_DIMENSIONS = (600,600)
    INPUT1_PIN = 18
    INPUT2_PIN = 17

    # initialization
    screen = intialize_pygame(SCREEN_DIMENSIONS) #reference to the pygame screen object
    sliders, pots = initialize_pots(POT_ADDRESSES) # references to the potentiometers
    pixels = initialize_pixels(sliders) # references to the LEDs
    initialize_GPIO(INPUT1_PIN, INPUT2_PIN)
    port = args.port if not args.noplotter else None
    plotter_thread = threading.Thread(target=plot_thread, args=(port,), daemon=True)
    plotter_thread.start()

    drawing = ArtproofDrawing(dimensions=DRAW_DIMENSIONS, values=[pot.value for pot in pots], screen = screen) # the art object

    # main loop
    main(pots=pots, screen=screen, pixels=pixels, drawing=drawing, btnL_pin=INPUT1_PIN, btnR_pin=INPUT2_PIN, seedstart=args.seed)
