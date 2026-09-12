/**
 * line-relay —— 無頭交辦的收件端（部署在老師自己的 Firebase 專案裡）。
 *
 * 它只做一件事：把老師從手機傳給自己 LINE 官方帳號的訊息，原封不動放進
 * Firestore 的 headless_events，語音再多存一份音檔到 Cloud Storage，然後回一句
 * 「收到了」。真正整理成紀錄的是老師電腦上的 scripts/headless.py ＋ AI 代理——
 * 這支不叫任何模型、不看內容、不做判斷。
 *
 * 為什麼是這個形狀（每一條都是踩過的）：
 *
 *  1. LINE 的 webhook 要在 **2 秒內**拿到回應，否則那一則會被判逾時（老師看到的是「沒反應」）。
 *     但**不可以**先 res.send(200) 再把寫入丟在背景跑：Cloud Functions 送出回應之後
 *     隨時可能把這個實例凍住（CPU 收掉），背景那半截會靜靜地消失。
 *     所以這裡是「回覆 ＋ 寫入**同時**跑，整包最多等 1.2 秒，時間到就先回 200」。
 *  2. 簽章一定要用 **raw body** 算（req.rawBody），用 JSON.stringify(req.body) 重組
 *     會因為空白與鍵序不同而永遠對不上。
 *  3. 文件 id ＝ LINE 的 webhookEventId：LINE 會重送，用它當 id 天然去重。
 *  4. 音檔下載如果沒在 1.2 秒內完成，文件上會留 audioPending，電腦端的 headless.py
 *     會自己去 LINE 的 content API 抓一次（它手上也有 channel token）。錄音不會因此掉。
 *  5. 配對：ownerUserId 還沒設定時，**任何人**傳訊息都會拿到「配對碼：<userId>」。
 *     這是刻意的——老師要有辦法在手機上拿到自己的 userId。拿到之後請馬上完成配對
 *     （填進 config/kit.json → 跑一次 headless.py --once），配對完就只認那一個人。
 *
 * 部署：
 *   firebase functions:secrets:set KIT_LINE_CHANNEL_SECRET
 *   firebase functions:secrets:set KIT_LINE_CHANNEL_TOKEN
 *   firebase deploy --only functions:line-relay --project <你的專案id>
 * 要 Blaze（隨用隨付）方案；這個用量幾乎一定是 0 元，但 Firebase 規定要綁信用卡。
 */
'use strict';

const crypto = require('crypto');
const { onRequest } = require('firebase-functions/v2/https');
const { defineSecret } = require('firebase-functions/params');
const { setGlobalOptions } = require('firebase-functions/v2');
const admin = require('firebase-admin');

const CHANNEL_SECRET = defineSecret('KIT_LINE_CHANNEL_SECRET');
const CHANNEL_TOKEN = defineSecret('KIT_LINE_CHANNEL_TOKEN');

// asia-east1（台灣）＝離使用者最近的區域，來回少掉 100ms 以上，2 秒的預算才夠用。
setGlobalOptions({ region: 'asia-east1', maxInstances: 3 });

admin.initializeApp();
const db = admin.firestore();

const BUDGET_MS = 1200;          // 回覆＋寫入整包最多等多久（LINE 給 2 秒）
const RECEIPT = '收到了，電腦醒著時會處理';
const EVENTS = 'headless_events';
const PAIRING = 'headless_pairing';
const INBOX_PREFIX = 'headless-inbox';

let ownerCache = { at: 0, id: null };

/** 只接受這個 LINE 使用者的訊息。正本在 Firestore meta/headless（由 headless.py 寫上去）。 */
async function ownerUserId() {
  const now = Date.now();
  if (ownerCache.id !== null && now - ownerCache.at < 60000) return ownerCache.id;
  let id = '';
  try {
    const snap = await db.doc('meta/headless').get();
    id = (snap.exists && snap.get('ownerUserId')) || '';
  } catch (e) {
    console.error('讀 meta/headless 失敗', e);
    id = '';
  }
  ownerCache = { at: now, id };
  return id;
}

/** x-line-signature：HMAC-SHA256(raw body, channel secret) 的 base64。時間安全比較。 */
function signatureOk(rawBody, header, secret) {
  if (!header || !secret || !rawBody) return false;
  const mine = crypto.createHmac('sha256', secret).update(rawBody).digest();
  let theirs;
  try {
    theirs = Buffer.from(String(header), 'base64');
  } catch (e) {
    return false;
  }
  return mine.length === theirs.length && crypto.timingSafeEqual(mine, theirs);
}

function withTimeout(promise, ms) {
  return Promise.race([promise, new Promise((r) => setTimeout(r, ms))]);
}

