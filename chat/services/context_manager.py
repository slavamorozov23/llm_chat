from typing import Dict, List, Any


class ContextManager:
    """
    Менеджер контекста для поэтапной генерации.
    
    КРИТИЧЕСКИ ВАЖНАЯ ФУНКЦИОНАЛЬНОСТЬ: saveLastAsContext
    ====================================================
    
    Этот модуль реализует одну из ключевых особенностей системы - возможность
    сохранения контекста между генерациями через механизм saveLastAsContext.
    
    ПРИНЦИП РАБОТЫ saveLastAsContext:
    =================================
    
    1. СОХРАНЕНИЕ КОНТЕКСТА:
       - Когда промпт имеет флаг "saveLastAsContext": true
       - Система сохраняет ТЕКСТ ПРОМПТА и ОТВЕТ LLM
       - Данные сохраняются в памяти, привязанные к user_id
    
    2. ИСПОЛЬЗОВАНИЕ КОНТЕКСТА:
       - При СЛЕДУЮЩЕЙ генерации сохраненный контекст автоматически добавляется
       - Контекст вставляется в начало системного промпта как дополнительная информация
       - Формат: "Предыдущий контекст: [промпт] -> [ответ]"
    
    3. ОЧИСТКА КОНТЕКСТА:
       - После использования контекст АВТОМАТИЧЕСКИ ОЧИЩАЕТСЯ
       - Это означает, что контекст работает только для ОДНОЙ следующей генерации
       - Если нужен постоянный контекст, его нужно сохранять в каждой генерации заново
    
    4. ИЗОЛЯЦИЯ ПО ПОЛЬЗОВАТЕЛЯМ:
       - Каждый пользователь имеет свой независимый контекст
       - Контексты разных пользователей никогда не пересекаются
    
    ПРИМЕР ИСПОЛЬЗОВАНИЯ:
    ====================
    
    Генерация 1:
    {
        "analysis": [{
            "prompt": "Проанализируй вопрос: Как работает ИИ?",
            "saveLastAsContext": true
        }]
    }
    Ответ: "Вопрос касается принципов работы искусственного интеллекта..."
    
    Генерация 2 (автоматически получит контекст):
    Системный промпт будет содержать:
    "Предыдущий контекст: Проанализируй вопрос: Как работает ИИ? -> Вопрос касается принципов работы искусственного интеллекта..."
    
    После Генерации 2 контекст очищается автоматически.
    
    ТЕХНИЧЕСКАЯ РЕАЛИЗАЦИЯ:
    =======================
    
    - saved_context: Dict[str, List[Dict]] - хранилище контекстов по user_id
    - get_saved_context() - получение сохраненного контекста
    - save_context() - сохранение нового контекста
    - clear_saved_context() - получение и очистка контекста (используется при генерации)
    - prepare_stage_context() - подготовка контекста для этапа с учетом предыдущих результатов
    
    НЕ УДАЛЯТЬ ЭТИ КОММЕНТАРИИ! Они содержат полное описание одной из самых
     сложных и важных частей системы поэтапной генерации.
     """
    
    def __init__(self):
        # Хранилище для контекста с saveLastAsContext
        self.saved_context = {}
    
    def get_saved_context(self, user_id: str) -> List[Dict]:
        
        return self.saved_context.get(user_id, [])
    
    def clear_saved_context(self, user_id: str) -> List[Dict]:
        
        saved_data = self.saved_context.get(user_id, [])
        if user_id in self.saved_context:
            del self.saved_context[user_id]
        return saved_data
    
    def save_context(self, user_id: str, context_data: List[Dict]) -> None:
        
        if context_data:
            self.saved_context[user_id] = context_data
    
    def prepare_stage_context(
        self, 
        user_message: str, 
        context_history: List[str], 
        stage_results: Dict, 
        saved_context_data: List = None
    ) -> str:
        
        context_parts = [f"Исходный вопрос пользователя: {user_message}"]
        
        # Добавляем сохраненный контекст из предыдущей генерации
        if saved_context_data:
            context_parts.append("\nКонтекст из предыдущей генерации:")
            for context_item in saved_context_data:
                context_parts.append(f"Промпт: {context_item['prompt']}")
                context_parts.append(f"Ответ: {context_item['response']}")
                context_parts.append("")
        
        if stage_results:
            context_parts.append("\nРезультаты предыдущих этапов:")
            for stage_name, responses in stage_results.items():
                context_parts.append(f"\n{stage_name}:")
                for i, response in enumerate(responses, 1):
                    context_parts.append(f"  {i}. {response}")
        
        return "\n".join(context_parts)
    
    def extract_save_context_data(self, prompts: List[Dict], responses: List[str]) -> List[Dict]:
        
        saved_context_data = []
        
        for i, prompt_item in enumerate(prompts):
            # Проверяем, нужно ли сохранить этот промпт и ответ для следующей генерации
            if prompt_item.get('saveLastAsContext', False):
                saved_context_data.append({
                    'prompt': prompt_item['prompt'],
                    'response': responses[i]
                })
        
        return saved_context_data