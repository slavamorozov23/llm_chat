import asyncio
import logging
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor
from .openrouter_service import OpenRouterService

# Настройка логгера
logger = logging.getLogger(__name__)


class GenerationExecutor:
    """
    Исполнитель асинхронной генерации ответов.
    
    НАЗНАЧЕНИЕ И АРХИТЕКТУРА:
    =========================
    
    Этот модуль выделен из StagedGenerationService для управления асинхронным
    выполнением промптов. Основные задачи:
    - Параллельное выполнение промптов в рамках одного этапа
    - Управление асинхронными операциями с OpenRouter API
    - Обработка ошибок при генерации
    - Сбор и агрегация результатов
    
    ПРИНЦИПЫ АСИНХРОННОСТИ:
    =======================
    
    1. ПАРАЛЛЕЛЬНОЕ ВЫПОЛНЕНИЕ ЭТАПОВ:
       - Все промпты в рамках одного этапа выполняются ПАРАЛЛЕЛЬНО
       - Это значительно ускоряет генерацию при наличии нескольких промптов
       - Например, этап с 3 промптами выполнится за время самого медленного промпта
    
    2. ПОСЛЕДОВАТЕЛЬНОСТЬ МЕЖДУ ЭТАПАМИ:
       - Этапы выполняются ПОСЛЕДОВАТЕЛЬНО
       - Следующий этап ждет завершения всех промптов предыдущего
       - Это обеспечивает доступность результатов предыдущих этапов
    
    3. ОБРАБОТКА ОШИБОК:
       - Если один промпт в этапе падает с ошибкой, остальные продолжают выполняться
       - Ошибки логируются, но не останавливают весь процесс
       - Результат ошибочного промпта заменяется на сообщение об ошибке
    
    ИНТЕГРАЦИЯ С saveLastAsContext:
    ===============================
    
    GenerationExecutor работает в тесной связке с ContextManager:
    - После выполнения промптов проверяет флаги saveLastAsContext
    - Собирает промпты и ответы, помеченные для сохранения
    - Передает их в ContextManager для сохранения
    
    ТЕХНИЧЕСКАЯ РЕАЛИЗАЦИЯ:
    =======================
    
    - execute_stage_prompts() - основной метод для выполнения этапа
    - _generate_single_response() - выполнение одного промпта
    - asyncio.gather() - для параллельного выполнения промптов
    - Обработка исключений на уровне отдельных промптов
    
    ПРИМЕР РАБОТЫ:
    ==============
    
    Этап с 3 промптами:
    [
        {"prompt": "Анализ A", "saveLastAsContext": true},
        {"prompt": "Анализ B"},
        {"prompt": "Анализ C"}
    ]
    
    Все 3 промпта выполняются одновременно, результаты собираются,
    промпт "Анализ A" и его ответ сохраняются для следующей генерации.
    
    НЕ УДАЛЯТЬ ЭТИ КОММЕНТАРИИ! Они объясняют сложную логику асинхронного
     выполнения и интеграции с системой контекста.
     """
    
    def __init__(self):
        self.openrouter = OpenRouterService()
        self.executor = ThreadPoolExecutor(max_workers=5)
    
    async def execute_stage_prompts(self, prompts: List[Dict], context: str) -> Tuple[List[str], List[Dict]]:
        
        tasks = []
        
        # Каждый промпт в этапе выполняется независимо с одинаковым контекстом
        for prompt_item in prompts:
            prompt_text = prompt_item['prompt']
            full_prompt = f"{context}\n\nЗадача: {prompt_text}"
            
            # Создаем асинхронную задачу (промпты не знают друг о друге)
            task = asyncio.create_task(
                self._generate_single_response(full_prompt)
            )
            tasks.append(task)
        
        # Ждем выполнения всех задач параллельно
        responses = await asyncio.gather(*tasks)
        
        # Собираем данные для сохранения контекста
        saved_context_data = []
        for i, prompt_item in enumerate(prompts):
            # Проверяем, нужно ли сохранить этот промпт и ответ для следующей генерации
            if prompt_item.get('saveLastAsContext', False):
                saved_context_data.append({
                    'prompt': prompt_item['prompt'],
                    'response': responses[i]
                })
        
        return responses, saved_context_data
    
    async def _generate_single_response(self, prompt: str) -> str:
        
        loop = asyncio.get_event_loop()
        
        # Выполняем синхронный вызов в отдельном потоке
        response = await loop.run_in_executor(
            self.executor,
            self.openrouter.generate_response,
            prompt
        )
        
        return response
    
    def cleanup(self):
        
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)