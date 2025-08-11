import asyncio
import logging
from typing import List, Dict, Tuple, Any
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

    async def execute_stage_prompts(self, prompts: List[Dict], context: str) -> Tuple[List[Dict[str, Any]], List[Dict]]:
        """
        Выполняет промпты этапа, поддерживая последовательный и параллельный режимы.

        Args:
            prompts: Список промптов для выполнения.
            context: Общий контекст для этого этапа.

        Returns:
            Кортеж, содержащий:
            - Список словарей с результатами ('response_text', 'block_outside_context').
            - Список данных для сохранения в межсессионный контекст.
        """
        is_step_by_step = any(p.get('step-by-stepRequest', False) for p in prompts)
        
        # Детальное логирование режима выполнения и флагов
        logger.debug(f"Stage analysis: prompts={len(prompts)}, step_by_step={is_step_by_step}")
        
        for i, prompt_item in enumerate(prompts, 1):
            step_by_step_flag = prompt_item.get('step-by-stepRequest', False)
            block_outside_flag = prompt_item.get('blockOutsideInterstageContext', False)
            prompt_preview = prompt_item['prompt'][:100] + "..." if len(prompt_item['prompt']) > 100 else prompt_item['prompt']
            logger.debug(f"Prompt {i}: step_by_step={step_by_step_flag}, blockOutsideInterstageContext={block_outside_flag}, text='{prompt_preview}'")
        
        logger.debug(f"Base context length: {len(context)}")
        context_preview = context[:200] + "..." if len(context) > 200 else context
        logger.debug(f"Base context preview: {context_preview}")
        responses_data = []
        
        if is_step_by_step:
            logger.debug("Executing stage in step-by-step mode")
            step_context = context
            for i, prompt_item in enumerate(prompts, 1):
                if 'messages' in prompt_item:  # Структурированный формат
                    logger.debug(f"Step {i}: structured prompt detected")
                    try:
                        response_text = await self._generate_single_response_structured(prompt_item, step_context)
                    except Exception as e:
                        response_text = f"[Ошибка генерации: {e}]"
                else:
                    prompt_text = prompt_item['prompt']
                    full_prompt = f"{step_context}\n\nЗадача: {prompt_text}"
                    logger.debug(f"Step {i}: sending request to LLM (full_prompt_len={len(full_prompt)})")
                    response_text = await self._generate_single_response(full_prompt)
                
                block_outside = prompt_item.get('blockOutsideInterstageContext', False)
                responses_data.append({
                    'response_text': response_text,
                    'block_outside_context': block_outside
                })
                
                logger.debug(f"Step {i} done. blockOutsideInterstageContext={block_outside}")
                step_context += f"\n\nРезультат предыдущего шага: {response_text}"
                logger.debug(f"Updated step context length: {len(step_context)}")
        else:
            logger.debug("Executing stage in parallel mode")
            tasks = []
            indices = []
            for i, prompt_item in enumerate(prompts, 1):
                if 'messages' in prompt_item:
                    logger.debug(f"Create task {i} (structured)")
                    task = asyncio.create_task(self._generate_single_response_structured(prompt_item, context))
                else:
                    prompt_text = prompt_item['prompt']
                    full_prompt = f"{context}\n\nЗадача: {prompt_text}"
                    logger.debug(f"Create task {i} (full_prompt_len={len(full_prompt)})")
                    task = asyncio.create_task(self._generate_single_response(full_prompt))
                tasks.append(task)
                indices.append(i)
            
            logger.debug(f"Running {len(tasks)} tasks in parallel")
            response_texts = await asyncio.gather(*tasks)
            logger.debug("Parallel tasks completed")

            for idx, prompt_item in enumerate(prompts):
                block_outside = prompt_item.get('blockOutsideInterstageContext', False)
                responses_data.append({
                    'response_text': response_texts[idx],
                    'block_outside_context': block_outside
                })
                logger.debug(f"Task {idx+1} processed. blockOutsideInterstageContext={block_outside}")

        # Логирование сохранения контекста
        saved_context_data = []
        logger.debug("saveLastAsContext flags analysis")
        for i, prompt_item in enumerate(prompts):
            save_context = prompt_item.get('saveLastAsContext', False)
            logger.debug(f"Prompt {i+1}: saveLastAsContext={save_context}")
            if save_context:
                saved_context_data.append({
                    'prompt': prompt_item['prompt'],
                    'response': responses_data[i]['response_text']
                })
                logger.debug(f"Saved context from prompt {i+1}")
        
        logger.info(f"Stage finished: responses={len(responses_data)}, saved_contexts={len(saved_context_data)}")
        # Убран шумный ANSI-разделитель
        # (если нужен разделитель при DEBUG, раскомментируйте следующую строку)
        # logger.debug("-" * 60)
         
        return responses_data, saved_context_data

    async def _generate_single_response(self, prompt: str) -> str:
        
        loop = asyncio.get_event_loop()
        
        # Выполняем синхронный вызов в отдельном потоке
        response = await loop.run_in_executor(
            self.executor,
            self.openrouter.generate_response,
            prompt
        )
        
        return response
    
    async def execute_stage_prompts_detailed(self, prompts: List[Dict], context: str, stage_name: str) -> Tuple[List[Dict[str, Any]], List[Dict], List[Dict]]:
        """
        Выполняет промпты этапа и возвращает полный детальный лог каждого LLM-запроса.
        
        Returns:
            - responses_data: как и раньше, список словарей {'response_text', 'block_outside_context'}
            - saved_context_data: данные для сохранения контекста
            - detailed_responses: список детальных ответов OpenRouterService по каждому промпту
        """
        is_step_by_step = any(p.get('step-by-stepRequest', False) for p in prompts)
        logger.debug(f"[DETAILED] Stage '{stage_name}': prompts={len(prompts)}, step_by_step={is_step_by_step}")
        responses_data: List[Dict[str, Any]] = []
        detailed_responses: List[Dict] = []
        
        if is_step_by_step:
            step_context = context
            for i, prompt_item in enumerate(prompts, 1):
                prompt_text = prompt_item['prompt']
                full_prompt = f"{step_context}\n\nЗадача: {prompt_text}"
                detailed = await self._generate_single_response_detailed(
                    full_prompt,
                    stage_info=f"{stage_name} (step {i})",
                    prompt_info=prompt_text[:120] + "..." if len(prompt_text) > 120 else prompt_text
                )
                detailed_responses.append(detailed)
                
                # Извлекаем текст ответа или ошибку
                if detailed.get('success') and detailed.get('response'):
                    response_text = detailed['response']['response_content']
                else:
                    response_text = f"[Ошибка генерации: {detailed.get('error', 'Неизвестная ошибка')}]"
                
                block_outside = prompt_item.get('blockOutsideInterstageContext', False)
                responses_data.append({
                    'response_text': response_text,
                    'block_outside_context': block_outside
                })
                step_context += f"\n\nРезультат предыдущего шага: {response_text}"
        else:
            # Параллельный режим
            tasks = []
            metas: List[Tuple[str, str]] = []
            for i, prompt_item in enumerate(prompts, 1):
                prompt_text = prompt_item['prompt']
                full_prompt = f"{context}\n\nЗадача: {prompt_text}"
                task = asyncio.create_task(self._generate_single_response_detailed(
                    full_prompt,
                    stage_info=f"{stage_name} (parallel prompt {i})",
                    prompt_info=prompt_text[:120] + "..." if len(prompt_text) > 120 else prompt_text
                ))
                tasks.append(task)
                metas.append((prompt_text, f"{stage_name} (parallel prompt {i})"))
            detailed_list = await asyncio.gather(*tasks)
            for idx, detailed in enumerate(detailed_list):
                detailed_responses.append(detailed)
                if detailed.get('success') and detailed.get('response'):
                    response_text = detailed['response']['response_content']
                else:
                    response_text = f"[Ошибка генерации: {detailed.get('error', 'Неизвестная ошибка')}]"
                block_outside = prompts[idx].get('blockOutsideInterstageContext', False)
                responses_data.append({
                    'response_text': response_text,
                    'block_outside_context': block_outside
                })
        
        # Сохранение контекста
        saved_context_data: List[Dict] = []
        for i, prompt_item in enumerate(prompts):
            if prompt_item.get('saveLastAsContext', False):
                saved_context_data.append({
                    'prompt': prompt_item['prompt'],
                    'response': responses_data[i]['response_text']
                })
        
        return responses_data, saved_context_data, detailed_responses

    async def _generate_single_response_detailed(self, prompt: str, stage_info: str, prompt_info: str) -> Dict:
        """
        Выполняет детальную генерацию одного промпта, передавая stage_info и prompt_info в OpenRouterService.
        """
        loop = asyncio.get_event_loop()
        detailed_response = await loop.run_in_executor(
            self.executor,
            self.openrouter.generate_response_detailed,
            prompt,
            None, # chat_history
            stage_info,
            prompt_info
        )
        return detailed_response

    def cleanup(self):
        """Освобождает ресурсы executor-а."""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)
            
    async def _generate_single_response_structured(self, prompt_item: Dict, context: str) -> str:
        """Выполняет генерацию с использованием структурированного формата."""
        # Структурированный формат с messages и JSON schema
        messages = []
        
        # Применяем контекст к содержимому сообщений
        for message in prompt_item["messages"]:
            content = message["content"]
            # Подставляем переменные контекста
            content = content.replace("{context}", context)
            
            messages.append({
                "role": message["role"],
                "content": content
            })
        
        # Проверяем наличие JSON схемы
        response_format = None
        if "json_schema" in prompt_item:
            response_format = {
                "type": "json_schema",
                "json_schema": prompt_item["json_schema"]
            }
        
        temperature = prompt_item.get("temperature", 0.7)
        
        loop = asyncio.get_event_loop()
        
        # Используем _make_request напрямую для структурированного формата
        detailed_response = await loop.run_in_executor(
            self.executor,
            lambda: self.openrouter._make_request(
                messages=messages,
                temperature=temperature,
                response_format=response_format,
                stage_info="Structured generation",
                prompt_info=str(messages[0]["content"][:100] + "..." if len(messages[0]["content"]) > 100 else messages[0]["content"])
            )
        )
        
        # Извлекаем контент из детального ответа
        if detailed_response.get("success") and detailed_response.get("response"):
            return detailed_response["response"]["response_content"]
        else:
            error_msg = detailed_response.get("error", "Неизвестная ошибка")
            raise Exception(f"Ошибка структурированной генерации: {error_msg}")
    
    async def _generate_single_response_structured_detailed(self, prompt_item: Dict, context: str, stage_info: str, prompt_info: str) -> Dict:
        """Выполняет детальную генерацию с использованием структурированного формата."""
        messages = []
        
        # Применяем контекст к содержимому сообщений
        for message in prompt_item["messages"]:
            content = message["content"]
            # Подставляем переменные контекста
            content = content.replace("{context}", context)
            
            messages.append({
                "role": message["role"],
                "content": content
            })
        
        # Проверяем наличие JSON схемы
        response_format = None
        if "json_schema" in prompt_item:
            response_format = {
                "type": "json_schema",
                "json_schema": prompt_item["json_schema"]
            }
        
        temperature = prompt_item.get("temperature", 0.7)
        
        loop = asyncio.get_event_loop()
        
        # Используем _make_request напрямую для получения полной детальной информации
        detailed_response = await loop.run_in_executor(
            self.executor,
            lambda: self.openrouter._make_request(
                messages=messages,
                temperature=temperature,
                response_format=response_format,
                stage_info=stage_info,
                prompt_info=prompt_info
            )
        )
        
        return detailed_response