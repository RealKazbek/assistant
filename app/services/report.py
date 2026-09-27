from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

class DailyReport:
    def __init__(self,db,settings): self.db=db; self.settings=settings; self.tz=ZoneInfo(settings.app_timezone)
    def bounds(self,day=None):
        now=datetime.now(self.tz); end=now.replace(hour=0,minute=0,second=0,microsecond=0) if day is None else datetime.combine(day+timedelta(days=1),datetime.min.time(),self.tz); start=end-timedelta(days=1); return start.timestamp(),end.timestamp(),start.date().isoformat()
    async def build(self,day=None):
        start,end,date=self.bounds(day); rows=await (await self.db.conn.execute("SELECT c.*,COUNT(m.id) cnt FROM conversations c JOIN messages m ON m.chat_id=c.chat_id AND m.created_at>=? AND m.created_at<? LEFT JOIN trusted_contacts tc ON tc.chat_id=c.chat_id AND tc.enabled=1 WHERE tc.id IS NULL GROUP BY c.chat_id ORDER BY cnt DESC",(start,end))).fetchall(); lines=[f"Daily report · {date}",f"Сегодня написали: {len(rows)}",""]; 
        for i,r in enumerate(rows,1):
            mem=await self.db.memory(r['chat_id']); lines.append(f"{i}. {r['first_name'] or 'Client'} @{r['username'] or '-'}\n"+f"Проект: {(mem['project_type'] if mem else None) or 'не определён'}\nБюджет: {(mem['budget'] if mem else None) or 'не сказал'}\nСтатус: {(mem['lead_status'] if mem else None) or 'unknown'}\n{('Память: '+mem['summary']) if mem and mem['summary'] else ''}\n")
        return '\n'.join(lines),date,len(rows),sum(r['cnt'] for r in rows)
