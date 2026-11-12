// Kawkab El Fahlawa — Telegram inbox on Cloudflare (free plan).
// • Talks the owner through an episode request instantly (Gemini), conversation kept in KV.
// • Everything else (idea buttons, approvals, «حالة»…) is queued in KV and a GitHub run is dispatched to process it.
// • The studio (GitHub Actions) pulls the queue with QUEUE_KEY and posts back its ETA text.
import BIBLE from "./bible.json";

const SYSTEM = `إنت منتج مسلسل الكرتون المصري «كوكب الفهلوة». صاحب القناة بيكلمك على تيليجرام عن حلقة عاوزها.
اتكلم معاه بالعامية المصرية، قصير وودود، زي زميل شغل. مهمتك:
1) تفهم الحلقة: مين الشخصيات، فين، إيه اللي بيحصل، النهاية/الإفيه، أي تفاصيل مهمة ليه.
2) لو حاجة أساسية ناقصة اسأل سؤال أو اتنين بالكتير في المرة (متعملش استجواب). لو هو قال «انت اختار» اختار انت.
3) لما الصورة تكمل: لخّص الخطة في 3–5 سطور (الحلقة قصيرة: 3–5 جمل حوار، كل جملة قصيرة تتقال في أقل من 3 ثواني)،
   وقوله هتجهز إمتى حسب المعلومة اللي جاتلك، واسأله «أبدأ؟».
4) لو وافق (تمام/ابدأ/موافق/يلا…) خلي ready=true.
5) لو طلب حاجة فيها أشخاص حقيقيين بأسمائهم، أو سياسة، أو دين بشكل مسيء، أو مشاهد مش محترمة — اعتذر بلطف واقترح بديل.
6) لو سأل عن التريند/الترندات/حاجة جديدة النهارده: استخدم «تريندات مصر النهارده» اللي جاتلك بس (متألفش تريندات)،
   واختار منها 3 أو 4 ينفعوا كوميديا عائلية، كل واحد في سطر: اسم التريند + ليه رائج باختصار + فكرة حلقة مضحكة بشخصياتنا.
   لو التريند عن شخص حقيقي (لاعب/ممثل/مسؤول) خد «الموضوع» بس ومتحطش الشخص نفسه في الحلقة.
   وفي الآخر اسأله يختار أنهي، أو يقولك «هات غيرهم».
الشخصيات المتاحة (استخدم الـ id في brief.characters):
${BIBLE.map((c) => `- ${c.id} = ${c.name} (${c.age}): ${c.personality}`).join("\n")}
رجّع JSON بس بالشكل ده:
{"reply": "ردك", "ready": false, "brief": {"title": "عنوان قصير", "premise": "الفكرة في سطرين",
 "details": "كل التفاصيل اللي اتفقتوا عليها", "characters": ["sayed_fahlawa"], "location": "cafe|alley|home|shop"}}`;
const COMMANDS = ["حالة", "الحالة", "status", "غير", "افكار", "أفكار", "more", "ابدا", "ابدأ", "start", "مساعدة", "help"];
const MODELS = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest"];

async function tg(env, method, body) {
  const r = await fetch(`https://api.telegram.org/bot${env.TG_TOKEN}/${method}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  return r.json().catch(() => ({}));
}
const say = (env, text, buttons) => tg(env, "sendMessage", { chat_id: env.TG_CHAT_ID, text: text.slice(0, 4000),
  ...(buttons ? { reply_markup: { inline_keyboard: buttons.map((row) => row.map(([t, d]) => ({ text: t, callback_data: d }))) } } : {}) });

async function enqueue(env, item) {
  const id = `q:${Date.now().toString().padStart(15, "0")}:${crypto.randomUUID().slice(0, 6)}`;
  await env.Q.put(id, JSON.stringify(item), { expirationTtl: 14 * 86400 });
  const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/dispatches`, { method: "POST",
    headers: { authorization: `Bearer ${env.GH_TOKEN}`, accept: "application/vnd.github+json", "user-agent": "kawkab-inbox" },
    body: JSON.stringify({ event_type: "tg" }) });
  return r.status;
}

