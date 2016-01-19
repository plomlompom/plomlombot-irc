#!/bin/bash

# This script runs the plomlombot in a virtual environment with temporarily
# installed required external Python libraries.
set -e

DIR_ENV=.temp_env

pyvenv $DIR_ENV 
source $DIR_ENV/bin/activate
pip install -r requirements.txt
set +e
echo
python3 plomlombot.py -n plomplombot "$@" 
deactivate
rm -rf $DIR_ENV 
