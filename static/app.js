// LEVEL UP LAB — フロントエンド(API クライアント + 描画)

let me = null;          // /api/me の結果
let meta = null;        // ランク定義・権限ラベル
let authMode = 'login';

// ---- API ----
async function api(path, options = {}) {
  const res = await fetch('/api' + path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // セッション失効: リロードして認証画面へ(/me の 401 は init が処理する)
    if (res.status === 401 && !path.startsWith('/auth/') && path !== '/me') {
      location.reload();
    }
    throw new Error(data.error || `エラー (${res.status})`);
  }
  return data;
}

// 描画系の未処理Promise拒否を防ぐラッパー
function safeRender(promise) {
  Promise.resolve(promise).catch(e => console.error('render error:', e));
}

// ---- 初期化 ----
async function init() {
  const [m, u] = await Promise.all([
    api('/meta'),
    api('/me').catch(() => null),
  ]);
  meta = m;
  me = u;
  document.getElementById('loading').style.display = 'none';
  if (!me) {
    document.getElementById('auth-screen').style.display = 'flex';
    return;
  }
  document.getElementById('app').style.display = 'block';
  renderAll();
}

// ---- 認証 ----
function switchAuthTab(mode) {
  authMode = mode;
  document.getElementById('tab-login').classList.toggle('active', mode === 'login');
  document.getElementById('tab-register').classList.toggle('active', mode === 'register');
  document.querySelector('.auth-submit').textContent = mode === 'login' ? 'ログイン' : '登録してはじめる';
  document.getElementById('auth-error').textContent = '';
}

async function submitAuth() {
  const name = document.getElementById('auth-name').value.trim();
  const password = document.getElementById('auth-password').value;
  const errEl = document.getElementById('auth-error');
  errEl.textContent = '';
  try {
    await api('/auth/' + (authMode === 'login' ? 'login' : 'register'), {
      method: 'POST',
      body: JSON.stringify({ name, password }),
    });
    me = await api('/me');
    document.getElementById('auth-screen').style.display = 'none';
    document.getElementById('app').style.display = 'block';
    renderAll();
    if (authMode === 'register') {
      showToast(`ようこそ、${me.name} さん!最初のクエストに挑戦しましょう`);
      openGuide();
    }
  } catch (e) {
    errEl.textContent = e.message;
  }
}

async function logout() {
  try { await api('/auth/logout', { method: 'POST' }); } catch (e) {}
  location.reload();
}

// ---- 遊び方ガイド ----
function openGuide() {
  const box = document.getElementById('guide-ranks');
  box.innerHTML = '';
  meta.ranks.forEach((r, i) => {
    const perms = (meta.rank_permissions[r.key] || [])
      .map(p => meta.permission_labels[p]).filter(Boolean).join('、');
    const row = document.createElement('div');
    row.className = 'guide-rank-row';
    row.innerHTML = `
      <span class="gr-emblem" style="background:linear-gradient(160deg,${r.color1},${r.color2})"></span>
      <span class="gr-name"></span>
      <span class="gr-exp">${r.min} EXP〜</span>
      <span class="gr-perm"></span>
    `;
    row.querySelector('.gr-name').textContent = `LV${i + 1} ${r.name}`;
    row.querySelector('.gr-perm').textContent = perms ? `🔓 ${perms}` : '';
    box.appendChild(row);
  });
  document.getElementById('guide-overlay').classList.add('show');
}
function closeGuide() { document.getElementById('guide-overlay').classList.remove('show'); }

// ---- おかえり通知(不在中の採用・称賛) ----
const EVENT_LABEL = {
  proposal_adopted: '🏆 あなたの改善提案が採用されました!',
  mentor_bonus: '👏 称賛ボーナスが届きました',
  admin_adjust: '🛠 運営からポイント調整がありました',
};

// ---- お知らせ ----
async function renderAnnouncements() {
  const box = document.getElementById('announce-box');
  const { items } = await api('/announcements');
  if (items.length === 0) { box.style.display = 'none'; return; }
  box.innerHTML = '';
  items.forEach(a => {
    const el = document.createElement('div');
    el.className = 'announce-item';
    el.innerHTML = '<span class="an-icon">📢</span><span class="an-body"></span><span class="an-when"></span>';
    el.querySelector('.an-body').textContent = a.body;
    el.querySelector('.an-when').textContent = fmtLocal(a.created_at);
    box.appendChild(el);
  });
  box.style.display = 'block';
}

function renderNoticeBanner() {
  const banner = document.getElementById('notice-banner');
  const events = me.unseen_events || [];
  if (events.length === 0) { banner.style.display = 'none'; return; }
  const list = document.getElementById('notice-list');
  list.innerHTML = '';
  events.forEach(ev => {
    const el = document.createElement('div');
    el.className = 'nb-item';
    const gains = [];
    if (ev.delta_exp) gains.push(`+${ev.delta_exp} EXP`);
    if (ev.delta_points) gains.push(`+${ev.delta_points} pt`);
    el.textContent = `${EVENT_LABEL[ev.type] || ev.type}${ev.note ? `(${ev.note})` : ''} ${gains.join(' / ')}`;
    const when = document.createElement('span');
    when.className = 'nb-when';
    when.textContent = fmtLocal(ev.created_at);
    el.appendChild(when);
    list.appendChild(el);
  });
  banner.style.display = 'block';
}

