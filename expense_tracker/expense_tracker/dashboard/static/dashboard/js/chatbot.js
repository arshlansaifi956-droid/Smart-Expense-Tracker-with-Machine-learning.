document_getCookie = (name) => {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
};

document.addEventListener('DOMContentLoaded', function() {
    const chatMessages = document.getElementById('chat-messages');
    const chatInput = document.getElementById('chat-input');
    const chatSend = document.getElementById('chat-send');

    if (!chatMessages || !chatInput || !chatSend) return;

    function addMessage(text, isBot = false) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${isBot ? 'bot' : 'user'}`;
        
        // Basic styling for dynamic messages
        msgDiv.style.padding = '10px 15px';
        msgDiv.style.borderRadius = isBot ? '12px 12px 12px 0' : '12px 12px 0 12px';
        msgDiv.style.alignSelf = isBot ? 'flex-start' : 'flex-end';
        msgDiv.style.maxWidth = '80%';
        msgDiv.style.fontSize = '0.9rem';
        msgDiv.style.background = isBot ? '#eef2ff' : '#5470ff';
        msgDiv.style.color = isBot ? '#1e293b' : '#ffffff';
        msgDiv.style.whiteSpace = 'pre-wrap';
        
        msgDiv.textContent = text;
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    async function getLlamaResponse(prompt) {
        const context = `
            User: ${user_name || 'User'}
            Total expenses: ${currencySymbol} ${total_expenses || 0}
            Monthly budget: ${currencySymbol} ${month_budget || 0}
            Budget used: ${budgetPercent || 0}%
            Categories: ${categoryData.labels.join(', ')}
        `;

        try {
            const response = await fetch('/chatbot-api/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document_getCookie('csrftoken')
                },
                body: JSON.stringify({
                    prompt: prompt,
                    context: context
                })
            });

            const data = await response.json();
            if (data.status === 'success') {
                return data.response;
            } else {
                return `Error: ${data.message}`;
            }
        } catch (error) {
            console.error('Chatbot Error:', error);
            return "Sorry, I couldn't connect to the financial assistant. Is Ollama running?";
        }
    }

    async function handleSend() {
        const text = chatInput.value.trim();
        if (!text) return;

        addMessage(text, false);
        chatInput.value = '';
        
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message bot typing';
        typingDiv.style.padding = '10px 15px';
        typingDiv.style.borderRadius = '12px 12px 12px 0';
        typingDiv.style.alignSelf = 'flex-start';
        typingDiv.style.background = '#eef2ff';
        typingDiv.style.fontSize = '0.8rem';
        typingDiv.style.color = '#64748b';
        typingDiv.textContent = 'Llama 3.1 is thinking...';
        chatMessages.appendChild(typingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        const response = await getLlamaResponse(text);
        chatMessages.removeChild(typingDiv);
        addMessage(response, true);
    }

    chatSend.addEventListener('click', handleSend);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSend();
    });
});
