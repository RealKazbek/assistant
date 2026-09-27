import asyncio, logging
from openai import AsyncOpenAI
from app.prompts.assistant import BASE_SYSTEM_PROMPT, profile_context
log=logging.getLogger(__name__)
class DeepSeekService:
    def __init__(self, settings, profile_loader=None, knowledge=None, memory=None): self.settings=settings; self.profile_loader=profile_loader; self.knowledge=knowledge; self.memory=memory; self.client=AsyncOpenAI(api_key=settings.deepseek_api_key,base_url=settings.deepseek_base_url,timeout=30,max_retries=0)
    async def reply(self, history, chat_id=None, user_text=None):
        for attempt in range(3):
            try:
                profile=await self.profile_loader() if self.profile_loader else {}
                knowledge=await self.knowledge.context(user_text,getattr(self.settings,'max_knowledge_chars',3000)) if self.knowledge and user_text else ""
                memory=await self.memory.context(chat_id) if self.memory and chat_id else ""
                basics={k:profile[k] for k in ("name","role","specialization","services") if k in profile}
                layered=BASE_SYSTEM_PROMPT+profile_context(basics)+"\n\nRelevant Kazbek knowledge:\n"+knowledge+"\n\nConversation memory:\n"+memory
                r=await self.client.chat.completions.create(model=self.settings.deepseek_model,messages=[{"role":"system","content":layered},*history[-getattr(self.settings,'recent_message_limit',6):]],temperature=0.6,max_tokens=self.settings.max_output_tokens)
                return (r.choices[0].message.content or "").strip()
            except Exception as e:
                log.warning("DeepSeek request failed attempt=%s error=%s",attempt+1,type(e).__name__)
                if attempt<2: await asyncio.sleep(2**attempt)
        return None
    async def close(self): await self.client.close()
