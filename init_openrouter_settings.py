#!/usr/bin/env python
"""
Скрипт для инициализации настроек OpenRouter
"""

import os
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
django.setup()

from chat.models import OpenRouterSettings

def init_openrouter_settings():
    
    if not OpenRouterSettings.objects.exists():
        settings = OpenRouterSettings.objects.create(
            api_key="",  # Пустой ключ, будет заполнен через админку
            model="openai/gpt-oss-20b:free"
        )
        print(f"Создана запись настроек OpenRouter: {settings}")
    else:
        print("Настройки OpenRouter уже существуют")

if __name__ == '__main__':
    init_openrouter_settings()