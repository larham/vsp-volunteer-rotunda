#!/usr/bin/env python

from urllib import request, parse
import subprocess
import sys
import os
import configparser


def main():
    """
    In order to notify via email when new opportunities are found, use Google forms via command line ( https://yaz.in/p/submitting-a-google-form-using-the-command-line/ ),

    * run diff program
    * send any errors to google form
    * send any changes to google form
    * do not send anything if there are no changes and no error
    """
    url, param = get_url()
    call = subprocess.run(["python", "opportunities.py", "opportunities.properties"],
                          text=True,
                          capture_output=True)

    if call.returncode != 0:
        data = parse.urlencode({param: call.stderr}).encode()
        req = request.Request(url, data=data)  # makes the method "POST"
        request.urlopen(req)
    elif len(call.stdout) > 1:
        data = parse.urlencode({param: call.stdout}).encode()
        req = request.Request(url, data=data)  # makes the method "POST"
        request.urlopen(req)
    else:
        print(call.stderr)  # echo progress output to stderr


def errprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def get_url():
    url = ""
    param = ""
    if len(sys.argv) == 1:
        errprint("Please supply a path to a parameters file")
        sys.exit(1)
    else:
        if not os.path.exists(sys.argv[1]):
            errprint("cannot find file: %s" % sys.argv[1])
            sys.exit(1)
        config = configparser.RawConfigParser()
        config.read(sys.argv[1])
        try:
            url = config.get('Cron', 'url')
            param = config.get('Cron', 'param')
        except Exception:
            errprint("""
Please supply a properties file with content like:

[Cron]
URL=https://docs.google.com/blah
param=myGoogleFormParameterId
""")
            sys.exit(1)

    return url, param


main()
