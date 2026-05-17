// remove_overlay_elements 调试脚本 v4 — 匹配重构后逻辑
// 结果渲染到页面 DOM 面板，不依赖 console
// 只分析不删除，最后可选手动执行 __debug_report.deleteAll()

(function () {
  "use strict";

  var panel = document.createElement("div");
  panel.id = "__debug_overlay_panel";
  panel.style.cssText =
    "position:fixed;top:10px;right:10px;z-index:2147483647;" +
    "width:750px;max-height:90vh;overflow:auto;" +
    "background:#1e1e1e;color:#d4d4d4;font:12px Consolas,monospace;" +
    "padding:12px;border:2px solid #007acc;border-radius:6px;" +
    "white-space:pre-wrap;word-break:break-all;box-shadow:0 4px 20px rgba(0,0,0,0.5);";
  document.body.appendChild(panel);

  var lines = [];
  function out(s) { lines.push(s); panel.textContent = lines.join("\n"); }
  function hdr(s) { lines.push(""); lines.push("═══ " + s + " ═══"); panel.textContent = lines.join("\n"); }
  function red(s) { out("\u{1F534} " + s); }

  try {
    function isVisible(elem) {
      var s = window.getComputedStyle(elem);
      return s.display !== "none" && s.visibility !== "hidden" && s.opacity !== "0";
    }

    function short(elem) {
      var tag = elem.tagName.toLowerCase();
      var id = elem.id ? "#" + elem.id : "";
      var c = (elem.className && typeof elem.className === "string")
        ? "." + elem.className.split(" ").slice(0, 2).join(".") : "";
      return "<" + tag + id + c + ">";
    }

    var hasInteractiveControls = function (elem) {
      return elem.matches("input, textarea, select, form") ||
        !!elem.querySelector("input, textarea, select, form, button[type='submit']");
    };

    var isSafeToRemove = function (elem) {
      if (elem === document.documentElement || elem === document.body) return false;
      if (hasInteractiveControls(elem)) return false;
      var rect = elem.getBoundingClientRect();
      if (rect.top <= 5 && (
        elem.matches('nav, header, [role="navigation"], [role="banner"]') ||
        elem.querySelector('nav, header, [role="navigation"], [role="banner"]')
      )) return false;
      return true;
    };

    var closeButtonSelectors = [
      'button[class*="close" i]', 'button[class*="dismiss" i]',
      'button[aria-label*="close" i]', 'button[title*="close" i]',
      'a[class*="close" i]', 'span[class*="close" i]',
    ];

    var overlaySelectors = [
      '[class*="cookie-banner" i]', '[id*="cookie-banner" i]',
      '[class*="cookie-consent" i]', '[id*="cookie-consent" i]',
      '[class*="newsletter" i]', '[class*="subscribe" i]',
      '[class*="popup" i]', '[class*="modal" i]',
      '[class*="overlay" i]', '[class*="dialog" i]',
      '[role="dialog"]', '[role="alertdialog"]',
    ];

    // ====== Step 1: close buttons ======
    hdr("Step 1: 关闭按钮 (点击，不删除)");
    var s1_count = 0;
    closeButtonSelectors.forEach(function (sel) {
      document.querySelectorAll(sel).forEach(function (btn) {
        if (isVisible(btn)) {
          out("  可点击: " + short(btn) + " | " + sel);
          s1_count++;
        }
      });
    });
    out("共 " + s1_count + " 个");

    // ====== Step 2: one-pass heuristic scan ======
    hdr("Step 2: 视觉启发式扫描 (分支A: 遮罩 | 分支B: 边缀)");
    var vh = window.innerHeight;
    var branchA_all = [], branchA_bad = [];
    var branchB_all = [], branchB_bad = [];

    document.querySelectorAll("*").forEach(function (elem) {
      if (elem === panel) return;
      if (elem === document.documentElement || elem === document.body) return;
      if (!elem.isConnected) return;
      if (elem.offsetWidth < 30 && elem.offsetHeight < 30) return;
      if (elem.offsetWidth * elem.offsetHeight < 900) return;

      try { var style = window.getComputedStyle(elem); } catch (e) { return; }
      if (!isVisible(elem)) return;
      if (style.pointerEvents === "none") return;

      var zIndex = parseInt(style.zIndex);
      var position = style.position;

      // Branch A
      if (zIndex > 999 || position === "fixed" || position === "absolute") {
        var bg = style.backgroundColor;
        var bgAlpha = bg.indexOf("rgba") !== -1 ? parseFloat(bg.split(",").pop()) : 1;
        var hasSemiTransBg = bgAlpha > 0 && bgAlpha < 1;
        var hasLowOpacity = parseFloat(style.opacity) < 1;

        var shouldRemove = (zIndex > 999 && (hasSemiTransBg || hasLowOpacity)) ||
          ((position === "fixed" || position === "absolute") && (hasSemiTransBg || hasLowOpacity));

        if (shouldRemove) {
          var safe = isSafeToRemove(elem);
          var info = {
            tag: short(elem),
            hasInput: hasInteractiveControls(elem),
            safe: safe,
            why: "zIdx=" + zIndex + " pos=" + position + " semiBg=" + hasSemiTransBg + " lowOp=" + hasLowOpacity,
            size: elem.offsetWidth + "x" + elem.offsetHeight,
            bg: bg,
            cls: (elem.className || "").toString().slice(0, 80),
            text: (elem.textContent || "").trim().slice(0, 50),
            elem: elem,
          };
          branchA_all.push(info);
          if (info.hasInput || !info.safe) branchA_bad.push(info);
        }
      }

      // Branch B
      if (position === "fixed") {
        var rect = elem.getBoundingClientRect();
        if (rect.height > vh * 0.25) return;
        var nearTop = rect.top <= 5;
        var nearBottom = rect.bottom >= vh - 5;
        if (nearTop || nearBottom) {
          var safeB = isSafeToRemove(elem);
          var info = {
            tag: short(elem),
            hasInput: hasInteractiveControls(elem),
            safe: safeB,
            nearTop: nearTop,
            nearBottom: nearBottom,
            rect: "t=" + rect.top.toFixed(0) + " b=" + rect.bottom.toFixed(0) + " h=" + rect.height.toFixed(0),
            cls: (elem.className || "").toString().slice(0, 80),
            text: (elem.textContent || "").trim().slice(0, 50),
            elem: elem,
          };
          branchB_all.push(info);
          if (info.hasInput || !info.safe) branchB_bad.push(info);
        }
      }
    });

    out("分支A (遮罩): " + branchA_all.length + " 候选, " + branchA_bad.length + " 异常");
    branchA_bad.forEach(function (e) {
      var label = (e.hasInput ? "[含INPUT] " : "") + (!e.safe ? "[isSafeToRemove=false] " : "");
      red(label + e.tag + " | " + e.why + " | " + e.size + " | " + e.bg + " | ." + e.cls);
    });

    out("");
    out("分支B (边缀): " + branchB_all.length + " 候选, " + branchB_bad.length + " 异常");
    branchB_bad.forEach(function (e) {
      var label = (e.hasInput ? "[含INPUT] " : "") + (!e.safe ? "[isSafeToRemove=false] " : "");
      red(label + e.tag + " | nearT=" + e.nearTop + " nearB=" + e.nearBottom + " | ." + e.cls);
    });

    // ====== Step 3: semantic selectors ======
    hdr("Step 3: 语义选择器匹配");
    var s3_all = [], s3_bad = [];

    overlaySelectors.forEach(function (sel) {
      try {
        document.querySelectorAll(sel).forEach(function (elem) {
          if (elem === panel) return;
          if (!isVisible(elem)) return;
          if (!isSafeToRemove(elem)) {
            var hasInp = hasInteractiveControls(elem);
            s3_bad.push({
              tag: short(elem),
              reason: "isSafeToRemove=false" + (hasInp ? " (含INPUT)" : ""),
              selector: sel,
              cls: (elem.className || "").toString().slice(0, 80),
              text: (elem.textContent || "").trim().slice(0, 50),
            });
            return;
          }
          if (elem.offsetWidth < 30 && elem.offsetHeight < 30) return;
          if (elem.offsetWidth * elem.offsetHeight < 900) return;
          try { var s = window.getComputedStyle(elem); } catch (e) { return; }
          if (s.pointerEvents === "none") return;
          s3_all.push({
            tag: short(elem),
            selector: sel,
            hasInput: hasInteractiveControls(elem),
            elem: elem,
          });
        });
      } catch (e) {}
    });

    out("候选: " + s3_all.length + " | 被isSafeToRemove拦截: " + s3_bad.length);
    s3_bad.forEach(function (e) {
      red(e.tag + " | " + e.reason + " | sel=" + e.selector + " | ." + e.cls);
    });

    // ====== Summary ======
    hdr("总结");
    var totalBad = branchA_bad.length + branchB_bad.length + s3_bad.length;
    var totalInputBad = branchA_bad.filter(function (e) { return e.hasInput; }).length +
      branchB_bad.filter(function (e) { return e.hasInput; }).length +
      s3_bad.filter(function (e) { return e.reason && e.reason.indexOf("含INPUT") !== -1; }).length;

    out("Step2 分支A 异常: " + branchA_bad.length);
    out("Step2 分支B 异常: " + branchB_bad.length);
    out("Step3 被拦截: " + s3_bad.length);
    out("");
    if (totalBad === 0) {
      out("✅ 无异常，所有候选都是干净的可删除目标");
    } else {
      out("⚠️ 以上 \u{1F534} 行需要关注");
      out("   含INPUT元素应被 isSafeToRemove 拦截");
      out("   如果没有被拦截（safe=true+hasInput=true），说明有 bug");
    }

    // Expose for manual deletion
    window.__debug_report = {
      branchA: branchA_all,
      branchB: branchB_all,
      step3: s3_all,
      deleteAll: function () {
        [branchA_all, branchB_all, s3_all].forEach(function (list) {
          list.forEach(function (e) { try { e.elem.remove(); } catch (_) {} });
        });
        return "done";
      },
    };
    out("");
    out("手动删除: __debug_report.deleteAll()");

  } catch (e) {
    out("ERROR: " + e.message + "\n" + (e.stack || ""));
  }
})();
