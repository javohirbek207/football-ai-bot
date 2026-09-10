INFO:apscheduler.executors.default:Running job "main.<locals>.<lambda> (trigger: interval[0:05:00], next run at: 2026-09-10 14:38:46 +05)" (scheduled at 2026-09-10 14:33:46.448940+05:00)
INFO:apscheduler.executors.default:Job "main.<locals>.<lambda> (trigger: interval[0:05:00], next run at: 2026-09-10 14:38:46 +05)" executed successfully
/opt/render/project/python/Python-3.14.3/lib/python3.14/asyncio/base_events.py:2047: RuntimeWarning: coroutine 'check_finished_matches' was never awaited
  handle = None  # Needed to break cycles when an exception occurs.
RuntimeWarning: Enable tracemalloc to get the object allocation traceback
==> Detected service running on port 10000
==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
INFO:aiogram.event:Update id=770012685 is not handled. Duration 0 ms by bot id=8530860989
==> Deploying...
==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
==> Running 'python main.py'
INFO:aiogram.event:Update id=770012686 is not handled. Duration 0 ms by bot id=8530860989
/opt/render/project/src/main.py:9: FutureWarning: 
All support for the `google.generativeai` package has ended. It will no longer be receiving 
updates or bug fixes. Please switch to the `google.genai` package as soon as possible.
See README for more details:
https://github.com/google-gemini/deprecated-generative-ai-python/blob/main/README.md
  import google.generativeai as genai
INFO:root:✅ AI modeli tanlandi: models/gemini-2.5-flash
INFO:aiohttp.access:127.0.0.1 [10/Sep/2026:09:35:50 +0000] "HEAD / HTTP/1.1" 200 153 "-" "Go-http-client/1.1"
INFO:apscheduler.scheduler:Adding job tentatively -- it will be properly scheduled when the scheduler starts
INFO:apscheduler.scheduler:Added job "main.<locals>.<lambda>" to job store "default"
INFO:apscheduler.scheduler:Scheduler started
INFO:root:Bot xatoliklardan tozalangan holda ishga tushdi...
INFO:aiogram.dispatcher:Start polling
INFO:aiogram.dispatcher:Run polling for bot @fbdnjskdjfhndjsmkbot id=8530860989 - 'Futbol Football'
ERROR:aiogram.dispatcher:Failed to fetch updates - TelegramConflictError: Telegram server says - Conflict: terminated by other getUpdates request; make sure that only one bot instance is running
WARNING:aiogram.dispatcher:Sleep for 1.000000 seconds and try again... (tryings = 0, bot id = 8530860989)
ERROR:aiogram.dispatcher:Failed to fetch updates - TelegramConflictError: Telegram server says - Conflict: terminated by other getUpdates request; make sure that only one bot instance is running
WARNING:aiogram.dispatcher:Sleep for 1.000000 seconds and try again... (tryings = 0, bot id = 8530860989)
ERROR:aiogram.dispatcher:Failed to fetch updates - TelegramConflictError: Telegram server says - Conflict: terminated by other getUpdates request; make sure that only one bot instance is running
WARNING:aiogram.dispatcher:Sleep for 1.273485 seconds and try again... (tryings = 1, bot id = 8530860989)
WARNING:aiogram.dispatcher:Received SIGTERM signal
INFO:aiogram.dispatcher:Polling stopped for bot @fbdnjskdjfhndjsmkbot id=8530860989 - 'Futbol Football'
INFO:aiogram.dispatcher:Polling stopped
==> Your service is live 🎉
INFO:aiohttp.access:127.0.0.1 [10/Sep/2026:09:35:58 +0000] "GET / HTTP/1.1" 200 182 "-" "Go-http-client/2.0"
==> 
==> ///////////////////////////////////////////////////////////
==> 
==> Available at your primary URL https://football-ai-bot-txnb.onrender.com
==> 
==> ///////////////////////////////////////////////////////////
ERROR:aiogram.dispatcher:Failed to fetch updates - TelegramConflictError: Telegram server says - Conflict: terminated by other getUpdates request; make sure that only one bot instance is running
WARNING:aiogram.dispatcher:Sleep for 1.250469 seconds and try again... (tryings = 1, bot id = 8530860989)
INFO:aiogram.dispatcher:Connection established (tryings = 2, bot id = 8530860989)
INFO:aiogram.event:Update id=770012687 is not handled. Duration 0 ms by bot id=8530860989
