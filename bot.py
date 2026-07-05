import os
import json
import logging
import asyncio
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
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

# Validate API keys
if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not set! Please set it in environment variables.")
    exit(1)
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY not set! Please set it in environment variables.")
    exit(1)

# Initialize OpenAI
try:
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}")
    exit(1)

# Dictionary API endpoints
DICTIONARY_API = "https://api.dictionaryapi.dev/api/v2/entries/en/"
SYNONYM_API = "https://api.datamuse.com/words"

# User states
STATE_IDLE, STATE_DEFINE, STATE_ASK = range(3)
user_states = {}
user_history = {}

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
        }
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a welcome message when /start is issued."""
        user_id = update.effective_user.id
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
        if user_id not in user_history:
            user_history[user_id] = []

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
        
        if context.args:
            word = ' '.join(context.args)
        else:
            await update.message.reply_text("Please provide a word. Example: /define hello")
            user_states[user_id] = STATE_DEFINE
            return
        
        if user_id in user_states and user_states[user_id] == STATE_DEFINE:
            word = ' '.join(context.args)
            if not word:
                await update.message.reply_text("Please type the word you want to define.")
                return
            user_states[user_id] = STATE_IDLE
        
        definition = await self.get_definition(word)
        
        if definition:
            if user_id not in user_history:
                user_history[user_id] = []
            user_history[user_id].append({
                'word': word,
                'type': 'definition',
                'timestamp': datetime.now().isoformat()
            })
            
            # Split long messages if needed
            if len(definition) > 4000:
                for i in range(0, len(definition), 4000):
                    await update.message.reply_text(definition[i:i+4000], parse_mode='Markdown')
            else:
                await update.message.reply_text(definition, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"Sorry, I couldn't find a definition for '{word}'. Please check the spelling.")

    async def get_definition(self, word):
        """Fetch definition from dictionary API."""
        try:
            response = requests.get(f"{DICTIONARY_API}{word}", timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                if not data:
                    return None
                    
                result = f"📚 *Definition of '{word}'*\n\n"
                
                for entry in data[:2]:
                    if 'meanings' in entry:
                        for meaning in entry['meanings'][:2]:
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
        
        if user_id in user_states and user_states[user_id] == STATE_ASK:
            question = ' '.join(context.args)
            if not question:
                await update.message.reply_text("Please type your question.")
                return
            user_states[user_id] = STATE_IDLE
        
        await update.message.chat.send_action(action="typing")
        response = await self.get_ai_response(question)
        
        if user_id not in user_history:
            user_history[user_id] = []
        user_history[user_id].append({
            'question': question[:50],
            'type': 'question',
            'timestamp': datetime.now().isoformat()
        })
        
        # Split long responses
        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                await update.message.reply_text(response[i:i+4000])
        else:
            await update.message.reply_text(response)

    async def get_ai_response(self, question):
        """Get response from OpenAI."""
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that defines words and answers questions concisely."},
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
        
        if user_id in user_states:
            if user_states[user_id] == STATE_DEFINE:
                context.args = [message_text]
                await self.define_word(update, context)
                return
            elif user_states[user_id] == STATE_ASK:
                context.args = [message_text]
                await self.ask_ai(update, context)
                return
        
        # Auto-detect intent
        if len(message_text.split()) <= 3 and not message_text.endswith('?'):
            definition = await self.get_definition(message_text)
            if definition:
                await update.message.reply_text(definition, parse_mode='Markdown')
                return
        
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
            response = requests.get(f"{SYNONYM_API}?rel_syn={word}", timeout=10)
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
            response = requests.get(f"{DICTIONARY_API}{word}", timeout=10)
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
        
        if user_id not in user_history or not user_history[user_id]:
            await update.message.reply_text("You have no query history yet.")
            return
        
        history_text = "📜 *Your Recent Queries:*\n\n"
        for i, item in enumerate(user_history[user_id][-10:], 1):
            if item['type'] == 'definition':
                history_text += f"{i}. 📚 '{item['word']}'\n"
            else:
                history_text += f"{i}. 🤖 '{item['question']}'\n"
        
        await update.message.reply_text(history_text, parse_mode='Markdown')

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics."""
        user_id = update.effective_user.id
        total_queries = len(user_history.get(user_id, []))
        
        stats_text = (
            f"📊 *Your Statistics*\n\n"
            f"Total queries: {total_queries}\n"
            f"Definitions: {sum(1 for q in user_history.get(user_id, []) if q['type'] == 'definition')}\n"
            f"Questions: {sum(1 for q in user_history.get(user_id, []) if q['type'] == 'question')}\n"
            f"Active since: {datetime.now().strftime('%Y-%m-%d')}"
        )
        
        await update.message.reply_text(stats_text, parse_mode='Markdown')

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors."""
        logger.error(f"Update {update} caused error {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text("An error occurred. Please try again later.")

async def main():
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
    
    # Add message handler for non-command messages
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        bot.handle_message
    ))
    
    # Add error handler
    application.add_error_handler(bot.error_handler)
    
    # Start the bot
    logger.info("🤖 Bot is starting...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Keep the bot running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down bot...")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        exit(1)
