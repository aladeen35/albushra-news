---
title: البشرى للأخبار
emoji: 📰
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# البشرى للأخبار على Hugging Face Spaces (مجانًا)

1. أنشئ حسابًا في huggingface.co ثم **New Space**، واختر **Docker** ثم **Blank**.
2. ارفع إلى المساحة:
   - هذا الملف `README.md` (يخبر المساحة بالمنفذ 7860).
   - الملف `Dockerfile` الموجود بجانبه.
   - مجلدَي `backend` و`frontend` من `news-observatory`.
3. في **Settings ← Variables and secrets** أضف السر `ADMIN_PASSWORD`.
4. تُبنى المساحة وتعمل على عنوان مثل `https://<اسمك>-albushra-news.hf.space`، والإدارة على `/admin`.

> المساحة المجانية تنام بعد يومين بلا زيارات وتستيقظ عند الزيارة. والبيانات مؤقتة وتُمسح عند إعادة التشغيل، فهي مناسبة للتجربة.
