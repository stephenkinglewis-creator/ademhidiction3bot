import os
import json
import logging
import asyncio
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv
import openai
import requests
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# API Keys
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
DICTIONARY_API_KEY = os.getenv('DICTIONARY_API_KEY')  # Optional

# Initialize OpenAI
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Dictionary API endpoints
DICTIONARY_API = "https://api.dictionaryapi.dev/api/v2/entries/en/"
SYNONYM_API = "https://api.datamuse.com/words"

# User states
STATE_IDLE, STATE_DEFINE, STATE_ASK = range(3)
user_states = {}

class DictionaryBot:
    def __init__(self):
        self.commands = {
            '/start': 'Start the bot',
            '/help': 'Get help and usage instructions',
            '/define': 'Define a word (usage: /define word)',
            '/ask': 'Ask any question to AI',
            '/synonyms': 'Find synonyms for a word',
            '/examples': 'Get example sentences',
            '/history': 'View your recent queries',
            '/stats': 'View bot statistics',
            '/language': 'Change language preference'
        }
        self.user_history = {}
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a welcome message when /start is issued."""
        welcome_message = (
            f"👋 Hello {update.effective_user.first_name}! I'm your Dictionary AI Bot.\n\n"
            "I can help you with:\n"
            "📚 Define words (use /define)\n"
            "🤖 Answer any question (use /ask or just ask me!)\n"
            "🔍 Find synonyms (use /synonyms)\n"
            "💬 Show examples (use /examples)\n"
            "📊 Track your history (use /history)\n\n"
            "Type /help to see all available commands."
        )
        await update.message.reply_text(welcome_message)
        
        # Initialize user history
        user_id = update.effective_user.id
        if user_id not in self.user_history:
            self.user_history[user_id] = []

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a help message when /help is issued."""
        help_text = "🤖 *Available Commands:*\n\n"
        for cmd, desc in self.commands.items():
            help_text += f"• `{cmd}` - {desc}\n"
        
        help_text += "\n*Tips:*\n"
        help_text += "• You can ask me questions directly without using commands\n"
        help_text += "• Use /define [word] to get dictionary definition\n"
        help_text += "• I can understand natural language queries"
        
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def define_word(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Define a word using dictionary API."""
        user_id = update.effective_user.id
        
        # Check if word is provided
        if context.args:
            word = ' '.join(context.args)
        else:
            await update.message.reply_text("Please provide a word. Example: /define hello")
            user_states[user_id] = STATE_DEFINE
            return
        
        # Check if we have a specific word and not in waiting state
        if user_id in user_states and user_states[user_id] == STATE_DEFINE:
            word = ' '.join(context.args)
            if not word:
                await update.message.reply_text("Please type the word you want to define.")
                return
            user_states[user_id] = STATE_IDLE
        
        # Get definition
        definition = await self.get_definition(word)
        
        if definition:
            # Save to history
            if user_id not in self.user_history:
                self.user_history[user_id] = []
            self.user_history[user_id].append({
                'word': word,
                'type': 'definition',
                'timestamp': datetime.now().isoformat()
            })
            
            await update.message.reply_text(definition, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"Sorry, I couldn't find a definition for '{word}'. Please check the spelling.")

    async def get_definition(self, word):
        """Fetch definition from dictionary API."""
        try:
            response = requests.get(f"{DICTIONARY_API}{word}")
            if response.status_code == 200:
                data = response.json()
                
                if not data:
                    return None
                    
                result = f"📚 *Definition of '{word}'*\n\n"
                
                for entry in data[:2]:  # Limit to first 2 entries
                    if 'meanings' in entry:
                        for meaning in entry['meanings'][:2]:  # Limit to first 2 meanings
                            part_of_speech = meaning.get('partOfSpeech', 'unknown')
                            result += f"*{part_of_speech}*\n"
                            
                            for definition in meaning.get('definitions', [])[:2]:
                                definition_text = definition.get('definition', '')
                                result += f"  • {definition_text}\n"
                                
                                if 'example' in definition:
                                    result += f"    _Example: {definition['example']}_\n"
                            result += "\n"
                
                return result.strip()
            return None
        except Exception as e:
            logger.error(f"Error getting definition: {e}")
            return None

    async def ask_ai(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Answer user's question using OpenAI."""
        user_id = update.effective_user.id
        
        if context.args:
            question = ' '.join(context.args)
        else:
            await update.message.reply_text("Please ask a question. Example: /ask What is artificial intelligence?")
            user_states[user_id] = STATE_ASK
            return
        
        # Check if we have a specific question
        if user_id in user_states and user_states[user_id] == STATE_ASK:
            question = ' '.join(context.args)
            if not question:
                await update.message.reply_text("Please type your question.")
                return
            user_states[user_id] = STATE_IDLE
        
        # Send typing indicator
        await update.message.chat.send_action(action="typing")
        
        # Get AI response
        response = await self.get_ai_response(question)
        
        # Save to history
        if user_id not in self.user_history:
            self.user_history[user_id] = []
        self.user_history[user_id].append({
            'question': question[:50],
            'type': 'question',
            'timestamp': datetime.now().isoformat()
        })
        
        await update.message.reply_text(response)

    async def get_ai_response(self, question):
        """Get response from OpenAI."""
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that defines words and answers questions."},
                    {"role": "user", "content": question}
                ],
                max_tokens=500,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error getting AI response: {e}")
            return "I'm sorry, I'm having trouble processing your question right now. Please try again later."

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle user messages without commands."""
        user_id = update.effective_user.id
        message_text = update.message.text
        
        # Check if user is in a waiting state
        if user_id in user_states:
            if user_states[user_id] == STATE_DEFINE:
                await self.define_word(update, context)
                return
            elif user_states[user_id] == STATE_ASK:
                context.args = [message_text]
                await self.ask_ai(update, context)
                return
        
        # Auto-detect intent
        # If it's a simple word (single word), try to define it
        if len(message_text.split()) <= 3 and not message_text.endswith('?'):
            definition = await self.get_definition(message_text)
            if definition:
                await update.message.reply_text(definition, parse_mode='Markdown')
                return
        
        # Otherwise, treat as a question for AI
        await update.message.chat.send_action(action="typing")
        response = await self.get_ai_response(message_text)
        await update.message.reply_text(response)

    async def synonyms(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Find synonyms for a word."""
        if not context.args:
            await update.message.reply_text("Please provide a word. Example: /synonyms happy")
            return
        
        word = ' '.join(context.args)
        
        try:
            response = requests.get(f"{SYNONYM_API}?rel_syn={word}")
            if response.status_code == 200:
                data = response.json()
                if data:
                    synonyms = [item['word'] for item in data[:10]]
                    result = f"🔍 *Synonyms for '{word}':*\n\n"
                    result += ", ".join(synonyms)
                    await update.message.reply_text(result, parse_mode='Markdown')
                else:
                    await update.message.reply_text(f"No synonyms found for '{word}'")
            else:
                await update.message.reply_text("Error fetching synonyms. Please try again.")
        except Exception as e:
            logger.error(f"Error getting synonyms: {e}")
            await update.message.reply_text("Error fetching synonyms. Please try again.")

    async def examples(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get example sentences for a word."""
        if not context.args:
            await update.message.reply_text("Please provide a word. Example: /examples beautiful")
            return
        
        word = ' '.join(context.args)
        
        try:
            response = requests.get(f"{DICTIONARY_API}{word}")
            if response.status_code == 200:
                data = response.json()
                examples = []
                
                for entry in data[:2]:
                    if 'meanings' in entry:
                        for meaning in entry['meanings'][:2]:
                            for definition in meaning.get('definitions', [])[:2]:
                                if 'example' in definition:
                                    examples.append(f"• {definition['example']}")
                
                if examples:
                    result = f"💬 *Example sentences for '{word}':*\n\n"
                    result += "\n".join(examples[:5])
                    await update.message.reply_text(result, parse_mode='Markdown')
                else:
                    await update.message.reply_text(f"No example sentences found for '{word}'")
            else:
                await update.message.reply_text("Error fetching examples. Please try again.")
        except Exception as e:
            logger.error(f"Error getting examples: {e}")
            await update.message.reply_text("Error fetching examples. Please try again.")

    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's query history."""
        user_id = update.effective_user.id
        
        if user_id not in self.user_history or not self.user_history[user_id]:
            await update.message.reply_text("You have no query history yet.")
            return
        
        history_text = "📜 *Your Recent Queries:*\n\n"
        for i, item in enumerate(self.user_history[user_id][-10:], 1):
            if item['type'] == 'definition':
                history_text += f"{i}. 📚 '{item['word']}'\n"
            else:
                history_text += f"{i}. 🤖 '{item['question']}'\n"
        
        await update.message.reply_text(history_text, parse_mode='Markdown')

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics."""
        user_id = update.effective_user.id
        total_queries = len(self.user_history.get(user_id, []))
        
        stats_text = (
            f"📊 *Your Statistics*\n\n"
            f"Total queries: {total_queries}\n"
            f"Definitions: {sum(1 for q in self.user_history.get(user_id, []) if q['type'] == 'definition')}\n"
            f"Questions: {sum(1 for q in self.user_history.get(user_id, []) if q['type'] == 'question')}\n"
            f"Active since: {datetime.now().strftime('%Y-%m-%d')}"
        )
        
        await update.message.reply_text(stats_text, parse_mode='Markdown')

    async def language(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Change language preference."""
        # This is a placeholder - you can add multi-language support
        await update.message.reply_text(
            "Currently only English is supported.\n"
            "Multi-language support will be added soon!"
        )

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors."""
        logger.error(f"Update {update} caused error {context.error}")
        await update.message.reply_text("An error occurred. Please try again later.")

def main():
    """Start the bot."""
    # Create application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    bot = DictionaryBot()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help))
    application.add_handler(CommandHandler("define", bot.define_word))
    application.add_handler(CommandHandler("ask", bot.ask_ai))
    application.add_handler(CommandHandler("synonyms", bot.synonyms))
    application.add_handler(CommandHandler("examples", bot.examples))
    application.add_handler(CommandHandler("history", bot.history))
    application.add_handler(CommandHandler("stats", bot.stats))
    application.add_handler(CommandHandler("language", bot.language))
    
    # Add message handler for non-command messages
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        bot.handle_message
    ))
    
    # Add error handler
    application.add_error_handler(bot.error_handler)
    
    # Start the bot
    print("🤖 Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
