#!/bin/bash

# cron script, expecting to be run ALREADY IN CORRECT current directory
# run via something like: 0 9-22 * * * /usr/bin/bash $INSTALL_DIR/cron.sh >> $LOG 2>&1

LOG=/tmp/opportunities.log
INSTALL_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

export PATH=$PATH >> $LOG 2>&1
cd "$INSTALL_DIR"
direnv exec $INSTALL_DIR bash -c "cd $INSTALL_DIR >> $LOG 2>&1  && ./notify.py  ./guild.properties >> $LOG 2>&1" >> $LOG 2>&1