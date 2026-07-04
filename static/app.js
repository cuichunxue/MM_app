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
    if (authMode === 'register') showToast(`ようこそ、${me.name} さん!最初のクエストに挑戦しましょう`);
  } catch (e) {
    errEl.textContent = e.message;
  }
}

async function logout() {
  try { await api('/auth/logout', { method: 'POST' }); } catch (e) {}
  location.reload();
}

// ---- 描画 ----
function renderAll() {
  renderStatus();
  renderBadges();
  safeRender(renderContents());
  safeRender(renderQuests());
  safeRender(renderProposals());
  safeRender(renderShop());
  safeRender(renderLeaderboard());
  safeRender(renderActivity());
  safeRender(renderAdmin());
  document.getElementById('quest-create-box').style.display =
    me.permissions.includes('create_quests') ? 'block' : 'none';
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
          ${item.quest_id ? '<span class="repeat-tag">⚔ クエスト連動</span>' : ''}
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
  const { quests } = await api('/quests');
  grid.innerHTML = '';
  quests.forEach(q => {
    const el = document.createElement('div');
    el.className = 'card';
    let btnLabel, btnClass = 'btn-earn', disabled = false;
    if (q.available) {
      btnLabel = `完了する (+${q.pts}pt)`;
    } else if (q.repeatable) {
      btnLabel = 'クールダウン中'; btnClass = 'btn-done'; disabled = true;
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
    showToast('💡 改善提案を投稿しました! +100 EXP / +30 pt');
    if (res.rank_up) setTimeout(() => showLevelUp(), 500);
  } catch (e) { showToast('⚠️ ' + e.message); }
}

async function renderProposals() {
  const feed = document.getElementById('proposal-feed');
  const { proposals, can_review } = await api('/proposals');
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
    el.innerHTML = `
      <div class="meta"><span class="who"></span><span class="when">${date}</span></div>
      <div class="txt"></div>
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span>${chip}${p.reviewer ? ` <span class="repeat-tag">by ${escapeText(p.reviewer)}</span>` : ''}</span>
        <span>
          ${canAct ? '<button class="approve-btn" data-act="approved">採用</button><button class="approve-btn reject-btn" data-act="rejected">見送り</button>' : ''}
        </span>
      </div>
    `;
    el.querySelector('.who').textContent = p.author + (p.mine ? '(あなた)' : '');
    el.querySelector('.txt').textContent = p.text;
    el.querySelectorAll('.approve-btn').forEach(btn => {
      btn.addEventListener('click', () => reviewProposal(p.id, btn.dataset.act));
    });
    feed.appendChild(el);
  });
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
    el.innerHTML = `
      <div class="top"><h4></h4><span class="cost">${s.cost} pt</span></div>
      <div class="desc"></div>
      <button class="btn ${btnClass}" ${disabled ? 'disabled' : ''}>${btnLabel}</button>
    `;
    el.querySelector('h4').textContent = s.title;
    el.querySelector('.desc').textContent = s.description;
    if (!disabled) el.querySelector('button').addEventListener('click', () => redeem(s));
    grid.appendChild(el);
  });
}

async function redeem(s) {
  try {
    const res = await api(`/shop/${s.id}/redeem`, { method: 'POST' });
    me = res.me;
    renderStatus();
    safeRender(renderShop()); safeRender(renderActivity());
    showToast(`🔓 「${s.title}」を解放しました`);
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
  approve_reward: '審査ボーナス', shop: 'ショップ交換', mentor_bonus: '称賛ボーナス', admin_adjust: '管理者調整',
};

async function renderActivity() {
  const box = document.getElementById('activity-log');
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
    `メンバー ${stats.users}人 / クエスト達成 ${stats.quest_completions}件 / 提案 ${stats.proposals}件(採用 ${stats.proposals_approved})`;
  const box = document.getElementById('admin-users');
  box.innerHTML = '';
  users.forEach(u => {
    const el = document.createElement('div');
    el.className = 'lb-row';
    el.innerHTML = `
      <span class="lb-name"></span>
      <span class="lb-xp">LV${u.level} / ${u.exp} EXP / ${u.points} pt</span>
      <button class="role-btn">${u.role === 'admin' ? 'member に降格' : 'admin に昇格'}</button>
    `;
    el.querySelector('.lb-name').textContent = `${u.name} [${u.role}]`;
    el.querySelector('.role-btn').addEventListener('click', async () => {
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

async function renderAdminQuests() {
  const box = document.getElementById('admin-quest-list');
  const { quests } = await api('/admin/quests');
  box.innerHTML = '';
  quests.forEach(q => {
    const el = document.createElement('div');
    el.className = 'lb-row' + (q.active ? '' : ' inactive');
    el.innerHTML = `
      <span class="lb-name"></span>
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
      }),
    });
    document.getElementById('as-title').value = '';
    document.getElementById('as-desc').value = '';
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

// Enterキーでログイン
document.getElementById('auth-password').addEventListener('keydown', e => {
  if (e.key === 'Enter') submitAuth();
});

init();
