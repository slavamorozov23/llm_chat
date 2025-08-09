/**
 * Модуль для управления сообщениями
 */
class MessageManager {
    constructor(chatMessages) {
        this.chatMessages = chatMessages;
    }

    addUserMessage(content) {
        const now = new Date();
        const timeStr = now.getHours().toString().padStart(2, '0') + ':' +
            now.getMinutes().toString().padStart(2, '0');

        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        messageDiv.innerHTML = `
            <strong>Вы:</strong>
            <div class="message-content">${this.escapeHtml(content)}</div>
            <div class="message-time">${timeStr}</div>
        `;

        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    addAssistantMessage(messageId, content, isGenerating = false) {
        const now = new Date();
        const timeStr = now.getHours().toString().padStart(2, '0') + ':' +
            now.getMinutes().toString().padStart(2, '0');

        let messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);

        if (!messageDiv) {
            messageDiv = document.createElement('div');
            messageDiv.className = 'message assistant';
            messageDiv.setAttribute('data-message-id', messageId);
            this.chatMessages.appendChild(messageDiv);
        }

        const generationStatus = isGenerating ?
            '<div class="generation-status">Генерация...</div>' : '';

        messageDiv.innerHTML = `
            <strong>LLM:</strong>
            <div class="message-content">${this.escapeHtml(content)}</div>
            ${generationStatus}
            <div class="message-time">${timeStr}</div>
        `;

        this.scrollToBottom();
    }

    updateMessageStatus(messageId, content, isGenerating, stage, statusText = '') {
        const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
        if (!messageDiv) return;

        const now = new Date();
        const timeStr = now.getHours().toString().padStart(2, '0') + ':' +
            now.getMinutes().toString().padStart(2, '0');

        // Используем переданный statusText или fallback к старой логике
        let displayStatus = statusText;
        if (isGenerating && !displayStatus) {
            switch (stage) {
                case 1: displayStatus = 'Генерация...'; break;
                case 2: displayStatus = 'Уточнение...'; break;
                case 3: displayStatus = 'Проверка...'; break;
                default: displayStatus = 'Обработка...';
            }
        }

        const generationStatus = isGenerating ?
            `<div class="generation-status">${displayStatus}</div>` : '';

        messageDiv.innerHTML = `
            <strong>LLM:</strong>
            <div class="message-content">${this.escapeHtml(content)}</div>
            ${generationStatus}
            <div class="message-time">${timeStr}</div>
        `;
    }

    addUserMessageFromData(message) {
        // Добавляем границу контекста если нужно
        if (message.is_context_boundary) {
            this.addContextBoundary();
        }

        const date = new Date(message.created_at);
        const timeStr = date.getHours().toString().padStart(2, '0') + ':' +
            date.getMinutes().toString().padStart(2, '0');

        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        messageDiv.innerHTML = `
            <strong>Вы:</strong>
            <div class="message-content">${this.escapeHtml(message.content)}</div>
            <div class="message-time">${timeStr}</div>
        `;

        this.chatMessages.appendChild(messageDiv);
    }

    addAssistantMessageFromData(message) {
        // Добавляем границу контекста если нужно
        if (message.is_context_boundary) {
            this.addContextBoundary();
        }

        const date = new Date(message.created_at);
        const timeStr = date.getHours().toString().padStart(2, '0') + ':' +
            date.getMinutes().toString().padStart(2, '0');

        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.setAttribute('data-message-id', message.id);

        let statusText = '';
        if (message.is_generating) {
            // Используем generation_status_text если доступен, иначе fallback к старой логике
            statusText = message.generation_status_text || 
                        (message.generation_stage === 1 ? 'Генерация...' : 
                         message.generation_stage === 2 ? 'Уточнение...' : 
                         message.generation_stage === 3 ? 'Проверка...' : 'Обработка...');
        }

        const generationStatus = message.is_generating ?
            `<div class="generation-status">${statusText}</div>` : '';

        messageDiv.innerHTML = `
            <strong>LLM:</strong>
            <div class="message-content">${this.escapeHtml(message.content)}</div>
            ${generationStatus}
            <div class="message-time">${timeStr}</div>
        `;

        this.chatMessages.appendChild(messageDiv);
    }

    clearMessages() {
        this.chatMessages.innerHTML = '';
    }

    updateMessageStatus(messageId, content, isGenerating, stage, statusText = '') {
        const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
        if (!messageDiv) return;

        const contentDiv = messageDiv.querySelector('.message-content');
        const statusDiv = messageDiv.querySelector('.generation-status');
        
        if (contentDiv) {
            contentDiv.textContent = content;
        }
        
        if (isGenerating && !statusDiv) {
            const statusElement = document.createElement('div');
            statusElement.className = 'generation-status';
            // Используем переданный statusText или fallback к старой логике
            const displayStatus = statusText || (stage === 1 ? 'Генерация...' : 
                                               stage === 2 ? 'Уточнение...' : 
                                               stage === 3 ? 'Проверка...' : 'Обработка...');
            statusElement.textContent = displayStatus;
            contentDiv.after(statusElement);
        } else if (isGenerating && statusDiv && statusText) {
            // Обновляем текст статуса если он передан
            statusDiv.textContent = statusText;
        } else if (!isGenerating && statusDiv) {
            statusDiv.remove();
        }
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    addContextBoundary() {
        const boundaryDiv = document.createElement('div');
        boundaryDiv.className = 'context-boundary';
        boundaryDiv.innerHTML = `
            <div class="context-boundary-line"></div>
            <div class="context-boundary-text">Граница контекста (64000 символов)</div>
            <div class="context-boundary-line"></div>
        `;
        this.chatMessages.appendChild(boundaryDiv);
    }
}