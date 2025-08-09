import threading
from .chat_manager import ChatManager
from .message_manager import MessageManager
from .response_generator import ResponseGenerator


class ChatService:
    
    
    def __init__(self):
        self.chat_manager = ChatManager()
        self.message_manager = MessageManager()
        self.response_generator = ResponseGenerator()
    
    def get_or_create_chat(self, user):
        
        return self.chat_manager.get_or_create_chat(user)
    
    def archive_chat(self, chat):
        
        return self.chat_manager.archive_chat(chat)
    
    def process_user_message(self, user, message_content):
        
        try:
            # Получаем или создаем чат
            chat = self.get_or_create_chat(user)
            
            # Создаем сообщение пользователя
            user_message = self.message_manager.create_user_message(chat, message_content)
            
            # Создаем сообщение ассистента с начальным статусом
            assistant_message = self.message_manager.create_assistant_message(chat)
            
            # Запускаем генерацию ответа в отдельном потоке
            thread = threading.Thread(
                target=self.response_generator.generate_response_stages,
                args=(assistant_message.id,)
            )
            thread.daemon = True
            thread.start()
            
            return {
                'chat_id': chat.id,
                'user_message_id': user_message.id,
                'assistant_message_id': assistant_message.id
            }
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error processing user message: {e}")
            raise