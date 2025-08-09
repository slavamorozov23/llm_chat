#!/usr/bin/env python
"""
Скрипт для инициализации конфигурации поэтапной генерации
"""

import os
import django
import json

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
django.setup()

from django.contrib.auth.models import User
from chat.models import StagedGenerationConfig

def init_staged_config():
    
    
    # Получаем первого пользователя (или создаем тестового)
    user = User.objects.first()
    if not user:
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        print(f"Создан тестовый пользователь: {user.username}")
    
    # Проверяем, есть ли уже конфигурация для этого пользователя
    if StagedGenerationConfig.objects.filter(user=user).exists():
        print(f"Конфигурация для пользователя {user.username} уже существует")
        return
    
    # Создаем конфигурацию с примером JSON
    config_data = {
        "stage1": [
            {
                "prompt": "это некий технический запрос"
            },
            {
                "prompt": "это некий технический запрос, ВТОРОЙ, который на этом этапе будет параллельно идти. Для 2 генерации LLM, на 1 этапе формирования поэтапного ответа"
            }
        ],
        "stage2": [
            {
                "prompt": "это некий технический запрос, который на этом этапе будет параллельно идти. LLM в качестве КОНТЕКСТА, получит полный текст ДВУХ ОТВЕТОВ LLM из stage1"
            },
            {
                "prompt": "это некий ВТОРОЙ технический запрос, который на этом этапе будет параллельно идти. LLM в качестве КОНТЕКСТА, получит полный текст ДВУХ ОТВЕТОВ LLM из stage1"
            },
            {
                "prompt": "это некий ТРЕТИЙ технический запрос, который на этом этапе будет параллельно идти. LLM в качестве КОНТЕКСТА, получит полный текст ДВУХ ОТВЕТОВ LLM из stage1"
            }
        ],
        "stage3": [
            {
                "prompt": "это некий технический запрос. На последнем этапе, он ОДИН, т.к. обьединит ВСЁ сгенерированное за все этапы ранее. ПОлучит текст всех этапов ранее и контекст НА ВХОДЕ, как общий массив контекста. И сгенерирует ФИНАЛЬНЫЙ ОТВЕТ, как ВЫХОДНОЙ"
            }
        ]
    }
    
    config = StagedGenerationConfig.objects.create(
        user=user,
        name="Конфигурация по умолчанию",
        config_data=config_data
    )
    
    print(f"Создана конфигурация поэтапной генерации: {config.name}")
    print(f"JSON конфигурация:")
    print(json.dumps(config_data, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    init_staged_config()