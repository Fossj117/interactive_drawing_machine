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
import random

from art import ArtproofDrawing, intialize_pygame
import stream

plot_lock = threading.Lock()
plotfile = None
def plot_thread(plotter_port):
    global plotfile, plot_lock
    plot = stream.open_port_and_home(plotter_port, verbose=False)
    while True:
        plot_lock.acquire()
        f = plotfile
        plot_lock.release()
        if f:
            os.system("vpype read {filename} layout -m .5in -v top 5x7in write {filename}".format(filename=f)) #format the created svg to a 5x7 layout
            os.system("vpype read party_signature.svg layout -m .5in -v bottom 5x7in read {filename} write {filename}".format(filename=f)) #add the signature svg
            os.system("vpype -c test_party_config.cfg read {filename} linemerge linesort gwrite -p test_party_config {filename}.gcode".format(filename=f)) #create gcode from merged file
            stream.stream_gcode(plot, open(f+".gcode"), verbose=False)
            plot_lock.acquire()
            plotfile = None
            plot_lock.release()
        else:
            time.sleep(0.1)

def initialize_GPIO(input_pin):
    GPIO.setwarnings(False) # Ignore warning for now
    #GPIO.setmode(GPIO.BOARD) # Use physical pin numbering
    GPIO.setup(input_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) # Set pin 10 to be an input pin and set initial value to be pulled low (off)

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

def main(pots, screen, pixels, drawing, input_pin): 
    global plotfile, plot_lock
    '''
    This what runs the event loop

    Args:
        pots: a list of AnalogInput objects (potentiometers)
        screen: the pygame screen object
        pixels: a list of NeoPixel objects (LEDs)
        drawing: the art object
        input_pin: the input pin for print button
    '''

    BACKGROUND_COLOR = pygame.Color('white')
    FPS = 5

    seed = 0
    random.seed(seed)

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
            text = font.render("BUSY Ploting: %s"%(plot_name), True, (0, 0, 0), (128, 128, 0))
        else:
            text = font.render("Ready!", True, (255, 255, 255), (0, 128, 0))
        textRect = text.get_rect()
        textRect.center = (300,900)
        screen.blit(text, textRect)

        #READ INPUTS
        values = [pot.value for pot in pots]
        if values != curr_values:
            drawing.update(values)
            curr_values = values

        #TODO show input hash

        #GENERATE ART
        drawing.draw()
        pygame.display.flip()
        
        if (not plot_busy) and GPIO.input(input_pin) == GPIO.HIGH: #PRINTING
            seed += 1
            random.seed(seed)
            fname = "drawing_{seed}.svg".format(seed=seed)
            drawing.to_svg(fname)
            last_printed_values = values
            plot_lock.acquire()
            plotfile = fname
            plot_lock.release()

        #TODO handle save button
        #if GPIO.input(input_pin) == GPIO.HIGH: # press again to go back


        # UPDATE LEDS
        for i, pixel in enumerate(pixels):
            pixel.fill(
                ( 0, 0, min(255, max(potentiometer_to_color(values[i]), 0)))
                )

        #UPDATE SCREEN
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
        
        clock.tick(FPS)


if __name__ == "__main__":

    POT_ADDRESSES = [0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39] # the addresses of the potentiometers
    SCREEN_DIMENSIONS = (600,1024)
    DRAW_DIMENSIONS = (600,600)
    INPUT_PIN = 18
    PLOTTER_PORT = "/dev/ttyUSB0"

    # initialization
    screen = intialize_pygame(SCREEN_DIMENSIONS) #reference to the pygame screen object
    sliders, pots = initialize_pots(POT_ADDRESSES) # references to the potentiometers
    pixels = initialize_pixels(sliders) # references to the LEDs
    initialize_GPIO(INPUT_PIN)
    plotter_thread = threading.Thread(target=plot_thread, args=(PLOTTER_PORT,))
    plotter_thread.start()

    drawing = ArtproofDrawing(dimensions=DRAW_DIMENSIONS, values=[pot.value for pot in pots], screen = screen) # the art object

    # main loop
    main(pots = pots, screen = screen, pixels=pixels, drawing=drawing, input_pin=INPUT_PIN)
