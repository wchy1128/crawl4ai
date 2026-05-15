// Generic expand/read-more script.

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