async function ackEvents() {
  const events = me.unseen_events || [];
  if (events.length === 0) return;
  const lastId = Math.max(...events.map(e => e.id));
  try {
    await api('/me/ack-events', { method: 'POST', body: JSON.stringify({ last_id: lastId }) });
    me.unseen_events = [];
    renderNoticeBanner();
  } catch (e) { showToast('⚠️ ' + e.message); }
}

// ---- 「いまできること」サマリー ----
const todayCounts = { quests: null, pending: null, canReview: false };

function updateTodayStrip() {
  const strip = document.getElementById('today-strip');
  const parts = [];
  if (todayCounts.quests !== null) {
    parts.push(`<span class="ts-item">🎯 いま挑戦できるクエスト <b>${todayCounts.quests}</b> 件</span>`);
  }
  if (todayCounts.canReview && todayCounts.pending > 0) {
    parts.push(`<span class="ts-item">📋 あなたの承認待ち提案 <b>${todayCounts.pending}</b> 件</span>`);
  }
  if (parts.length === 0) { strip.style.display = 'none'; return; }
  strip.innerHTML = parts.join('');
  strip.style.display = 'flex';
}

// ---- アカウント設定 ----
function openAccount() {
  document.getElementById('acc-name').value = me.name;
  document.getElementById('acc-error').textContent = '';
  document.getElementById('account-overlay').classList.add('show');
}
function closeAccount() { document.getElementById('account-overlay').classList.remove('show'); }

async function changeName() {
  const name = document.getElementById('acc-name').value.trim();
  const errEl = document.getElementById('acc-error');
  errEl.textContent = '';
  if (name === me.name) { closeAccount(); return; }
  try {
    await api('/auth/profile', { method: 'PATCH', body: JSON.stringify({ name }) });
    me = await api('/me');
    renderAll();
    closeAccount();
    showToast(`表示名を「${name}」に変更しました(次回ログインもこの名前です)`);
  } catch (e) { errEl.textContent = e.message; }
}

async function changePassword() {
  const errEl = document.getElementById('acc-error');
  errEl.textContent = '';
  try {
    await api('/auth/password', {
      method: 'POST',
      body: JSON.stringify({
        current_password: document.getElementById('acc-current').value,
        new_password: document.getElementById('acc-new').value,
      }),
    });
    document.getElementById('acc-current').value = '';
    document.getElementById('acc-new').value = '';
    closeAccount();
    showToast('🔑 パスワードを変更しました');
  } catch (e) { errEl.textContent = e.message; }
}

// 誤タップ防止: 1回目で確認表示、4秒以内の2回目で実行
function askConfirm(btn, label, fn) {
  if (btn.dataset.armed === '1') {
    delete btn.dataset.armed;
    clearTimeout(btn._confirmTimer);
    fn();
    return;
  }
  btn.dataset.armed = '1';
  const orig = btn.textContent;
  btn.textContent = label;
  btn.classList.add('confirming');
  btn._confirmTimer = setTimeout(() => {
    delete btn.dataset.armed;
    btn.textContent = orig;
    btn.classList.remove('confirming');
  }, 4000);
}

