from telebot import TeleBot, ExceptionHandler
from asyncio import new_event_loop, set_event_loop
from g4f import Client
from googletrans import Translator
from time import gmtime, strftime
import telebot
import json
import nest_asyncio

nest_asyncio.apply()

class Logger(ExceptionHandler):
	def handle(self, exception):
		print(exception)
		return True

bot = TeleBot('7600666100:AAGWWL34hzd8gvg0zRpVVx3y9SHZtG8da84', exception_handler=Logger())
client = Client()
translator = Translator()

loop = new_event_loop()
set_event_loop(loop)

description = '''
Telecensor

Universal bot for filtering and censoring Telegram chats.

Developers:

Сырцов Вадим — developer.
Wrote the entire bot code, connected GPT4.

/help — help.
/config — configure the bot.
'''

help = '''
Help:

/config — get current rules.
/config [rule] — toogle rule.

Rules:

filter_offensive — filter insults and obscene language.
filter_explicit — filter explicit content.
filter_links — filter links and phone numbers.
filter_adverstiments — filter adverstiments.
ban_users — ban users for repetitive violations.
ignore_admins — ignore admins' messages.
'''

config_rules = {
	'filter_offensive': 'hate speech, obscene language, insults, slurs, negative language, violience',
	'filter_explicit': 'inappropriate, excplicit, or adult content',
	'filter_links': 'links, phone numbers',
	'filter_adverstiments': 'advertisments',
	'ban_users': '',
	'ignore_admins': ''
}

config = None
violations = {}

log = open('log.txt', 'a+', encoding='utf8')

def translate_text(text: str, lang: str):
	return loop.run_until_complete(translator.translate(text, dest=lang)).text

def detect_language(text: str):
	return loop.run_until_complete(translator.detect(text)).lang

def load_config(chat_id):
	global config
	with open('config.json', 'r') as f:
		config_json = json.load(f)
	chat_id = str(chat_id)
	if not chat_id in config_json:
		config = []
	else:
		config = config_json[chat_id]

def save_config(chat_id):
	config_json = None
	with open('config.json', 'r') as f:
		config_json = json.load(f)
	chat_id = str(chat_id)
	config_json[chat_id] = config
	with open('config.json', 'w') as f:
		json.dump(config_json, f)

@bot.message_handler(commands=['help'])
def command_help(msg: telebot.types.Message):
	lang = msg.text.split()
	if not len(lang) == 2:
		lang = 'en'
	else:
		lang = lang[1]
	bot.send_message(msg.chat.id, translate_text(description, lang))
	bot.send_message(msg.chat.id, translate_text(help, lang))

@bot.message_handler(commands=['config'])
def command_config(msg: telebot.types.Message):
	global config
	cmd = msg.text.split()
	if not bot.get_chat_member(msg.chat.id, msg.from_user.id).status in ('creator', 'administrator'):
		return bot.reply_to(msg, 'Access denied.')
	if not len(cmd) in (1, 2) or len(cmd) == 2 and not cmd[1] in config_rules:
		return bot.reply_to(msg, 'Invalid request.')
	load_config(msg.chat.id)
	if len(cmd) == 1:
		return bot.reply_to(msg, f'Rules: {', '.join(config)}{'.' if len(config) >= 1 else '—'}')
	rule = cmd[1]
	if not rule in config:
		config.append(rule)
		bot.reply_to(msg, f'Enabled rule {rule}.')
	else:
		config.remove(rule)
		bot.reply_to(msg, f'Disabled rule {rule}.')
	save_config(msg.chat.id)

@bot.message_handler(func=lambda message: True)
def handle_msg(msg: telebot.types.Message):
	load_config(msg.chat.id)
	is_user_admin = bot.get_chat_member(msg.chat.id, msg.from_user.id).status in ('creator', 'administrator')
	if is_user_admin and ('ignore_admins' in config):
		return
	msg_time = strftime("%Y-%m-%d %H:%M:%S", gmtime())
	msg_lang = detect_language(msg.text)
	msg_translated_text = translate_text(msg.text, 'en')
	filter_text = ', '.join(tuple(map(config_rules.__getitem__, config)))
	user_banned = False
	response_text = client.chat.completions.create(
			model='gpt-4o-mini',
			messages=[{'role': 'user', 'content': f'Say "yes" if the text below contains {filter_text}:\n\n{msg.text}\n\n{msg.from_user.username}\n{msg.from_user.full_name}'}],
			web_search=False,
			max_tokens=2048
	).choices[0].message.content
	response_remove = response_text.lower().find('yes') != -1
	if response_remove:
		if 'ban_users' in config:
			key = str(msg.from_user.id)
			if key in violations:
				violations[key] += 1
			else:
				violations[key] = 1
			if not is_user_admin and violations[key] >= 3:
				bot.ban_chat_member(msg.chat.id, msg.from_user.id, 604800, False)
				bot.reply_to(translate_text(f'User was banned for repetive violation of the rules.', msg_lang))
			bot.reply_to(msg, translate_text(f'Message deleted for violation of the rules ({violations[key]}/3).', msg_lang))
		else:
			bot.reply_to(msg, translate_text('Message deleted for violation of the rules.', msg_lang))
		bot.delete_message(msg.chat.id, msg.id)
	log.write(f'Recieved message in chat ({msg.chat.id}) from {msg.from_user.username} ({msg.from_user.full_name}) at {msg_time}:\nMessage language: {msg_lang}\nMessage text: {msg.text}\nMessage translated text: {msg_translated_text}\nFilter text: {filter_text}\nRemove: {'Yes' if response_remove else 'No'}\nUser banned: {'Yes' if user_banned else 'No'}\n\n' + '-' * 64 + '\n\n')
	log.flush()

bot.infinity_polling(none_stop=True)