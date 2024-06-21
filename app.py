import time
import threading
import subprocess
from flask import Flask, render_template, request, jsonify
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
from rpi_ws281x import PixelStrip, Color
import adafruit_dht
import board
from RPLCD.i2c import CharLCD


app = Flask(__name__)

# GPIO pin configuration
garage_pin = 12
windows_pin = 18
door_pin = 13
button_pin = 21
buzzer_pin = 17
raindrop_pin = 23
pir_pin = 27
fan_pin = 16
flame_pin = 20
yellow_leds = 5

# Set up GPIO mode
GPIO.setmode(GPIO.BCM)
GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(raindrop_pin, GPIO.IN)
GPIO.setup(pir_pin, GPIO.IN)
GPIO.setup(flame_pin, GPIO.IN)
GPIO.setup(buzzer_pin, GPIO.OUT)
GPIO.setup(garage_pin, GPIO.OUT)
GPIO.setup(windows_pin, GPIO.OUT)
GPIO.setup(door_pin, GPIO.OUT)
GPIO.setup(fan_pin, GPIO.OUT)
GPIO.setup(yellow_leds, GPIO.OUT)


# LED strip configuration:
LED_COUNT = 8           # Number of LED pixels.
LED_PIN = 19            # GPIO pin connected to the pixels (18 uses PWM!).
LED_FREQ_HZ = 800000    # LED signal frequency in hertz (usually 800kHz)
LED_DMA = 10            # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 50    # Set to 0 for darkest and 255 for brightest
LED_INVERT = False      # Invert the signal (when using NPN transistor level shift)
LED_CHANNEL = 1         # Set to '1' for GPIOs 13, 19, 41, 45 or 53

# LCD config
I2C_ADDR = 0x27
lcd = CharLCD('PCF8574', I2C_ADDR, cols=16, rows=2)

# Definire chr/symb speciale, matrix 5x8
degree = [
    0b00110,
    0b01001,
    0b01001,
    0b00110,
    0b00000,
    0b00000,
    0b00000,
    0b00000
]

fan_symbol = [
    0b01010,
    0b10101,
    0b01110,
    0b00100,
    0b00100,
    0b01110,
    0b10101,
    0b01010
]

# Inregistrare chr la locatii (intre 0-7)
lcd.create_char(0, degree)
lcd.create_char(1, fan_symbol)

# Initializare RFID reader
reader = SimpleMFRC522()

# Initiere DTH sensor
dht_device = adafruit_dht.DHT11(board.D6)  # GPIO6

# Creare neopixel obiect si initializare librarie
strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()

# Global variables
button_pressed = False
image_counter = 1
raindrop_state = False
authorized_ids = [346825954548,122799991249]
alarm = False

def set_angle(angle,servo_pin):
    # Initialize PWM
    pwm = GPIO.PWM(servo_pin, 50)  # 50Hz
    pwm.start(2.5)  # Initial position

    duty = angle / 18 + 2.5
    pwm.ChangeDutyCycle(duty)
    time.sleep(1)
    pwm.ChangeDutyCycle(0)

    # Stop PWM
    pwm.stop()

def monitor_button():
    global button_pressed
    print("Button monitoring started")  # Debug message
    while True:
        if GPIO.input(button_pin) == GPIO.LOW:
            if not button_pressed:
                buzzer_on()
                print("Button pressed - Buzzer ON")
                capture_image()
                button_pressed = True
        else:
            if button_pressed:
                buzzer_off()
                print("Button released - Buzzer OFF")
                button_pressed = False
        time.sleep(0.1)

def monitor_raindrop():
    global raindrop_state
    while True:
        if GPIO.input(raindrop_pin) == GPIO.LOW:
            if not raindrop_state:
                print("Rain detected")
                set_angle(0,windows_pin)
                raindrop_state = True
        else:
            if raindrop_state:
                print("Ploaie terminata")
                # doar daca se dorecte deschiderea windows dupa ce a trecut ploaia
                # set_angle(180,windows_pin)
                raindrop_state = False
        time.sleep(5)

def capture_image():
    global image_counter
    file_path = f"/home/admin/Desktop/image{image_counter}.jpg"
    bash_command = f"libcamera-still -o {file_path}"
    try:
        subprocess.run(bash_command, shell=True, check=True)
        print(f"Image saved as {file_path}")
        image_counter += 1
    except subprocess.CalledProcessError as e:
        print(f"Failed to capture image: {e}")

def monitor_rfid():
    while True:
            id, text = reader.read_no_block()
            if id is not None:
                print("ID: %s\nText: %s" % (id, text))
                if id in authorized_ids:
                    print("Bun venit acasa!")
                    set_angle(180,door_pin)
                    time.sleep(5)
                    set_angle(0,door_pin)
                else:
                    print("Access neautorizat!!!")
            time.sleep(1)

def monitor_pir():
        while not alarm:
            if GPIO.input(pir_pin):
                print("Motion Detected!")
                turn_on_ledstrip()
                time.sleep(10)
                if alarm == False:
                    turn_off_ledstrip()

        time.sleep(1)

def monitor_flame():
    while True:
        time_counter = 5
        while not GPIO.input(flame_pin):
            if time_counter == 0:
                if alarm == False:
                    alarm_on()
                break  # reincepe monitorizarea
            time.sleep(1)
            time_counter -= 1
        time.sleep(0.1)

