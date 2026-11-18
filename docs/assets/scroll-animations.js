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
  // Lets the head script in _layouts/page.html know this file actually ran.
  // If it never does (blocked/failed request), that script un-hides the page
  // after a few seconds instead of leaving pre-hidden content invisible.
  window.__bqAnimReady = true;

  // Every IntersectionObserver this page creates, kept so a replay can
  // disconnect them first instead of stacking duplicates on top.
  let observers = [];

  // Fraction of an element that must be on screen before it fades in.
  const REVEAL_RATIO = 0.15;

  function makeObserver(className, options) {
    const els = document.querySelectorAll('.' + className);
    if (!els.length) return;
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.intersectionRatio >= REVEAL_RATIO) {
          entry.target.classList.add('bq-inview');
        } else if (!entry.isIntersecting) {
          entry.target.classList.remove('bq-inview');
        }
        // Between 0 and REVEAL_RATIO (a sliver still on screen): leave it
        // alone. Hiding at that point is what made elements visibly fade
        // away while still partly in view whenever an image finished
        // loading and pushed them toward the bottom edge.
      });
    }, options || { threshold: [0, REVEAL_RATIO] });
    els.forEach((el) => observer.observe(el));
    observers.push(observer);
  }

  function makeListObserver() {
    const lists = document.querySelectorAll('.bq-scroll-list');
    if (!lists.length) return;
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        const items = entry.target.querySelectorAll('li');
        if (entry.intersectionRatio >= REVEAL_RATIO) {
          if (!entry.target.classList.contains('bq-inview')) {
            items.forEach((li, i) => { li.style.transitionDelay = (i * 0.12) + 's'; });
            entry.target.classList.add('bq-inview');
          }
        } else if (!entry.isIntersecting) {
          entry.target.classList.remove('bq-inview');
          items.forEach((li) => { li.style.transitionDelay = '0s'; });
        }
      });
    }, { threshold: [0, REVEAL_RATIO] });
    lists.forEach((el) => observer.observe(el));
    observers.push(observer);
  }

  function startObservers() {
    observers.forEach((o) => o.disconnect());
    observers = [];
    makeObserver('bq-scroll-fade');
    makeObserver('bq-scroll-border');
    makeObserver('bq-feature-card');
    makeObserver('bq-scroll-heading');
    makeListObserver();
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
      //
      // Headings get the underline-draw animation only, no fade/slide on
      // the text itself -- explicitly requested (titles and headers
      // should not fade in, only their animated underlines), reversing
      // an earlier change that added bq-scroll-fade here too.
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
    // <summary> elements (the collapsible report-slide headers on the
    // Results page, e.g. "1. Front Cover") aren't a <p>, heading, list,
    // or <img> -- none of the selectors above ever match them, so they
    // got no animation class of any kind, confirmed directly as a real
    // reported gap rather than assumed.
    document.querySelectorAll('.page-content summary').forEach((el) => {
      el.classList.add('bq-scroll-fade');
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

  // Used only when the browser restores this page from its back-forward
  // cache (Back/Forward), which shows the page exactly as it was left --
  // already faded in -- without re-running any of the load logic above.
  // Hidden state is restored with transitions switched off (html.bq-no-transition,
  // see site.css) so elements snap to hidden instead of visibly fading out,
  // then the observers are recreated so everything fades in again.
  function replayAnimations() {
    const root = document.documentElement;
    observers.forEach((o) => o.disconnect());
    observers = [];
    root.classList.add('bq-no-transition');
    document.querySelectorAll('.bq-inview').forEach((el) => el.classList.remove('bq-inview'));
    document.querySelectorAll('.bq-scroll-list li').forEach((li) => { li.style.transitionDelay = ''; });
    void root.offsetHeight; // commit the hidden state before transitions come back
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        root.classList.remove('bq-no-transition');
        startObservers();
      });
    });
  }

  function init() {
    tagCodeBlocks();
    autoTagContent();
    setupFooterReveal();
    // Safe to start immediately: site.css already hides every animated
    // element (by page structure, not by the classes tagged above), so the
    // tagging is a visual no-op and there is no visible->hidden transition
    // to race against. Observers used to wait for the window `load` event
    // (via `pageshow`), which waits for every image and iframe -- on
    // Visualizations that meant a blank page until the multi-MB GIFs
    // finished, and on Home until the whole Streamlit dashboard loaded.
    // Elements that get pushed around when an image finishes loading are
    // handled by the observers themselves: they re-evaluate on every layout
    // change, and an element that leaves the viewport is off-screen anyway.
    startObservers();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // pageshow fires after a normal load too (persisted === false) -- nothing
  // to do then, init() already handled it. Only a bfcache restore needs a
  // replay.
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) replayAnimations();
  });
})();
