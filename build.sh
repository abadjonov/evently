#!/usr/bin/env bash
# Har qanday buyruq xato bersa Render build jarayonini darhol to'xtatish uchun
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
