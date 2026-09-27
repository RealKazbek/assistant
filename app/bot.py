import asyncio, logging, time
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.enums import ChatAction
from aiogram.types import BusinessConnection, Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from aiogram.types import BotCommandScopeChat
from aiogram.exceptions import TelegramBadRequest
from app.services.rate_limit import RateLimiter
from app.services.timing import reply_wait
from app.services.classifier import classify_intent, detect_language, language_supported, personal_fallback, unsupported_fallback, control_action, is_symbol_only, symbol_reply, simple_reply
log=logging.getLogger(__name__); FALLBACK="что-то сейчас ответ не проходит, Казбек позже сам ответит)"
DEFAULT_PROFILE={"name":"Kazbek","role":"Software Developer","specialization":"Frontend / Full-stack Development","languages":"Russian, Kazakh, English","services":"Websites, landing pages, corporate websites, React, Next.js, TypeScript, FastAPI, APIs, PostgreSQL, Telegram bots, automation, integrations, dashboards, MVP products, custom web applications","portfolio":"https://realkazbek.site","telegram":"@realkazbek","github":"https://github.com/RealKazbek","project_pixel_lane":"Smart-city traffic management and simulation platform","project_nexttrade":"Full-stack trading-related project","pricing_policy":"Do not invent prices. Ask for project scope and requirements first.","availability_policy":"Do not promise availability or deadlines without Kazbek confirming personally."}
HANDOFF=("позови казбека","хочу поговорить с казбеком","пусть казбек ответит","нужен сам казбек","қазбекті шақыр","қазбекпен сөйлескім келеді","let me talk to kazbek","i want to speak to kazbek","kazbek personally")
OPT_OUT=("отключись","не отвечай","не пиши","стоп","хватит","не нужен бот")
ENABLE=("старт ии","включи ии","включись","можешь отвечать","отвечай снова","бот старт","запусти ии","start ai","enable ai","turn ai on","start replying","қосыл")
class App:
 def __init__(self,s,db,ai,knowledge=None,memory=None,report=None):
  self.settings=s; self.db=db; self.ai=ai; self.knowledge=knowledge; self.memory=memory; self.report=report; self.bot=Bot(s.telegram_bot_token); self.dp=Dispatcher(); self.router=Router(); self.started=time.monotonic(); self.connections=set(); self.limiter=RateLimiter(s.rate_limit_messages,s.rate_limit_window_seconds); self.pending_tasks={}; self.batch_generation={}; self.batch_first_at={}; self.batch_initial={}; self.dp.include_router(self.router); self._wire()
 async def start(self):
  profile=await self.db.profile_all()
  for k,v in DEFAULT_PROFILE.items():
   if profile.get(k) is None: await self.db.profile_set(k,v)
  if self.knowledge: await self.knowledge.seed()
  for row in await self.db.chats(100):
   if await self.db.pending_messages(row['chat_id']): await self.schedule_batch(row['chat_id'])
  await self.bot.set_my_commands([BotCommand(command=x,description=y) for x,y in [("start","Панель управления"),("status","Статус бота"),("chats","Управление чатами"),("profile","Профиль Казбека"),("kb","База знаний"),("trusted","Доверенные контакты"),("ai_on","Включить AI"),("ai_off","Выключить AI"),("daily_report","Отчёт за сегодня"),("help","Помощь")]],scope=BotCommandScopeChat(chat_id=self.settings.owner_telegram_id))
 def _wire(self):
  @self.router.business_connection()
  async def connection(c:BusinessConnection): self.connections.add(c.id); log.info("business connection id=%s user_id=%s enabled=%s",c.id,c.user.id,c.is_enabled)
  @self.router.business_message()
  async def business(m:Message): await self.handle_business(m)
  @self.router.edited_business_message()
  async def edited(m:Message): log.info("ignored edited business message chat=%s",m.chat.id)
  @self.router.deleted_business_messages()
  async def deleted(m): log.info("received deleted business messages")
  for cmd,fn in [("ai_on",self.ai_on),("ai_off",self.ai_off),("ai_status",self.ai_status),("status",self.status),("pause",self.ai_off),("resume",self.ai_on),("pause_15",lambda m:self.pause(m,15)),("pause_60",lambda m:self.pause(m,60)),("chats",self.chats),("profile",self.profile),("help",self.help)]:
   self.router.message(Command(cmd))(fn)
  for cmd,fn in [("chat_on",self.chat_on),("chat_off",self.chat_off),("chat_status",self.chat_status),("chat_info",self.chat_info),("handoff",self.handoff),("unhandoff",self.unhandoff),("profile_set",self.profile_set),("profile_delete",self.profile_delete),("kb",self.kb),("kb_search",self.kb_search),("kb_show",self.kb_show),("kb_set",self.kb_set),("kb_enable",self.kb_enable),("kb_disable",self.kb_disable),("kb_delete",self.kb_delete),("memory",self.memory_cmd),("memory_clear",self.memory_clear_cmd),("lead_status",self.lead_status),("daily_report",self.daily_report),("daily_report_yesterday",self.daily_report_yesterday),("debug_context",self.debug_context),("trusted",self.trusted),("trusted_add",self.trusted_add),("trusted_remove",self.trusted_remove),("trusted_info",self.trusted_info),("trusted_note",self.trusted_note),("chat_type",self.chat_type)]: self.router.message(Command(cmd))(fn)
  @self.router.message(Command("start"))
  async def start_cmd(m):
   if await self.owner(m): await m.answer(await self.panel_text(),reply_markup=self.main_keyboard())
   else: await m.answer("этот бот используется как ассистент профиля Казбека)")
  @self.router.callback_query()
  async def callback(q):
   try: await self.handle_callback(q)
   except Exception: log.exception("owner callback failed data=%s",q.data); await q.answer("Не удалось открыть раздел",show_alert=True)
 async def owner(self,m): return bool(m.from_user and m.from_user.id==self.settings.owner_telegram_id)
 async def global_on(self): return (await self.db.get_setting("ai_enabled","true"))=="true" and not await self.global_pause()
 async def global_pause(self):
  until=float(await self.db.get_setting("global_pause_until","0") or 0); return until>time.time()
 async def target(self,m):
  args=(m.text or "").split();
  if len(args)>1:
   try:return int(args[1])
   except ValueError:return None
  if m.reply_to_message and m.reply_to_message.chat:return m.reply_to_message.chat.id
  return None
 async def set_global(self,on): await self.db.set_setting("ai_enabled","true" if on else "false"); await self.db.set_setting("global_pause_until","0")
 async def ai_on(self,m):
  if await self.owner(m): await self.set_global(True); await m.answer("AI включён.")
 async def ai_off(self,m):
  if await self.owner(m): await self.set_global(False); await m.answer("AI выключен.")
 async def pause(self,m,minutes):
  if await self.owner(m): await self.db.set_setting("global_pause_until",time.time()+minutes*60); await m.answer(f"AI поставлен на паузу на {minutes} мин.")
 async def ai_status(self,m):
  if await self.owner(m): await m.answer(await self.status_text())
 async def status(self,m):
  if await self.owner(m): await m.answer(await self.status_text())
 async def status_text(self):
  c=await self.db.counts(); on=await self.global_on(); return f"📊 Статус\n\nБот: 🟢 Работает\nBusiness: {'🟢 Подключён' if self.connections else '⚪ Не подключён'}\nDeepSeek: 🟢 Настроен\nAI: {'🟢 Включён' if on else '🔴 Выключен'}\n\nЧаты:\nВсего: {c['total']}\nAI включён: {c['enabled']}\nAI выключен: {c['disabled']}\nНа паузе: {c['paused']}\nПереданы Казбеку: {c['handoff']}\n\nАптайм: {int(time.monotonic()-self.started)} сек.\nСообщений обработано: {c['processed']}"
 async def chat_toggle(self,m,on):
  if await self.owner(m):
   chat=await self.target(m)
   if chat is not None: await self.db.upsert_chat(chat); await self.db.set_chat(chat,ai_enabled=int(on)); await m.answer(f"Чат {chat}: AI {'включён' if on else 'выключен'}.")
 async def chat_on(self,m): await self.chat_toggle(m,True)
 async def chat_off(self,m): await self.chat_toggle(m,False)
 async def chat_status(self,m):
  if await self.owner(m): await m.answer(await self.chat_text(await self.target(m)))
 async def chat_info(self,m): await self.chat_status(m)
 async def chat_text(self,chat):
  if chat is None:return "Использование: /chat_status <chat_id>"
  r=await self.db.chat(chat)
  if not r:return "Чат не найден"
  return f"Chat ID: {r['chat_id']}\nUser ID: {r['user_id']}\nName: {r['first_name'] or ''} {r['last_name'] or ''}\nUsername: @{r['username'] or '-'}\nAI: {'ON' if r['ai_enabled'] else 'OFF'}\nHandoff: {'yes' if r['handoff_requested'] else 'no'}\nManual pause until: {r['manual_pause_until'] or 'no'}\nLanguage: {r['language'] or '-'}\nMessages: {await self.db.message_count(chat)}"
 async def chats(self,m):
  if await self.owner(m): await m.answer("\n".join(f"{r['chat_id']} | @{r['username'] or r['first_name'] or '-'} | AI: {'включён' if r['ai_enabled'] else 'выключен'} | пауза: {'да' if r['manual_pause_until'] and r['manual_pause_until']>time.time() else 'нет'}" for r in await self.db.chats(30)) or "Чатов пока нет.")
 async def handoff(self,m):
  if await self.owner(m):
   c=await self.target(m)
   if c is not None: await self.db.upsert_chat(c); await self.db.set_chat(c,handoff_requested=1); await m.answer("Handoff enabled.")
 async def unhandoff(self,m):
  if await self.owner(m):
   c=await self.target(m)
   if c is not None: await self.db.set_chat(c,handoff_requested=0); await m.answer("Handoff cleared.")
 async def profile(self,m):
  if await self.owner(m): await m.answer("👤 Профиль Казбека\n\n"+"\n".join(f"{k}: {v}" for k,v in (await self.db.profile_all()).items()))
 async def profile_set(self,m):
  if await self.owner(m):
   p=(m.text or "").split(maxsplit=2)
   if len(p)==3: await self.db.profile_set(p[1],p[2]); await m.answer("Profile updated.")
 async def profile_delete(self,m):
  if await self.owner(m):
   p=(m.text or "").split();
   if len(p)>1: await self.db.profile_delete(p[1]); await m.answer("Profile key deleted.")
 async def help(self,m):
  if await self.owner(m): await m.answer("/ai_on /ai_off /ai_status /chats /chat_info /chat_on /chat_off /handoff /unhandoff /profile /kb /memory /trusted /trusted_add /trusted_remove /chat_type /daily_report")
 async def trusted(self,m):
  if await self.owner(m): await m.answer("Trusted contacts\n"+"\n".join(f"{r['display_name'] or 'Contact'} @{r['username'] or '-'} · {r['telegram_user_id'] or r['chat_id']}" for r in await self.db.trusted_all() if r['enabled']) or 'No trusted contacts.')
 async def trusted_add(self,m):
  if await self.owner(m):
   p=(m.text or '').split(); ident=p[1] if len(p)>1 else None
   if ident:
    await self.db.trusted_add(chat_id=int(ident) if ident.lstrip('-').isdigit() else None,user_id=int(ident) if ident.lstrip('-').isdigit() else None,username=ident.lstrip('@')); await m.answer('Trusted contact added.')
 async def trusted_remove(self,m):
  if await self.owner(m):
   p=(m.text or '').split();
   if len(p)>1: await self.db.trusted_remove(p[1]); await m.answer('Trusted contact removed.')
 async def trusted_info(self,m):
  if await self.owner(m):
   p=(m.text or '').split(); r=await self.db.trusted_get(p[1]) if len(p)>1 else None; await m.answer((f"{r['display_name'] or 'Contact'}\nuser_id: {r['telegram_user_id']}\nchat_id: {r['chat_id']}\nusername: @{r['username'] or '-'}\nnote: {r['note'] or '-'}" if r else 'Not found'))
 async def trusted_note(self,m):
  if await self.owner(m):
   p=(m.text or '').split(maxsplit=2)
   if len(p)>2: await self.db.trusted_note(p[1],p[2]); await m.answer('Trusted note updated.')
 async def chat_type(self,m):
  if await self.owner(m):
   p=(m.text or '').split();
   if len(p)>2: await self.db.upsert_chat(int(p[1])); await self.db.set_chat(int(p[1]),conversation_type=p[2],ai_enabled=0 if p[2]=='trusted' else 1); await m.answer('Chat type updated.')
 async def kb(self,m):
  if await self.owner(m):
   rows=await self.db.kb_all(); counts={};
   for r in rows: counts[r['category']]=counts.get(r['category'],0)+1
   await m.answer("Knowledge Base\n"+"\n".join(f"{k}: {v}" for k,v in sorted(counts.items()))+f"\n\nTotal: {len(rows)}")
 async def kb_search(self,m):
  if await self.owner(m): await m.answer("\n".join(f"{r['key']}: {r['title']}" for r in await self.knowledge.retrieve((m.text or '').split(maxsplit=1)[-1])) or "Nothing found")
 async def kb_show(self,m):
  if await self.owner(m):
   p=(m.text or '').split(maxsplit=1); r=await self.db.kb_get(p[1]) if len(p)>1 else None; await m.answer((r['content'] if r else 'Not found')[:4000])
 async def kb_set(self,m):
  if await self.owner(m):
   p=(m.text or '').split(maxsplit=3)
   if len(p)==4: await self.db.kb_upsert(p[1],p[2],p[1],p[3]); await m.answer('Knowledge card saved.')
 async def kb_enable(self,m): await self.kb_enabled(m,True)
 async def kb_disable(self,m): await self.kb_enabled(m,False)
 async def kb_enabled(self,m,on):
  if await self.owner(m):
   p=(m.text or '').split();
   if len(p)>1: await self.db.kb_set_enabled(p[1],on); await m.answer('Knowledge card updated.')
 async def kb_delete(self,m):
  if await self.owner(m):
   p=(m.text or '').split();
   if len(p)>1: await self.db.kb_delete(p[1]); await m.answer('Knowledge card deleted.')
 async def memory_cmd(self,m):
  if await self.owner(m):
   c=await self.target(m); r=await self.db.memory(c) if c else None; await m.answer((f"Проект: {r['project_type']}\nОписание: {r['project_description']}\nДля кого: {r['target_users_json']}\nФункции: {r['requirements_json']}\nБюджет: {r['budget']}\nСрок: {r['deadline']}\nРеференсы: {r['references_json']}\nОткрытые вопросы: {r['open_questions_json']}\nSummary: {r['summary']}" if r else 'Память не найдена')[:4000])
 async def memory_clear_cmd(self,m):
  if await self.owner(m):
   c=await self.target(m)
   if c: await self.db.memory_clear(c); await m.answer('Memory cleared.')
 async def lead_status(self,m):
  if await self.owner(m):
   p=(m.text or '').split();
   if len(p)>2: await self.db.save_memory(int(p[1]),lead_status=p[2]); await m.answer('Lead status updated.')
 async def daily_report(self,m,day=None):
  if await self.owner(m) and self.report:
   text,date,chats,messages=await self.report.build(day); await m.answer(text[:4000]);
 async def daily_report_yesterday(self,m):
  from datetime import timedelta
  await self.daily_report(m,(__import__('datetime').datetime.now(self.report.tz).date()-timedelta(days=1)))
 async def debug_context(self,m):
  if await self.owner(m):
   c=await self.target(m); mem=await self.db.memory(c) if c else None; await m.answer(f"KB retrieval is query-dependent\nMemory chars: {len((mem['summary'] if mem else '') or '')}\nRecent messages: {len(await self.db.history(c,self.settings.recent_message_limit)) if c else 0}")
 def cancel_batch(self,chat_id,mark_manual=False):
  task=self.pending_tasks.pop(chat_id,None)
  if task: task.cancel()
  self.batch_generation[chat_id]=self.batch_generation.get(chat_id,0)+1
 async def schedule_batch(self,chat_id,initial=None):
  self.cancel_batch(chat_id); generation=self.batch_generation[chat_id]; self.batch_first_at.setdefault(chat_id,time.monotonic())
  if chat_id not in self.batch_initial: self.batch_initial[chat_id]=bool(initial) if initial is not None else not await self.db.conversation_active(chat_id,self.settings.conversation_idle_reset_minutes)
  wait=self.settings.initial_reply_debounce_seconds if self.batch_initial[chat_id] else self.settings.active_reply_debounce_seconds
  async def runner():
   try: await asyncio.sleep(wait); await self.process_batch(chat_id,generation)
   except asyncio.CancelledError: return
   except Exception: log.exception("debounce batch failed chat=%s",chat_id)
  self.pending_tasks[chat_id]=asyncio.create_task(runner())
 async def process_batch(self,chat_id,generation):
  if self.batch_generation.get(chat_id)!=generation:return
  rows=await self.db.pending_messages(chat_id)
  if not rows:return
  r=await self.db.chat(chat_id)
  if not r or r['manual_pause_until'] and r['manual_pause_until']>time.time() or not r['ai_enabled'] or r['handoff_requested'] or not await self.global_on(): return
  allowed,notify=self.limiter.allow(r['user_id'] or chat_id)
  if not allowed:return
  text="Client sent several messages:\n"+"\n".join(f"- {x['content']}" for x in rows)
  await self.typing_for_chat(r)
  answer=await self.ai.reply(await self.db.history(chat_id,self.settings.recent_message_limit),chat_id,text)
  if self.batch_generation.get(chat_id)!=generation or await self.db.pending_messages(chat_id)!=rows:return
  if answer:
   await self.bot.send_message(chat_id=chat_id,text=answer,business_connection_id=r['business_connection_id'])
   await self.db.save_message(chat_id,'assistant',answer,None,r['business_connection_id'],r['user_id']); await self.db.mark_processed([x['id'] for x in rows])
  self.pending_tasks.pop(chat_id,None); self.batch_first_at.pop(chat_id,None); self.batch_initial.pop(chat_id,None)
 async def typing_for_chat(self,r): await self.bot.send_chat_action(chat_id=r['chat_id'],action=ChatAction.TYPING,business_connection_id=r['business_connection_id'])
 def main_keyboard(self):
  return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🟢 Включить AI",callback_data="admin:ai:on"),InlineKeyboardButton(text="🔴 Выключить AI",callback_data="admin:ai:off")],[InlineKeyboardButton(text="💬 Чаты",callback_data="admin:chats:0"),InlineKeyboardButton(text="⏸ Паузы",callback_data="admin:paused:0")],[InlineKeyboardButton(text="👤 Профиль",callback_data="admin:profile"),InlineKeyboardButton(text="🧠 База знаний",callback_data="admin:kb")],[InlineKeyboardButton(text="⭐ Доверенные",callback_data="admin:trusted"),InlineKeyboardButton(text="📊 Статус",callback_data="admin:status")],[InlineKeyboardButton(text="⚙️ Настройки",callback_data="admin:settings")]])
 async def panel_text(self):
  c=await self.db.counts(); return f"Казбек Assistant\n\nAI: {'🟢 Включён' if await self.global_on() else '🔴 Выключен'}\nTelegram Business: {'🟢 Подключён' if self.connections else '⚪ Не подключён'}\nЧатов: {c['total']}\nНа паузе: {c['paused']}\n\nВыберите действие:"
 async def edit_panel(self,q,text,markup=None):
  try: await q.message.edit_text(text,reply_markup=markup or self.main_keyboard())
  except TelegramBadRequest as e:
   if "message is not modified" not in str(e).lower(): raise
  await q.answer()
 async def handle_callback(self,q:CallbackQuery):
  if not q.from_user or q.from_user.id!=self.settings.owner_telegram_id: await q.answer("Недоступно",show_alert=True); return
  d=q.data.split(":")
  if d[0]!="admin": return
  if d[1]=="main": return await self.edit_panel(q,await self.panel_text())
  if d[1]=="noop": return await q.answer()
  if d[1]=="ai": await self.set_global(d[2]=="on"); return await self.edit_panel(q,await self.panel_text())
  if d[1]=="status": return await self.edit_panel(q,await self.status_text(),InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню",callback_data="admin:main")]]))
  if d[1]=="settings": return await self.edit_panel(q,f"⚙️ Настройки\n\nПервый ответ: {self.settings.initial_reply_debounce_seconds:g} сек\nСледующие ответы: {self.settings.active_reply_debounce_seconds:g} сек\nСброс активного диалога: {self.settings.conversation_idle_reset_minutes:g} мин\nРучная пауза после ответа Казбека: {self.settings.human_takeover_minutes} мин\nПамять: {self.settings.recent_message_limit} сообщений\nОтчёт: 00:00\nЧасовой пояс: {self.settings.app_timezone}",InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню",callback_data="admin:main")]]))
  if d[1]=="profile": return await self.edit_panel(q,"👤 Профиль Казбека\n\n"+"\n".join(f"{k}: {v}" for k,v in (await self.db.profile_all()).items()),InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню",callback_data="admin:main")]]))
  if d[1] in {"knowledge","kb"}:
   rows=await self.db.kb_all(); counts={}
   for r in rows: counts[r['category']]=counts.get(r['category'],0)+1
   return await self.edit_panel(q,"🧠 База знаний\nКарточек: "+str(len(rows))+"\n\n"+"\n".join(f"{k}: {v}" for k,v in sorted(counts.items())),InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню",callback_data="admin:main")]]))
  if d[1]=="trusted":
   rows=[r for r in await self.db.trusted_all() if r['enabled']]; text="Trusted contacts\n\n"+"\n".join(f"{r['display_name'] or 'Contact'} @{r['username'] or '-'} · {r['telegram_user_id'] or r['chat_id']}" for r in rows)
   return await self.edit_panel(q,text or "⭐ Доверенные контакты\n\nПока нет доверенных контактов.",InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню",callback_data="admin:main")]]))
  if d[1] in {"chats","paused"}: return await self.render_chats(q,int(d[2]) if len(d)>2 else 0,d[1]=="paused")
  if d[1]=="chat": return await self.chat_callback(q,d)
 async def render_chats(self,q,page,paused=False):
  rows=await self.db.chats(100); rows=[r for r in rows if not paused or not r["ai_enabled"] or r["handoff_requested"] or (r["manual_pause_until"] and r["manual_pause_until"]>time.time())]; size=8; pages=max(1,(len(rows)+size-1)//size); page=min(page,pages-1); chunk=rows[page*size:(page+1)*size]; buttons=[[InlineKeyboardButton(text=f"{r['first_name'] or 'Client'} · @{r['username'] or '-'} · {'🟢' if r['ai_enabled'] else '🔴'}",callback_data=f"admin:chat:{r['chat_id']}")] for r in chunk]; nav=[]
  if page: nav.append(InlineKeyboardButton(text="◀️",callback_data=f"admin:{'paused' if paused else 'chats'}:{page-1}"))
  nav.append(InlineKeyboardButton(text=f"Page {page+1}/{pages}",callback_data="admin:noop"))
  if page+1<pages: nav.append(InlineKeyboardButton(text="▶️",callback_data=f"admin:{'paused' if paused else 'chats'}:{page+1}"))
  buttons += [nav,[InlineKeyboardButton(text="🏠 Главное меню",callback_data="admin:main")]]; await self.edit_panel(q,"⏸ Паузы" if paused else "💬 Чаты",InlineKeyboardMarkup(inline_keyboard=buttons))
 async def chat_callback(self,q,d):
  if len(d)==3:
   row=await self.db.chat(int(d[2]));
   if not row:return await q.answer("Chat not found",show_alert=True)
   buttons=[[InlineKeyboardButton(text="🔴 Выключить AI" if row["ai_enabled"] else "🟢 Включить AI",callback_data=f"admin:chat:{'off' if row['ai_enabled'] else 'on'}:{row['chat_id']}" )],[InlineKeyboardButton(text="⏸ Пауза 1 час",callback_data=f"admin:chat:pause60:{row['chat_id']}"),InlineKeyboardButton(text="🤝 Передать Казбеку" if not row['handoff_requested'] else "↩️ Вернуть AI",callback_data=f"admin:chat:{'handoff' if not row['handoff_requested'] else 'return'}:{row['chat_id']}")],[InlineKeyboardButton(text="🧹 Очистить историю",callback_data=f"admin:chat:history:{row['chat_id']}"),InlineKeyboardButton(text="🗑 Забыть чат",callback_data=f"admin:chat:forget:{row['chat_id']}")],[InlineKeyboardButton(text="◀️ Назад",callback_data="admin:chats:0")]]
   pause_text=(time.strftime('%H:%M',time.localtime(row['manual_pause_until'])) if row['manual_pause_until'] and row['manual_pause_until']>time.time() else 'нет')
   return await self.edit_panel(q,f"Чат: {row['first_name'] or 'Клиент'}\nUsername: @{row['username'] or '-'}\nЯзык: {row['language'] or '-'}\nAI: {'🟢 Включён' if row['ai_enabled'] else '🔴 Выключен'}\nПередача Казбеку: {'Да' if row['handoff_requested'] else 'Нет'}\nРучная пауза: {pause_text}\nСообщений: {await self.db.message_count(row['chat_id'])}",InlineKeyboardMarkup(inline_keyboard=buttons))
  action,chat=d[2],int(d[3]);
  if action=="on": await self.db.set_chat(chat,ai_enabled=1)
  elif action=="off": await self.db.set_chat(chat,ai_enabled=0)
  elif action=="pause60": await self.db.set_chat(chat,manual_pause_until=time.time()+3600)
  elif action=="handoff": await self.db.set_chat(chat,handoff_requested=1)
  elif action=="return": await self.db.set_chat(chat,handoff_requested=0)
  elif action=="history": await self.db.clear_history(chat)
  elif action=="forget": await self.db.forget_chat(chat); return await self.edit_panel(q,"Chat forgotten",InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Back",callback_data="admin:chats:0")]]))
  await self.chat_callback(q,["admin","chat",str(chat)])
 async def handle_business(self,m):
  try:
   started=time.monotonic()
   if not m.business_connection_id or not m.chat or m.chat.type!="private" or not m.from_user:return
   key=f"business:{m.business_connection_id}:{m.chat.id}:{m.message_id}";
   if await self.db.seen(key):return
   await self.db.upsert_chat(m.chat.id,m.business_connection_id,m.from_user.id,m.from_user.username,m.from_user.first_name,m.from_user.last_name,m.from_user.language_code)
   text=m.text or m.caption; log.info("business message chat=%s user=%s chars=%s",m.chat.id,m.from_user.id,len(text or ""))
   if not text:return
   lowered=text.lower().strip(); previous=(await self.db.chat(m.chat.id))['language']
   lang,confidence=detect_language(text,previous); supported,_,_=language_supported(text)
   if confidence: await self.db.set_chat(m.chat.id,language=lang)
   control=control_action(text); sender_business_bot=getattr(m,'sender_business_bot',None); bot_generated=bool(sender_business_bot) or (m.from_user and m.from_user.id==self.bot.id); owner_message=m.from_user.id==self.settings.owner_telegram_id and not bot_generated
   if control=='stop':
    await self.db.set_chat(m.chat.id,ai_enabled=0,handoff_requested=0,manual_pause_until=None)
    log.info("Business chat %s: AI disabled by %s control phrase",m.chat.id,'owner' if owner_message else 'client')
    if not owner_message: await self.send(m,"окей, больше не буду отвечать)")
    return
   if control=='start':
    await self.db.set_chat(m.chat.id,ai_enabled=1,handoff_requested=0,manual_pause_until=None)
    log.info("Business chat %s: AI enabled by %s control phrase",m.chat.id,'owner' if owner_message else 'client')
    if not owner_message: await self.send(m,"окей, я снова тут)")
    return
   if owner_message:
    self.cancel_batch(m.chat.id)
    pending=await self.db.pending_messages(m.chat.id); await self.db.mark_processed([x['id'] for x in pending],manual=True)
    await self.db.save_message(m.chat.id,"owner",text,m.message_id,m.business_connection_id,m.from_user.id,username=m.from_user.username,first_name=m.from_user.first_name,last_name=m.from_user.last_name,language=lang)
    if self.memory: await self.memory.update(m.chat.id,text,role='owner')
    await self.db.set_chat(m.chat.id,manual_pause_until=time.time()+self.settings.human_takeover_minutes*60)
    log.info("Business chat %s: manual owner takeover until=%s",m.chat.id,int(time.time()+self.settings.human_takeover_minutes*60)); return
   trusted=await self.db.trusted_get(m.chat.id) or await self.db.trusted_get(m.from_user.id)
   if trusted: return
   if any(p in lowered for p in ENABLE):
    await self.db.set_chat(m.chat.id,ai_enabled=1,handoff_requested=0,manual_pause_until=None); await self.send(m,"я снова тут)"); return
   if any(p in lowered for p in OPT_OUT):
    await self.db.set_chat(m.chat.id,ai_enabled=0,handoff_requested=1); await self.send(m,"окей, больше не буду отвечать)"); return
   if any(p in lowered for p in HANDOFF): await self.db.set_chat(m.chat.id,handoff_requested=1); await self.send(m,"понял, передам Казбеку)"); return
   conversation_was_active=await self.db.conversation_active(m.chat.id,self.settings.conversation_idle_reset_minutes)
   saved_id=await self.db.save_message(m.chat.id,"user",text,m.message_id,m.business_connection_id,m.from_user.id,username=m.from_user.username,first_name=m.from_user.first_name,last_name=m.from_user.last_name,language=lang)
   if self.memory:
    await self.memory.update(m.chat.id,text)
    await self.memory.maybe_summarize(m.chat.id)
   r=await self.db.chat(m.chat.id)
   if not await self.global_on() or not r['ai_enabled'] or r['handoff_requested'] or (r['manual_pause_until'] and r['manual_pause_until']>time.time()):
    await self.db.mark_processed([saved_id],manual=bool(r['manual_pause_until'] and r['manual_pause_until']>time.time())); return
   await self.schedule_batch(m.chat.id,initial=not conversation_was_active)
  except Exception: log.exception("failed business update")
 async def send(self,m,text): await self.bot.send_message(chat_id=m.chat.id,text=text,business_connection_id=m.business_connection_id,reply_parameters={"message_id":m.message_id})
 async def typing(self,m): await self.bot.send_chat_action(chat_id=m.chat.id,action=ChatAction.TYPING,business_connection_id=m.business_connection_id)
 async def run(self): await self.dp.start_polling(self.bot,allowed_updates=["business_connection","business_message","edited_business_message","deleted_business_messages","message"],handle_signals=True)
 async def close(self):
  tasks=list(self.pending_tasks.values())
  self.pending_tasks.clear()
  for task in tasks: task.cancel()
  if tasks: await asyncio.gather(*tasks,return_exceptions=True)
  if self.ai: await self.ai.close()
  await self.db.close()
  await self.bot.session.close()
