// بيبني الشريط العلوي والقائمة الجانبية حول <main> في كل صفحة داخلية.
const NAV = [['dashboard', 'نظرة عامة'], ['knowledge', 'قاعدة المعرفة'], ['bot', 'بوت تليجرام'], ['conversations', 'المحادثات', 2], ['company', 'ملف الشركة'], ['billing', 'الاشتراك']];
(() => {
  const cur = document.body.dataset.page, main = document.querySelector('main');
  const top = `<header class="top"><a class="logo" href="dashboard.html"><i>T</i>TeleDesk</a><input placeholder="ابحث في المحادثات والملفات" aria-label="بحث"><span class="tag">● البوت شغال</span></header>`;
  const side = `<nav class="side">${NAV.map(([k, t, n]) => `<a href="${k}.html" class="${k === cur ? 'on' : ''}">${t}${n ? `<span class="tag a">${n}</span>` : ''}</a>`).join('')}
  <div class="plan"><div class="row sp"><b>خطة Pro</b><span>14%</span></div><div class="bar"><i style="width:14%"></i></div><div class="mut">1,429 من 10,000 رسالة</div></div></nav>`;
  document.body.insertAdjacentHTML('afterbegin', top + '<div class="wrap">' + side + '</div>');
  document.querySelector('.wrap').appendChild(main);
})();