async function lineApi(path, token, body, host) {
  const res = await fetch('https://' + (host || 'api.line.me') + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('LINE ' + path + ' HTTP ' + res.status + ' ' + (await res.text()).slice(0, 200));
}

function reply(replyToken, text, token) {
  if (!replyToken) return Promise.resolve();
  return lineApi('/v2/bot/message/reply', token, {
    replyToken,
    messages: [{ type: 'text', text: text.slice(0, 400) }],
  });
}

/** 語音訊息的音檔：從 LINE 的 content API 拉下來，放進這個專案自己的 Storage。 */
async function saveAudio(messageId, token) {
  const res = await fetch('https://api-data.line.me/v2/bot/message/' + messageId + '/content', {
    headers: { Authorization: 'Bearer ' + token },
  });
  if (!res.ok) throw new Error('content API HTTP ' + res.status);
  const buf = Buffer.from(await res.arrayBuffer());
  const path = INBOX_PREFIX + '/' + messageId + '.m4a';
  await admin.storage().bucket().file(path).save(buf, {
    contentType: 'audio/m4a',
    resumable: false,
    metadata: { cacheControl: 'private, max-age=0' },
  });
  return { path, bytes: buf.length };
}

/**
 * 一則事件 → 一份 headless_events 文件。
 * 音檔另外存；存不成（沒開 Storage、逾時）就把原因寫在文件上，不讓整則掉。
 */
async function handleEvent(ev, token) {
  const id = ev.webhookEventId || (ev.message && ev.message.id) || String(Date.now());
  const m = ev.message || {};
  const kind = m.type === 'audio' ? 'audio' : 'text';
  const doc = db.collection(EVENTS).doc(id);
  const base = {
    type: kind,
    text: kind === 'text' ? String(m.text || '') : '',
    messageId: String(m.id || ''),
    userId: String((ev.source && ev.source.userId) || ''),
    receivedAt: new Date(ev.timestamp || Date.now()).toISOString(),
    status: 'pending',
    storagePath: '',
    audioPending: kind === 'audio',
    error: '',
    relayVersion: 1,
  };
  // create（不是 set）：同一個 webhookEventId 重送時直接撞掉，不會覆蓋電腦端已經改過的 status。
  try {
    await doc.create(base);
  } catch (e) {
    if (e && e.code === 6) return;           // ALREADY_EXISTS＝LINE 重送，正常，不必再做一次
    throw e;
  }
  if (kind !== 'audio') return;
  try {
    const saved = await saveAudio(base.messageId, token);
    await doc.update({ storagePath: saved.path, bytes: saved.bytes, audioPending: false });
  } catch (e) {
    console.error('音檔存不進 Storage', e);
    // 不改 status：電腦端的 headless.py 看到 audioPending 會自己去 LINE 抓一次。
    await doc.update({ error: String((e && e.message) || e).slice(0, 300) }).catch(() => {});
  }
}

exports['line-relay'] = onRequest(
  { secrets: [CHANNEL_SECRET, CHANNEL_TOKEN], timeoutSeconds: 60, memory: '256MiB', cors: false },
  async (req, res) => {
    if (req.method !== 'POST') {
      res.status(405).send('POST only');
      return;
    }
    const secret = CHANNEL_SECRET.value();
    const token = CHANNEL_TOKEN.value();
    if (!signatureOk(req.rawBody, req.get('x-line-signature'), secret)) {
      // 401 而不是 200：LINE 主控台的「驗證」按鈕會送一個空的簽章，本來就該被擋。
      res.status(401).send('bad signature');
      return;
    }
    const events = (req.body && req.body.events) || [];
    const owner = await ownerUserId();
    const work = [];
    for (const ev of events) {
      if (ev.type !== 'message') continue;
      const uid = (ev.source && ev.source.userId) || '';
      if (!owner) {
        // 還沒配對：把 userId 當配對碼回給他，並記下來讓 headless.py --pair 讀得到。
        work.push(reply(ev.replyToken, '配對碼：' + uid, token).catch((e) => console.error(e)));
        work.push(
          db.collection(PAIRING).doc(uid || 'unknown')
            .set({ userId: uid, seenAt: new Date().toISOString() }, { merge: true })
            .catch((e) => console.error(e))
        );
        continue;
      }
      if (uid !== owner) continue;            // 不是本人：靜靜丟掉，不回話（不給陌生人任何回饋）
      work.push(reply(ev.replyToken, RECEIPT, token).catch((e) => console.error(e)));
      work.push(handleEvent(ev, token).catch((e) => console.error('寫入失敗', e)));
    }
    // 回覆與寫入同時跑，整包最多等 BUDGET_MS——先回 200 再背景寫的話，
    // 實例被凍住那半截就沒了（見檔頭第 1 條）。
    await withTimeout(Promise.allSettled(work), BUDGET_MS);
    res.status(200).send('ok');
  }
);
