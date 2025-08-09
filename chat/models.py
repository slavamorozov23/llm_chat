from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

class Chat(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='chat')
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_archived = models.BooleanField(default=False)
    
    def should_archive(self):
        
        return timezone.now() - self.last_activity > timedelta(days=1)
    
    def __str__(self):
        return f"Chat of {self.user.username}"

class Message(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Поля для отслеживания генерации
    is_generating = models.BooleanField(default=False)
    generation_stage = models.IntegerField(default=0)  # 0-готово, 1-первичная генерация, 2-убираем воду, 3-проверяем соответствие
    generation_status_text = models.CharField(max_length=200, blank=True)  # Текст статуса генерации
    raw_response = models.TextField(blank=True)  # Сырой ответ от LLM
    
    # Поле для отметки границ контекста
    is_context_boundary = models.BooleanField(default=False)  # Отмечает границу контекста (64000 символов)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."

class ArchivedChat(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='archived_chats')
    messages_data = models.JSONField()  # Сохраняем все сообщения в JSON
    archived_at = models.DateTimeField(auto_now_add=True)
    original_created_at = models.DateTimeField()
    
    class Meta:
        ordering = ['-archived_at']
    
    def __str__(self):
        return f"Archived chat of {self.user.username} from {self.original_created_at}"

class StagedGenerationConfig(models.Model):
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='staged_configs')
    name = models.CharField(max_length=100, help_text="Название конфигурации")
    config_data = models.JSONField(help_text="JSON конфигурация этапов генерации")
    is_active = models.BooleanField(default=False, help_text="Активная конфигурация")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['user', 'name']
    
    def __str__(self):
        return f"{self.user.username} - {self.name}"
    
    def save(self, *args, **kwargs):
        # Если эта конфигурация становится активной, деактивируем остальные
        if self.is_active:
            StagedGenerationConfig.objects.filter(
                user=self.user, 
                is_active=True
            ).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class OpenRouterSettings(models.Model):
    
    api_key = models.CharField(
        max_length=200, 
        help_text="API ключ для OpenRouter",
        blank=True
    )
    model = models.CharField(
        max_length=100, 
        default="openai/gpt-oss-20b:free",
        help_text="Модель для генерации ответов"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Настройки OpenRouter"
        verbose_name_plural = "Настройки OpenRouter"
    
    def __str__(self):
        return f"OpenRouter Settings - {self.model}"
    
    def save(self, *args, **kwargs):
        # Обеспечиваем, что существует только одна запись настроек
        if not self.pk and OpenRouterSettings.objects.exists():
            raise ValueError("Может существовать только одна запись настроек OpenRouter")
        super().save(*args, **kwargs)