// UTCのDB日時文字列をローカルの "M/D HH:mm" に変換
function fmtLocal(utcStr) {
  const d = new Date(utcStr.replace(' ', 'T') + 'Z');
  return d.toLocaleString('ja-JP', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// ---- 描画 ----
function renderAll() {
  renderStatus();
  renderBadges();
  renderNoticeBanner();
  safeRender(renderAnnouncements());
  safeRender(renderContents());
  safeRender(renderQuests());
  safeRender(renderProposals());
  safeRender(renderShop());
  safeRender(renderLeaderboard());
  safeRender(renderActivity());
  safeRender(renderAdmin());
  document.getElementById('quest-create-box').style.display =
    me.permissions.includes('create_quests') ? 'block' : 'none';
  document.getElementById('nav-admin').style.display = me.role === 'admin' ? '' : 'none';
}

function renderStatus() {
  const r = me.rank;
  document.getElementById('lv-num').textContent = r.level;
  document.getElementById('rank-title').textContent = 'RANK — ' + r.current.key.toUpperCase();
  document.getElementById('rank-name').textContent = r.current.title;
  const em = document.getElementById('emblem');
  em.style.background = `linear-gradient(160deg, ${r.current.color1}, ${r.current.color2})`;
  em.style.boxShadow = `0 0 22px ${r.current.color2}55`;

  const span = r.next ? (r.next.min - r.current.min) : 1;
  const into = me.exp - r.current.min;
  const pct = r.next ? Math.min(100, Math.round((into / span) * 100)) : 100;
  document.getElementById('xp-fill').style.width = pct + '%';
  document.getElementById('xp-text').textContent = `EXP ${me.exp} / ${r.next ? r.next.min : r.current.min}`;
  document.getElementById('xp-next').textContent = r.next ? `次のランクまで ${r.next.min - me.exp} EXP` : '最高ランク到達';
  document.getElementById('points-num').textContent = me.points;

  const boostChip = document.getElementById('boost-chip');
  boostChip.style.display = me.boost_charges > 0 ? 'block' : 'none';
  document.getElementById('boost-num').textContent = me.boost_charges;

  // 権限チップ: 保持している権限 + 未解放権限(どうすれば解放されるか)
  renderNoticeBanner();

  const wrap = document.getElementById('perm-chips');
  wrap.innerHTML = '';
  for (const [perm, label] of Object.entries(meta.permission_labels)) {
    const el = document.createElement('span');
    const has = me.permissions.includes(perm);
    el.className = 'perm-chip' + (has ? '' : ' locked');
    el.textContent = (has ? '✓ ' : '🔒 ') + label;
    wrap.appendChild(el);
  }
}

const CAT_LABEL = { usage: '利用', learning: '学習', kaizen: '改善' };
const TYPE_LABEL = { tool: '🛠 ツール', article: '📄 記事', video: '🎬 動画' };

// ---- コンテンツ(社内ツール・記事・動画) ----
async function renderContents() {
  const grid = document.getElementById('content-grid');
  if (!grid.children.length) grid.innerHTML = '<div class="empty-note" style="grid-column:1/-1;">読み込み中...</div>';
  const { items, can_manage } = await api('/contents');
  document.getElementById('content-create-box').style.display = can_manage ? 'block' : 'none';
  if (items.length === 0) {
    grid.innerHTML = '<div class="empty-note" style="grid-column:1/-1;">まだコンテンツがありません。' +
      (can_manage ? '最初のツールや記事を登録しましょう!' : '登録をお楽しみに!') + '</div>';
    return;
  }
  grid.innerHTML = '';
  items.forEach(item => {
    const el = document.createElement('div');
    el.className = 'card' + (item.active ? '' : ' archived');
    el.innerHTML = `
      <div class="top">
        <div>
          <span class="type-tag type-${item.type}">${TYPE_LABEL[item.type] || item.type}</span>
          ${item.quest_id ? '<span class="repeat-tag">🔗 クエスト連動</span>' : ''}
          ${item.active ? '' : '<span class="repeat-tag">アーカイブ済み</span>'}
          <h4></h4>
        </div>
        ${item.url ? '<a class="content-link" target="_blank" rel="noopener">開く ↗</a>' : ''}
      </div>
      <div class="desc"></div>
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span class="repeat-tag content-author"></span>
        ${can_manage ? `<button class="archive-btn">${item.active ? 'アーカイブ' : '再公開'}</button>` : ''}
      </div>
    `;
    el.querySelector('h4').textContent = item.title;
    el.querySelector('.desc').textContent = item.description || '';
    el.querySelector('.content-author').textContent = item.author ? `登録: ${item.author}` : '';
    if (item.url) el.querySelector('.content-link').href = item.url;
    const btn = el.querySelector('.archive-btn');
    if (btn) btn.addEventListener('click', async () => {
      try {
        await api(`/contents/${item.id}`, { method: 'PATCH', body: JSON.stringify({ active: !item.active }) });
        safeRender(renderContents()); safeRender(renderQuests());
        showToast(item.active ? '📦 アーカイブしました(連動クエストも停止)' : '✅ 再公開しました');
      } catch (e) { showToast('⚠️ ' + e.message); }
    });
    grid.appendChild(el);
  });
}

async function createContent() {
  const expVal = document.getElementById('cc-exp').value;
  const ptsVal = document.getElementById('cc-pts').value;
  const body = {
    title: document.getElementById('cc-title').value,
    url: document.getElementById('cc-url').value,
    description: document.getElementById('cc-desc').value,
    type: document.getElementById('cc-type').value,
    auto_quest: document.getElementById('cc-autoquest').checked,
  };
  if (expVal) body.quest_exp = parseInt(expVal, 10);
  if (ptsVal) body.quest_pts = parseInt(ptsVal, 10);
  try {
    const res = await api('/contents', { method: 'POST', body: JSON.stringify(body) });
    ['cc-title', 'cc-url', 'cc-desc', 'cc-exp', 'cc-pts'].forEach(id => document.getElementById(id).value = '');
    safeRender(renderContents()); safeRender(renderQuests());
    if (me.role === 'admin') safeRender(renderAdminQuests());
    showToast(res.quest_id ? '📚 コンテンツを登録し、対応クエストを公開しました' : '📚 コンテンツを登録しました');
  } catch (e) { showToast('⚠️ ' + e.message); }
}

async function renderQuests() {
  const grid = document.getElementById('quest-grid');
  if (!grid.children.length) grid.innerHTML = '<div class="empty-note" style="grid-column:1/-1;">読み込み中...</div>';
  const { quests } = await api('/quests');
  // 挑戦可能 → クールダウン中 → 完了済み の順に整列(元の並びは維持)
  const group = q => q.available ? 0 : (q.repeatable ? 1 : 2);
  quests.sort((a, b) => group(a) - group(b));
  todayCounts.quests = quests.filter(q => q.available).length;
  updateTodayStrip();
  grid.innerHTML = '';
  quests.forEach(q => {
    const el = document.createElement('div');
    el.className = 'card';
    let btnLabel, btnClass = 'btn-earn', disabled = false;
    if (q.available) {
      btnLabel = `完了する (+${q.pts}pt)`;
    } else if (q.repeatable) {
      btnLabel = q.next_available_at
        ? `クールダウン中(${fmtLocal(q.next_available_at)} から再挑戦可)`
        : 'クールダウン中';
      btnClass = 'btn-done'; disabled = true;
    } else {
      btnLabel = '完了済み ✓'; btnClass = 'btn-done'; disabled = true;
    }
    el.innerHTML = `
      <div class="top">
        <div>
          <span class="cat-tag cat-${q.category}">${CAT_LABEL[q.category] || q.category}</span>
          ${q.repeatable ? '<span class="repeat-tag">↻ 繰り返し可</span>' : ''}
          <h4></h4>
        </div>
        <span class="reward">+${q.exp} EXP</span>
      </div>
      <div class="desc"></div>
      ${q.content_url ? '<a class="content-link quest-content-link" target="_blank" rel="noopener"></a>' : ''}
      <button class="btn ${btnClass}" ${disabled ? 'disabled' : ''}>${btnLabel}</button>
    `;
    el.querySelector('h4').textContent = q.title;
    el.querySelector('.desc').textContent = q.description;
    if (q.content_url) {
      const link = el.querySelector('.quest-content-link');
      link.href = q.content_url;
      link.textContent = `▶ ${q.content_title || 'コンテンツ'} を開く`;
    }
    if (!disabled) el.querySelector('button').addEventListener('click', () => completeQuest(q));
    grid.appendChild(el);
  });
}

async function completeQuest(q) {
  try {
    const res = await api(`/quests/${q.id}/complete`, { method: 'POST' });
    me = res.me;
    renderStatus(); renderBadges();
    safeRender(renderQuests()); safeRender(renderShop());
    safeRender(renderLeaderboard()); safeRender(renderActivity());
    const boostNote = res.awarded.boosted ? '(ブースト適用!)' : '';
    showToast(`✅ 「${q.title}」達成! +${res.awarded.exp} EXP / +${res.awarded.pts} pt ${boostNote}`);
    if (res.rank_up) setTimeout(() => showLevelUp(), 500);
  } catch (e) { showToast('⚠️ ' + e.message); }
}

async function createQuest() {
  const body = {
    title: document.getElementById('qc-title').value,
    description: document.getElementById('qc-desc').value,
    exp: parseInt(document.getElementById('qc-exp').value, 10),
    pts: parseInt(document.getElementById('qc-pts').value, 10),
    category: document.getElementById('qc-cat').value,
    cooldown_hours: document.getElementById('qc-cd').value ? parseInt(document.getElementById('qc-cd').value, 10) : null,
  };
  try {
    await api('/quests', { method: 'POST', body: JSON.stringify(body) });
    document.getElementById('qc-title').value = '';
    document.getElementById('qc-desc').value = '';
    safeRender(renderQuests());
    showToast('🛠️ クエストを公開しました');
  } catch (e) { showToast('⚠️ ' + e.message); }
}

// ---- 改善提案 ----
async function submitProposal() {
  const input = document.getElementById('proposal-input');
  const text = input.value.trim();
  if (!text) { showToast('提案内容を入力してください'); return; }
  try {
    const res = await api('/proposals', { method: 'POST', body: JSON.stringify({ text }) });
    me = res.me;
    input.value = '';
    renderStatus(); renderBadges();
    safeRender(renderProposals()); safeRender(renderShop());
    safeRender(renderActivity()); safeRender(renderLeaderboard());
    showToast(res.rewarded
      ? '💡 改善提案を投稿しました! +100 EXP / +30 pt'
      : '💡 改善提案を投稿しました(本日の投稿報酬は上限に達しています)');
    if (res.rank_up) setTimeout(() => showLevelUp(), 500);
  } catch (e) { showToast('⚠️ ' + e.message); }
}

async function renderProposals() {
  const feed = document.getElementById('proposal-feed');
  if (!feed.children.length) feed.innerHTML = '<div class="empty-note">読み込み中...</div>';
  const { proposals, can_review } = await api('/proposals');
  todayCounts.canReview = can_review;
  todayCounts.pending = proposals.filter(p => p.status === 'pending' && !p.mine).length;
  updateTodayStrip();
  if (proposals.length === 0) {
    feed.innerHTML = '<div class="empty-note">まだ改善提案がありません。最初の提案を投稿してみましょう!</div>';
    return;
  }
  feed.innerHTML = '';
  proposals.forEach(p => {
    const el = document.createElement('div');
    el.className = 'proposal-item';
    const date = p.created_at.slice(5, 10).replace('-', '/');
    const chip = p.status === 'approved' ? '<span class="approve-chip done">✓ 採用済み</span>'
      : p.status === 'rejected' ? '<span class="approve-chip rejected">見送り</span>'
      : '<span class="approve-chip pending">審査中</span>';
    const canAct = can_review && p.status === 'pending' && !p.mine;
    const canEdit = p.mine && p.status === 'pending';
    el.innerHTML = `
      <div class="meta"><span class="who"></span><span class="when">${date}</span></div>
      <div class="txt"></div>
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span>${chip}${p.reviewer ? ` <span class="repeat-tag">by ${escapeText(p.reviewer)}</span>` : ''}</span>
        <span class="prop-actions">
          ${canEdit ? '<button class="p-edit">✏️ 編集</button><button class="p-withdraw">取り下げ</button>' : ''}
          ${canAct ? '<button class="approve-btn" data-act="approved">採用</button><button class="approve-btn reject-btn" data-act="rejected">見送り</button>' : ''}
        </span>
      </div>
    `;
    el.querySelector('.who').textContent = p.author + (p.mine ? '(あなた)' : '');
    el.querySelector('.txt').textContent = p.text;
    el.querySelectorAll('.approve-btn').forEach(btn => {
      btn.addEventListener('click', () => reviewProposal(p.id, btn.dataset.act));
    });
    const editBtn = el.querySelector('.p-edit');
    if (editBtn) editBtn.addEventListener('click', () => startEditProposal(el, p));
    const wdBtn = el.querySelector('.p-withdraw');
    if (wdBtn) wdBtn.addEventListener('click', () =>
      askConfirm(wdBtn, 'もう一度押すと取り下げ(報酬返還)', () => withdrawProposal(p.id)));
    feed.appendChild(el);
  });
}

function startEditProposal(el, p) {
  const txtEl = el.querySelector('.txt');
  if (el.querySelector('.prop-edit-area')) return; // 二重起動防止
  const area = document.createElement('textarea');
  area.className = 'prop-edit-area';
  area.value = p.text;
  const save = document.createElement('button');
  save.className = 'approve-btn';
  save.textContent = '保存';
  const cancel = document.createElement('button');
  cancel.className = 'approve-btn reject-btn';
  cancel.textContent = 'キャンセル';
  txtEl.style.display = 'none';
  txtEl.after(area, save, cancel);
  cancel.addEventListener('click', () => { area.remove(); save.remove(); cancel.remove(); txtEl.style.display = ''; });
  save.addEventListener('click', async () => {
    try {
      await api(`/proposals/${p.id}`, { method: 'PATCH', body: JSON.stringify({ text: area.value.trim() }) });
      safeRender(renderProposals());
      showToast('✏️ 提案を更新しました');
    } catch (e) { showToast('⚠️ ' + e.message); }
  });
  area.focus();
}

async function withdrawProposal(id) {
  try {
    const res = await api(`/proposals/${id}`, { method: 'DELETE' });
    me = res.me;
    renderStatus(); renderBadges();
    safeRender(renderProposals()); safeRender(renderActivity()); safeRender(renderLeaderboard());
    showToast('提案を取り下げました(投稿報酬を返還)');
  } catch (e) { showToast('⚠️ ' + e.message); }
}

async function reviewProposal(id, decision) {
  try {
    const res = await api(`/proposals/${id}/review`, { method: 'POST', body: JSON.stringify({ decision }) });
    me = res.me;
    renderStatus();
    safeRender(renderProposals()); safeRender(renderActivity());
    safeRender(renderLeaderboard()); safeRender(renderAdmin());
    showToast(decision === 'approved' ? '🏆 提案を採用しました(投稿者にボーナス加算 / あなたに +20 EXP)' : '審査を完了しました(+20 EXP)');
    if (res.rank_up) setTimeout(() => showLevelUp(), 500);
  } catch (e) { showToast('⚠️ ' + e.message); }
}

// ---- ショップ ----
async function renderShop() {
  const grid = document.getElementById('shop-grid');
  if (!grid.children.length) grid.innerHTML = '<div class="empty-note" style="grid-column:1/-1;">読み込み中...</div>';
  const { items } = await api('/shop');
  grid.innerHTML = '';
  items.forEach(s => {
    const done = s.redeemed && !s.repeatable;
    const canAfford = me.points >= s.cost;
    const locked = !!s.locked_reason;
    const el = document.createElement('div');
    el.className = 'card';
    let btnLabel = '交換する', btnClass = 'btn-spend', disabled = false;
    if (done) { btnLabel = '解放済み ✓'; btnClass = 'btn-done'; disabled = true; }
    else if (locked) { btnLabel = s.locked_reason; btnClass = 'btn-done'; disabled = true; }
    else if (!canAfford) { btnLabel = 'ポイント不足'; disabled = true; }
    const boughtTag = s.redeemed && s.repeatable
      ? `<span class="repeat-tag">✓ 購入済み ×${s.redeemed_count}(再購入可)</span>` : '';
    el.innerHTML = `
      <div class="top"><div><h4></h4>${boughtTag}</div><span class="cost">${s.cost} pt</span></div>
      <div class="desc"></div>
      ${s.redeemed && s.redeem_note ? '<div class="redeem-note"></div>' : ''}
      <button class="btn ${btnClass}" ${disabled ? 'disabled' : ''}>${btnLabel}</button>
    `;
    el.querySelector('h4').textContent = s.title;
    el.querySelector('.desc').textContent = s.description;
    const noteEl = el.querySelector('.redeem-note');
    if (noteEl) noteEl.textContent = '📌 ' + s.redeem_note;
    if (!disabled) {
      const btn = el.querySelector('button');
      btn.addEventListener('click', () =>
        askConfirm(btn, `${s.cost}pt 消費します — もう一度押して確定`, () => redeem(s)));
    }
    grid.appendChild(el);
  });
}

async function redeem(s) {
  try {
    const res = await api(`/shop/${s.id}/redeem`, { method: 'POST' });
    me = res.me;
    renderStatus();
    safeRender(renderShop()); safeRender(renderActivity());
    showToast(`🔓 「${s.title}」を解放しました` + (s.redeem_note ? ` — ${s.redeem_note}` : ''));
  } catch (e) { showToast('⚠️ ' + e.message); }
}

// ---- バッジ・ランキング・履歴 ----
function renderBadges() {
  const grid = document.getElementById('badge-grid');
  grid.innerHTML = '';
  let n = 0;
  me.badges.forEach(b => {
    if (b.unlocked) n++;
    const el = document.createElement('div');
    el.className = 'badge' + (b.unlocked ? ' unlocked' : '');
    el.innerHTML = `<span class="icon">${b.icon}</span><span class="name"></span>`;
    el.querySelector('.name').textContent = b.name;
    grid.appendChild(el);
  });
  document.getElementById('badge-count').textContent = `${n} / ${me.badges.length} 解除`;
}

async function renderLeaderboard() {
  const box = document.getElementById('leaderboard');
  if (!box.children.length) box.innerHTML = '<div class="empty-note">読み込み中...</div>';
  const { rows } = await api('/leaderboard');
  if (rows.length === 0) {
    box.innerHTML = '<div class="empty-note">まだ誰もいません。最初のプレイヤーになりましょう!</div>';
    return;
  }
  box.innerHTML = '';
  const isMentor = me.permissions.includes('mentor');
  rows.forEach((row, i) => {
    const el = document.createElement('div');
    el.className = 'lb-row' + (row.me ? ' me' : '');
    el.innerHTML = `
      <span class="lb-rank">${i + 1}</span>
      <span class="lb-name"></span>
      <span class="lb-xp">LV${row.level} / ${row.exp} EXP</span>
      ${isMentor && !row.me ? '<button class="praise-btn">👏 称賛 +30EXP</button>' : ''}
    `;
    el.querySelector('.lb-name').textContent = row.name + (row.me ? ' (あなた)' : '');
    const btn = el.querySelector('.praise-btn');
    if (btn) btn.addEventListener('click', () => praise(row, btn));
    box.appendChild(el);
  });
}

async function praise(row, btn) {
  try {
    await api(`/users/${row.id}/praise`, { method: 'POST' });
    btn.disabled = true;
    btn.textContent = '👏 贈りました';
    showToast(`👏 ${row.name} さんに称賛ボーナスを贈りました(+30 EXP)`);
  } catch (e) { showToast('⚠️ ' + e.message); }
}

const LEDGER_LABEL = {
  quest: 'クエスト達成', proposal_submit: '改善提案を投稿', proposal_adopted: '提案が採用',
  proposal_withdrawn: '提案を取り下げ', approve_reward: '審査ボーナス', shop: 'ショップ交換',
  mentor_bonus: '称賛ボーナス', admin_adjust: '管理者調整',
};

async function renderActivity() {
  const box = document.getElementById('activity-log');
  if (!box.children.length) box.innerHTML = '<div class="empty-note">読み込み中...</div>';
  const { rows } = await api('/activity');
  if (rows.length === 0) {
    box.innerHTML = '<div class="empty-note">まだ履歴がありません</div>';
    return;
  }
  box.innerHTML = '';
  rows.forEach(r => {
    const el = document.createElement('div');
    el.className = 'lb-row';
    const parts = [];
    if (r.delta_exp) parts.push(`${r.delta_exp > 0 ? '+' : ''}${r.delta_exp} EXP`);
    if (r.delta_points) parts.push(`${r.delta_points > 0 ? '+' : ''}${r.delta_points} pt`);
    el.innerHTML = `
      <span class="lb-name"></span>
      <span class="lb-xp">${parts.join(' / ') || '—'}</span>
      <span class="lb-xp">${r.created_at.slice(5, 16)}</span>
    `;
    el.querySelector('.lb-name').textContent = (LEDGER_LABEL[r.type] || r.type) + (r.note ? `:${r.note}` : '');
    box.appendChild(el);
  });
}

// ---- 管理者 ----
async function renderAdmin() {
  const panel = document.getElementById('admin-panel');
  if (me.role !== 'admin') { panel.style.display = 'none'; return; }
  panel.style.display = 'block';
  const [{ users }, stats] = await Promise.all([api('/admin/users'), api('/admin/stats')]);
  document.getElementById('admin-stats').textContent =
    `メンバー ${stats.users}人 / クエスト達成 ${stats.quest_completions}件 / 提案 ${stats.proposals}件(採用 ${stats.proposals_approved})` +
    (stats.unfulfilled_redemptions > 0 ? ` / ⚠ 未対応の交換 ${stats.unfulfilled_redemptions}件` : '');
  renderAdminTrend(stats.trend || []);
  safeRender(renderAdminRedemptions());
  safeRender(renderAdminAnnouncements());
  const box = document.getElementById('admin-users');
  box.innerHTML = '';
  users.forEach(u => {
    const el = document.createElement('div');
    const dormant = u.inactive_days >= 7;
    el.className = 'lb-row' + (dormant ? ' dormant' : '');
    const lastActive = u.last_active
      ? `最終活動 ${fmtLocal(u.last_active)}` : '活動なし';
    el.innerHTML = `
      <span class="lb-name"></span>
      <span class="lb-xp">${dormant ? '⚠ ' : ''}${lastActive}</span>
      <span class="lb-xp">LV${u.level} / ${u.exp} EXP / ${u.points} pt</span>
      <button class="role-btn adjust-btn">調整</button>
      <button class="role-btn pw-btn">PW再設定</button>
      <button class="role-btn">${u.role === 'admin' ? 'member に降格' : 'admin に昇格'}</button>
    `;
    el.querySelector('.lb-name').textContent = `${u.name} [${u.role}]`;
    el.querySelector('.adjust-btn').addEventListener('click', () => toggleAdjustForm(el, u));
    el.querySelector('.pw-btn').addEventListener('click', async () => {
      const pw = prompt(`${u.name} さんの新しいパスワード(8文字以上)を入力してください。\n本人が忘れた場合の再設定用です。既存のログインはすべて無効になります。`);
      if (pw === null) return;
      try {
        await api(`/admin/users/${u.id}/password`, { method: 'POST', body: JSON.stringify({ password: pw }) });
        showToast(`🔑 ${u.name} さんのパスワードを再設定しました`);
      } catch (e) { showToast('⚠️ ' + e.message); }
    });
    el.querySelector('.role-btn:not(.pw-btn):not(.adjust-btn)').addEventListener('click', async () => {
      try {
        await api(`/admin/users/${u.id}/role`, {
          method: 'POST',
          body: JSON.stringify({ role: u.role === 'admin' ? 'member' : 'admin' }),
        });
        safeRender(renderAdmin());
        showToast('ロールを変更しました');
      } catch (e) { showToast('⚠️ ' + e.message); }
    });
    box.appendChild(el);
  });
  renderAdminQuests();
  renderAdminShop();
}

// 手動EXP/pt調整のインラインフォーム
function toggleAdjustForm(row, u) {
  const existing = row.nextElementSibling;
  if (existing && existing.classList.contains('adjust-row')) { existing.remove(); return; }
  const form = document.createElement('div');
  form.className = 'lb-row adjust-row';
  form.innerHTML = `
    <span class="lb-name">${'　'}↳ 調整量(マイナス可)</span>
    <label class="repeat-tag">EXP <input class="mini-input aj-exp" type="number" value="0" min="-1000" max="1000"></label>
    <label class="repeat-tag">pt <input class="mini-input aj-pts" type="number" value="0" min="-500" max="500"></label>
    <input class="mini-input aj-note" type="text" placeholder="理由(本人に表示)" style="width:180px;" maxlength="60">
    <button class="save-btn">適用</button>
  `;
  form.querySelector('.save-btn').addEventListener('click', async () => {
    try {
      const res = await api(`/admin/users/${u.id}/adjust`, {
        method: 'POST',
        body: JSON.stringify({
          exp: parseInt(form.querySelector('.aj-exp').value, 10) || 0,
          points: parseInt(form.querySelector('.aj-pts').value, 10) || 0,
          note: form.querySelector('.aj-note').value,
        }),
      });
      safeRender(renderAdmin()); safeRender(renderLeaderboard());
      showToast(`🛠 ${u.name} さんに調整を適用しました(EXP ${res.applied_exp >= 0 ? '+' : ''}${res.applied_exp} / pt ${res.applied_pts >= 0 ? '+' : ''}${res.applied_pts})`);
    } catch (e) { showToast('⚠️ ' + e.message); }
  });
  row.after(form);
}

async function renderAdminRedemptions() {
  const box = document.getElementById('admin-redemptions');
  const { redemptions } = await api('/admin/redemptions');
  if (redemptions.length === 0) {
    box.innerHTML = '<div class="empty-note">まだ交換はありません</div>';
    return;
  }
  box.innerHTML = '';
  redemptions.forEach(r => {
    const el = document.createElement('div');
    el.className = 'lb-row' + (r.fulfilled_at ? ' inactive' : '');
    el.innerHTML = `
      <span class="lb-name"></span>
      <span class="lb-xp">${fmtLocal(r.created_at)}</span>
      <span class="lb-xp fulfill-state"></span>
      <button class="role-btn">${r.fulfilled_at ? '未対応に戻す' : '✓ 対応済みにする'}</button>
    `;
    el.querySelector('.lb-name').textContent = `${r.user} — ${r.item}`;
    el.querySelector('.fulfill-state').textContent = r.fulfilled_at
      ? (r.fulfilled_by_name ? `対応済み(${r.fulfilled_by_name})` : '自動履行')
      : '⏳ 未対応';
    el.querySelector('.role-btn').addEventListener('click', async () => {
      try {
        await api(`/admin/redemptions/${r.id}/fulfill`, { method: 'POST' });
        safeRender(renderAdminRedemptions());
      } catch (e) { showToast('⚠️ ' + e.message); }
    });
    box.appendChild(el);
  });
}

function renderAdminTrend(trend) {
  const box = document.getElementById('admin-trend');
  if (trend.length === 0) {
    box.innerHTML = '<div class="empty-note">まだ活動データがありません</div>';
    return;
  }
  box.innerHTML = '';
  trend.forEach(t => {
    const el = document.createElement('div');
    el.className = 'lb-row';
    el.innerHTML = `
      <span class="lb-xp" style="width:84px;">${t.d.slice(5).replace('-', '/')}</span>
      <span class="lb-name">アクティブ ${t.active_users}人</span>
      <span class="lb-xp">${t.actions} アクション</span>
    `;
    box.appendChild(el);
  });
}

async function renderAdminAnnouncements() {
  const box = document.getElementById('admin-announcements');
  const { items } = await api('/admin/announcements');
  if (items.length === 0) {
    box.innerHTML = '<div class="empty-note">配信中のお知らせはありません</div>';
    return;
  }
  box.innerHTML = '';
  items.forEach(a => {
    const el = document.createElement('div');
    el.className = 'lb-row' + (a.active ? '' : ' inactive');
    el.innerHTML = `
      <span class="lb-name"></span>
      <span class="lb-xp">${fmtLocal(a.created_at)}</span>
      <button class="role-btn">${a.active ? '掲載終了' : '再掲載'}</button>
    `;
    el.querySelector('.lb-name').textContent = (a.active ? '📢 ' : '') + a.body;
    el.querySelector('.role-btn').addEventListener('click', async () => {
      try {
        await api(`/admin/announcements/${a.id}`, { method: 'PATCH', body: JSON.stringify({ active: !a.active }) });
        safeRender(renderAdminAnnouncements()); safeRender(renderAnnouncements());
      } catch (e) { showToast('⚠️ ' + e.message); }
    });
    box.appendChild(el);
  });
}

async function adminPostAnnouncement() {
  const body = document.getElementById('an-body').value.trim();
  if (!body) { showToast('お知らせの内容を入力してください'); return; }
  try {
    await api('/admin/announcements', { method: 'POST', body: JSON.stringify({ body }) });
    document.getElementById('an-body').value = '';
    safeRender(renderAdminAnnouncements()); safeRender(renderAnnouncements());
    showToast('📢 お知らせを配信しました');
  } catch (e) { showToast('⚠️ ' + e.message); }
}

async function renderAdminQuests() {
  const box = document.getElementById('admin-quest-list');
  const { quests } = await api('/admin/quests');
  box.innerHTML = '';
  quests.forEach(q => {
    const el = document.createElement('div');
    el.className = 'lb-row' + (q.active ? '' : ' inactive');
    el.innerHTML = `
      <span class="lb-name"></span>
      <span class="lb-xp">達成 ${q.completions}回</span>
      <label class="repeat-tag">EXP <input class="mini-input q-exp" type="number" min="1" max="300" value="${q.exp}"></label>
      <label class="repeat-tag">pt <input class="mini-input q-pts" type="number" min="0" max="100" value="${q.pts}"></label>
      <button class="save-btn">保存</button>
      <button class="role-btn">${q.active ? '無効化' : '有効化'}</button>
    `;
    el.querySelector('.lb-name').textContent =
      q.title + (q.content_title ? `(連動: ${q.content_title})` : '') + (q.active ? '' : ' [停止中]');
    el.querySelector('.save-btn').addEventListener('click', async () => {
      try {
        await api(`/admin/quests/${q.id}`, {
          method: 'PATCH',
          body: JSON.stringify({
            exp: parseInt(el.querySelector('.q-exp').value, 10),
            pts: parseInt(el.querySelector('.q-pts').value, 10),
          }),
        });
        safeRender(renderQuests()); safeRender(renderAdminQuests());
        showToast('💾 クエストの報酬を更新しました');
      } catch (e) { showToast('⚠️ ' + e.message); }
    });
    el.querySelector('.role-btn').addEventListener('click', async () => {
      try {
        await api(`/admin/quests/${q.id}`, { method: 'PATCH', body: JSON.stringify({ active: !q.active }) });
        safeRender(renderQuests()); safeRender(renderAdminQuests());
        showToast(q.active ? 'クエストを無効化しました' : 'クエストを有効化しました');
      } catch (e) { showToast('⚠️ ' + e.message); }
    });
    box.appendChild(el);
  });
}

async function renderAdminShop() {
  const box = document.getElementById('admin-shop-list');
  const { items } = await api('/admin/shop');
  box.innerHTML = '';
  items.forEach(s => {
    const el = document.createElement('div');
    el.className = 'lb-row' + (s.active ? '' : ' inactive');
    el.innerHTML = `
      <span class="lb-name"></span>
      <label class="repeat-tag">pt <input class="mini-input s-cost" type="number" min="1" max="500" value="${s.cost}"></label>
      <button class="save-btn">保存</button>
      <button class="role-btn">${s.active ? '停止' : '再開'}</button>
    `;
    el.querySelector('.lb-name').textContent =
      s.title + (s.repeatable ? '(繰返し可)' : '') + (s.active ? '' : ' [停止中]');
    el.querySelector('.save-btn').addEventListener('click', async () => {
      try {
        await api(`/admin/shop/${s.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ cost: parseInt(el.querySelector('.s-cost').value, 10) }),
        });
        safeRender(renderShop()); safeRender(renderAdminShop());
        showToast('💾 アイテム価格を更新しました');
      } catch (e) { showToast('⚠️ ' + e.message); }
    });
    el.querySelector('.role-btn').addEventListener('click', async () => {
      try {
        await api(`/admin/shop/${s.id}`, { method: 'PATCH', body: JSON.stringify({ active: !s.active }) });
        safeRender(renderShop()); safeRender(renderAdminShop());
        showToast(s.active ? 'アイテムを停止しました' : 'アイテムを再開しました');
      } catch (e) { showToast('⚠️ ' + e.message); }
    });
    box.appendChild(el);
  });
}

async function adminAddShopItem() {
  try {
    await api('/admin/shop', {
      method: 'POST',
      body: JSON.stringify({
        title: document.getElementById('as-title').value,
        description: document.getElementById('as-desc').value,
        cost: parseInt(document.getElementById('as-cost').value, 10),
        repeatable: document.getElementById('as-repeat').checked,
        redeem_note: document.getElementById('as-note').value,
      }),
    });
    document.getElementById('as-title').value = '';
    document.getElementById('as-desc').value = '';
    document.getElementById('as-note').value = '';
    safeRender(renderShop()); safeRender(renderAdminShop());
    showToast('🛒 ショップにアイテムを追加しました');
  } catch (e) { showToast('⚠️ ' + e.message); }
}

// ---- UI ユーティリティ ----
function escapeText(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => t.classList.remove('show'), 3200);
}

function showLevelUp() {
  const r = me.rank;
  document.getElementById('lu-rank-name').textContent = r.current.key.toUpperCase();
  document.getElementById('lu-sub').textContent = `称号が「${r.current.title}」に進化しました`;
  const newPerms = (meta.rank_permissions[r.current.key] || [])
    .map(p => meta.permission_labels[p]).filter(Boolean);
  document.getElementById('lu-perms').textContent =
    newPerms.length ? `🔓 新権限解放: ${newPerms.join('、')}` : '';
  document.getElementById('levelup-overlay').classList.add('show');
}

function closeOverlay() { document.getElementById('levelup-overlay').classList.remove('show'); }

// 演出・設定オーバーレイは背景クリックでも閉じられるようにする
document.getElementById('levelup-overlay').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeOverlay();
});
document.getElementById('account-overlay').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeAccount();
});
document.getElementById('guide-overlay').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeGuide();
});

// Enterキーでログイン
document.getElementById('auth-password').addEventListener('keydown', e => {
  if (e.key === 'Enter') submitAuth();
});

init();