const BLOCKED = /وفاة|توفي|مقتل|قتل|انتحار|حادث|ضحايا|اغتصاب|تحرش|إرهاب|حرب|غزة|قصف|مرض|سرطان|طفل|أطفال|طفلة|رئيس الجمهورية|السيسي|انتخابات|حزب|كنيسة|مسجد|طائفي|سياسي|محاكمة|سجن|اعتقال|متهم|فساد/i;
const TREND_WORDS = /تر[يى]?ند|ترند|الترند|التريند|رائج|الجديد النهارده|اخبار النهارده|أخبار النهارده|الناس بتتكلم/;
const unx = (t) => (t || "").replace(/<!\[CDATA\[|\]\]>/g, "").replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;/g, "'").trim();

async function trends(env) {
  const cached = await env.Q.get("trends");
  if (cached) return JSON.parse(cached);
  const out = [];
  try {
    const x = await (await fetch("https://trends.google.com/trending/rss?geo=EG", { headers: { "user-agent": "Mozilla/5.0" } })).text();
    for (const it of x.split("<item>").slice(1)) {
      const title = unx((it.match(/<title>([\s\S]*?)<\/title>/) || [])[1]);
      const traffic = unx((it.match(/<ht:approx_traffic>([\s\S]*?)<\/ht:approx_traffic>/) || [])[1]);
      const news = unx((it.match(/<ht:news_item_title>([\s\S]*?)<\/ht:news_item_title>/) || [])[1]);
      if (title && !BLOCKED.test(title + " " + news)) out.push({ title, traffic, news });
    }
  } catch (e) {}
  try {
    const x = await (await fetch("https://news.google.com/rss?hl=ar&gl=EG&ceid=EG:ar", { headers: { "user-agent": "Mozilla/5.0" } })).text();
    for (const it of x.split("<item>").slice(1, 16)) {
      const title = unx((it.match(/<title>([\s\S]*?)<\/title>/) || [])[1]);
      if (title && !BLOCKED.test(title)) out.push({ title, traffic: "خبر", news: "" });
    }
  } catch (e) {}
  const list = out.slice(0, 25);
  if (list.length) await env.Q.put("trends", JSON.stringify(list), { expirationTtl: 90 * 60 });
  return list;
}

