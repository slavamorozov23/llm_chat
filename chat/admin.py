from django.contrib import admin
from django import forms
from .models import Chat, Message, ArchivedChat, StagedGenerationConfig, OpenRouterSettings


class StagedGenerationConfigForm(forms.ModelForm):
    config_data = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 20,
            'cols': 80,
            'style': 'font-family: monospace; white-space: pre;'
        }),
        help_text='JSON конфигурация этапов генерации'
    )
    
    class Meta:
        model = StagedGenerationConfig
        fields = '__all__'

@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'last_activity', 'is_archived')
    list_filter = ('is_archived', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('created_at', 'last_activity')
    ordering = ('-last_activity',)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('chat', 'role', 'content_preview', 'generation_stage', 'created_at')
    list_filter = ('role', 'generation_stage', 'created_at')
    search_fields = ('content', 'chat__user__username')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Содержимое'

@admin.register(ArchivedChat)
class ArchivedChatAdmin(admin.ModelAdmin):
    list_display = ('user', 'original_created_at', 'archived_at', 'message_count')
    list_filter = ('archived_at', 'original_created_at')
    search_fields = ('user__username',)
    readonly_fields = ('original_created_at', 'archived_at', 'messages_data')
    ordering = ('-archived_at',)
    
    def message_count(self, obj):
        return len(obj.messages_data) if obj.messages_data else 0
    message_count.short_description = 'Количество сообщений'


@admin.register(StagedGenerationConfig)
class StagedGenerationConfigAdmin(admin.ModelAdmin):
    form = StagedGenerationConfigForm
    list_display = ('name', 'user', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at', 'user')
    search_fields = ('name', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'name', 'is_active')
        }),
        ('Конфигурация', {
            'fields': ('config_data',),
            'description': 'JSON конфигурация этапов генерации. Пример структуры:<br>'
                          '<pre>{\n'
                          '  "stage1": [{"prompt": "запрос 1"}, {"prompt": "запрос 2"}],\n'
                          '  "stage2": [{"prompt": "запрос с контекстом stage1"}],\n'
                          '  "stage3": [{"prompt": "финальный запрос"}]\n'
                          '}</pre>'
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Устанавливаем текущего пользователя по умолчанию
        if not obj:
            form.base_fields['user'].initial = request.user
        return form


@admin.register(OpenRouterSettings)
class OpenRouterSettingsAdmin(admin.ModelAdmin):
    list_display = ('model', 'api_key_preview', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('API Настройки', {
            'fields': ('api_key', 'model'),
            'description': 'Настройки для подключения к OpenRouter API'
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def api_key_preview(self, obj):
        if obj.api_key:
            return f"{obj.api_key[:10]}...{obj.api_key[-4:]}" if len(obj.api_key) > 14 else obj.api_key
        return "Не установлен"
    api_key_preview.short_description = 'API ключ'
    
    def has_add_permission(self, request):
        # Разрешаем добавление только если нет записей
        return not OpenRouterSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        # Запрещаем удаление, чтобы всегда была одна запись
        return False
