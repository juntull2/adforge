() => {
  const result = [];
  const labels = [...document.querySelectorAll('span,div')].filter(
    e => e.children.length === 0 && /^(라이브러리 ID:|Library ID:)/.test(e.textContent.trim())
  );
  for (const label of labels) {
    let card = label.parentElement;
    while (card && !card.querySelector('a[href]')) card = card.parentElement;
    if (!card || (card.innerText.match(/(?:라이브러리 ID:|Library ID:)/g) || []).length !== 1) continue;
    const id = label.textContent.match(/\d+/)?.[0];
    const links = [...card.querySelectorAll('a[href]')].map(a => ({text: a.innerText.trim(), url: a.href}));
    const profile = links.find(a => /^https:\/\/(?:www\.)?facebook.com\//.test(a.url) && !/\/ads\//.test(a.url));
    const name = profile?.text || card.querySelector('img[alt]')?.alt || '';
    const pageId = profile?.url.match(/facebook.com\/([^/?]+)/)?.[1] || '';
    const outbound = links.filter(a => !/^https:\/\/(?:www\.)?facebook.com\//.test(a.url));
    const landing = outbound.find(a => /l\.facebook\.com\/l\.php/.test(a.url)) || outbound[0];
    let landingUrl = landing?.url || '';
    try { landingUrl = new URL(landingUrl).searchParams.get('u') || landingUrl; } catch (_) {}
    const buttons = [...card.querySelectorAll('[role="button"]')].map(b => b.innerText.trim());
    const body = buttons.filter(t => t.length > 45).sort((a,b) => b.length-a.length)[0] || '';
    const match = card.innerText.match(/(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?.*게재 시작/);
    let start = match ? `${match[1]}-${match[2].padStart(2,'0')}-${match[3].padStart(2,'0')}` : '';
    if (!start) {
      const en = card.innerText.match(/Started running on (.+)/i);
      if (en && !Number.isNaN(Date.parse(en[1]))) start = new Date(en[1]).toISOString().slice(0,10);
    }
    const videos = [...card.querySelectorAll('video')].map(v => ({
      video_sd_url: /^https?:/.test(v.currentSrc || v.src) ? (v.currentSrc || v.src) : '',
      video_preview_image_url: v.poster
    }));
    const images = [...card.querySelectorAll('img')].filter(i => i.alt !== name && i.currentSrc).map(i => ({original_image_url:i.currentSrc}));
    result.push({ad_archive_id:id, page_id:pageId, page_name:name, start_date:start,
      is_active:!/(비활성|Inactive)/.test(card.innerText.slice(0,60)),
      snapshot:{page_id:pageId, page_name:name, body:{text:body}, link_url:landingUrl,
        title:landing?.text || '', caption:landingUrl ? new URL(landingUrl).hostname : '',
        videos, images, extra_links:outbound.map(a => ({link_url:a.url}))}
    });
  }
  return result;
}
