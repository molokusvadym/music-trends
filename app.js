(function () {
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- 1. The dither pattern --------------------------------------------------
     For every pixel we compute a smooth number between 0 and 1 (a mix of waves),
     then compare it with a repeating 8x8 grid of thresholds (a "Bayer matrix").
     Above the threshold = black dot, below = nothing. That is ordered dithering. */
  var BAYER = [[0,32,8,40,2,34,10,42],[48,16,56,24,50,18,58,26],[12,44,4,36,14,46,6,38],[60,28,52,20,62,30,54,22],
               [3,35,11,43,1,33,9,41],[51,19,59,27,49,17,57,25],[15,47,7,39,13,45,5,37],[63,31,55,23,61,29,53,21]];
  var SIZE = 104;                                   /* the canvas is 104 x 104 pixels, scaled up by CSS */

  function seededRandom(text) {                     /* same text in -> same numbers out */
    var h = 1779033703 ^ text.length;
    for (var i = 0; i < text.length; i++) { h = Math.imul(h ^ text.charCodeAt(i), 3432918353); h = h << 13 | h >>> 19; }
    return function () {
      h = Math.imul(h ^ h >>> 16, 2246822507); h = Math.imul(h ^ h >>> 13, 3266489909); h ^= h >>> 16;
      return (h >>> 0) / 4294967296;
    };
  }
  function patternFor(seed) {                       /* each artist gets its own wave settings */
    var r = seededRandom(seed);
    return { cx: .25 + r() * .5, cy: .25 + r() * .5, a: 1 + r() * 4, b: 1 + r() * 4,
             p: r() * 6.28, q: r() * 6.28, rings: 2 + r() * 5 };
  }
  function drawDither(canvas, time) {
    var P = canvas._pattern; if (!P) return;
    var ctx = canvas.getContext('2d'), img = ctx.createImageData(SIZE, SIZE), px = img.data;
    for (var y = 0; y < SIZE; y++) {
      for (var x = 0; x < SIZE; x++) {
        var u = x / SIZE, v = y / SIZE, dx = u - P.cx, dy = v - P.cy, dist = Math.sqrt(dx * dx + dy * dy);
        var waves = .5 + .25 * Math.sin(u * P.a * 6.28 + P.p + time) + .25 * Math.sin(v * P.b * 6.28 + P.q - time * .8);
        var rings = .5 + .5 * Math.cos(dist * P.rings * 6.28 - time * 1.2);
        var value = (waves * .6 + rings * .4) * (1.1 - dist * .8) * .6;    /* lower number = fewer dots, more photo showing */
        if (value > (BAYER[y & 7][x & 7] + .5) / 64) {
          var i = (y * SIZE + x) * 4; px[i] = 21; px[i + 1] = 21; px[i + 2] = 21; px[i + 3] = 255;
        }
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  /* ---- 2. Show the hovered row's artist in the frame ---- */
  var canvases = [].slice.call(document.querySelectorAll('canvas'));
  canvases.forEach(function (c) { c.width = c.height = SIZE; });

  function show(item) {
    var fig = item.closest('.split').querySelector('.fig'), canvas = fig.querySelector('canvas');
    fig.querySelector('img').src = item.dataset.img;
    canvas._pattern = patternFor(item.dataset.seed);
    drawDither(canvas, canvas._time || 0);
    fig.querySelector('[data-fig]').textContent = '[ FIG. ' + item.dataset.rank + ' ]';
    fig.querySelector('[data-title]').textContent = item.dataset.title;
    fig.querySelector('[data-sub]').textContent = item.dataset.sub;
  }
  document.querySelectorAll('.split').forEach(function (split) {
    var items = split.querySelectorAll('.item'); if (!items.length) return;
    show(items[0]);
    items.forEach(function (item) {
      item.addEventListener('mouseenter', function () { show(item); });
      item.addEventListener('focus', function () { show(item); });
    });
  });

  /* ---- 3. Animation: redraw the visible patterns about 20 times a second ---- */
  if (!reduceMotion) {
    var last = 0;
    (function loop(now) {
      if (now - last > 50) {
        last = now;
        canvases.forEach(function (c) {
          if (c.offsetParent !== null && c._pattern) { c._time = (c._time || 0) + .05; drawDither(c, c._time); }
        });
      }
      requestAnimationFrame(loop);
    })(0);
  }

  /* ---- 4. Sections: only one open at a time, nav button shows which ---- */
  var sections = [].slice.call(document.querySelectorAll('details.acc'));
  var navLinks = [].slice.call(document.querySelectorAll('.nav a'));
  function markOpen() {
    navLinks.forEach(function (a) { a.classList.toggle('on', document.getElementById(a.hash.slice(1)).open); });
  }
  sections.forEach(function (d) {
    d.addEventListener('toggle', function () {
      if (d.open) sections.forEach(function (o) { if (o !== d) o.open = false; });
      markOpen();
    });
  });
  markOpen();

  function goTo(id) {
    document.getElementById(id).open = true;
    setTimeout(function () {
      document.getElementById(id).scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    }, 40);
  }
  navLinks.forEach(function (a) {
    a.addEventListener('click', function (e) { e.preventDefault(); goTo(a.hash.slice(1)); });
  });
  document.addEventListener('keydown', function (e) {        /* press 1, 2, 3 or 4 */
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    var link = document.querySelector('.nav a[data-key="' + e.key + '"]');
    if (link) goTo(link.hash.slice(1));
  });
})();
