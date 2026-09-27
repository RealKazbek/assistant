import time
from pathlib import Path
import aiosqlite

class Database:
    def __init__(self, path: str): self.path, self.conn = path, None
    async def connect(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True); self.conn = await aiosqlite.connect(self.path); self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at REAL NOT NULL); CREATE TABLE IF NOT EXISTS profile (key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at REAL NOT NULL); CREATE TABLE IF NOT EXISTS conversations (chat_id INTEGER PRIMARY KEY,business_connection_id TEXT,user_id INTEGER,username TEXT,first_name TEXT,last_name TEXT,language TEXT,ai_enabled INTEGER NOT NULL DEFAULT 1,handoff_requested INTEGER NOT NULL DEFAULT 0,manual_pause_until REAL,created_at REAL NOT NULL,updated_at REAL NOT NULL); CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,telegram_message_id INTEGER,created_at REAL NOT NULL); CREATE TABLE IF NOT EXISTS processed_updates (update_key TEXT PRIMARY KEY,created_at REAL NOT NULL); CREATE TABLE IF NOT EXISTS trusted_contacts (id INTEGER PRIMARY KEY,telegram_user_id INTEGER UNIQUE,chat_id INTEGER UNIQUE,username TEXT,display_name TEXT,note TEXT,enabled INTEGER DEFAULT 1,created_at REAL NOT NULL,updated_at REAL NOT NULL); CREATE TABLE IF NOT EXISTS knowledge_cards (id INTEGER PRIMARY KEY,key TEXT UNIQUE,category TEXT,title TEXT,content TEXT,tags TEXT,priority INTEGER DEFAULT 0,enabled INTEGER DEFAULT 1,created_at REAL NOT NULL,updated_at REAL NOT NULL); CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(key UNINDEXED,category,title,content,tags); CREATE TABLE IF NOT EXISTS conversation_memory (chat_id INTEGER PRIMARY KEY,summary TEXT,client_intent TEXT,project_type TEXT,budget TEXT,deadline TEXT,lead_status TEXT DEFAULT 'unknown',requirements_json TEXT,open_questions_json TEXT,important_facts_json,last_summary_message_id INTEGER,last_summary_at REAL,updated_at REAL NOT NULL); CREATE TABLE IF NOT EXISTS daily_reports (report_date TEXT PRIMARY KEY,sent_at REAL NOT NULL,chat_count INTEGER,message_count INTEGER); CREATE TABLE IF NOT EXISTS ai_usage (id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,request_type TEXT,prompt_tokens INTEGER,completion_tokens INTEGER,total_tokens INTEGER,created_at REAL NOT NULL); CREATE INDEX IF NOT EXISTS idx_messages_chat_time ON messages(chat_id,created_at);""")
        cur=await self.conn.execute("PRAGMA table_info(conversations)"); cols={r[1] for r in await cur.fetchall()}
        for name, definition in {"username":"TEXT","first_name":"TEXT","last_name":"TEXT","language":"TEXT","ai_enabled":"INTEGER NOT NULL DEFAULT 1","handoff_requested":"INTEGER NOT NULL DEFAULT 0","manual_pause_until":"REAL","conversation_type":"TEXT DEFAULT 'unknown'","last_client_message_at":"REAL","last_ai_reply_at":"REAL","last_activity_at":"REAL"}.items():
            if name not in cols: await self.conn.execute(f"ALTER TABLE conversations ADD COLUMN {name} {definition}")
        if await self.get_setting("ai_enabled") is None: await self.set_setting("ai_enabled","true")
        cur=await self.conn.execute("PRAGMA table_info(messages)"); mcols={r[1] for r in await cur.fetchall()}
        for name, definition in {"processed_for_reply":"INTEGER NOT NULL DEFAULT 0","covered_by_manual_takeover":"INTEGER NOT NULL DEFAULT 0"}.items():
            if name not in mcols: await self.conn.execute(f"ALTER TABLE messages ADD COLUMN {name} {definition}")
        for name, definition in {"project_description":"TEXT","target_users_json":"TEXT","references_json":"TEXT","owner_agreed_price":"TEXT","owner_agreed_deadline":"TEXT","owner_agreed_scope":"TEXT"}.items():
            cur=await self.conn.execute("PRAGMA table_info(conversation_memory)"); cols={r[1] for r in await cur.fetchall()}
            if name not in cols: await self.conn.execute(f"ALTER TABLE conversation_memory ADD COLUMN {name} {definition}")
        await self.conn.commit()
    async def close(self):
        if self.conn: await self.conn.close()
    async def get_setting(self,key,default=None):
        row=await (await self.conn.execute("SELECT value FROM settings WHERE key=?",(key,))).fetchone(); return row[0] if row else default
    async def set_setting(self,key,value): await self.conn.execute("INSERT INTO settings VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(key,str(value),time.time())); await self.conn.commit()
    async def profile_all(self): return {r[0]:r[1] for r in await (await self.conn.execute("SELECT key,value FROM profile ORDER BY key")).fetchall()}
    async def profile_set(self,key,value): await self.conn.execute("INSERT INTO profile VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(key,value,time.time())); await self.conn.commit()
    async def profile_delete(self,key): await self.conn.execute("DELETE FROM profile WHERE key=?",(key,)); await self.conn.commit()
    async def trusted_add(self,chat_id=None,user_id=None,username=None,display_name=None,note=None):
        now=time.time(); await self.conn.execute("INSERT INTO trusted_contacts(chat_id,telegram_user_id,username,display_name,note,enabled,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?) ON CONFLICT(chat_id) DO UPDATE SET telegram_user_id=COALESCE(excluded.telegram_user_id,telegram_user_id),username=COALESCE(excluded.username,username),display_name=COALESCE(excluded.display_name,display_name),note=COALESCE(excluded.note,note),enabled=1,updated_at=excluded.updated_at",(chat_id,user_id,username,display_name,note,now,now)); await self.conn.commit()
    async def trusted_get(self,identifier):
        try: row=await (await self.conn.execute("SELECT * FROM trusted_contacts WHERE (chat_id=? OR telegram_user_id=?) AND enabled=1",(int(identifier),int(identifier)))).fetchone()
        except ValueError: row=await (await self.conn.execute("SELECT * FROM trusted_contacts WHERE username=? AND enabled=1",(identifier.lstrip('@'),))).fetchone()
        return row
    async def trusted_all(self): return await (await self.conn.execute("SELECT * FROM trusted_contacts ORDER BY display_name,username")).fetchall()
    async def trusted_remove(self,identifier):
        row=await self.trusted_get(identifier)
        if row: await self.conn.execute("UPDATE trusted_contacts SET enabled=0,updated_at=? WHERE id=?",(time.time(),row['id'])); await self.conn.commit()
        return row
    async def trusted_note(self,identifier,note):
        row=await self.trusted_get(identifier)
        if row: await self.conn.execute("UPDATE trusted_contacts SET note=?,updated_at=? WHERE id=?",(note,time.time(),row['id'])); await self.conn.commit()
    async def trusted_count(self): return (await (await self.conn.execute("SELECT COUNT(*) FROM trusted_contacts WHERE enabled=1")).fetchone())[0]
    async def kb_upsert(self,key,category,title,content,tags="",priority=0):
        now=time.time(); await self.conn.execute("INSERT INTO knowledge_cards(key,category,title,content,tags,priority,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,1,?,?) ON CONFLICT(key) DO UPDATE SET category=excluded.category,title=excluded.title,content=excluded.content,tags=excluded.tags,priority=excluded.priority,updated_at=excluded.updated_at",(key,category,title,content,tags,priority,now,now)); await self.conn.execute("DELETE FROM knowledge_fts WHERE key=?",(key,)); await self.conn.execute("INSERT INTO knowledge_fts(key,category,title,content,tags) VALUES(?,?,?,?,?)",(key,category,title,content,tags)); await self.conn.commit()
    async def kb_search(self,query,limit=4):
        terms=" ".join("\""+x.replace('"','')+"*\"" for x in query.lower().split() if len(x)>2) or "*"; rows=await (await self.conn.execute("SELECT k.* FROM knowledge_fts f JOIN knowledge_cards k ON k.key=f.key WHERE k.enabled=1 AND knowledge_fts MATCH ? ORDER BY k.priority DESC LIMIT ?",(terms,limit))).fetchall(); return rows
    async def kb_all(self): return await (await self.conn.execute("SELECT * FROM knowledge_cards ORDER BY category,priority DESC,key")).fetchall()
    async def kb_get(self,key): return await (await self.conn.execute("SELECT * FROM knowledge_cards WHERE key=?",(key,))).fetchone()
    async def kb_set_enabled(self,key,enabled): await self.conn.execute("UPDATE knowledge_cards SET enabled=?,updated_at=? WHERE key=?",(int(enabled),time.time(),key)); await self.conn.commit()
    async def kb_delete(self,key): await self.conn.execute("DELETE FROM knowledge_fts WHERE key=?",(key,)); await self.conn.execute("DELETE FROM knowledge_cards WHERE key=?",(key,)); await self.conn.commit()
    async def memory(self,chat_id): return await (await self.conn.execute("SELECT * FROM conversation_memory WHERE chat_id=?",(chat_id,))).fetchone()
    async def save_memory(self,chat_id,**v):
        now=time.time(); await self.conn.execute("INSERT INTO conversation_memory(chat_id,summary,client_intent,project_type,project_description,target_users_json,budget,deadline,references_json,lead_status,requirements_json,open_questions_json,important_facts_json,owner_agreed_price,owner_agreed_deadline,owner_agreed_scope,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET summary=COALESCE(excluded.summary,summary),client_intent=COALESCE(excluded.client_intent,client_intent),project_type=COALESCE(excluded.project_type,project_type),project_description=COALESCE(excluded.project_description,project_description),target_users_json=COALESCE(excluded.target_users_json,target_users_json),budget=COALESCE(excluded.budget,budget),deadline=COALESCE(excluded.deadline,deadline),references_json=COALESCE(excluded.references_json,references_json),lead_status=COALESCE(excluded.lead_status,lead_status),requirements_json=COALESCE(excluded.requirements_json,requirements_json),open_questions_json=COALESCE(excluded.open_questions_json,open_questions_json),important_facts_json=COALESCE(excluded.important_facts_json,important_facts_json),owner_agreed_price=COALESCE(excluded.owner_agreed_price,owner_agreed_price),owner_agreed_deadline=COALESCE(excluded.owner_agreed_deadline,owner_agreed_deadline),owner_agreed_scope=COALESCE(excluded.owner_agreed_scope,owner_agreed_scope),last_summary_message_id=COALESCE(excluded.last_summary_message_id,last_summary_message_id),last_summary_at=COALESCE(excluded.last_summary_at,last_summary_at),updated_at=excluded.updated_at",(chat_id,v.get("summary"),v.get("client_intent"),v.get("project_type"),v.get("project_description"),v.get("target_users_json"),v.get("budget"),v.get("deadline"),v.get("references_json"),v.get("lead_status","unknown"),v.get("requirements_json","[]"),v.get("open_questions_json","[]"),v.get("important_facts_json","[]"),v.get("owner_agreed_price"),v.get("owner_agreed_deadline"),v.get("owner_agreed_scope"),now)); await self.conn.commit()
    async def memory_clear(self,chat_id): await self.conn.execute("DELETE FROM conversation_memory WHERE chat_id=?",(chat_id,)); await self.conn.commit()
    async def meaningful_since(self,chat_id,last_id=0): return (await (await self.conn.execute("SELECT COUNT(*) FROM messages WHERE chat_id=? AND id>? AND role='user'",(chat_id,last_id))).fetchone())[0]
    async def last_message_id(self,chat_id):
        row=await (await self.conn.execute("SELECT MAX(id) FROM messages WHERE chat_id=?",(chat_id,))).fetchone(); return row[0] or 0
    async def report_sent(self,date): return bool(await (await self.conn.execute("SELECT 1 FROM daily_reports WHERE report_date=?",(date,))).fetchone())
    async def mark_report(self,date,chats,messages): await self.conn.execute("INSERT OR REPLACE INTO daily_reports VALUES(?,?,?,?)",(date,time.time(),chats,messages)); await self.conn.commit()
    async def upsert_chat(self,chat_id,business_connection_id=None,user_id=None,username=None,first_name=None,last_name=None,language=None):
        now=time.time(); await self.conn.execute("INSERT INTO conversations(chat_id,business_connection_id,user_id,username,first_name,last_name,language,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET business_connection_id=COALESCE(excluded.business_connection_id,business_connection_id),user_id=COALESCE(excluded.user_id,user_id),username=COALESCE(excluded.username,username),first_name=COALESCE(excluded.first_name,first_name),last_name=COALESCE(excluded.last_name,last_name),language=COALESCE(excluded.language,language),updated_at=excluded.updated_at",(chat_id,business_connection_id,user_id,username,first_name,last_name,language,now,now)); await self.conn.commit()
    async def chat(self,chat_id): return await (await self.conn.execute("SELECT * FROM conversations WHERE chat_id=?",(chat_id,))).fetchone()
    async def chats(self,limit=30): return await (await self.conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?",(limit,))).fetchall()
    async def set_chat(self,chat_id,**values):
        allowed={k:v for k,v in values.items() if k in {"ai_enabled","handoff_requested","manual_pause_until","language","conversation_type"}}
        if allowed: await self.conn.execute("UPDATE conversations SET "+",".join(f"{k}=?" for k in allowed)+",updated_at=? WHERE chat_id=?",(*allowed.values(),time.time(),chat_id)); await self.conn.commit()
    async def set_handoff(self, chat_id, until): await self.set_chat(chat_id, manual_pause_until=until)
    async def handoff_active(self, chat_id):
        row=await self.chat(chat_id); return bool(row and row["manual_pause_until"] and row["manual_pause_until"]>time.time())
    async def seen(self,key):
        if await (await self.conn.execute("SELECT 1 FROM processed_updates WHERE update_key=?",(key,))).fetchone(): return True
        await self.conn.execute("INSERT INTO processed_updates VALUES(?,?)",(key,time.time())); await self.conn.commit(); return False
    async def save_message(self,chat_id,role,content,telegram_message_id=None,business_connection_id=None,user_id=None,**user):
        await self.upsert_chat(chat_id,business_connection_id,user_id,**user); now=time.time(); cur=await self.conn.execute("INSERT INTO messages(chat_id,role,content,telegram_message_id,created_at) VALUES(?,?,?,?,?)",(chat_id,role,content,telegram_message_id,now));
        if role=='user': await self.conn.execute("UPDATE conversations SET last_client_message_at=?,last_activity_at=? WHERE chat_id=?",(now,now,chat_id))
        elif role=='assistant': await self.conn.execute("UPDATE conversations SET last_ai_reply_at=?,last_activity_at=? WHERE chat_id=?",(now,now,chat_id))
        else: await self.conn.execute("UPDATE conversations SET last_activity_at=? WHERE chat_id=?",(now,chat_id))
        await self.conn.commit(); return cur.lastrowid
    async def conversation_active(self,chat_id,idle_minutes):
        r=await self.chat(chat_id); return bool(r and r['last_ai_reply_at'] and r['last_activity_at'] and time.time()-r['last_activity_at'] < idle_minutes*60)
    async def pending_messages(self,chat_id): return await (await self.conn.execute("SELECT * FROM messages WHERE chat_id=? AND role='user' AND processed_for_reply=0 AND covered_by_manual_takeover=0 ORDER BY id",(chat_id,))).fetchall()
    async def mark_processed(self,ids,manual=False):
        if ids: await self.conn.execute(f"UPDATE messages SET processed_for_reply=1,covered_by_manual_takeover=? WHERE id IN ({','.join('?' for _ in ids)})",(1 if manual else 0,*ids)); await self.conn.commit()
    async def history(self,chat_id,limit): return [dict(r) for r in reversed(await (await self.conn.execute("SELECT role,content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",(chat_id,limit))).fetchall())]
    async def message_count(self,chat_id): return (await (await self.conn.execute("SELECT COUNT(*) FROM messages WHERE chat_id=?",(chat_id,))).fetchone())[0]
    async def clear_history(self,chat_id): await self.conn.execute("DELETE FROM messages WHERE chat_id=?",(chat_id,)); await self.conn.commit()
    async def forget_chat(self,chat_id): await self.conn.execute("DELETE FROM messages WHERE chat_id=?",(chat_id,)); await self.conn.execute("DELETE FROM conversations WHERE chat_id=?",(chat_id,)); await self.conn.commit()
    async def counts(self):
        q=lambda sql,args=(): self.conn.execute(sql,args)
        total=(await (await q("SELECT COUNT(*) FROM conversations")).fetchone())[0]; processed=(await (await q("SELECT COUNT(*) FROM processed_updates")).fetchone())[0]; enabled=(await (await q("SELECT COUNT(*) FROM conversations WHERE ai_enabled=1")).fetchone())[0]; paused=(await (await q("SELECT COUNT(*) FROM conversations WHERE manual_pause_until>?",(time.time(),))).fetchone())[0]; handoff=(await (await q("SELECT COUNT(*) FROM conversations WHERE handoff_requested=1")).fetchone())[0]
        return {"total":total,"enabled":enabled,"disabled":total-enabled,"paused":paused,"handoff":handoff,"processed":processed}
