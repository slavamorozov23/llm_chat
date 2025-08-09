from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from chat.models import Chat
from chat.services import ChatService

class Command(BaseCommand):
    help = 'Архивирует чаты старше 24 часов'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Количество часов после которых чат архивируется (по умолчанию 24)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать какие чаты будут архивированы без фактического архивирования'
        )
    
    def handle(self, *args, **options):
        hours = options['hours']
        dry_run = options['dry_run']
        
        # Находим чаты старше указанного количества часов
        cutoff_time = timezone.now() - timedelta(hours=hours)
        old_chats = Chat.objects.filter(
            created_at__lt=cutoff_time,
            is_archived=False
        ).select_related('user')
        
        if not old_chats.exists():
            self.stdout.write(
                self.style.SUCCESS(f'Нет чатов старше {hours} часов для архивирования')
            )
            return
        
        self.stdout.write(
            f'Найдено {old_chats.count()} чатов старше {hours} часов'
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('РЕЖИМ ТЕСТИРОВАНИЯ - архивирование не будет выполнено'))
            for chat in old_chats:
                self.stdout.write(
                    f'  - Чат пользователя {chat.user.username} от {chat.created_at}'
                )
            return
        
        # Архивируем чаты
        chat_service = ChatService()
        archived_count = 0
        error_count = 0
        
        for chat in old_chats:
            try:
                chat_service.archive_chat(chat.user)
                archived_count += 1
                self.stdout.write(
                    f'✓ Архивирован чат пользователя {chat.user.username}'
                )
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ Ошибка архивирования чата пользователя {chat.user.username}: {str(e)}'
                    )
                )
        
        # Итоговая статистика
        self.stdout.write('\n' + '='*50)
        self.stdout.write(
            self.style.SUCCESS(f'Успешно архивировано: {archived_count} чатов')
        )
        
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f'Ошибок при архивировании: {error_count}')
            )
        
        self.stdout.write('Архивирование завершено!')