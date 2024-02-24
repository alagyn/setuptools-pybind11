#!/bin/bash

HOME=$(realpath $(dirname $0))

export PYTHONPATH=$HOME/..

$HOME/../venv/bin/python -m build --wheel