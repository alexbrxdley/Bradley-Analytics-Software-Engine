/*
Bradley Quant scroll animations.

Unlike the common IntersectionObserver pattern (observe once, unobserve
after the element first appears), every element here is watched forever:
scrolling an element OUT of view resets it back to its hidden state, so
scrolling it back INTO view plays the animation again from the start.
This applies to every page that includes this script.

Classes used:
  .bq-scroll-fade   -- plain body text: fades and slides up
  .bq-scroll-border -- gallery images: fades and slides up (never side-slide,
                        and never applied to the banner -- banners and
                        images in general never move on this site, this is
                        a one-time reveal, not continuous motion)
  .bq-feature-card  -- the 6 homepage cards: card fades/slides up first,
                        then its paragraph text fades in after, same
                        duration as the card itself
  .bq-scroll-heading -- section headings: a gold underline draws in,
                         matching the nav bar's own underline style
  .bq-scroll-list    -- a <ul>/<ol> whose items stagger in one after
                         another, each with the same fade duration as
                         body text
*/
(function () {
  function makeObserver(className, options) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        entry.target.classList.toggle('bq-inview', entry.isIntersecting);
      });
    }, options || { threshold: 0.15 });
    document.querySelectorAll('.' + className).forEach((el) => observer.observe(el));
  }

  function makeListObserver() {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        const items = entry.target.querySelectorAll('li');
        if (entry.isIntersecting) {
          items.forEach((li, i) => { li.style.transitionDelay = (i * 0.12) + 's'; });
          entry.target.classList.add('bq-inview');
        } else {
          entry.target.classList.remove('bq-inview');
          items.forEach((li) => { li.style.transitionDelay = '0s'; });
        }
      });
    }, { threshold: 0.15 });
    document.querySelectorAll('.bq-scroll-list').forEach((el) => observer.observe(el));
  }

  function tagCodeBlocks() {
    document.querySelectorAll('.page-content pre').forEach((el) => {
      el.classList.add('bq-scroll-fade');
    });
  }

  // Bradley Analytics' content pages are plain markdown (no hand-inserted
  // HTML/classes per paragraph, unlike some hand-authored pages elsewhere)
  // -- auto-tagging every paragraph, sub-heading, and list here covers all
  // six content pages at once instead of manually editing each one.
  function autoTagContent() {
    document.querySelectorAll('.page-content p').forEach((el) => {
      el.classList.add('bq-scroll-fade');
    });
    document.querySelectorAll('.page-content h2, .page-content h3').forEach((el) => {
      // .bq-scroll-heading uses display:inline-block so the underline
      // matches the text's own width -- applying that directly to the
      // heading element itself was a real, confirmed bug: inline-block
      // headings can flow onto the SAME LINE as an adjacent sibling
      // heading (e.g. "Features" immediately followed by "Automated NBA
      // Data Collection" on one line), instead of each stacking on its
      // own line the way block-level headings normally do. Wrapping the
      // text in an inner span keeps the heading itself block-level
      // (normal stacking) while the span handles the inline-block sizing.
      const inner = document.createElement('span');
      inner.className = 'bq-scroll-heading';
      inner.innerHTML = el.innerHTML;
      el.innerHTML = '';
      el.appendChild(inner);
    });
    document.querySelectorAll('.page-content ul, .page-content ol').forEach((el) => {
      el.classList.add('bq-scroll-list');
    });
    document.querySelectorAll('.page-content img').forEach((el) => {
      el.classList.add('bq-scroll-border');
    });
  }

  function setupFooterReveal() {
    const stack = document.querySelector('.footer-logo-stack');
    if (!stack) return;
    // Click toggles the Analytics logo hidden/shown. If already revealed
    // and the click lands on the Analytics logo itself, let it navigate
    // normally instead of toggling. Hover still reveals it on desktop via
    // CSS alone; this is the click/tap equivalent for touch devices,
    // which have no hover state at all.
    stack.addEventListener('click', (e) => {
      const isRevealed = stack.classList.contains('bq-revealed');
      if (!isRevealed) {
        e.preventDefault();
        stack.classList.add('bq-revealed');
      } else if (!e.target.closest('.footer-quant-link')) {
        e.preventDefault();
        stack.classList.remove('bq-revealed');
      }
    });
    // Scrolling the stack out of view and back resets it to hidden,
    // requiring a fresh hover or click to reveal again each time.
    const footerObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) stack.classList.remove('bq-revealed');
      });
    }, { threshold: 0 });
    footerObserver.observe(stack);
  }

  function resetAndReplayAnimations() {
    // Forces each element's pre-animation inline style directly rather
    // than only removing .bq-inview and hoping the resulting CSS
    // transition fires -- confirmed through direct testing that the
    // class-only approach never actually replayed anything visibly,
    // seemingly because the browser coalesces the remove-then-re-add
    // into a single style recalculation with no net change to animate,
    // the same class of issue solved by forcing an explicit state this
    // way for the Streamlit app's own page-fade earlier. Reads each
    // element's fully-settled (post-animation) inline values first
    // (getComputedStyle), since different classes animate different
    // properties and this needs to know which ones to force and later
    // restore for each one, rather than assuming.
    const managed = document.querySelectorAll('.bq-scroll-fade, .bq-scroll-border, .bq-feature-card, .bq-scroll-list');
    const restoreList = [];
    managed.forEach((el) => {
      const cs = getComputedStyle(el);
      restoreList.push({ el, opacity: cs.opacity, transform: cs.transform });
      el.classList.remove('bq-inview');
      el.style.transition = 'none';
      el.style.opacity = '0';
      el.style.transform = (cs.transform && cs.transform !== 'none') ? 'translateY(14px)' : '';
    });
    // Headings animate their underline via a ::after pseudo-element,
    // which has no JS-accessible style object of its own -- forced back
    // to 0 width through the dedicated .bq-force-reset class instead
    // (see site.css) rather than the inline-style approach above.
    const headings = document.querySelectorAll('.bq-scroll-heading');
    headings.forEach((el) => {
      el.classList.remove('bq-inview');
      el.classList.add('bq-force-reset');
    });
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        restoreList.forEach(({ el }) => {
          el.style.transition = '';
          el.style.opacity = '';
          el.style.transform = '';
        });
        headings.forEach((el) => el.classList.remove('bq-force-reset'));
        makeObserver('bq-scroll-fade');
        makeObserver('bq-scroll-border');
        makeObserver('bq-feature-card');
        makeObserver('bq-scroll-heading');
        makeListObserver();
      });
    });
  }

  function init() {
    tagCodeBlocks();
    autoTagContent();
    setupFooterReveal();
    makeObserver('bq-scroll-fade');
    makeObserver('bq-scroll-border');
    makeObserver('bq-feature-card');
    makeObserver('bq-scroll-heading');
    makeListObserver();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // pageshow fires on every page view, including a fresh load -- but
  // critically, ALSO when the browser restores a page from its
  // back-forward cache (clicking Back/Forward to a page you already
  // visited), which normally skips re-running any of the above load
  // logic entirely and just repaints the page exactly as it was left,
  // already fully faded in. event.persisted is true specifically for
  // that restored-from-cache case, which is what this checks for
  // before replaying everything from scratch.
  // pageshow fires on every page view. Originally this only reacted
  // when event.persisted was true (a real bfcache restore, which
  // skips the normal load sequence and shows the page exactly as it
  // was left, already fully faded in). Direct testing with a real
  // browser back-navigation surfaced a case where the page came back
  // already fully visible despite persisted being reported as false
  // -- rather than depend on correctly detecting which case is
  // happening, this now resets and replays unconditionally on every
  // pageshow. That's harmless on a genuinely fresh first load (nothing
  // has .bq-inview yet at that point, so there's nothing to reset),
  // and correctly handles every other case without needing to know
  // which navigation mechanism actually occurred.
  window.addEventListener('pageshow', () => {
    resetAndReplayAnimations();
  });
})();
