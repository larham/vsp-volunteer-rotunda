#!/usr/bin/env python

import configparser
import datetime
import getpass
import os
import sys
import time
import re
import natsort

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from urllib3.exceptions import ReadTimeoutError

from bs4 import BeautifulSoup


USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 12_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36'
DOWNLOAD_DIR = os.path.dirname(os.path.abspath(
    __file__)) + "/opportunities/"
FAILED_LOGIN_RESULT = "/tmp/post_login_result.html"
OPPORTUNITIES_FILE_BASE = "opportunities-"
NUM_OLD_FILES_PRESERVED = 10
ERR_CODE_TIMEOUT = 33


def main():
    """
    Program for parsing opportunities data from the rotundasoftware.com web site.
    Use javascript in headless browser to login.
    Compare current opportunities against last remembered page.
    Write errors and progress output to stderr.
    Write to standard out ONLY if a change was detected.
    Save contents of opportunities page to a new file ONLY if a change was detected.
    """
    browser = get_browser()
    user, password, url = get_user_pass()
    ensureDirs()

    prev_content = get_previously_downloaded_events()

    login(browser, url, user, password)

    # why no redirect after login?
    
    # .../web-terminal/login/guildtheatre?killSession=1
    # .../web-terminal/home
    home = re.sub(r'\/login\/.*', '/home', url)
    
    try:
        browser.get(home)

        if not is_logged_in(browser):
            errprint("login unsuccessful")
            sys.exit(1)

        # .../web-terminal/full-schedules
        full_schedules = re.sub(r'\/login\/.*', '/full-schedules', url)
        browser.get(full_schedules)
        content = str(browser.page_source)

        if not 'class="tab full-schedules selected"' in content:
            # try again
            browser.get(full_schedules)
            content = str(browser.page_source)
    except ReadTimeoutError:
        errprint("fetch timed out; quitting")
        sys.exit(ERR_CODE_TIMEOUT)
            
    if not 'class="tab full-schedules selected"' in content:
        with open(FAILED_LOGIN_RESULT, 'w+') as f:
            f.write(content)
        errprint("Cannot find tab selector in content at: " + full_schedules)
        errprint("failed schedules result page is at %s" % FAILED_LOGIN_RESULT)
        sys.exit(1)

    current_events = parseRotunda(content)
    prev_events = parseRotunda(prev_content)

    # a set comparison in this direction will ignore any events in 'prev' which were expired by date
    diff = set(current_events.keys()) - set(prev_events.keys())
    if diff:
        save_page(content)
        if not prev_events:
            errprint(
                "Initial results were recorded successfully. Please run again later to compare.")
            sys.exit(0)  # first time running comparison

        print_diff([current_events[id] for id in diff])
    else:
        errprint("no change")


def print_diff(list):
    # print to stdout all changes that were found
    list.sort(key=lambda x: x['datetime'])
    for event in list:
        print(event["name"], ", ", event["datetime"], ", within date range: ", event["daterange"], ', https://secure.rotundasoftware.com%s'
              % (event['href']))


def errprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def parseRotunda(content):
    """
    This method may break if RotundaSoftware.com changes their content!!!!
    """
    if not content:
        return {}
    events = {}
    
    soup = BeautifulSoup(content, 'html.parser')
    gigs = soup.find_all('td', class_='modui-base ministry-group-view label')
    for gig in gigs:
        link = gig.find('a')
        id = link['href']
        datetime = link.get_text()
        name = gig.get_text()
        # Thu, 6:30 PM - 9:30 PM - at null(Some Band Name)
        name = re.sub(r'.*null\(', '', name)
        name = name.replace(')', '')
        
        daterange = ""
        for parent in gig.parents:
            if parent.has_attr('class'):
                # print("parent found w/ class: ", parent.get('class'))
                if parent.get('class') == ['modui-base', 'mass-group-view']:
                    # print("parent text found:  ", parent.contents)
                    soup2 = BeautifulSoup(str(parent), 'html.parser')
                    daterange = soup2.find('div', class_ = 'mass-group-label').get_text()
                    break
        events[id] = { 'href': id, 'daterange':daterange, 'datetime': datetime, 'name': name }
        
    return events

