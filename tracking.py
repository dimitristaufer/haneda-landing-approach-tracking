# pylint: disable=W,C,R
from time import sleep
import json
import re
import os
import hashlib
import signal
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import WebDriverException

DRIVER_PATH = ''
options = webdriver.ChromeOptions()
options.add_argument("no-sandbox")
options.add_argument('--headless')
options.add_argument('--disable-gpu')
caps = DesiredCapabilities().CHROME
#caps["pageLoadStrategy"] = "normal"  #  complete
caps["pageLoadStrategy"] = "eager"  #  interactive
#caps["pageLoadStrategy"] = "none"
driver = webdriver.Chrome(desired_capabilities=caps, executable_path=DRIVER_PATH, options=options)

def handlesigint(signum, frame):
    global driver
    driver.close()
    exit(1)

def login():
    driver.get('https://ja.flightaware.com/live/airport/RJTT/arrivals')
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located(
            (By.XPATH, '//*[@id="loginForm"]/div[1]/input[1]')))
    except TimeoutException:
        print("Loading took too much time!")

    driver.find_element_by_xpath(
        '//*[@id="loginForm"]/div[1]/input[1]').send_keys("email-address")
    driver.find_element_by_xpath(
        '//*[@id="loginForm"]/div[1]/input[2]').send_keys("password")
    driver.find_element_by_xpath('//*[@id="loginButton"]').click()

    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located(
            (By.XPATH, '//*[@id="mainBody"]/div[1]/table[2]/tbody/tr/td[1]/table/thead/tr[1]/th')))
        print("Logged in!")
    except TimeoutException:
        print("Loading took too much time!")


def getDirection(flightURL):
    try:
        driver.get(flightURL+'/tracklog')
    except WebDriverException:
        print("Some other exception (1). Restarting..")
        return "abort"
    
    try:
        WebDriverWait(driver, 6).until(EC.presence_of_element_located(
            (By.XPATH, '//*[@id="mainBody"]/div[1]/div[4]/div/table/tbody')))
        #print("Page is ready!")
    except TimeoutException:
        print("Flight was cancelled. Skipping..")
        return "flight was cancelled"

    table = driver.find_element_by_xpath(
        '//*[@id="mainBody"]/div[1]/div[4]/div/table/tbody')
    # skip first 10 lines (take-off)
    for row in reversed(table.find_elements_by_css_selector('tr')[10:]):
        cells = row.find_elements_by_tag_name('td')
        if len(cells) >= 7:
            altitude = 1000
            if re.sub(",", "", cells[6].text).isdigit():
                altitude = int(re.sub(",", "", cells[6].text))
            course = re.findall(r'\d+', cells[3].text)[0]
            if altitude > 1000:
                return course
            #print("Altitude: " + str(altitude) + ", Course: " + str(course))


def getFlights(flightName):
    try:
        driver.get('https://flightaware.com/live/flight/' +
                   str(flightName)+'/history')
    except Exception:
        print("Some other exception (2). Restarting..")
        return None

    try:
        WebDriverWait(driver, 6).until(EC.presence_of_element_located(
            (By.XPATH, '//*[@id="mainBody"]/div[1]/table[2]/tbody/tr/td/table[2]/tbody')))
    except TimeoutException:
        print("Loading took too much time!")
        print("Probably private flight. Skipping..")
        return []

    table = driver.find_element_by_xpath(
        '//*[@id="mainBody"]/div[1]/table[2]/tbody/tr/td/table[2]/tbody')
    i = 31
    flights = []
    # skip first, because in future
    for row in table.find_elements_by_css_selector('tr')[2:]:
        flight = {}
        valid = True
        for column, cell in enumerate(row.find_elements_by_tag_name('td')):
            if 'live/flight/' in cell.get_attribute('innerHTML'):  # Date Link
                # print(cell.text)
                flightURL = cell.find_elements_by_tag_name(
                    'a')[0].get_attribute("href")
                flight["id"] = hashlib.sha256(str(
                    flightName+str(re.sub("DATE", "", cell.text))).encode('utf-8')).hexdigest()[:32]
                flight["name"] = flightName
                flight["date"] = str(re.sub("DATE", "", cell.text))
                flight["url"] = flightURL
            if column == 5:  # Arrival Time
                flight["time"] = str(
                    re.sub("&nbsp;", "", cell.find_elements_by_tag_name('span')[0].text))
            if column == 3:  # Destination
                if not "HND" in cell.text:
                    valid = False
        if i >= 0 and valid == True:
            flights.append(flight)
            i -= 1
    return flights

