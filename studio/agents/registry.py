"""The AI team. Each agent says what it does, how it works (LLM reasoning vs deterministic code),
which module implements it and whether it is live. Nothing here is a name-only placeholder:
`status` is "live", "partial" (works with documented limits) or "planned" (not built yet)."""

AGENTS = [
    # id, Arabic name, kind, module, status, responsibility
    ("A01", "المنتج التنفيذي", "code", "studio.orchestrator", "live", "يدير مراحل كل حلقة ويعيد المحاولة ويستأنف من آخر مرحلة ناجحة"),
    ("A02", "المدير الإبداعي", "llm", "studio.agents.ideas", "live", "يختار الأفكار ويمنع تكرار الأفكار السابقة ويحمي هوية المسلسل"),
    ("A03", "محلل الترندات", "code+llm", "studio.agents.trends", "live", "يجمع ترندات مصر من Google Trends وGoogle News (RSS رسمي) ويقيّمها"),
    ("A04", "مدقق المعلومات", "llm", "studio.agents.ideas", "partial", "يقصر الوقائع على ما في عناوين المصادر ويحوّل غير الموثق لموقف خيالي عام"),
    ("A05", "رئيس كتاب الكوميديا", "llm", "studio.agents.writer", "live", "يكتب الحلقة: افتتاحية قوية، تصعيد، قفلة"),
    ("A06", "خبير الحوار المصري", "llm", "studio.agents.writer", "live", "يضبط اللهجة ولغة كل شخصية وطول الجمل"),
    ("A07", "مراجع السيناريو", "llm+code", "studio.agents.writer", "live", "يقيّم من 100 ويرفض ويطلب إعادة كتابة (حد أقصى محاولتين)"),
    ("A08", "مخرج الستوري بورد", "llm+code", "studio.agents.storyboard", "live", "يقسم الحلقة للقطات: مكان، شخصيات، كادر، حركة، حوار"),
    ("A09", "مسؤول ثبات الشخصيات", "code", "studio.agents.consistency", "partial", "يبني أول فريم من المراجع المعتمدة ويقارن ألوان اللقطة بالمرجع"),
    ("A10", "المدير الفني", "code", "config/characters.json", "live", "الهوية البصرية والأماكن ثابتة في ملف واحد معتمد"),
    ("A11", "مهندس البرومبت", "code", "studio.agents.storyboard", "live", "يبني برومبت كل لقطة من الـ Bible + Negative prompt + 9:16"),
    ("A12", "متخصص الأنيميشن", "code", "studio.video", "live", "يولد اللقطات على Kaggle GPU مجانًا (Wan 2.2) أو Mock في الديمو"),
    ("A13", "مخرج الأصوات", "code", "studio.audio", "live", "صوت ثابت لكل شخصية (edge-tts مصري + طبقة وسرعة مميزة)"),
    ("A14", "مهندس الصوت", "code", "studio.edit", "live", "توحيد مستوى الصوت (loudnorm) والمكساج"),
    ("A15", "متخصص مزامنة الشفاه", "-", "-", "planned", "مزامنة حقيقية تحتاج GPU إضافي؛ حاليًا الحركة تتولد مع وصف 'يتكلم'"),
    ("A16", "المونتير", "code", "studio.edit", "live", "تجميع اللقطات بالترتيب على توقيت الحوار + مقدمة + 1080x1920"),
    ("A17", "مسؤول الكابشن", "code", "studio.edit", "live", "كابشن عربي ASS في المنطقة الآمنة + ملف SRT منفصل"),
    ("A18", "مراجع الجودة البصرية", "code", "studio.agents.qa", "live", "فحص المقاس والمدة والتلف والشاشات السوداء"),
    ("A19", "مراجع جودة الصوت", "code", "studio.agents.qa", "live", "فحص وجود الصوت ومستواه والصمت"),
    ("A20", "مراجع المحتوى والسلامة", "llm+code", "studio.agents.safety", "live", "قائمة كلمات ممنوعة + مراجعة LLM للسخرية والتشهير والإفصاح"),
    ("A21", "مدير اعتماد الجودة", "code", "studio.agents.qa", "live", "يجمع الدرجات: APPROVED / REVISION_REQUIRED / REJECTED / HUMAN_REVIEW_REQUIRED"),
    ("A22", "استراتيجية المنصات", "-", "-", "planned", "يحتاج بيانات أداء فعلية بعد النشر"),
    ("A23", "متخصص العناوين والوصف", "llm", "studio.agents.writer", "live", "عنوان ووصف وهاشتاجات مع وسم المحتوى المولد بالذكاء الاصطناعي"),
    ("A24", "مدير النشر", "code", "studio.publish", "partial", "MANUAL_PUBLISH_REQUIRED حتى تربط الحسابات؛ يمنع النشر المكرر"),
    ("A25", "محلل الأداء", "-", "-", "planned", "يحتاج APIs التحليلات بعد ربط الحسابات"),
    ("A26", "محلل التعليقات", "-", "-", "planned", "يحتاج صلاحية قراءة التعليقات بعد ربط الحسابات"),
]
