# Opportunities

## Monitor new volunteer opportunities from Volunteer Scheduler Pro (VSP) at rotundasoftware.com 

The VSP website provides a way to volunteer.

However, there is no current feature for volunteers to get notifications when new opportunities are added, at least for some organizations.

This tool can tell when new opportunities appear. If new opportunities are available (compared to the last time it was run), it will print out lines like

```output
My Band Name, Fri, 6:30 PM - 9:00 PM within date range: May 23 - May 24, https://secure.rotundasoftware.com/...
My Band Name, Sat, 6:30 PM - 9:00 PM within date range: May 23 - May 24, https://secure.rotundasoftware.com/...
```

## Installation

On ubuntu linux, the provided `./install_python_selenium.sh` adds the python & selenium tools necessary.

On a mac OS you can install with `brew install python3 chromedriver` (assuming `homebrew` is already installed).

On any platform, the `direnv` tool is recommended since a dotfile script is included to help automation.

Requirements for python pip modules are listed in `setup.py`. The command to install/update all modules is:

`python setup.py install`

## How to run the program `opportunities.py` to see if there are new opportunities

The command to run Opportunities is:

`python opportunities.py`

The program will prompt you for your username, password, and url.  

Your url for your organization starts with 'https://secure.rotundasoftware.com', and may have your organization's name in it.

The first time you run the program, there will be no output since there is no comparison history yet. The next time you run it, it will have a comparison, and will show new opportunities if there are any.

## Properties file

Although Opportunities can prompt you for your login to rotundasoftware.com, you may wish to create a properties file so that you can rerun it more easily. The format for the properties file is like these dummy examples:

```properties
[Opportunities]
username=myemail@someserver.com
password=mysecretpassword
url=https://secure.rotundasoftware.com/insert-your-organizations-url-info-here
```

To use a properties file, invoke `opportunity.py` and supply the path to your properties file as the first argument, like so: 

`./opportunities.py <my properties file>`

## How to run the notifier program `notify.py`

An additional program, `notify.py`, is provided to run the `opportunities.py` program and send an email, by way of a Google™ Form entry. In other words, if there is a new opportunity, the `notify.py` program will send an entry to a Google Form that you specify. That form, in turn, can send you an email.

You can [learn about Google Forms](https://support.google.com/docs/answer/6281888?hl=en&co=GENIE.Platform%3DDesktop) and create one with a 'Long Answer' type of survey question (multiple lines are possible in the answers). Also enable it to email you when new entries arrive. If you then determine the URL for this survey, and the [name of that 'Long Answer' parameter](https://yaz.in/p/submitting-a-google-form-using-the-command-line/), you can add them to a properties file like these dummy examples:

```properties
[Cron]
param=entry.12345myNumber
url=https://docs.google.com/myFormId/formResponse?usp=pp_url&submit=Submit
```

Invoking the notifier is then as:

`./notify.py guild.properties`

## Cron

You may want to make a `cron` job to run this periodically. A provided script `cron.sh` helps with the complications of path and output of cron jobs. It assumes that the current directory is set correctly. A cron job something like the following will invoke it hourly between 9am and 10pm.

```cron
LOG=/tmp/opportunities.log
INSTALL_DIR=/path/to/opportunities/
0 9-22 * * * date > $LOG && cd $INSTALL_DIR >> $LOG 2>&1  && /usr/bin/bash $INSTALL_DIR/cron.sh >> $LOG 2>&1
```

## Disclaimers

This Opportunity software and its authors are NOT affiliated with Rotunda Software Inc.
Google is a trademark of Google, Inc.
