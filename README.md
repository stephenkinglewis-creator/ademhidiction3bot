# Telegram Dictionary AI Bot

A Telegram bot that defines words and answers questions using AI.

## Features
- 📚 Dictionary definitions
- 🤖 AI-powered question answering
- 🔍 Synonyms and examples
- 📊 Query history
- 🎯 Auto-detect intent

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create `.env` file with your API keys
4. Run: `python bot.py`

## Deployment on Railway

1. Push code to GitHub
2. Connect repository to Railway
3. Add environment variables
4. Deploy!

## Environment Variables

- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
- `OPENAI_API_KEY`: OpenAI API key
- `DICTIONARY_API_KEY`: (Optional) Dictionary API key

## Commands

- `/start` - Start the bot
- `/help` - Show help
- `/define [word]` - Define a word
- `/ask [question]` - Ask a question
- `/synonyms [word]` - Find synonyms
- `/examples [word]` - Get example sentences
- `/history` - View your history
- `/stats` - View statistics
