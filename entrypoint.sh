#!/bin/bash
set -e

# Run the command as appuser
exec gosu appuser "$@"