def ensureDirs():
    if not os.path.exists(DOWNLOAD_DIR):
        os.mkdir(DOWNLOAD_DIR)


def prompt_login_creds():
    user = input("Username: ")
    password = getpass.getpass("Password: ")
    url = input("URL for your organization's rotundasoftware.com site: ")
    return user, password, url


def login(browser, url, user, password):
    errprint("attempting to log in...")
    try:
        browser.get(url)
        # wait for full rendering
        submit = WebDriverWait(browser, 15).until(
            EC.presence_of_element_located((By.XPATH, "//button[@class='button']")))

        email = browser.find_element(By.NAME, "username")
        email.send_keys(user)
        passwd = browser.find_element(By.NAME, "value")
        passwd.send_keys(password)
        submit.click()
        WebDriverWait(browser, 15).until(EC.url_changes(browser.current_url))
    except TimeoutException:
        errprint("login timed out; quitting")
        sys.exit(ERR_CODE_TIMEOUT)
    errprint("url after login: %s" % browser.current_url)


def pretty_datetime():
    value = datetime.datetime.now()
    return value.strftime('%Y-%m-%dT%H-%M-%S')


def save_page(content):
    # errprint("saving page to %s" % DOWNLOAD_DIR)
    filename = DOWNLOAD_DIR + "opportunities-%s.html" % pretty_datetime()
    files = os.listdir(DOWNLOAD_DIR)
    with open(filename, 'w+') as f:
        f.write(content)

    wait4download(DOWNLOAD_DIR, 10, len(files) + 1)
    return str(content)


def wait4download(directory, timeout, nfiles=None):
    """
    Wait for downloads to finish with a specified timeout.

    Args
    ----
    directory : str
        The path to the folder where the files will be downloaded.
    timeout : int
        How many seconds to wait until timing out.
    nfiles : int, defaults to None
        If provided, also wait for the expected number of files.

    """
    seconds = 0
    dl_wait = True
    while dl_wait and seconds < timeout:
        time.sleep(1)
        dl_wait = False
        files = os.listdir(directory)
        if nfiles and len(files) != nfiles:
            dl_wait = True

        seconds += 1
    return seconds


def is_logged_in(browser):
    # a redirect to a page with a login means that you have NOT successfully logged in.
    # a page with a login has "Sign In" in text.
    content = str(browser.page_source)
    success = "Don't have an account yet?" not in content and "Full Schedules" in content
    if not success:
        with open(FAILED_LOGIN_RESULT, 'w+') as f:
            f.write(browser.page_source)
            errprint("failed login result page is at %s" % FAILED_LOGIN_RESULT)
            sys.exit(1)

    return success


def get_browser():
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('no-sandbox')
    options.add_argument('disable-dev-shm-usage')
    options.add_argument(f'user-agent={USER_AGENT}')
    
    return webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)


def get_user_pass():
    user = ""
    password = ""
    url = ""
    if len(sys.argv) > 1:
        if not os.path.exists(sys.argv[1]):
            errprint("cannot find file: %s" % sys.argv[1])
            sys.exit(1)
        config = configparser.RawConfigParser()
        config.read(sys.argv[1])
        try:
            user = config.get('Opportunities', 'username')
            password = config.get('Opportunities', 'password')
            url = config.get('Opportunities', 'url')
        except Exception:
            errprint("""
Expected file to have a header and 2 required entries like:

[Opportunities]
username=myemail@someserver.com
password=mysecretpassword
url=https://secure.rotundasoftware.com/info_with_my_organization_name
""")
            sys.exit(1)

    if user == "" or password == "" or url == "":
        user, password, url = prompt_login_creds()
    return user, password, url


def get_previously_downloaded_events():
    prev_content = None
    # filenames are sortable resulting in datetime order, ascending
    files = natsort.natsorted(os.listdir(DOWNLOAD_DIR))
    if len(files) > 0:
        last = files[-1]
        filename = DOWNLOAD_DIR + last
        with open(filename, 'r') as f:
            prev_content = f.read()

    # SIDE EFFECT!
    # delete oldest to leave most recent N files
    while len(files) > NUM_OLD_FILES_PRESERVED:
        os.remove(os.path.join(DOWNLOAD_DIR, files[0]))
        del files[0]
    return prev_content


main()
