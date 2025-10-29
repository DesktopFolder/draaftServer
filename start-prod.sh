#!/bin/bash

. .env/bin/activate
fastapi run src/server.py --port 3731
