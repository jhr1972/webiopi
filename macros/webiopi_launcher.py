import os
import subprocess
import sys

# Elevate the actual command via sudo
cmd = ["sudo", "python3", "-m", "webiopi"] + sys.argv[1:]
subprocess.run(cmd)
