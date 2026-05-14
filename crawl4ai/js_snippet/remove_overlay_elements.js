async () => {
    // Function to check if element is visible
    const isVisible = (elem) => {
        const style = window.getComputedStyle(elem);
        return style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0";
    };

    // Common selectors for popups and overlays
    const commonSelectors = [
        // Close buttons first
        'button[class*="close" i]',
        'button[class*="dismiss" i]',
        'button[aria-label*="close" i]',
        'button[title*="close" i]',
        'a[class*="close" i]',
        'span[class*="close" i]',

        // Cookie notices
        '[class*="cookie-banner" i]',
        '[id*="cookie-banner" i]',
        '[class*="cookie-consent" i]',
        '[id*="cookie-consent" i]',

        // Newsletter/subscription dialogs
        '[class*="newsletter" i]',
        '[class*="subscribe" i]',

        // Generic popups/modals
        '[class*="popup" i]',
        '[class*="modal" i]',
        '[class*="overlay" i]',
        // ISSUE: [class*="dialog" i] may match non-dialog elements, e.g. Wikipedia's body
        // has class "uls-dialog-sticky-hide" which contains "dialog" but is just a CSS flag,
        // not an actual dialog element. Protected by structural root guard below.
        '[class*="dialog" i]',
        '[role="dialog"]',
        '[role="alertdialog"]',
    ];

    // Try to click close buttons first
    for (const selector of commonSelectors.slice(0, 6)) {
        const closeButtons = document.querySelectorAll(selector);
        for (const button of closeButtons) {
            if (isVisible(button)) {
                try {
                    button.click();
                    await new Promise((resolve) => setTimeout(resolve, 100));
                } catch (e) {
                    console.warn("remove_overlay_elements: click error", e.toString());
                }
            }
        }
    }

    // Remove remaining overlay elements
    const allElements = document.querySelectorAll("*");
    for (const elem of allElements) {
        // Never remove structural root elements — guards against selectors like
        // [class*="dialog" i] matching <body> with class "uls-dialog-sticky-hide"
        if (elem === document.documentElement || elem === document.body) continue;

        const style = window.getComputedStyle(elem);
        const zIndex = parseInt(style.zIndex);
        const position = style.position;

        if (!isVisible(elem)) continue;
        if (!(zIndex > 999 || position === "fixed" || position === "absolute")) continue;
        // ISSUE: original code removed tiny elements (accessibility labels, screen reader text)
        // because position:absolute + rgba(0,0,0,0) background matched. Wikipedia had 100+ such
        // elements (cite-accessibility-label, vector-toc-toggle, etc.).
        // Fix: require minimum size so only real overlays are removed.
        if (elem.offsetWidth < 30 && elem.offsetHeight < 30) continue;
        if (elem.offsetWidth * elem.offsetHeight < 900) continue;

        const isLarge = elem.offsetWidth > window.innerWidth * 0.5 ||
            elem.offsetHeight > window.innerHeight * 0.5;
        // ISSUE: backgroundColor.includes("rgba") matched fully transparent backgrounds
        // like rgba(0,0,0,0), which are common for layout/accessibility elements, not overlays.
        // Fix: parse alpha value and only match semi-transparent (alpha > 0 and < 1).
        const bg = style.backgroundColor;
        const bgAlpha = bg.includes("rgba") ? parseFloat(bg.split(",").pop()) : 1;
        const hasSemiTransBg = bgAlpha > 0 && bgAlpha < 1;
        const hasLowOpacity = parseFloat(style.opacity) < 1;

        if (isLarge || hasSemiTransBg || hasLowOpacity) {
            elem.remove();
        }
    }

    // Remove elements matching common selectors
    for (const selector of commonSelectors) {
        try {
            const elements = document.querySelectorAll(selector);
            elements.forEach((elem) => {
                // Never remove structural root elements — same guard as above
                if (elem === document.documentElement || elem === document.body) return;
                if (isVisible(elem)) {
                    elem.remove();
                }
            });
        } catch (e) {
            console.warn("remove_overlay_elements: selector error", selector, e.toString());
        }
    }

    // Remove fixed/sticky elements at the top/bottom edges of the viewport
    // (navigation bars, ad strips, notification bars, floating buttons)
    // Skip large elements that are likely content (e.g. Wikipedia sticky TOC, table headers)
    const elements = document.querySelectorAll("*");
    elements.forEach((elem) => {
        // Never remove structural root elements — same guard as above
        if (elem === document.documentElement || elem === document.body) return;
        const style = window.getComputedStyle(elem);
        if (!(style.position === "fixed" || style.position === "sticky") || !isVisible(elem)) {
            return;
        }
        const rect = elem.getBoundingClientRect();
        const vh = window.innerHeight;
        // Skip large elements (likely content, not UI chrome)
        if (rect.height > vh * 0.25) {
            return;
        }
        // Must be near top or bottom edge of viewport
        const nearTop = rect.top <= 5;
        const nearBottom = rect.bottom >= vh - 5;
        if (nearTop || nearBottom) {
            elem.remove();
        }
    });

    // Remove margin-right and padding-right from body (often added by modal scripts)
    // ISSUE: previous elements removal could destroy <body>, making document.body null.
    // Fix: null guard before accessing body.style.
    if (document.body) {
        document.body.style.marginRight = "0px";
        document.body.style.paddingRight = "0px";
        document.body.style.overflow = "auto";
        document.body.scrollIntoView(false);
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
};