def alarm_on():
    global alarm
    alarm = True
    print("Alarma pornita!")
    buzzer_on()
    alarma_lights()
    set_angle(180,door_pin)
    set_angle(180,garage_pin)

def alarm_off():
    global alarm
    alarm = False
    print("Alarma oprita!")
    buzzer_off()
    turn_off_ledstrip()
    set_angle(0,door_pin)
    set_angle(0,garage_pin)

    

def monitor_dth():
    prev_temperature = 0
    prev_humidity = 0
    while True:
        try:
            # Read data from the sensor
            temperature = dht_device.temperature
            humidity = dht_device.humidity
            
            # Check if the reading was successful
            if humidity != None and temperature != None:
                if int(temperature) != int(prev_temperature) or int(prev_humidity) != int(humidity):
                    print(f'Temperature: {temperature:.1f}  Humidity: {humidity:.1f}%')
                    time.sleep(1)
                    lcd.clear()
                    lcd.write_string(f'Temp:   {temperature}\x00C')
                    lcd.crlf()
                    lcd.write_string(f'Umedit: {humidity}%')
                    prev_temperature = temperature
                    prev_humidity = humidity

                if temperature >= 30:
                    fan_on()
                else:
                    fan_off()
            else:
                print('Failed to read from DHT11 sensor')
        except RuntimeError as error:
            # Errors happen fairly often, DHT's are hard to read, just keep going
            print(error.args[0])
        except Exception as error:
            dht_device.exit()
            raise error
        # Wait 2 seconds before the next reading
        time.sleep(2)

# Curata LED stripul / stinge luminile
def turn_off_ledstrip():
    """Turn off all pixels."""
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()
    time.sleep(3)

def turn_on_ledstrip():
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(100, 50, 255))
    strip.show()

def alarma_lights():
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(255, 0, 0))
    strip.show()
   

def fan_on():
    GPIO.output(fan_pin, GPIO.HIGH)
    lcd.cursor_pos = (0, 15)
    lcd.write_string('\x01')

def fan_off():
    GPIO.output(fan_pin, GPIO.LOW)
    lcd.cursor_pos = (0, 15)
    lcd.write_string(' ')

def buzzer_on():
    GPIO.output(buzzer_pin, GPIO.LOW)

def buzzer_off():
    GPIO.output(buzzer_pin, GPIO.HIGH)

def leds_kitchen_on():
    GPIO.output(yellow_leds, GPIO.HIGH)

def leds_kitchen_off():
    GPIO.output(yellow_leds, GPIO.LOW)
    


# Incepe monitorizare in threaduri separate
button_thread = threading.Thread(target=monitor_button)
button_thread.daemon = True
button_thread.start()

raindrop_thread = threading.Thread(target=monitor_raindrop)
raindrop_thread.daemon = True
raindrop_thread.start()

rfid_thread = threading.Thread(target=monitor_rfid)
rfid_thread.daemon = True
rfid_thread.start()

pir_thread = threading.Thread(target=monitor_pir)
pir_thread.daemon = True
pir_thread.start()

dth_thread = threading.Thread(target=monitor_dth)
dth_thread.daemon = True
dth_thread.start()

flame_thread = threading.Thread(target=monitor_flame)
flame_thread.daemon = True
flame_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/control', methods=['POST'])
def control_servo():
    data = request.get_json()
    command = data.get('command', '').lower()
    
    if not command:
        return 'No command received', 400

    try:
        print(f"Command received: {command}")
        if "open the garage" in command:
            set_angle(180,garage_pin)
        elif "close the garage" in command:
            set_angle(0, garage_pin)
        elif "open the windows" in command:
            set_angle(180, windows_pin)
        elif "close the windows" in command:
            set_angle(0, windows_pin)
        elif "open the door" in command:
            set_angle(180, door_pin)
        elif "close the door" in command:
            set_angle(0, door_pin)
        elif "alarm off" in command:
            alarm_off()
        elif "lights on in the kitchen" in command:
            leds_kitchen_on()
        elif "lights off in the kitchen" in command:
            leds_kitchen_off()
        elif "lights on" in command:
            turn_on_ledstrip()
        elif "lights off" in command:
            turn_off_ledstrip()
        elif "fan on" in command:
            fan_on()
        elif "fan off" in command:
            fan_off()
        elif "buzzer on" in command:
            buzzer_on()
        elif "buzzer off" in command:
            buzzer_off()
        else:
            return 'Comand? necunoscut?', 400
        return 'Command executed'
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
       turn_off_ledstrip()
       GPIO.cleanup()







def monitor_dth():
    prev_temperature = 0
    prev_humidity = 0
    while True:
        try:
            temperature = dht_device.temperature
            humidity = dht_device.humidity
            if humidity is not None and temperature is not None:
                if int(temperature) != int(prev_temperature) or int(prev_humidity) != int(humidity):
                    print(f'Temperature: {temperature:.1f}  Humidity: {humidity:.1f}%')
                    time.sleep(1)
                    lcd.clear()
                    lcd.write_string(f'Temp:   {temperature}\x00C')
                    lcd.crlf()
                    lcd.write_string(f'Umedit: {humidity}%')
                    prev_temperature = temperature
                    prev_humidity = humidity
                if temperature >= 30:
                    fan_on()
                else:
                    fan_off()
            else:
                print('Failed to read from DHT11 sensor')
        except RuntimeError as error:
            print(error.args[0])
        except Exception as error:
            dht_device.exit()
            raise error
        time.sleep(2)




