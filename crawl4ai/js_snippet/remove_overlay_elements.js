async () => {
    // Function to check if element is visible
    const isVisible = (elem) => {
        const style = window.getComputedStyle(elem);
        return style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0";
    };

    // ISSUE: Never remove elements that contain interactive form controls.
    // These are legitimate app functionality areas (search bars, login forms,
    // product drawers with input fields), not garbage overlays.
    // Checks descendants, not just the element itself — a drawer <div> is not
    // an input, but it contains inputs that must be protected.
    const hasInteractiveControls = (elem) =>
        elem.matches("input, textarea, select, form") ||
        elem.querySelector("input, textarea, select, form, button[type='submit']");

    // Unified safety guard — all removal paths must pass this check.
    // Each condition targets a specific historical false-positive pattern.
    const isSafeToRemove = (elem) => {
        // ISSUE: [class*="dialog" i] matches Wikipedia <body class="uls-dialog-sticky-hide">.
        // Never remove structural root elements regardless of what selectors match.
        if (elem === document.documentElement || elem === document.body) return false;

        // Never remove elements containing interactive form controls
        if (hasInteractiveControls(elem)) return false;

        // ISSUE: fixed top navigation bars span full viewport width with high
        // z-index on documentation sites. Removing them makes the next content
        // container become the first layout element and get falsely removed too.
        const rect = elem.getBoundingClientRect();
        if (rect.top <= 5 && (
            elem.matches('nav, header, [role="navigation"], [role="banner"]') ||
            elem.querySelector('nav, header, [role="navigation"], [role="banner"]')
        )) return false;

        return true;
    };

    // ---- Selectors ----

    // Step 1 only: close/dismiss buttons to click (non-destructive dismissal)
    const closeButtonSelectors = [
        'button[class*="close" i]',
        'button[class*="dismiss" i]',
        'button[aria-label*="close" i]',
        'button[title*="close" i]',
        'a[class*="close" i]',
        'span[class*="close" i]',
    ];

    // Step 3 only: elements that declare themselves as overlays via class/role.
    // All matches must pass size and safety guards before removal.
    const overlaySelectors = [
        // Cookie notices
        '[class*="cookie-banner" i]',
        '[id*="cookie-banner" i]',
        '[class*="cookie-consent" i]',
        '[id*="cookie-consent" i]',

        // Newsletter/subscription dialogs
        '[class*="newsletter" i]',
        '[class*="subscribe" i]',

        // Generic popups/modals — keyword-based matching is aggressive and
        // may hit false positives. Protected by size guard and safety checks.
        '[class*="popup" i]',
        '[class*="modal" i]',
        '[class*="overlay" i]',
        // ISSUE: [class*="dialog" i] may match non-dialog elements, e.g.
        // Wikipedia <body class="uls-dialog-sticky-hide"> which contains
        // "dialog" but is just a CSS flag, not an actual dialog element.
        // Protected by root-element guard in isSafeToRemove.
        '[class*="dialog" i]',
        '[role="dialog"]',
        '[role="alertdialog"]',
    ];

    // ================================================================
    // Step 1: Non-destructive dismissal — click close buttons first
    // ================================================================
    for (const selector of closeButtonSelectors) {
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

    // ================================================================
    // Step 2: Visual heuristic — one full-DOM scan, two independent branches
    // ================================================================
    const vh = window.innerHeight;
    const allElements = document.querySelectorAll("*");
    for (const elem of allElements) {
        // Never remove structural root elements
        if (elem === document.documentElement || elem === document.body) continue;
        // Skip descendants of already-removed ancestors (branch A removal side-effect)
        if (!elem.isConnected) continue;

        // Cheap pre-filter: tiny elements are never overlays.
        // Avoids expensive getComputedStyle on them.
        // ISSUE: original code removed tiny position:absolute elements with
        // rgba(0,0,0,0) background — screen-reader labels, accessibility hints.
        // Wikipedia had 100+ such elements (cite-accessibility-label, etc.).
        if (elem.offsetWidth < 30 && elem.offsetHeight < 30) continue;
        if (elem.offsetWidth * elem.offsetHeight < 900) continue;

        const style = window.getComputedStyle(elem);
        if (!isVisible(elem)) continue;

        // ISSUE: pointer-events: none means the element is explicitly marked
        // as a non-interactive decorative layer (tooltips, visual effects).
        // These are not blocking overlays that need removal.
        if (style.pointerEvents === "none") continue;

        const zIndex = parseInt(style.zIndex);
        const position = style.position;

        // ---- Branch A: Overlay detection ----
        // Detects elements that look like overlays based on CSS layering +
        // visual evidence (semi-transparency or low opacity).
        if (zIndex > 999 || position === "fixed" || position === "absolute") {
            const bg = style.backgroundColor;
            // ISSUE: backgroundColor includes "rgba" matches fully transparent
            // backgrounds like rgba(0,0,0,0), common for layout/accessibility
            // elements. Parse alpha and only treat semi-transparent (0 < alpha < 1)
            // as overlay evidence.
            const bgAlpha = bg.includes("rgba") ? parseFloat(bg.split(",").pop()) : 1;
            const hasSemiTransBg = bgAlpha > 0 && bgAlpha < 1;
            const hasLowOpacity = parseFloat(style.opacity) < 1;

            // ISSUE: isLarge (width > 50vw || height > 50vh) was previously
            // a standalone removal trigger for zIndex > 999 elements. Removed
            // because large panels with high z-index and opaque backgrounds
            // are normal app UI (e.g. Aliyun product drawer 820×909,
            // zIdx=1003, bg=#fff), not overlay backdrops.
            // Overlays MUST have semi-transparent background or low opacity
            // as visual evidence. If future sites reveal opaque full-screen
            // custom popups that escape this, isLarge could be reinstated as
            // a secondary signal (requiring co-occurrence with other overlay
            // indicators), never as a standalone trigger.
            const shouldRemoveByOverlay =
                (zIndex > 999 && (hasSemiTransBg || hasLowOpacity)) ||
                ((position === "fixed" || position === "absolute") && (hasSemiTransBg || hasLowOpacity));

            if (shouldRemoveByOverlay && isSafeToRemove(elem)) {
                elem.remove();
                continue; // Removed, skip branch B
            }
        }

        // ---- Branch B: Edge chrome detection ----
        // Detects fixed-position UI chrome pinned to viewport edges
        // (cookie bars, ad strips, notification bars).
        // ISSUE: Only checks position:fixed, NOT sticky.
        // position:sticky is a document-flow layout property used for
        // legitimate content structure (sticky table headers, sticky TOC,
        // sticky sidebars), not UI chrome. The original code included sticky
        // which caused false removal of <thead> and similar structural elements.
        if (position === "fixed") {
            const rect = elem.getBoundingClientRect();
            // Skip large elements that are likely content, not chrome.
            // e.g. Wikipedia sticky TOC, large notification panels.
            if (rect.height > vh * 0.25) continue;

            const nearTop = rect.top <= 5;
            const nearBottom = rect.bottom >= vh - 5;

            if ((nearTop || nearBottom) && isSafeToRemove(elem)) {
                elem.remove();
            }
        }
    }

    // ================================================================
    // Step 3: Semantic selector-based removal
    // ================================================================
    for (const selector of overlaySelectors) {
        try {
            const elements = document.querySelectorAll(selector);
            elements.forEach((elem) => {
                if (!isVisible(elem)) return;
                if (!isSafeToRemove(elem)) return;

                // ISSUE: generic keyword selectors (popup, modal, overlay,
                // dialog) can match tiny decorative elements. Require
                // minimum size to avoid false positives.
                if (elem.offsetWidth < 30 && elem.offsetHeight < 30) return;
                if (elem.offsetWidth * elem.offsetHeight < 900) return;

                // ISSUE: pointer-events: none marks non-interactive
                // decorative elements that happen to match keyword selectors.
                const style = window.getComputedStyle(elem);
                if (style.pointerEvents === "none") return;

                elem.remove();
            });
        } catch (e) {
            console.warn("remove_overlay_elements: selector error", selector, e.toString());
        }
    }

    // ================================================================
    // Step 4: Body style cleanup
    // ================================================================
    // Remove margin-right and padding-right from body (often added by modal
    // scripts to compensate for scrollbar removal).
    // ISSUE: previous element removal could have destroyed <body>, making
    // document.body null. Null guard required before accessing body.style.
    if (document.body) {
        document.body.style.marginRight = "0px";
        document.body.style.paddingRight = "0px";
        document.body.style.overflow = "auto";
        document.body.scrollIntoView(false);
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
};
