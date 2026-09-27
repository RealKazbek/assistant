import json, re, time

class MemoryService:
    def __init__(self,db,settings): self.db=db; self.settings=settings
    async def context(self,chat_id):
        r=await self.db.memory(chat_id)
        if not r:return ""
        return (f"Project: {r['project_type'] or 'unknown'}\nDescription: {r['project_description'] or 'unknown'}\nAudience: {r['target_users_json'] or '[]'}\nKnown requirements: {r['requirements_json'] or '[]'}\nBudget: {r['budget'] or 'unknown'}\nDeadline: {r['deadline'] or 'unknown'}\nReferences: {r['references_json'] or '[]'}\nOpen questions: {r['open_questions_json'] or '[]'}\nOwner facts: {r['important_facts_json'] or '[]'}\nOwner agreed price: {r['owner_agreed_price'] or 'unknown'}\nOwner agreed deadline: {r['owner_agreed_deadline'] or 'unknown'}\nSummary: {(r['summary'] or '')[:self.settings.max_memory_summary_chars]}")[:self.settings.max_memory_summary_chars+1400]
    async def update(self,chat_id,text,role='user'):
        r=await self.db.memory(chat_id); old=dict(r) if r else {}; low=text.lower()
        if role=='owner':
            price=re.search(r'(\d[\d\s]{2,})\s*(?:к|кк|kzt|тенге)',low); deadline=re.search(r'(?:до|к)\s*(\d{1,2}\s*[а-я]+)',low)
            await self.db.save_memory(chat_id,owner_agreed_price=(price.group(1).replace(' ','')+' KZT') if price else None,owner_agreed_deadline=deadline.group(1) if deadline else None,owner_agreed_scope=text,important_facts_json=json.dumps([text],ensure_ascii=False)); return
        project=old.get('project_type'); description=old.get('project_description'); audience=json.loads(old.get('target_users_json') or '[]'); req=json.loads(old.get('requirements_json') or '[]'); refs=json.loads(old.get('references_json') or '[]')
        if 'платонус' in low or 'platonus' in low: project='education_platform'; description='сайт/система, похожая на Platonus'
        elif 'бот' in low: project='telegram_bot'
        elif 'лендинг' in low: project='landing'
        elif 'сайт' in low and not project: project='website'
        if any(x in low for x in ('учител','учени','студент','школ')): audience += [x for x in ('учителя' if 'учител' in low else '', 'ученики' if 'учени' in low or 'студент' in low else '') if x and x not in audience]
        if any(x in low for x in ('личный кабинет','кабинет','авторизац','вход')) and 'личный кабинет' not in req: req.append('личный кабинет')
        for item,words in [('каталог',('каталог',)),('уведомления',('уведомлен',)),('оценки',('оценк',)),('расписание',('расписан',)),('админ-панель',('админ',))]:
            if any(w in low for w in words) and item not in req:req.append(item)
        price=re.search(r'(\d[\d\s]{2,})\s*(?:к|кк|kzt|тенге)',low); date=re.search(r'(?:до|к)\s*(\d{1,2}\s*[а-я]+)',low)
        if 'http' in low: refs.append(text.strip())
        intent='hire_developer' if any(x in low for x in ('нужен','хочу','надо','сделать','разработ')) else old.get('client_intent')
        summary=(old.get('summary') or '')+' '+text; summary=summary.strip()[-self.settings.max_memory_summary_chars:]
        await self.db.save_memory(chat_id,summary=summary,client_intent=intent,project_type=project,project_description=description,target_users_json=json.dumps(audience,ensure_ascii=False),budget=(price.group(1).replace(' ','')+' KZT') if price else None,deadline=date.group(1) if date else None,references_json=json.dumps(refs,ensure_ascii=False),lead_status='qualifying' if intent=='hire_developer' else old.get('lead_status','unknown'),requirements_json=json.dumps(req,ensure_ascii=False),open_questions_json=old.get('open_questions_json','[]'),important_facts_json=old.get('important_facts_json','[]'))
    async def maybe_summarize(self,chat_id):
        r=await self.db.memory(chat_id); last=r['last_summary_message_id'] if r else 0
        if await self.db.meaningful_since(chat_id,last) < self.settings.summary_trigger_new_messages:return False
        messages=await self.db.history(chat_id,self.settings.recent_message_limit); text=' '.join(x['content'] for x in messages if x['role'] in ('user','owner'))
        await self.db.save_memory(chat_id,summary=text[-self.settings.max_memory_summary_chars:],last_summary_message_id=await self.db.last_message_id(chat_id),last_summary_at=time.time()); return True
