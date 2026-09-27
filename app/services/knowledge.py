from app.db.database import Database

CARDS=[
('profile.about','profile','About Kazbek','Kazbek is a software developer focused on web development, backend systems, Telegram bots, automation, APIs, and full-stack applications. Works with Python, Go, JavaScript, TypeScript, React, Next.js, FastAPI, Django, PostgreSQL, Docker, VPS, GitHub and CI/CD. Does not normally take mobile apps, 1C, WordPress, or standalone UI/UX from scratch. Can implement from Figma, references, screenshots, or existing designs.','kazbek developer python react telegram',60),
('profile.contacts','profile','Public Contacts','Public portfolio: https://realkazbek.site\nTelegram: @realkazbek\nGitHub: https://github.com/RealKazbek\nDo not reveal private credentials or secrets.','portfolio contacts telegram github',60),
('portfolio.main','portfolio','Kazbek Portfolio','The only approved public portfolio item is https://realkazbek.site. Do not invent commercial projects or present private experiments as commercial work.','portfolio examples work projects',70),
('services.web','services','Web Development','Landing pages, personal and portfolio sites, corporate and business sites, ecommerce, dashboards, admin panels, SaaS interfaces, client portals, full-stack sites and MVPs.','site website landing corporate ecommerce dashboard',80),
('services.backend','services','Backend Development','Python, FastAPI, Django, Go, REST APIs, integrations, PostgreSQL, databases, authentication, automation backends and internal systems.','backend api fastapi django go postgres',80),
('services.telegram','services','Telegram Bots','Simple bots, database/API bots, admin bots, business automation, AI bots, DeepSeek/OpenAI integrations, notifications and workflow bots.','telegram bot база api ai',80),
('services.automation','services','Automation','Parsers, API integrations, repetitive process automation, internal tools, scheduled jobs, bot workflows, small CRM systems and data processing.','automation parser integration crm',80),
('services.infrastructure','services','Deployment and Infrastructure','Domain connection, VPS setup, deployment, HTTPS, Docker, databases, GitHub, CI/CD and basic production server setup.','deploy deployment vps domain https docker',80),
('pricing.landing','pricing','Landing Page Pricing','Approximate range: 40,000-80,000 KZT. Estimate only; animation, integrations and special requirements can increase it.','price cost landing лендинг',90),
('pricing.small_site','pricing','Small Website Pricing','Approximate range: 50,000-100,000 KZT for a portfolio, simple business or small multi-page site. Final price depends on functionality.','price cost small website сайт',90),
('pricing.corporate','pricing','Corporate Website Pricing','Approximate range: 80,000-180,000 KZT. Depends on pages, admin, integrations, content, backend and design complexity.','price cost corporate сайт',90),
('pricing.ecommerce','pricing','Ecommerce Pricing','Approximate range: 120,000-250,000 KZT. Depends on catalog, cart, checkout, payments, admin, accounts, delivery and integrations.','price cost ecommerce shop магазин',90),
('pricing.telegram_simple','pricing','Simple Telegram Bot Pricing','Approximate range: 30,000-60,000 KZT for simple bot flows without complex backend logic.','price cost telegram bot простой',90),
('pricing.telegram_advanced','pricing','Telegram Bot with Database/API Pricing','Approximate range: 60,000-140,000 KZT for database, external API, admin logic, notifications and user state.','price cost telegram bot база api',90),
('pricing.telegram_ai','pricing','AI Telegram Bot Pricing','Approximate range: 80,000-180,000 KZT. Depends on provider, memory, retrieval, integrations, deployment and business logic.','price cost telegram ai ии',90),
('pricing.dashboard','pricing','Dashboard Pricing','Approximate range: 70,000-180,000 KZT. Depends on data, APIs, auth, charts, roles and backend.','price cost dashboard admin панель',90),
('pricing.backend','pricing','Backend/API Pricing','Approximate range: 50,000-150,000 KZT. Depends on endpoints, database, auth, logic and integrations.','price cost backend api',90),
('pricing.mvp','pricing','Full-stack MVP Pricing','Approximate range: 100,000-250,000 KZT. Large or complex MVPs may exceed this range.','price cost mvp fullstack',90),
('pricing.automation','pricing','Parser and Automation Pricing','Approximate range: 30,000-100,000 KZT depending on complexity and integrations.','price cost parser automation',90),
('pricing.deploy','pricing','Deployment Pricing','Approximate range: 10,000-30,000 KZT for VPS, domain, HTTPS, deployment and environment setup.','price cost deploy vps',90),
('policy.pricing','policy','Pricing Rules','Do not give an exact final price immediately. Understand scope, ask one useful question, give an approximate range, say details affect the price, and leave final negotiation to Kazbek. Do not automatically lower prices or negotiate discounts.','price cost pricing дорого',100),
('policy.payment','policy','Payment Terms','Default prepayment is 10%. Accepted: Kaspi, Halyk, transfer by phone number, cash. No installment, credit or QR payment. Unusual terms require Kazbek confirmation.','payment оплатить kaspi halyk предоплата',100),
('timeline.default','timeline','Approximate Development Timelines','Rough estimates only: small task 1-3 days, landing 2-5 days, small site 3-7 days, simple bot 2-7 days, corporate site 1-2 weeks, ecommerce 1-3 weeks, dashboard 1-3 weeks, MVP 2-4 weeks, CRM from 1 month. Never guarantee before scope review.','deadline срок сроки days дни',100),
]

class KnowledgeService:
    def __init__(self,db): self.db=db
    async def seed(self):
        for c in CARDS: await self.db.kb_upsert(*c)
    async def retrieve(self,text):
        low=text.lower(); keys=[]
        if any(x in low for x in ('оплат','каспи','kaspi','halyk')): keys=['policy.payment']
        elif any(x in low for x in ('работ','портфолио','пример')): keys=['portfolio.main','profile.contacts']
        elif 'депло' in low or 'vps' in low: keys=['services.infrastructure','pricing.deploy']
        elif any(x in low for x in ('цена','сколько','стоимость','price','cost')): keys=['policy.pricing', 'pricing.telegram_advanced' if 'бот' in low else 'pricing.landing']
        elif any(x in low for x in ('срок','день','deadline')): keys=['timeline.default']
        elif 'бот' in low: keys=['services.telegram','pricing.telegram_advanced']
        elif 'сайт' in low: keys=['services.web']
        if keys: return [r for k in keys if (r:=await self.db.kb_get(k))][:4]
        rows=await self.db.kb_search(text,4); return rows
    async def context(self,text,max_chars=3000):
        out=[]
        for r in await self.retrieve(text):
            item=f"[{r['key']}] {r['title']}: {r['content']}"; out.append(item)
        return "\n".join(out)[:max_chars]
