/* el():輕量 DOM 建構輔助(屬性/子節點;null/false 子節點略過) */
export const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;          // null/false → 不設屬性
    if (k === 'class') e.className = v;
    else if (k === 'onclick') e.onclick = v;
    else if (k === 'text') e.textContent = v;
    else if (k === 'disabled') e.disabled = !!v;      // 布林屬性正確處理
    else e.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    e.appendChild(typeof kid === 'string' ? document.createTextNode(kid) : kid);
  }
  return e;
};
