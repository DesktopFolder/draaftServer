#!/bin/bash

. .env/bin/activate
fastapi dev src/server.py --port 8000
