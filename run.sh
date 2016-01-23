#!/bin/bash

# This script runs the plomlombot in a virtual environment with temporarily
# installed required external Python libraries.
set -e

DIR_ENV=.temp_env

pyvenv $DIR_ENV 
source $DIR_ENV/bin/activate
pip install -r requirements.txt
#pip install -r requirements2.txt
echo
set +e
python3 plomlombot.py "$@"
set -e
deactivate
rm -rf $DIR_ENV 
