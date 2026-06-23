// ===== Cloudflare 挑战页等待器（对所有域名生效） =====
// 每 500ms 查一次：CF 拦截元素是否还在 DOM 中。
// 都不在 → 放行；存在 → 继续等，直到挑战通过或上层超时。
// 正常页面零开销：一次 querySelector 立即 resolve。
//
// 覆盖的 CF 拦截形态：
//   #challenge-form                                 — 旧版「Checking your browser…」5 秒盾
//   .cf-browser-verification                        — 同上的 wrapper class
//   #challenge-stage                                — 2024+ 新版 JS challenge 容器
//   iframe[src*='challenges.cloudflare.com']        — Turnstile 验证码 iframe（stackoverflow 等用）
//   #cf-chl-widget                                  — Turnstile widget 挂载点
const CF_CHALLENGE_SELECTOR = [
    "#challenge-form",
    ".cf-browser-verification",
    "#challenge-stage",
    "iframe[src*='challenges.cloudflare.com']",
    "#cf-chl-widget",
].join(", ");

// 最长等 25 秒，超时后放行（让上层拿到挑战页 HTML 自行判断/重试）。
// 不 reject 而是 resolve：避免与 page_timeout(120s) 叠加浪费配额，也方便上层
// 通过 <title>Just a moment...</title> 等特征识别 CF 挑战页。
await new Promise((resolve) => {
    const deadline = Date.now() + 25000;
    const poll = () => {
        if (!document.querySelector(CF_CHALLENGE_SELECTOR) || Date.now() > deadline) {
            resolve();
        } else {
            setTimeout(poll, 500);
        }
    };
    poll();
});

// ===== Expand/read-more (whitelisted domains only) =====

const whitelist = ["zhihu.com", "csdn.net", "stackoverflow.com"];
if (!whitelist.some((domain) => location.hostname === domain || location.hostname.endsWith(`.${domain}`))) {
    return;
}

const targets = "button, a, [role='button']";
const groupRe = /^(查看全部|展开全部|显示全部)|(?:全部回答|全部评论|全部回复|(?:view|show)\s+all\s+(?:answers|comments|replies)|more replies|more comments)/i;
const itemRe = /(?:阅读全文|展开全文|展开剩余|继续阅读|read more|show more|see more|view more)/i;
const clicked = new WeakSet();
const wait = (base) => new Promise((resolve) => setTimeout(resolve, base + Math.floor(Math.random() * 200)));

for (const [rule, waitMs] of [[groupRe, 250], [itemRe, 200]]) {
    for (let round = 0; round < 3; round++) {
        const matched = [];

        for (const el of document.querySelectorAll(targets)) {
            if (clicked.has(el) || el.matches(":disabled, [aria-disabled='true']")) {
                continue;
            }

            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            if (
                style.display === "none" ||
                style.visibility === "hidden" ||
                style.opacity === "0" ||
                rect.width === 0 ||
                rect.height === 0
            ) {
                continue;
            }

            const text = `${el.innerText || el.textContent || ""} ${el.getAttribute("aria-label") || ""}`
                .replace(/\s+/g, " ")
                .trim();

            if (!rule.test(text)) continue;
            
            if (
                el.tagName === "A" &&
                rule === itemRe &&
                !/^(#|javascript:)/i.test(el.getAttribute("href") || "")
            ) {
                continue;
            }

            matched.push(el);
        }

        if (matched.length === 0) {
            break;
        }

        for (const el of matched) {
            try {
                el.click();
                clicked.add(el);
            } catch (_) {}

            for (let p = el.parentElement, i = 0; p && i < 4; p = p.parentElement, i++) {
                p.style.maxHeight = "none";
                p.style.overflow = "visible";
                p.style.webkitMaskImage = "none";
                p.style.maskImage = "none";
            }
        }

        await wait(waitMs);
    }
}
