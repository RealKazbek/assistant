import pytest
from app.config import load_settings
from app.services.rate_limit import RateLimiter
def test_config(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN","x"); monkeypatch.setenv("DEEPSEEK_API_KEY","y"); monkeypatch.setenv("OWNER_TELEGRAM_ID","7"); assert load_settings().owner_telegram_id==7
def test_rate_limit():
    r=RateLimiter(2,60); assert r.allow(1)[0]; assert r.allow(1)[0]; assert not r.allow(1)[0]; assert r.allow(2)[0]
@pytest.mark.asyncio
async def test_db_isolation_and_trim(tmp_path):
    from app.db.database import Database
    d=Database(str(tmp_path/"x.db")); await d.connect()
    for i in range(4): await d.save_message(1,"user",str(i))
    await d.save_message(2,"user","other"); assert [x["content"] for x in await d.history(1,2)]==["2","3"]; assert (await d.history(2,12))[0]["content"]=="other"; await d.close()
@pytest.mark.asyncio
async def test_duplicate(tmp_path):
    from app.db.database import Database
    d=Database(str(tmp_path/"x.db")); await d.connect(); assert not await d.seen("a"); assert await d.seen("a"); await d.close()
@pytest.mark.asyncio
async def test_handoff(tmp_path):
    import time
    from app.db.database import Database
    d=Database(str(tmp_path/"x.db")); await d.connect(); await d.save_message(1,"user","x"); await d.set_handoff(1,time.time()+60); assert await d.handoff_active(1); await d.close()

@pytest.mark.asyncio
async def test_persistent_controls_and_profile(tmp_path):
    from app.db.database import Database
    path=str(tmp_path/"state.db")
    d=Database(path); await d.connect(); await d.set_setting("ai_enabled", "false"); await d.upsert_chat(10, user_id=2, username="client"); await d.set_chat(10, ai_enabled=0, handoff_requested=1, manual_pause_until=9999999999); await d.profile_set("role", "Developer"); await d.close()
    d=Database(path); await d.connect(); assert await d.get_setting("ai_enabled")=="false"; row=await d.chat(10); assert row["ai_enabled"]==0 and row["handoff_requested"]==1; assert (await d.profile_all())["role"]=="Developer"; await d.close()

@pytest.mark.asyncio
async def test_profile_is_in_prompt():
    from unittest.mock import AsyncMock
    from app.services.deepseek import DeepSeekService
    class S: deepseek_api_key="x"; deepseek_base_url="http://localhost"; deepseek_model="m"; max_output_tokens=3
    async def profile(): return {"role":"Developer"}
    service=DeepSeekService(S(), profile); service.client.chat.completions.create=AsyncMock(return_value=type("R",(),{"choices":[type("C",(),{"message":type("M",(),{"content":"ok"})()})()]})())
    assert await service.reply([{"role":"user","content":"hi"}])=="ok"; sent=service.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]; assert "Developer" in sent; await service.close()

def test_reply_wait_never_adds_delay_after_slow_generation():
    from app.services.timing import reply_wait
    assert reply_wait(0, 6, 4, 6, rng=lambda a,b: b) == 0
    assert 4 <= reply_wait(0, 0, 4, 6, rng=lambda a,b: a) <= 4

def test_personal_and_language_classifier():
    from app.services.classifier import classify_intent, language_supported, personal_fallback, identity_reply, control_action, is_symbol_only, symbol_reply, simple_reply
    assert classify_intent("где ты?")=="personal"
    assert classify_intent("где ты? сайт нужен")=="business"
    assert classify_intent("ты спишь?")=="personal"
    assert language_supported("сәлем")[0] and language_supported("hello")[0]
    assert not language_supported("你好")[0]
    fallback=personal_fallback("ru"); assert fallback.endswith(")") or "👌" in fallback
    assert identity_reply("ru") in ("я ассистент Казбека)","ассистент Казбека 👋")
    assert sum(personal_fallback("ru").count(x) for x in ("👋","🙂","👌","👍","😂","🤝","🔥","✨","🚀")) <= 1
    assert control_action("  ИИ СТОП. ")=="stop" and control_action("старт ии!")=="start"
    assert symbol_reply("?") == "что?)" and is_symbol_only("👍") and not language_supported("?")[0]
    assert language_supported("React?")[0] and language_supported("Go API")[0]
    assert simple_reply("да")=="понял)"
    assert simple_reply("алеее")=="я тут)"
    assert simple_reply("ты тут?")=="я тут)"
    assert simple_reply("сайт сделай мне") is None

@pytest.mark.asyncio
async def test_trusted_persists(tmp_path):
    from app.db.database import Database
    path=str(tmp_path/"trusted.db"); d=Database(path); await d.connect(); await d.trusted_add(chat_id=42,user_id=7,username="friend",display_name="Friend",note="family"); await d.close()
    d=Database(path); await d.connect(); row=await d.trusted_get(7); assert row["username"]=="friend" and row["note"]=="family"; await d.trusted_remove(7); assert await d.trusted_get(7) is None; await d.close()

@pytest.mark.asyncio
async def test_structured_memory_extracts_and_survives_restart(tmp_path):
    from app.db.database import Database
    from app.services.memory import MemoryService
    class S: max_memory_summary_chars=2000; summary_trigger_new_messages=8; recent_message_limit=6
    path=str(tmp_path/"memory.db"); d=Database(path); await d.connect(); mem=MemoryService(d,S())
    for text in ("мне нужен сайт", "как платонус", "для учителей и учеников", "нужны личные кабинеты", "бюджет 100к", "до 15 октября"):
        await d.save_message(1,"user",text); await mem.update(1,text)
    await d.close(); d=Database(path); await d.connect(); row=await d.memory(1); assert row["project_type"]=="education_platform"; assert "учителя" in row["target_users_json"]; assert "личный кабинет" in row["requirements_json"]; assert row["budget"]; assert row["deadline"]=="15 октября"; await d.close()

@pytest.mark.asyncio
async def test_conversation_mode_uses_last_ai_reply(tmp_path):
    import time
    from app.db.database import Database
    d=Database(str(tmp_path/"mode.db")); await d.connect(); await d.save_message(1,"user","привет"); assert not await d.conversation_active(1,60); await d.save_message(1,"assistant","привет)"); assert await d.conversation_active(1,60); await d.conn.execute("UPDATE conversations SET last_activity_at=? WHERE chat_id=?",(time.time()-61*60,1)); await d.conn.commit(); assert not await d.conversation_active(1,60); await d.close()
