import asyncio, logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.config import load_settings
from app.db.database import Database
from app.services.deepseek import DeepSeekService
from app.bot import App
from app.services.knowledge import KnowledgeService
from app.services.memory import MemoryService
from app.services.report import DailyReport
async def main():
    s=load_settings(); logging.basicConfig(level=getattr(logging,s.log_level.upper(),logging.INFO),format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db=Database(s.database_path); await db.connect(); kb=KnowledgeService(db); memory=MemoryService(db,s); report=DailyReport(db,s); app=App(s,db,None,kb,memory,report); await app.start(); ai=DeepSeekService(s,db.profile_all,kb,memory); app.ai=ai
    me=await app.bot.get_me(); logging.getLogger(__name__).info("starting bot username=%s id=%s",me.username,me.id)
    async def daily_loop():
        tz=ZoneInfo(s.app_timezone)
        while True:
            now=datetime.now(tz)
            try: hour,minute=(int(x) for x in s.daily_report_time.split(":",1))
            except (ValueError,TypeError): hour,minute=0,0
            nxt=(now+timedelta(days=1)).replace(hour=hour,minute=minute,second=0,microsecond=0); await asyncio.sleep(max(1,(nxt-now).total_seconds()))
            day=(nxt-timedelta(days=1)).date(); date=day.isoformat()
            if s.daily_report_enabled and not await db.report_sent(date):
                text,_,chats,messages=await report.build(day); await app.bot.send_message(s.owner_telegram_id,text[:4000]); await db.mark_report(date,chats,messages)
    task=asyncio.create_task(daily_loop())
    try: await app.run()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await app.close()
if __name__=="__main__": asyncio.run(main())