async function gemini(env, history, brief, eta, trendList) {
  const trendText = trendList && trendList.length
    ? "\n\nتريندات مصر النهارده (Google Trends + Google News، دلوقتي):\n" + trendList.map((t, i) => `${i + 1}. ${t.title}${t.traffic ? ` (${t.traffic})` : ""}${t.news ? ` — ${t.news}` : ""}`).join("\n")
    : "";
  const convo = history.slice(-16).map((m) => `${m.role === "owner" ? "صاحب القناة" : "إنت"}: ${m.text}`).join("\n");
  const prompt = `المعلومة عن الميعاد: ${eta}${trendText}\n\nالخطة لحد دلوقتي (JSON): ${JSON.stringify(brief)}\n\nالمحادثة:\n${convo}\n\nرد على آخر رسالة.`;
  for (const m of MODELS) {
    const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${m}:generateContent`, { method: "POST",
      headers: { "x-goog-api-key": env.GEMINI_API_KEY, "content-type": "application/json" },
      body: JSON.stringify({ systemInstruction: { parts: [{ text: SYSTEM }] }, contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { temperature: 0.7, responseMimeType: "application/json" } }) });
    if (!r.ok) continue;
    try {
      const d = await r.json();
      const out = JSON.parse(d.candidates[0].content.parts.map((p) => p.text || "").join(""));
      const ids = new Set(BIBLE.map((c) => c.id));
      out.brief = out.brief || {};
      out.brief.characters = (out.brief.characters || []).filter((c) => ids.has(c));
      if (!out.brief.characters.length) out.brief.characters = ["sayed_fahlawa", "zizo_trend"];
      return out;
    } catch (e) { continue; }
  }
  return null;
}

async function startEpisode(env, chat) {
  const b = chat.brief || {};
  if (!b.premise) { await say(env, "لسه محتاج أعرف الحلقة عن إيه 🙂 احكيلي."); return; }
  await enqueue(env, { _kind: "start_episode", brief: b });
  await env.Q.delete("chat");
  const eta = (await env.Q.get("eta")) || "";
  await say(env, `🎬 تمام! «${b.title || "الحلقة"}» داخلة الإنتاج دلوقتي.${eta ? "\n" + eta + "." : ""}\nهبعتلك الحلقة تشوفها وتوافق قبل أي نشر.`);
}

async function chatTurn(env, text) {
  const chat = JSON.parse((await env.Q.get("chat")) || '{"history":[],"brief":{}}');
  chat.history.push({ role: "owner", text: text.slice(0, 1500) });
  const eta = (await env.Q.get("eta")) || "الميعاد هيتحدد أول ما الفريق يشوف الطابور";
  const wantsTrends = TREND_WORDS.test(text) || chat.history.slice(-6).some((m) => TREND_WORDS.test(m.text));
  const out = await gemini(env, chat.history, chat.brief, eta, wantsTrends ? await trends(env) : null);
  if (!out) { await say(env, "معلش Gemini مضغوط دلوقتي 🙏 ابعتلي تاني كمان دقيقة."); return; }
  chat.brief = out.brief; chat.history.push({ role: "bot", text: out.reply || "تمام" });
  await env.Q.put("chat", JSON.stringify(chat), { expirationTtl: 3 * 86400 });
  if (out.ready) { await say(env, out.reply || "تمام"); return startEpisode(env, chat); }
  await say(env, out.reply || "تمام", chat.brief.premise ? [[["✅ ابدأ الحلقة", "chat:go"], ["🗑️ إلغاء", "chat:cancel"]]] : null);
}

const authed = (req, env) => req.headers.get("authorization") === `Bearer ${env.QUEUE_KEY}`;

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (req.method === "POST" && url.pathname === "/tg") {
      if (req.headers.get("x-telegram-bot-api-secret-token") !== env.TG_SECRET) return new Response("no", { status: 401 });
      const u = await req.json();
      const msg = u.message || (u.callback_query || {}).message || {};
      if (String((msg.chat || {}).id) !== String(env.TG_CHAT_ID)) return new Response("ok");
      ctx.waitUntil((async () => {
        await tg(env, "sendChatAction", { chat_id: env.TG_CHAT_ID, action: "typing" });
        const cb = u.callback_query;
        if (cb) {
          const data = cb.data || "";
          if (data === "chat:cancel") { await env.Q.delete("chat"); await tg(env, "answerCallbackQuery", { callback_query_id: cb.id, text: "اتلغت" });
            return say(env, "اتلغت 👍 ابعتلي في أي وقت لو عندك فكرة حلقة."); }
          if (data === "chat:go") { await tg(env, "answerCallbackQuery", { callback_query_id: cb.id, text: "يلا 🎬" });
            return startEpisode(env, JSON.parse((await env.Q.get("chat")) || "{}")); }
          await tg(env, "answerCallbackQuery", { callback_query_id: cb.id, text: "⏳ وصلت، الفريق هيرد خلال دقيقة أو اتنين" });
          return enqueue(env, u);
        }
        const text = ((u.message || {}).text || "").trim();
        if (!text) return;
        const t = text.replace(/أ/g, "ا");
        const inChat = !!(await env.Q.get("chat"));
        if (COMMANDS.includes(t) || COMMANDS.includes(text)) {
          if (!inChat || ["حالة", "الحالة", "status"].includes(t)) {
            await say(env, "⏳ وصلت، ثواني والفريق يرد…"); return enqueue(env, u);
          }
        }
        return chatTurn(env, text);
      })());
      return new Response("ok");
    }
    if (url.pathname === "/pending" && authed(req, env)) {
      const list = await env.Q.list({ prefix: "q:" });
      const items = [];
      for (const k of list.keys) { const v = await env.Q.get(k.name); if (v) items.push({ key: k.name, item: JSON.parse(v) }); }
      return Response.json(items);
    }
    if (req.method === "POST" && url.pathname === "/ack" && authed(req, env)) {
      const { keys = [] } = await req.json();
      await Promise.all(keys.filter((k) => k.startsWith("q:")).map((k) => env.Q.delete(k)));
      return Response.json({ ok: true });
    }
    if (req.method === "POST" && url.pathname === "/status" && authed(req, env)) {
      const { eta = "" } = await req.json();
      await env.Q.put("eta", String(eta).slice(0, 400));
      return Response.json({ ok: true });
    }
    return new Response("kawkab inbox");
  },
};
