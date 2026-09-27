import random
import re

KZ="әғқңөұүһі"
def detect_language(text, previous=None):
    t=text.lower().strip()
    if not t:return previous or 'en',False
    if any(c in t for c in KZ) or t in ('сәлем','қайдасың'): return 'kk',True
    if re.search(r'[а-яё]',t): return 'ru',len(t)>3 or previous is None
    if re.search(r'[a-z]',t):
        if any(x in t for x in ('react','next','api','python','typescript','website','bot','go')): return previous or 'en',True
        return 'en',len(t)>2
    if any(ord(c)>127 for c in t): return 'unknown',False
    return previous or 'en',False

def language_supported(text):
    if text.strip() and not any(c.isalpha() for c in text): return False,'unknown',False
    lang,conf=detect_language(text)
    return lang in ('ru','kk','en') and (conf or lang=='en'),lang,conf

def normalize_control(text):
    return re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE).strip()

STOP_CONTROLS=("стоп ии","ии стоп","ai stop","stop ai","бот стоп","выключи ии","отключи ии")
START_CONTROLS=("старт ии","ии старт","ai start","start ai","бот старт","включи ии","включись","запусти ии")
def control_action(text):
    t=" ".join(normalize_control(text).split())
    if t in STOP_CONTROLS:return 'stop'
    if t in START_CONTROLS:return 'start'
    return None

def is_symbol_only(text):
    return bool(text.strip()) and not any(c.isalpha() for c in text)

def symbol_reply(text,lang='ru'):
    t=text.strip()
    if t.startswith('?'): return {'ru':'что?)','kk':'не болды?)','en':'what?)'}.get(lang,'что?)')
    if '👍' in t:return '👌'
    if '😂' in t:return '😂'
    if t.startswith('!'):return 'да?)' if lang=='ru' else 'yeah?)'
    return None

def simple_reply(text,lang='ru'):
    t=text.lower().strip()
    if t in ('привет','мривет'): return 'привет 👋'
    if t in ('эй','але','алло','алеее','ты тут','ты тут?'): return 'да)' if t in ('эй','але') else 'я тут)'
    if t in ('да','ага'): return 'понял)'
    if t in ('нет','ну'): return 'да?)' if t=='ну' else 'понял)'
    if t in ('ок','окей'): return '👌'
    if t in ('понял','поняла'): return 'ага)'
    if t in ('спасибо','спс'): return 'не за что)'
    if t in ('кто ты','ты кто','кто ты?'): return {'ru':'я ассистент Казбека 👋','kk':'Қазбектің ассистентімін 👋','en':"I'm Kazbek's assistant 👋"}.get(lang,'я ассистент Казбека 👋')
    return None

BUSINESS_WORDS=('сайт','бот','проект','разработ','цена','стоимость','оплат','лендинг','апи','прилож','магазин','сервис','делать','website','bot','project','price','build','app','api','сайт')
PERSONAL_PATTERNS=(r'где ты',r'ты где',r'қайдасың',r'не істеп',r'үйдесің',r'қашан кел',r'қоңырау шал',r'where are you',r'what are you doing',r'are you home',r'call me',r'when are you coming',r'are you awake',r'ты спишь',r'ты дома',r'че делаеш',r'че делаешь',r'как дела',r'го выйдем',r'го выйдем',r'позвони',r'эй брат')
def classify_intent(text):
    t=text.lower()
    business=any(x in t for x in BUSINESS_WORDS)
    personal=any(re.search(p,t) for p in PERSONAL_PATTERNS)
    if business:return 'business'
    if personal:return 'personal'
    return 'unknown'

def personal_fallback(lang):
    variants={'ru':['Казбек скоро сам ответит)','он чуть позже сам ответит)','Казбек сейчас занят, потом сам отпишет)','он как освободится, сам ответит 👌'],'kk':['Қазбек кейін өзі жауап береді)','босағанда өзі жауап береді 👌'],'en':["Kazbek will reply himself a bit later)","he'll reply when he's free 👌"]}
    return random.choice(variants.get(lang,variants['en']))

def identity_reply(lang='ru'):
    return random.choice({'ru':['я ассистент Казбека)','ассистент Казбека 👋'],'kk':['Қазбектің ассистентімін)','Қазбектің ассистентімін 👋'],'en':["I'm Kazbek's assistant)","Kazbek's assistant 👋"]}.get(lang,['Kazbek\'s assistant)']))
def unsupported_fallback(lang):
    return "Я сейчас понимаю только русский, казахский и английский)" if lang=='ru' else "Sorry, I currently understand only Russian, Kazakh, and English)"