def start():
    try:
        f = open('arrivals.json')
        arrivals = json.load(f)
        numberOfArrivals = len(arrivals)
        arrivalRound = 0
        flightsProcessed = 0

        login()

        for arrival in arrivals:
            print("--- Started Flight Number " + arrival + " -")
            if os.path.isfile('processedFlightNumbers.json'):
                f = open('processedFlightNumbers.json')
                processedFlightNumbers = json.load(f)
                if arrival in processedFlightNumbers:
                    print("Already processed. Skipping..")
                    flightsProcessed += 31
                    arrivalRound += 1
                    percentDone = int((arrivalRound / numberOfArrivals) * 100)
                    print("- " + str(percentDone) + " % Done -")
                    print("- " + str(flightsProcessed) + " Flights Processed -")
                    continue
            print("sleeping..")
            sleep(5)
            flights = getFlights(arrival)
            if flights == None:
                print("Stopping previous round (2)..")
                break
            if len(flights) == 0:
                print("Continuing due to private..")
                continue
            
            for flight in flights:
                flightCopy = flight
                flightId = flightCopy["id"]
                if os.path.isfile('flightData.json'):
                    f = open('flightData.json')
                    oldFlightData = json.load(f)
                    if flightId in oldFlightData.keys():
                        print("already in there: " + flightId)
                        flightsProcessed += 1
                        continue

                flightCopy["direction"] = getDirection(flightCopy["url"])
                if flightCopy["direction"] == "flight was cancelled":
                    sleep(5)
                    continue
                if flightCopy["direction"] == "abort":
                    flights = []
                    print("Stopping previous round (1)..")
                    break
                print(flightCopy)
                flightsProcessed += 1

                del flightCopy["id"]
                flightData = {flightId: flightCopy}

                if os.path.isfile('flightData.json'):
                    f = open('flightData.json')
                    oldFlightData = json.load(f)
                    flightData.update(oldFlightData)

                with open("flightData.json", "w") as j:
                    json.dump(flightData, j, ensure_ascii=False)
            
            if len(flights) == 0:
                print("Stopping previous round (3)..")
                break

            print("- Finished Flight Number " + arrival + " ---")
            arrivalRound += 1
            percentDone = int((arrivalRound / numberOfArrivals) * 100)
            print("- " + str(percentDone) + " % Done -")
            print("- " + str(flightsProcessed) + " Flights Processed -")

            processedFlightNumbers = [arrival]
            if os.path.isfile('processedFlightNumbers.json'):
                f = open('processedFlightNumbers.json')
                processedFlightNumbersOld = json.load(f)
                processedFlightNumbers.extend(processedFlightNumbersOld)
            with open("processedFlightNumbers.json", "w") as j:
                json.dump(processedFlightNumbers, j, ensure_ascii=False)

        # between 140 and 180 degrees is flying over Tokyo

        '''
                0
        275            90
            180  x
            
        '''
        
        sleep(5)
        restart()
        
    except Exception as e:
        print(e)
        print("### Crashed, restarting...")
        restart()


def restart():
    global driver
    try:
        driver.quit()
    except Exception:
        print("Couldn't quit.")
    driver = webdriver.Chrome(desired_capabilities=caps, executable_path=DRIVER_PATH, options=options)
    sleep(5)
    start()


signal.signal(signal.SIGINT, handlesigint)
start()

'''
def getArrivals():
    
    login()

    flights = []
    i = 300

    while i > 0:
        try:
            table = driver.find_element_by_xpath('//*[@id="mainBody"]/div[1]/table[2]/tbody/tr/td[1]/table/tbody')
            for row in table.find_elements_by_css_selector('tr'):
                for cell in row.find_elements_by_tag_name('td'):
                    if 'live/flight/id' in cell.get_attribute('innerHTML'):
                        #print(cell.text)
                        flights.append(cell.text)
            i -= 1
            print(i)
            try:
                driver.find_element_by_xpath('//*[@id="mainBody"]/div[1]/table[2]/tbody/tr/td[1]/span[2]/a').click()
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, '//*[@id="mainBody"]/div[1]/table[2]/tbody/tr/td[1]/table/thead/tr[1]/th')))
                print("Loaded Table!")
                sleep(2)
            except NoSuchElementException:
                break
        except TimeoutException:
            print("Loading took too much time!")


    flights = list(set(flights)) # remove duplicates
    with open("arrivals.json", "w") as j:
        json.dump(flights, j, ensure_ascii=False)
'''
