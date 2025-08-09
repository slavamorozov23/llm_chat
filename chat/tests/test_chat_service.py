import pytest
from unittest.mock import Mock, patch
from chat.services.chat_service import ChatService
from chat.models import Chat, Message


@pytest.mark.django_db
class TestChatService:
    
    @pytest.fixture(autouse=True)
    def setup(self, openrouter_settings):
        self.chat_service = ChatService()
    
    def test_get_or_create_chat_creates_new(self, user):
        chat = self.chat_service.get_or_create_chat(user)
        
        assert chat is not None
        assert chat.user == user
        assert not chat.is_archived
        assert Chat.objects.filter(user=user).count() == 1
    
    def test_get_or_create_chat_returns_existing(self, user):
        chat1 = self.chat_service.get_or_create_chat(user)
        chat2 = self.chat_service.get_or_create_chat(user)
        
        assert chat1.id == chat2.id
        assert Chat.objects.filter(user=user).count() == 1
    
    def test_archive_chat_deletes_and_archives(self, chat, message):
        chat_id = chat.id
        Message.objects.create(chat=chat, role='assistant', content='Response')
        
        self.chat_service.archive_chat(chat)
        
        assert not Chat.objects.filter(id=chat_id).exists()
        assert chat.user.archived_chats.count() == 1
        
        archived = chat.user.archived_chats.first()
        assert len(archived.messages_data) == 2
        assert archived.messages_data[0]['content'] == message.content
    
    @patch('chat.services.response_generator.ResponseGenerator.generate_response_stages')
    def test_process_user_message_creates_messages(self, mock_generate, user):
        message_content = "Test message"
        
        result = self.chat_service.process_user_message(user, message_content)
        
        assert 'chat_id' in result
        assert 'user_message_id' in result
        assert 'assistant_message_id' in result
        
        user_msg = Message.objects.get(id=result['user_message_id'])
        assert user_msg.content == message_content
        assert user_msg.role == 'user'
        
        assistant_msg = Message.objects.get(id=result['assistant_message_id'])
        assert assistant_msg.role == 'assistant'
        assert assistant_msg.is_generating
        
        mock_generate.assert_called_once_with(assistant_msg.id)
    
    @patch('chat.services.response_generator.ResponseGenerator.generate_response_stages')
    def test_process_user_message_handles_error(self, mock_generate, user):
        mock_generate.side_effect = Exception("Test error")
        
        with pytest.raises(Exception) as exc_info:
            self.chat_service.process_user_message(user, "Test")
        
        assert "Test error" in str(exc_info.value)
    
    def test_archive_old_chat_creates_new(self, user, freezer):
        # Устанавливаем начальную дату
        freezer.move_to('2025-01-01')
        chat = self.chat_service.get_or_create_chat(user)
        original_id = chat.id
        
        # Перемещаемся на 2 дня вперед (больше чем 1 день для архивации)
        freezer.move_to('2025-01-03')
        
        new_chat = self.chat_service.get_or_create_chat(user)
        
        assert new_chat.id != original_id
        assert not Chat.objects.filter(id=original_id).exists()
        assert user.archived_chats.count() == 1